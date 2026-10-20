#!/usr/bin/env python3
"""孪生回放出帧（内部工单 P1）：按既有逐步日志重放动作序列，重现送模帧并另出俯视渲染。

用途：首期视频只取 `runs/2026-09-25-pilot01` 与基线批的回合；跑批时只保存了每模型前 2 回合的帧（`run_batch --frames 2`），
其余回合的机载画面须由日志回放重现。孪生对同一 seed 完全确定（布局流与随机化流均由 seed 派生，`twin/arena.py`；
动作噪声 RNG 由 seed 派生，`twin/robot_twin.py`），因此「reset(seed) → 按日志逐步 act」得到的位姿与帧与原跑批一致。

本工具只读 `twin/`、`harness/` 的公开接口，不改监视区；每步核对回放位姿与日志位姿（容差 1e-6），不符即退出 3。
对已有帧的回合可 `--verify-frames` 逐字节比对（退出 4 为不符）。`config_sha256` 与 run 的 `meta.json` 不符退出 2。

用法（仓根）：
  .venv/bin/python tools/replay_frames.py --run episodes/runs/2026-09-25-pilot01 --agent qwen3-vl-plus--nothink--official --seed 1012 \
      --out <仓外或 video 目录>/frames/qwen_s1012 [--overhead] [--overhead-size 1080] [--verify-frames]
输出：<out>/eye/s<seed>_t<step>.png（送模帧，与 run_batch 同名；末尾多一帧 t<步数>＝最后动作后的画面）；--overhead 时另出 <out>/overhead/ 同名俯视帧；
      <out>/replay.json（步数、位姿最大差、帧比对结果、config_sha256）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness.interface import Action  # noqa: E402
from twin.config import load_config  # noqa: E402
from twin.robot_twin import TwinRobot  # noqa: E402


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _save_png(img: np.ndarray, path: str) -> None:
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(img).save(path)


def _load_png(path: str) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"))


class Overhead:
    """俯视渲染：在孪生模型上另开一个渲染器，自由相机垂直向下看场地中心，不碰孪生自身的 eye 相机。"""

    def __init__(self, robot: TwinRobot, size: int, arena_m: float):
        import mujoco
        self.mujoco = mujoco
        # 离屏帧缓冲由模型 vis.global 决定（twin 未设，缺省 640×480）；只在编译后的模型对象上抬高，不改 twin/ 的 XML 生成
        robot.model.vis.global_.offwidth = max(int(robot.model.vis.global_.offwidth), size)
        robot.model.vis.global_.offheight = max(int(robot.model.vis.global_.offheight), size)
        self.renderer = mujoco.Renderer(robot.model, height=size, width=size)
        self.cam = mujoco.MjvCamera()
        self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.cam.lookat[:] = (0.0, 0.0, 0.0)
        self.cam.azimuth = 90.0
        self.cam.elevation = -90.0
        fovy = float(robot.model.vis.global_.fovy)
        # 透视相机：让 arena_m（含余量）的半边正好落在视场内
        self.cam.distance = (arena_m / 2.0) / math.tan(math.radians(fovy / 2.0))
        self.robot = robot

    def render(self) -> np.ndarray:
        self.renderer.update_scene(self.robot.data, camera=self.cam)
        return self.renderer.render().copy()

    def close(self) -> None:
        self.renderer.close()


def replay(run: str, agent: str, seed: int, out: str, overhead: bool, overhead_size: int,
           verify_frames: bool, pose_tol: float = 1e-6) -> int:
    meta = json.load(open(os.path.join(run, "meta.json"), encoding="utf-8"))
    cfg = load_config()
    csha = _sha(cfg["_path"])
    if meta.get("config_sha256") and meta["config_sha256"] != csha:
        print(f"✘ config_sha256 不符：run {meta['config_sha256'][:12]} ≠ 当前 {csha[:12]}", file=sys.stderr)
        return 2
    log_path = os.path.join(run, "logs", agent, f"seed{seed}.jsonl")
    rows = [json.loads(l) for l in open(log_path, encoding="utf-8") if l.strip()]
    robot = TwinRobot(cfg=cfg)
    ov = None
    try:
        obs = robot.reset(seed, "")
        if rows and rows[0].get("start_pose"):
            p0 = robot.pose(); sp = rows[0]["start_pose"]
            d0 = max(abs(p0.x - sp["x"]), abs(p0.y - sp["y"]), abs(p0.yaw_rad - sp["yaw_rad"]))
            if d0 > pose_tol:
                print(f"✘ 起点位姿不符 {d0:.3e}", file=sys.stderr); return 3
        if overhead:
            ov = Overhead(robot, overhead_size, float(cfg["arena"].get("size_m", 2.0)) * 1.1)
        max_dpose, frame_cmp = 0.0, {"compared": 0, "mismatch": 0}
        existing = os.path.join(run, "frames", agent)
        for row in rows:
            step = int(row["step"])
            fn = f"s{seed:04d}_t{step:03d}.png"
            _save_png(obs.image, os.path.join(out, "eye", fn))
            if verify_frames and os.path.exists(os.path.join(existing, fn)):
                ref = _load_png(os.path.join(existing, fn))
                frame_cmp["compared"] += 1
                if ref.shape != obs.image.shape or not np.array_equal(ref, obs.image):
                    frame_cmp["mismatch"] += 1
            if ov is not None:
                _save_png(ov.render(), os.path.join(out, "overhead", fn))
            res = robot.act(Action(row["action"]))
            if row.get("pose") and res.pose:
                lp = row["pose"]
                d = max(abs(res.pose.x - lp["x"]), abs(res.pose.y - lp["y"]), abs(res.pose.yaw_rad - lp["yaw_rad"]))
                max_dpose = max(max_dpose, d)
                if d > pose_tol:
                    print(f"✘ 第 {step} 步位姿不符 {d:.3e}（回放 {res.pose} vs 日志 {lp}）", file=sys.stderr)
                    return 3
            if row["action"] == Action.STOP.value:
                break
            obs = robot.observe()
        # 末帧：最后一个动作之后的画面（跑批不保存——最后一步后不再送模；文件名按「已走步数」顺延，便于按 glob 连续读入）
        n_end = len(rows)
        if ov is not None:
            _save_png(ov.render(), os.path.join(out, "overhead", f"s{seed:04d}_t{n_end:03d}.png"))
        if rows and rows[-1]["action"] == Action.STOP.value:
            obs = robot.observe()
        _save_png(obs.image, os.path.join(out, "eye", f"s{seed:04d}_t{n_end:03d}.png"))
        info = {"run": run, "agent": agent, "seed": seed, "steps": len(rows), "max_pose_diff": max_dpose,
                "config_sha256": csha, "frames_verified": frame_cmp, "overhead": bool(overhead)}
        os.makedirs(out, exist_ok=True)
        json.dump(info, open(os.path.join(out, "replay.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"✔ replay {agent} seed {seed}: steps={len(rows)} max_pose_diff={max_dpose:.2e} "
              f"frames_compared={frame_cmp['compared']} mismatch={frame_cmp['mismatch']} → {out}")
        if verify_frames and frame_cmp["mismatch"]:
            return 4
        return 0
    finally:
        if ov is not None:
            ov.close()
        robot.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True); ap.add_argument("--agent", required=True); ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--overhead", action="store_true")
    ap.add_argument("--overhead-size", type=int, default=1080); ap.add_argument("--verify-frames", action="store_true")
    a = ap.parse_args(argv)
    return replay(a.run, a.agent, a.seed, a.out, a.overhead, a.overhead_size, a.verify_frames)


if __name__ == "__main__":
    sys.exit(main())
