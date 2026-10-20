"""已知地图上的 A* 规划器（PG-001 补丁 3 Q1）。

两个用途：
1. 「astar」oracle——在离散动作格（前进 forward_m／左右转 turn_deg）上搜索到下一检查点的最少动作序列，
   作为**天花板基准**（模型只看图，它看全图；成绩上限，不进榜单）。原贪心 oracle 降为「greedy」基线。
2. **布局可解性判定**——每个种子在标称条件（无打滑、无噪声）下从起点顺序规划到 5 个检查点，任一段无解、
   或总步数超过回合上限 max_steps，即判不可解并剔除，剔除率记入 run 目录（seeds.csv／meta.json）。

只读孪生真值（布局几何＋位姿），永不进模型观测（harness.interface 第 5 条）。
状态＝(x, y, 朝向档 k)，朝向＝起始朝向＋k·turn_deg，坐标连续、闭集按 CELL_M 量化去重；
碰撞模型精确到车身矩形：原地转＝车身外接圆（矩形绕中心旋转的精确包络）；前进＝沿车头方向拉长 forward_m
的有向矩形（平移扫掠的精确包络）。另加 MARGIN_M 安全余量，覆盖 3% 运动噪声与接触判定误差。
返回的动作序列会从起点按标称运动学重放并逐步复核碰撞，复核不过即以更细网格重搜，保证「有解」可复现。
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any, Optional

from harness.interface import Action

CELL_M = 0.02          # 闭集位置量化格（只用于去重；状态坐标本身连续）
HEAD_BIN = math.radians(5.0)   # 闭集朝向量化格（转角按打滑缩放后不再整除 360°，故按绝对朝向分箱去重）
VALIDATE_MARGIN_M = 0.01       # 复用余下计划时的复核余量：比规划余量小一档（滞回），免得 6 mm 噪声就重规划
MARGIN_M = 0.02        # 规划安全余量：0.2 m×3% 噪声≈6 mm/步（1σ）＋接触判定误差
GOAL_MARGIN_M = 0.03   # 规划目标半径＝到达半径−此值：噪声下不擦边
MAX_EXPANSIONS = 120000


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _corners(x: float, y: float, hx: float, hy: float, yaw: float) -> list[tuple[float, float]]:
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + dx * c - dy * s, y + dx * s + dy * c) for dx, dy in ((hx, hy), (hx, -hy), (-hx, -hy), (-hx, hy))]


def _rects_separated(a: tuple, b: tuple) -> bool:
    """两有向矩形 (x, y, hx, hy, yaw) 是否分离——分离轴定理，4 条候选轴。"""
    A, B = _corners(*a), _corners(*b)
    for yaw in (a[4], b[4]):
        for ang in (yaw, yaw + math.pi / 2):
            nx, ny = math.cos(ang), math.sin(ang)
            pa = [px * nx + py * ny for px, py in A]
            pb = [px * nx + py * ny for px, py in B]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return True
    return False


@dataclass
class World:
    """规划用静态几何：墙内面 ±half、圆形物（圆柱障碍＋检查点立柱）、有向矩形障碍、车身半长半宽。"""
    half: float
    robot_half_len: float
    robot_half_wid: float
    circles: list[tuple[float, float, float]]                  # (x, y, r)
    boxes: list[tuple[float, float, float, float, float]]      # (x, y, hx, hy, yaw)
    margin: float = MARGIN_M

    @classmethod
    def from_layout(cls, cfg: dict[str, Any], layout, margin: float = MARGIN_M) -> "World":
        rb = cfg["robot"]
        circles, boxes = [], []
        for o in layout.obstacles:
            if o["kind"] == "cylinder":
                circles.append((o["x"], o["y"], o["size"] / 2))
            else:
                boxes.append((o["x"], o["y"], o["size"] / 2, o["size"] / 2, o["yaw"]))
        pr = cfg["checkpoints"]["post_radius_m"]
        circles += [(x, y, pr) for x, y in layout.checkpoints]
        return cls(cfg["arena"]["size_m"] / 2, rb["length_m"] / 2, rb["width_m"] / 2, circles, boxes, margin)

    @property
    def robot_circ_r(self) -> float:
        return math.hypot(self.robot_half_len, self.robot_half_wid)

    def rect_free(self, cx: float, cy: float, yaw: float, hl: float, hw: float) -> bool:
        m = self.margin
        c, s = math.cos(yaw), math.sin(yaw)
        for px, py in _corners(cx, cy, hl, hw, yaw):
            if abs(px) > self.half - m or abs(py) > self.half - m:
                return False
        for ox, oy, r in self.circles:                       # 圆心转到矩形坐标系，取矩形上最近点
            lx = (ox - cx) * c + (oy - cy) * s
            ly = -(ox - cx) * s + (oy - cy) * c
            qx = min(max(lx, -hl), hl); qy = min(max(ly, -hw), hw)
            if math.hypot(lx - qx, ly - qy) <= r + m:
                return False
        for ox, oy, hx, hy, oyaw in self.boxes:
            if not _rects_separated((cx, cy, hl, hw, yaw), (ox, oy, hx + m, hy + m, oyaw)):
                return False
        return True

    def point_clearance(self, cx: float, cy: float, r: float) -> float:
        """半径 r 的圆盘（车身外接圆）到最近物体的带符号间隙（负＝相交），不含余量。"""
        best = min(self.half - abs(cx), self.half - abs(cy)) - r
        for ox, oy, orr in self.circles:
            best = min(best, math.hypot(ox - cx, oy - cy) - orr - r)
        for ox, oy, hx, hy, oyaw in self.boxes:
            c, s = math.cos(oyaw), math.sin(oyaw)
            lx = (cx - ox) * c + (cy - oy) * s
            ly = -(cx - ox) * s + (cy - oy) * c
            qx = min(max(lx, -hx), hx); qy = min(max(ly, -hy), hy)
            best = min(best, math.hypot(lx - qx, ly - qy) - r)
        return best

    def disc_free(self, cx: float, cy: float, r: float) -> bool:
        return self.point_clearance(cx, cy, r) > self.margin


class AStarPlanner:
    def __init__(self, world: World, forward_m: float, turn_deg: float):
        self.w = world
        self.d = forward_m
        self.turn = math.radians(turn_deg)
        self.sweep_hl = (2 * world.robot_half_len + forward_m) / 2      # 前进扫掠矩形的半长
        self.rot_r = world.robot_circ_r
        self.expansions = 0

    # ---------- 运动学（标称） ----------
    def step(self, x: float, y: float, yaw: float, a: Action) -> tuple[float, float, float]:
        if a == Action.FORWARD:
            return x + self.d * math.cos(yaw), y + self.d * math.sin(yaw), yaw
        if a == Action.LEFT:
            return x, y, wrap(yaw + self.turn)
        if a == Action.RIGHT:
            return x, y, wrap(yaw - self.turn)
        return x, y, yaw

    def action_free(self, x: float, y: float, yaw: float, a: Action) -> bool:
        if a == Action.FORWARD:
            return self.w.rect_free(x + self.d / 2 * math.cos(yaw), y + self.d / 2 * math.sin(yaw), yaw, self.sweep_hl, self.w.robot_half_wid)
        if a in (Action.LEFT, Action.RIGHT):
            return self.w.disc_free(x, y, self.rot_r)
        return True

    def simulate(self, x: float, y: float, yaw: float, actions: list[Action]) -> tuple[tuple[float, float, float], bool]:
        """按标称运动学重放，逐步复核碰撞；返回 (终点位姿, 全程无碰撞)。"""
        for a in actions:
            if not self.action_free(x, y, yaw, a):
                return (x, y, yaw), False
            x, y, yaw = self.step(x, y, yaw, a)
        return (x, y, yaw), True

    # ---------- 搜索 ----------
    def _h(self, x: float, y: float, yaw: float, gx: float, gy: float, gr: float) -> float:
        dist = math.hypot(gx - x, gy - y)
        if dist <= gr:
            return 0.0
        fwd = math.ceil((dist - gr) / self.d - 1e-9)
        err = abs(wrap(math.atan2(gy - y, gx - x) - yaw))
        window = self.turn / 2 + math.asin(min(1.0, gr / dist))       # 朝向落在此窗内即可直行进圈
        turns = math.ceil(max(0.0, err - window) / self.turn - 1e-9)
        return fwd + turns

    def _search(self, x: float, y: float, yaw: float, gx: float, gy: float, gr: float, cell: float, max_exp: int) -> Optional[list[Action]]:
        nb = int(round(2 * math.pi / HEAD_BIN))

        def key(s):
            return (int(round(s[0] / cell)), int(round(s[1] / cell)), int(round(wrap(yaw + s[2] * self.turn) / HEAD_BIN)) % nb)
        start = (x, y, 0)
        k0 = key(start)
        parent: dict[tuple, tuple] = {k0: (None, None)}
        gbest: dict[tuple, int] = {k0: 0}
        openq = [(self._h(x, y, yaw, gx, gy, gr), 0, 0, start)]
        cnt = 1
        self.expansions = 0
        while openq:
            _, g, _, s = heapq.heappop(openq)
            ks = key(s)
            if g > gbest.get(ks, 1 << 30):
                continue
            sx, sy, k = s
            # 目标：进圈且原地可转（否则贴柱停下，下一段一动就碰）
            if math.hypot(gx - sx, gy - sy) <= gr and self.w.disc_free(sx, sy, self.rot_r):
                acts = []
                while parent[ks][0] is not None:
                    ks, a = parent[ks]
                    acts.append(a)
                return acts[::-1]
            self.expansions += 1
            if self.expansions > max_exp:
                return None
            th = yaw + k * self.turn
            succ = []
            if self.action_free(sx, sy, th, Action.FORWARD):
                succ.append((Action.FORWARD, (sx + self.d * math.cos(th), sy + self.d * math.sin(th), k)))
            if self.action_free(sx, sy, th, Action.LEFT):
                succ.append((Action.LEFT, (sx, sy, k + 1)))
                succ.append((Action.RIGHT, (sx, sy, k - 1)))
            for a, ns in succ:
                kn = key(ns)
                ng = g + 1
                if ng < gbest.get(kn, 1 << 30):
                    gbest[kn] = ng
                    parent[kn] = (ks, a)
                    heapq.heappush(openq, (ng + self._h(ns[0], ns[1], yaw + ns[2] * self.turn, gx, gy, gr), ng, cnt, ns))
                    cnt += 1
        return None

    def plan(self, x: float, y: float, yaw: float, goal: tuple[float, float], goal_r: float,
             max_expansions: int = MAX_EXPANSIONS) -> Optional[list[Action]]:
        """到 goal 圆（半径 goal_r）的最少动作序列；已在圈内返回 []；无解返回 None。结果经标称重放复核。"""
        gx, gy = goal
        if math.hypot(gx - x, gy - y) <= goal_r and self.w.disc_free(x, y, self.rot_r):
            return []
        for cell in (CELL_M, CELL_M / 4):        # 量化去重偶发把不同位置并成一格：复核不过就细网格重搜
            acts = self._search(x, y, yaw, gx, gy, goal_r, cell, max_expansions)
            if acts is None:
                return None
            end, ok = self.simulate(x, y, yaw, acts)
            if ok and math.hypot(gx - end[0], gy - end[1]) <= goal_r and self.w.disc_free(end[0], end[1], self.rot_r):
                return acts
        return None


def course_plan(cfg: dict[str, Any], layout, max_steps: int, margin: float = MARGIN_M) -> dict[str, Any]:
    """整回合可解性：标称条件下从起点顺序规划 5 段。返回 solvable／reason／steps／legs／expansions。"""
    world = World.from_layout(cfg, layout, margin)
    m = cfg["motion"]
    pl = AStarPlanner(world, m["forward_m"], m["turn_deg"])
    goal_r = cfg["checkpoints"]["reach_radius_m"] - GOAL_MARGIN_M
    x, y, yaw = layout.start
    legs, total, exp = [], 0, 0
    for i, cp in enumerate(layout.checkpoints, start=1):
        acts = pl.plan(x, y, yaw, cp, goal_r)
        exp += pl.expansions
        if acts is None:
            return {"seed": layout.seed, "solvable": False, "reason": f"no_path_leg{i}", "steps": total, "legs": legs, "expansions": exp}
        (x, y, yaw), _ = pl.simulate(x, y, yaw, acts)
        legs.append(len(acts)); total += len(acts)
    if total > max_steps:
        return {"seed": layout.seed, "solvable": False, "reason": "exceeds_max_steps", "steps": total, "legs": legs, "expansions": exp}
    return {"seed": layout.seed, "solvable": True, "reason": "", "steps": total, "legs": legs, "expansions": exp}
