"""真机端 Robot 实现占位（PG-002 卡 C 落地；本文件只定契约与串口协议草案，不含可运行控制）。

目标套件：微雪 UGV02（protocol/kit-candidates.md 推荐项）——ESP32 从控，USB 串口 115200，JSON 指令：
  {"T":13,"X":<m/s>,"Z":<rad/s>}  速度闭环下发；{"T":0} 急停；固件 3 s 无指令自动停车（心跳）。
安全（DEC-20260925-04，沿用 RIG 三层急停）：①固件限速＝MotionSpec.linear_mps／angular_dps 上限 ②离散有界动作＝每次 act() 只发一段定时速度指令后归零
③三层急停＝固件心跳超时／上位机看门狗／人工物理断电。碰撞与位姿由俯拍相机判定（PG-002），未接通前 ActResult.collided=None、pose=None。
"""
from __future__ import annotations

from typing import Any, Optional

from .interface import Action, ActResult, MotionSpec, Observation, Pose


class RealRobotUGV02:
    name = "ugv02-real"

    def __init__(self, port: str = "/dev/tty.usbserial", camera_index: int = 0, motion: MotionSpec = MotionSpec()):
        self.port, self.camera_index, self.motion = port, camera_index, motion
        raise NotImplementedError("真机端实现属 PG-002；接口契约见 harness/interface.py，协议草案见本文件说明")

    def reset(self, seed: int) -> Observation: ...
    def observe(self) -> Observation: ...
    def act(self, action: Action) -> ActResult: ...
    def pose(self) -> Optional[Pose]: ...
    def course(self) -> dict[str, Any]: ...
    def close(self) -> None: ...
