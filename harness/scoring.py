"""自动计分（PG-001 P4；DEC-20260925-04；补丁 4 P1 仿真分）。**计分单一真源**：榜单与发布栈只读本模块产出，不另写公式。

五指标原料：checkpoint_score（0–5，连续）、collisions（接触步数）、collision_events（接触起始事件）、path_ratio、
每次成功美元成本与每步 API 侧时延（汇总层）。
- 检查点按顺序计：只有「下一个」检查点可被到达（机器人中心进入 reach_radius_m 内）。
- 连续分：已到达数 ＋ 向下一检查点的最佳进度 (1 − d_best/d_start)，裁到 [0, 0.99]。
- 碰撞（两种计数）：collisions＝ActResult.collided 为 True 的动作数（接触步数；持续贴着每步都计）；
  collision_events＝接触起始事件数（前一动作无接触、本动作有接触才计 1；持续贴着算 1 次）。
- total = checkpoint_score − collision_penalty × collisions（旧口径，可为负，不裁；保留作对照列）。
- **仿真分 sim_score ∈ [0, 1]（协议 v0 §「仿真分」，榜单用）**：
  sim_score = max(0, reached/N_cp − min(SIM_PENALTY_PER_EVENT × collision_events, SIM_PENALTY_CAP))
  成功项＝到达检查点占比（全到＝1）；碰撞项按接触起始事件计、每回合封顶；总分不低于 0。
- path_ratio = 实际轨迹长 ÷ 理想路径长；理想路径＝折线 start→c1→…→c5 各段长之和，**每段扣除一个到达半径**（进入半径即算到达，不必走到柱心）；
  只对成功回合汇总，不进仿真分。
- success = 5 个检查点全部到达。
- **跨 run 派生量（PG-003 补丁 3 P7，自 tools/build_site.py 迁入；站点只读本模块）**：transfer_gap＝真机分 − 仿真分（同模型、同种子集；
  协议 §5.2）；fidelity＝各模型 |迁移差| 的均值，模型数 ≥5 另给仿真／真机排名的 Spearman 相关（DEC-20260925-05；真机段口径于
  PG-002 开跑前另打 tag protocol-v0-real-prereg）。本模块不依赖 numpy／mujoco：站点构建与 CI 只装标准库即可导入。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 只作类型标注；运行期不引入 interface（其依赖 numpy），让 tools/build_site.py 在无 numpy 的 CI 里也能导入本模块
    from .interface import ActResult, Pose

SIM_PENALTY_PER_EVENT = 0.1   # 仿真分：每个接触起始事件扣 0.1（＝旧口径 0.5 分/次 ÷ 5 分满分）
SIM_PENALTY_CAP = 0.5         # 仿真分：单回合碰撞扣分封顶


@dataclass
class ScoreState:
    checkpoints: list[tuple[float, float]]
    start: tuple[float, float]
    reach_radius_m: float = 0.30
    collision_penalty: float = 0.5
    reached: int = 0
    collisions: int = 0
    collision_events: int = 0
    traveled_m: float = 0.0
    steps: int = 0
    _in_contact: bool = False
    _last: tuple[float, float] | None = None
    _d_start: float = 0.0
    _d_best: float = 0.0
    events: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._last = self.start
        self._init_leg(self.start)

    def _init_leg(self, frm: tuple[float, float]) -> None:
        if self.reached < len(self.checkpoints):
            cx, cy = self.checkpoints[self.reached]
            self._d_start = max(math.hypot(cx - frm[0], cy - frm[1]), 1e-6)
            self._d_best = self._d_start

    def update(self, res: ActResult) -> None:
        self.steps += 1
        if res.collided:
            self.collisions += 1
            if not self._in_contact:                       # 接触起始事件：前一动作无接触
                self.collision_events += 1
                self.events.append({"step": self.steps, "event": "collision_start"})
            else:
                self.events.append({"step": self.steps, "event": "collision"})
        self._in_contact = bool(res.collided)
        if res.pose is None:
            return
        p = (res.pose.x, res.pose.y)
        if self._last is not None:
            self.traveled_m += math.hypot(p[0] - self._last[0], p[1] - self._last[1])
        self._last = p
        # 允许一步内连续到达（几乎不会发生，但保持单调）
        while self.reached < len(self.checkpoints):
            cx, cy = self.checkpoints[self.reached]
            d = math.hypot(cx - p[0], cy - p[1])
            if d <= self.reach_radius_m:
                self.reached += 1
                self.events.append({"step": self.steps, "event": f"reached_{self.reached}"})
                self._init_leg(p)
                continue
            self._d_best = min(self._d_best, d)
            break

    @property
    def success(self) -> bool:
        return self.reached >= len(self.checkpoints)

    @property
    def checkpoint_score(self) -> float:
        partial = 0.0
        if not self.success:
            partial = min(max(1.0 - self._d_best / self._d_start, 0.0), 0.99)
        return self.reached + partial

    @property
    def penalty(self) -> float:
        return self.collision_penalty * self.collisions

    @property
    def total(self) -> float:
        return self.checkpoint_score - self.penalty

    @property
    def sim_score(self) -> float:
        """协议 v0「仿真分」：到达占比 − 封顶的事件扣分，不低于 0。"""
        progress = self.reached / max(len(self.checkpoints), 1)
        penalty = min(SIM_PENALTY_PER_EVENT * self.collision_events, SIM_PENALTY_CAP)
        return max(0.0, progress - penalty)

    @property
    def ideal_path_m(self) -> float:
        pts = [self.start] + list(self.checkpoints)
        return sum(max(math.hypot(b[0] - a[0], b[1] - a[1]) - self.reach_radius_m, 0.0) for a, b in zip(pts, pts[1:]))

    @property
    def path_ratio(self) -> float:
        return self.traveled_m / max(self.ideal_path_m, 1e-6)

    def summary(self) -> dict:
        return {
            "checkpoints_reached": self.reached,
            "checkpoint_score": round(self.checkpoint_score, 4),
            "collisions": self.collisions,
            "collision_events": self.collision_events,
            "penalty": round(self.penalty, 4),
            "total_score": round(self.total, 4),
            "sim_score": round(self.sim_score, 4),
            "traveled_m": round(self.traveled_m, 4),
            "ideal_path_m": round(self.ideal_path_m, 4),
            "path_ratio": round(self.path_ratio, 4),
            "success": int(self.success),
            "steps": self.steps,
        }


# ---------- 跨 run 派生量（补丁 3 P7；协议 §5.2 迁移差；DEC-20260925-05 保真度） ----------

def transfer_gap(real_score: float, sim_score: float, ndigits: int = 4) -> float:
    """迁移差＝真机分 − 仿真分（同模型、同种子集；负值＝真机比仿真差）。成功率差同式。"""
    return round(float(real_score) - float(sim_score), ndigits)


def ranks(xs: list[float]) -> list[float]:
    """并列取平均秩（1 起）。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(a: list[float], b: list[float], min_n: int = 5, ndigits: int = 4):
    """仿真／真机排名的 Spearman 相关；模型数 < min_n（默认 5）或长度不等返回 None；秩方差为 0 返回 None。"""
    if len(a) < min_n or len(a) != len(b):
        return None
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return round(cov / (va * vb), ndigits) if va and vb else None


def fidelity(sim_scores: list[float], real_scores: list[float], ndigits: int = 4) -> dict | None:
    """孪生保真度：各模型 |迁移差| 的均值（越低越好）＋ 模型数 ≥5 时的 Spearman；无配对模型返回 None。"""
    if not sim_scores or len(sim_scores) != len(real_scores):
        return None
    gaps = [abs(transfer_gap(r, s, ndigits)) for s, r in zip(sim_scores, real_scores)]
    return {"n_models": len(gaps), "mean_abs_gap": round(sum(gaps) / len(gaps), ndigits),
            "spearman": spearman([float(x) for x in sim_scores], [float(x) for x in real_scores], ndigits=ndigits)}
