"""TwinRobot：harness.interface.Robot 的 MuJoCo 实现（停-看-想-动）。"""
from __future__ import annotations

import math
import os
import random
import sys
import time
from typing import Any, Optional

if sys.platform == "darwin":
    os.environ.setdefault("MUJOCO_GL", "cgl")
else:
    os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco
import numpy as np

from harness.interface import Action, ActResult, MotionSpec, Observation, Pose, now
from .arena import Layout, sample_layout
from .config import load_config
from .mjcf import build_xml
from .textures import ensure_sign_pngs


class TwinRobot:
    name = "twin01-mujoco"

    def __init__(self, config_path: str | None = None, cfg: dict[str, Any] | None = None):
        self.cfg = cfg or load_config(config_path)
        m = self.cfg["motion"]
        self.motion = MotionSpec(m["forward_m"], m["turn_deg"], m["linear_mps"], m["angular_dps"], m["settle_s"])
        self.asset_dir = ensure_sign_pngs(self.cfg["checkpoints"]["count"])
        self.model: Optional[mujoco.MjModel] = None
        self.data: Optional[mujoco.MjData] = None
        self.renderer: Optional[mujoco.Renderer] = None
        self.layout: Optional[Layout] = None
        self._step_i = 0
        self._reached = 0
        self._rng = random.Random(0)
        self.instruction = ""

    # ---------- 生命周期 ----------
    def reset(self, seed: int, instruction: str = "") -> Observation:
        self.layout = sample_layout(self.cfg, seed)
        xml = build_xml(self.cfg, self.layout, self.asset_dir)
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)
        self.data.qpos[2] = self.layout.start[2]
        mujoco.mj_forward(self.model, self.data)
        cam = self.cfg["camera"]
        if self.renderer is not None:
            self.renderer.close()
        self.renderer = mujoco.Renderer(self.model, height=cam["height"], width=cam["width"])
        self._chassis = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "chassis")
        self._floor = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
        self._body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "robot")
        self._step_i = 0
        self._rng = random.Random(seed * 104729 + 7)
        self.instruction = instruction                        # 只回显；任务语义在 harness.task
        self._settle(self.motion.settle_s)
        return self.observe()

    def close(self) -> None:
        if self.renderer is not None:
            self.renderer.close(); self.renderer = None

    # ---------- 看 ----------
    def pose(self) -> Pose:
        # 世界坐标取刚体 xpos（滑动关节 qpos 只是相对起点的位移，不能直接当坐标用）；yaw 取铰链角（body 无初始旋转）
        p = self.data.xpos[self._body]
        return Pose(float(p[0]), float(p[1]), float((self.data.qpos[2] + math.pi) % (2 * math.pi) - math.pi))

    def set_pose(self, x: float, y: float, yaw_rad: float) -> None:
        """测试／标定用：直接放置机器人（世界坐标）。"""
        sx, sy, _ = self.layout.start
        self.data.qpos[0], self.data.qpos[1], self.data.qpos[2] = x - sx, y - sy, yaw_rad
        self.data.qvel[:] = 0.0
        mujoco.mj_forward(self.model, self.data)

    def course(self) -> dict[str, Any]:
        return {"checkpoints": [list(c) for c in self.layout.checkpoints], "start": list(self.layout.start[:2]),
                "reach_radius_m": self.cfg["checkpoints"]["reach_radius_m"], "seed": self.layout.seed,
                "obstacles": len(self.layout.obstacles)}

    def observe(self) -> Observation:
        self.renderer.update_scene(self.data, camera="eye")
        img = self.renderer.render().copy()
        p = self.pose()
        # 真值只给脚本化 Agent（greedy／astar）与计分器；layout＋cfg 供 A* 建图。模型类 Agent 经 for_model() 剥离
        gt = {"pose": (p.x, p.y, p.yaw_rad), "checkpoints": list(self.layout.checkpoints), "layout": self.layout, "cfg": self.cfg}
        return Observation(img, self.instruction, self._step_i, now(), {"gt": gt})

    # ---------- 动 ----------
    def _substeps_per_tick(self) -> int:
        return max(1, int(round(1.0 / (self.cfg["physics"]["control_hz"] * self.cfg["physics"]["timestep"]))))

    def _run(self, v_lin: float, w_ang: float, duration_s: float) -> bool:
        """以体坐标线速度 v_lin、角速度 w_ang 运行 duration_s；返回是否碰撞。"""
        collided = False
        ticks = int(round(duration_s * self.cfg["physics"]["control_hz"]))
        sub = self._substeps_per_tick()
        for _ in range(ticks):
            yaw = float(self.data.qpos[2])
            self.data.ctrl[0] = v_lin * math.cos(yaw)
            self.data.ctrl[1] = v_lin * math.sin(yaw)
            self.data.ctrl[2] = w_ang
            for _ in range(sub):
                mujoco.mj_step(self.model, self.data)
                if not collided and self._in_contact():
                    collided = True
        return collided

    def _settle(self, seconds: float) -> None:
        self.data.ctrl[:] = 0.0
        for _ in range(int(seconds / self.cfg["physics"]["timestep"])):
            mujoco.mj_step(self.model, self.data)
        self.data.qvel[:] = 0.0
        mujoco.mj_forward(self.model, self.data)

    def _in_contact(self) -> bool:
        d = self.data
        for i in range(d.ncon):
            c = d.contact[i]
            if (c.geom1 == self._chassis or c.geom2 == self._chassis):
                other = c.geom2 if c.geom1 == self._chassis else c.geom1
                if other != self._floor:
                    return True
        return False

    def act(self, action: Action) -> ActResult:
        t0 = time.perf_counter()
        m = self.motion; rz = self.cfg["randomization"]
        noise = (rz.get("motion_noise_pct", 0) / 100.0) if rz.get("enabled", True) else 0.0
        slip = self.layout.slip
        collided = False
        if action == Action.FORWARD:
            dist = m.forward_m * slip * (1 + self._rng.gauss(0, noise))
            collided = self._run(m.linear_mps, 0.0, dist / m.linear_mps)
        elif action in (Action.LEFT, Action.RIGHT):
            ang = math.radians(m.turn_deg) * slip * (1 + self._rng.gauss(0, noise))
            w = math.radians(m.angular_dps) * (1 if action == Action.LEFT else -1)
            collided = self._run(0.0, w, ang / abs(w))
        self._settle(m.settle_s)
        self._step_i += 1
        return ActResult(action, time.perf_counter() - t0, collided, self.pose(), {"slip": round(slip, 3)})
