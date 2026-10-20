"""停-看-想-动接口（PG-001 P2；DEC-20260925-04／05）。

契约（孪生 twin/ 与真机 harness/robot_real.py 必须同时满足）：
1. 「停」：任何时刻只有 act() 内部机器人在动；observe() 与 decide() 期间机器人静止。
2. 「看」：observe() 返回一帧机载相机 RGB 图（HxWx3 uint8）＋自然语言指令；不返回位姿、地图、真值。
3. 「想」：Agent.decide() 只看 Observation，输出离散动作之一；每步记 API 侧时延与美元成本。
4. 「动」：act() 执行**恰好一个**固定步长的有界动作（前进 forward_m 米／左右转 turn_deg 度／停），
   机器人完全静止后才返回；返回值里的碰撞与位姿只供计分器用，永远不进 Observation。
5. 真值隔离：Observation.extra 里允许放 "gt" 键（孪生真值，供 ScriptedOracle 与计分），
   但 LLM 类 Agent 不得读取；run_batch 在送入模型前会剥离。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

import numpy as np


class Action(str, Enum):
    FORWARD = "forward"
    LEFT = "left"
    RIGHT = "right"
    STOP = "stop"

    @classmethod
    def parse(cls, text: str) -> Optional["Action"]:
        """从模型自由文本里解析动作：优先 JSON {"action": ...}，否则找最后出现的动作词。"""
        import json, re
        t = (text or "").strip()
        m = re.search(r"\{[^{}]*\}", t)
        if m:
            try:
                v = json.loads(m.group(0)).get("action", "")
                if isinstance(v, str) and v.strip().lower() in cls._value2member_map_:
                    return cls(v.strip().lower())
            except Exception:
                pass
        hits = [(mm.start(), mm.group(0).lower()) for mm in re.finditer(r"\b(forward|left|right|stop)\b", t, re.I)]
        return cls(hits[-1][1]) if hits else None


@dataclass(frozen=True)
class MotionSpec:
    """离散有界动作的固定步长——孪生与真机固件共用同一组数（真机限速即 linear_mps／angular_dps 上限）。"""
    forward_m: float = 0.20
    turn_deg: float = 30.0
    linear_mps: float = 0.20
    angular_dps: float = 60.0
    settle_s: float = 0.30       # 动作结束后静置时间，确保「停」


@dataclass
class Pose:
    x: float
    y: float
    yaw_rad: float


@dataclass
class Observation:
    image: np.ndarray            # HxWx3 uint8 RGB，机载相机
    instruction: str             # 自然语言指令（由 harness 任务层每步渲染写入；机器人只回显）
    step: int                    # 本回合第几步（0 起）
    t_wall: float                # time.time()
    extra: dict[str, Any] = field(default_factory=dict)   # 见模块说明第 5 条

    def for_model(self) -> "Observation":
        """剥离真值后的副本（送模型前必须调用）。"""
        return Observation(self.image, self.instruction, self.step, self.t_wall, {k: v for k, v in self.extra.items() if k != "gt"})


@dataclass
class ActResult:
    action: Action
    duration_s: float
    collided: Optional[bool]     # 孪生：本动作内是否发生物理接触；真机：俯拍判定，未接通时 None
    pose: Optional[Pose]         # 孪生：真值；真机：俯拍估计或 None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Robot(Protocol):
    name: str
    motion: MotionSpec

    def reset(self, seed: int, instruction: str = "") -> Observation: ...
    def observe(self) -> Observation: ...
    def act(self, action: Action) -> ActResult: ...
    def pose(self) -> Optional[Pose]: ...
    def course(self) -> dict[str, Any]:
        """计分器需要的静态布局：checkpoints [(x,y),...] 按顺序、start (x,y)、reach_radius_m。真机由俯拍标定给出。"""
        ...
    def close(self) -> None: ...


@dataclass
class Decision:
    action: Optional[Action]     # None＝输出不可解析
    latency_s: float             # API 侧时延（发出请求→收到完整响应）
    usd_cost: float
    model_id: str
    raw_text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.action is not None


@runtime_checkable
class Agent(Protocol):
    name: str
    model_id: str
    # needs_gt: bool ——可选属性；为 True 时回合循环不剥离 obs.extra["gt"]。只有脚本化 Agent 可以设，模型类禁止。

    def start_episode(self, instruction: str, seed: int) -> None: ...
    def decide(self, obs: Observation) -> Decision: ...


def now() -> float:
    return time.time()
