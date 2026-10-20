"""脚本化 Agent：不调 API，成本 0，均不进榜单。

- RandomAgent：随机基线（下界）。
- GreedyAgent：贪心真值导航——朝下一检查点转向、对准即前进，不避障（PG-001 原 oracle；补丁 3 Q1 降为基线）。
- AStarAgent：已知地图 A*（补丁 3 Q1 **天花板基准**）——按 twin/planner.py 的离散动作格规划最少动作序列并逐步执行，
  规划用该回合的真实打滑系数缩放步长与转角（oracle 读真值，天花板即「全知」上界）；每步把余下计划从真实位姿重放复核
  （余量 1 cm，滞回）不过即重规划；无解时先去掉安全余量重搜，
  仍无解（多半已贴上物体）则选三个动作中外接圆间隙最大者脱困，不盲推。
后两者需要 obs.extra['gt']（孪生真值：位姿、检查点、布局、配置）；模型类 Agent 永远拿不到。
"""
from __future__ import annotations

import math
import random
import time
from typing import Any

from ..interface import Action, Decision, Observation


def _greedy_action(x: float, y: float, yaw: float, goal: tuple[float, float], turn_deg: float) -> Action:
    err = math.atan2(goal[1] - y, goal[0] - x) - yaw
    err = (err + math.pi) % (2 * math.pi) - math.pi
    half = math.radians(turn_deg) / 2
    return Action.FORWARD if abs(err) <= half else (Action.LEFT if err > 0 else Action.RIGHT)


class RandomAgent:
    name = "random"
    model_id = "scripted/random"

    def __init__(self, stop_prob: float = 0.01):
        self.stop_prob = stop_prob
        self.rng = random.Random(0)

    def start_episode(self, instruction: str, seed: int) -> None:
        self.rng = random.Random(seed * 7919 + 1)

    def decide(self, obs: Observation) -> Decision:
        t = time.perf_counter()
        a = Action.STOP if self.rng.random() < self.stop_prob else self.rng.choice([Action.FORWARD, Action.FORWARD, Action.LEFT, Action.RIGHT])
        return Decision(a, time.perf_counter() - t, 0.0, self.model_id, raw_text=a.value)


class GreedyAgent:
    """贪心真值导航基线：不避障（故会撞，顺带验证碰撞计分）。需要 obs.extra['gt']。"""
    name = "greedy"
    model_id = "scripted/greedy"
    needs_gt = True

    def __init__(self, turn_deg: float = 30.0):
        self.turn_deg = turn_deg

    def start_episode(self, instruction: str, seed: int) -> None:
        pass

    def decide(self, obs: Observation) -> Decision:
        t = time.perf_counter()
        gt = obs.extra.get("gt")
        if gt is None:
            raise RuntimeError("GreedyAgent 需要 obs.extra['gt']（只在孪生上可用，且不得经 for_model() 剥离）")
        nxt = obs.extra.get("next_checkpoint", 1)
        if nxt > len(gt["checkpoints"]) or gt.get("done"):
            a = Action.STOP
        else:
            x, y, yaw = gt["pose"]
            a = _greedy_action(x, y, yaw, tuple(gt["checkpoints"][nxt - 1]), self.turn_deg)
        return Decision(a, time.perf_counter() - t, 0.0, self.model_id, raw_text=a.value)


class AStarAgent:
    """已知地图 A* 天花板基准。每段规划到下一检查点；余下计划从真实位姿重放复核不过即重规划。"""
    name = "astar"
    model_id = "scripted/astar"
    needs_gt = True

    def __init__(self):
        self._seed = None
        self._pl = self._pl0 = None
        self._plan: list[Action] = []
        self._plan_goal = 0
        self.replans = 0

    def start_episode(self, instruction: str, seed: int) -> None:
        self._plan, self._plan_goal, self.replans = [], 0, 0

    def _escape(self, x: float, y: float, yaw: float, goal: tuple[float, float]) -> Action:
        """贴上物体、A* 无解时的脱困：取动作后外接圆间隙最大者（前进看中点与终点），间隙同者取朝向目标误差小者。"""
        w0, pl = self._pl0.w, self._pl0
        r = w0.robot_circ_r
        best = None
        for a in (Action.FORWARD, Action.LEFT, Action.RIGHT):
            nx, ny, nyaw = pl.step(x, y, yaw, a)
            if a == Action.FORWARD:
                c = min(w0.point_clearance((x + nx) / 2, (y + ny) / 2, r), w0.point_clearance(nx, ny, r))
            else:
                c = w0.point_clearance(x, y, r)
            err = abs((math.atan2(goal[1] - ny, goal[0] - nx) - nyaw + math.pi) % (2 * math.pi) - math.pi)
            cand = (round(c, 4), -err, a)
            if best is None or cand > best:
                best = cand
        return best[2]

    def _ensure(self, gt: dict[str, Any]) -> None:
        lay = gt["layout"]
        if self._pl is not None and self._seed == lay.seed:
            return
        from twin.planner import GOAL_MARGIN_M, VALIDATE_MARGIN_M, AStarPlanner, World   # 延迟导入：harness 不依赖 twin，除非用此 oracle
        cfg = gt["cfg"]; m = cfg["motion"]
        slip = float(getattr(lay, "slip", 1.0) or 1.0)        # 真值打滑：实际位移／转角＝指令×slip（twin/robot_twin.act）
        d, turn = m["forward_m"] * slip, m["turn_deg"] * slip
        self._pl = AStarPlanner(World.from_layout(cfg, lay), d, turn)
        self._plv = AStarPlanner(World.from_layout(cfg, lay, margin=VALIDATE_MARGIN_M), d, turn)
        self._pl0 = AStarPlanner(World.from_layout(cfg, lay, margin=0.0), d, turn)
        self._goal_r = cfg["checkpoints"]["reach_radius_m"] - GOAL_MARGIN_M
        self._turn_deg = m["turn_deg"]
        self._seed = lay.seed

    def decide(self, obs: Observation) -> Decision:
        t = time.perf_counter()
        gt = obs.extra.get("gt")
        if gt is None:
            raise RuntimeError("AStarAgent 需要 obs.extra['gt']（只在孪生上可用，且不得经 for_model() 剥离）")
        nxt = obs.extra.get("next_checkpoint", 1)
        cps = gt["checkpoints"]
        if nxt > len(cps) or gt.get("done"):
            return Decision(Action.STOP, time.perf_counter() - t, 0.0, self.model_id, raw_text="stop")
        self._ensure(gt)
        x, y, yaw = gt["pose"]
        goal = tuple(cps[nxt - 1])
        extra: dict[str, Any] = {}
        reuse = False
        if self._plan and self._plan_goal == nxt:          # 余下计划从真实位姿重放：无碰撞且仍能进圈才复用
            end, ok = self._plv.simulate(x, y, yaw, self._plan)
            reuse = ok and math.hypot(goal[0] - end[0], goal[1] - end[1]) <= self._goal_r
        if not reuse:
            acts, src = self._pl.plan(x, y, yaw, goal, self._goal_r), "astar"
            if not acts:
                acts, src = self._pl0.plan(x, y, yaw, goal, self._goal_r), "astar_margin0"
            if not acts:
                acts, src = [self._escape(x, y, yaw, goal)], "escape"
            self._plan, self._plan_goal = list(acts), nxt
            self.replans += 1
            extra = {"replanned": True, "planner": src, "plan_len": len(acts), "expansions": self._pl.expansions}
        a = self._plan.pop(0)
        return Decision(a, time.perf_counter() - t, 0.0, self.model_id, raw_text=a.value, extra=extra)
