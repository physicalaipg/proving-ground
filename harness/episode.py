"""单回合循环：停-看-想-动 ＋ 逐步日志（JSONL）＋ 帧样例。"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from typing import Optional

import numpy as np

from .interface import Action, Agent, Observation, Robot, now
from .scoring import ScoreState
from .task import Task


def _save_png(img: np.ndarray, path: str) -> None:
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(img).save(path)


def run_episode(robot: Robot, agent: Agent, seed: int, max_steps: int, task: Task,
                log_path: Optional[str] = None, frames_dir: Optional[str] = None,
                frame_every: int = 1, quiet: bool = True, invalid_retries: int = 2) -> dict:
    """跑一回合。返回汇总 dict（含五指标原料）。log_path 为 JSONL，每步一行。

    任务语义全在本层：指令文本按计分器的「下一检查点」每步渲染；机器人只提供物理与相机。
    模型输出不可解析／API 出错：同一观测重问最多 invalid_retries 次，仍不行则本回合结束（记 invalid_outputs）。
    """
    obs = robot.reset(seed, task.render(1))
    course = robot.course()
    score = ScoreState(checkpoints=[tuple(c) for c in course["checkpoints"]], start=tuple(course["start"]),
                       reach_radius_m=task.reach_radius_m)
    agent.start_episode(obs.instruction, seed)
    logf = open(log_path, "w", encoding="utf-8") if log_path else None
    # 日志补起点（ONE-027 ⑧，DEC-20261010-08 三条件）：动作前的起点位姿，只作第 0 步行的**附加字段** start_pose（追加在行尾），
    # 既有字段、顺序、数值零改动；旧读法（failure_modes／a3／tables 按 step／action／pose 读）忽略该键。计分不读它。
    _p0 = robot.pose() if log_path else None
    start_pose = asdict(_p0) if _p0 else None
    usd, lat, tok_in, tok_out, invalid, api_errors = 0.0, [], 0, 0, 0, 0
    tiers: set[str] = set()
    stopped, t0 = False, time.time()
    try:
        for step in range(max_steps):
            obs.instruction = task.render(score.reached + 1)
            obs.extra["next_checkpoint"] = min(score.reached + 1, task.n_checkpoints)
            if frames_dir and step % frame_every == 0:
                _save_png(obs.image, os.path.join(frames_dir, f"s{seed:04d}_t{step:03d}.png"))
            # 真值隔离：只有显式声明 needs_gt 的脚本化 Agent 能看到 gt；模型类 Agent 一律剥离
            model_obs = obs if getattr(agent, "needs_gt", False) else obs.for_model()
            dec = None
            for attempt in range(invalid_retries + 1):
                dec = agent.decide(model_obs)
                usd += dec.usd_cost; lat.append(dec.latency_s); tok_in += dec.tokens_in; tok_out += dec.tokens_out
                if dec.extra.get("price_tier"):
                    tiers.add(str(dec.extra["price_tier"]))
                if dec.extra.get("error"):
                    api_errors += 1
                if dec.valid:
                    break
                invalid += 1
            action = dec.action if dec.valid else Action.STOP
            res = robot.act(action)
            score.update(res)
            if logf:
                row = {"step": step, "t": now(), "action": action.value, "decision_valid": dec.valid, "next_checkpoint": obs.extra["next_checkpoint"],
                       "latency_s": round(dec.latency_s, 4), "usd_cost": round(dec.usd_cost, 6),
                       "tokens_in": dec.tokens_in, "tokens_out": dec.tokens_out, "raw_text": dec.raw_text[:300],
                       "collided": res.collided, "pose": asdict(res.pose) if res.pose else None,
                       "reached": score.reached, "collision_events": score.collision_events, "extra": {**dec.extra, **res.extra}}
                if step == 0:
                    row["start_pose"] = start_pose
                logf.write(json.dumps(row, ensure_ascii=False) + "\n")
            if action == Action.STOP:
                stopped = True
                break
            if score.success:
                break
            obs = robot.observe()
            if not quiet:
                print(f"  step {step:3d} {action.value:8s} reached={score.reached} coll={score.collisions} lat={dec.latency_s:.2f}s")
    finally:
        if logf:
            logf.close()
    s = score.summary()
    s.update({
        "seed": seed, "agent": agent.name, "model_id": agent.model_id, "robot": robot.name,
        "usd_cost": round(usd, 6), "api_latency_mean_s": round(float(np.mean(lat)) if lat else 0.0, 4),
        "api_latency_p95_s": round(float(np.percentile(lat, 95)) if lat else 0.0, 4),
        "tokens_in": tok_in, "tokens_out": tok_out, "invalid_outputs": invalid, "api_errors": api_errors,
        "stopped_by_agent": int(stopped), "wall_s": round(time.time() - t0, 3), "events": score.events,
        "price_tier": "+".join(sorted(tiers)),
    })
    return s
