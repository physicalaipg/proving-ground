"""布局采样与域随机化（全部由种子决定，可复现）。"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Layout:
    seed: int
    start: tuple[float, float, float]              # x, y, yaw_rad
    checkpoints: list[tuple[float, float]]
    sign_yaws: list[float]
    obstacles: list[dict[str, Any]]
    floor_rgb: tuple[tuple[float, float, float], tuple[float, float, float]]
    wall_rgba: tuple[float, float, float, float]
    light: dict[str, Any]
    friction: float
    slip: float
    extra: dict[str, Any] = field(default_factory=dict)


def _far(p, pts, d):
    return all(math.hypot(p[0] - q[0], p[1] - q[1]) >= d for q in pts)


def sample_layout(cfg: dict[str, Any], seed: int) -> Layout:
    rng = random.Random(seed)                     # 布局流：起点、检查点、障碍几何——与随机化开关无关
    drng = random.Random(seed ^ 0x5F3759DF)      # 随机化流：颜色、光照、摩擦、打滑——关掉时不消耗布局流
    half = cfg["arena"]["size_m"] / 2
    cp = cfg["checkpoints"]; ob = cfg["obstacles"]; rb = cfg["robot"]; rz = cfg["randomization"]
    ena = bool(rz.get("enabled", True))

    # 起点（角落附近，带抖动）
    s = rb["start"]
    # 起点抖动后车身必须整体在墙内（外接圆半径＋3 cm），否则一出生就顶墙、原地转必碰（PG-001 补丁 3 Q1 发现）
    fit = half - math.hypot(rb["length_m"] / 2, rb["width_m"] / 2) - 0.03
    sx = min(max(s["x"] + rng.uniform(-s["jitter_m"], s["jitter_m"]), -fit), fit)
    sy = min(max(s["y"] + rng.uniform(-s["jitter_m"], s["jitter_m"]), -fit), fit)
    syaw = math.radians(s["yaw_deg"] + rng.uniform(-s["jitter_deg"], s["jitter_deg"]))
    start = (sx, sy, syaw)

    # 检查点：顺序采样，满足间距与距墙约束
    lim = half - cp["wall_margin_m"]
    cps: list[tuple[float, float]] = []
    tries = 0
    while len(cps) < cp["count"]:
        tries += 1
        if tries > 20000:
            raise RuntimeError(f"seed {seed}: 检查点采样失败，放宽 min_gap_m/wall_margin_m")
        p = (rng.uniform(-lim, lim), rng.uniform(-lim, lim))
        if _far(p, cps, cp["min_gap_m"]) and _far(p, [start[:2]], 0.6):
            cps.append(p)
    # 数字牌朝向：面向上一检查点（第 1 个面向起点），让机器人接近时正对
    yaws = []
    for i, p in enumerate(cps):
        prev = cps[i - 1] if i > 0 else start[:2]
        yaws.append(math.atan2(prev[1] - p[1], prev[0] - p[0]))

    # 障碍
    n_ob = rng.randint(ob["count_min"], ob["count_max"])
    obs: list[dict[str, Any]] = []
    tries = 0
    while len(obs) < n_ob:
        tries += 1
        if tries > 20000:
            break
        sz = rng.uniform(ob["size_min_m"], ob["size_max_m"])
        p = (rng.uniform(-half + 0.2, half - 0.2), rng.uniform(-half + 0.2, half - 0.2))
        if not (_far(p, cps, ob["clearance_m"]) and _far(p, [start[:2]], ob["clearance_m"] + 0.1)
                and _far(p, [(o["x"], o["y"]) for o in obs], 0.35)):
            continue
        kind = rng.choice(["box", "cylinder"])
        rgba = (drng.uniform(0.2, 0.9), drng.uniform(0.2, 0.9), drng.uniform(0.2, 0.9), 1.0) if (ena and rz.get("textures", True)) else (0.55, 0.45, 0.35, 1.0)
        obs.append({"kind": kind, "x": p[0], "y": p[1], "size": sz, "height": ob["height_m"], "yaw": rng.uniform(0, math.pi), "rgba": rgba})

    # 域随机化（光照/纹理/摩擦/打滑）
    if ena and rz.get("textures", True):
        floor = ((drng.uniform(0.15, 0.5),) * 3, (drng.uniform(0.5, 0.9),) * 3)
        floor = (tuple(v + drng.uniform(-0.08, 0.08) for v in floor[0]), tuple(v + drng.uniform(-0.08, 0.08) for v in floor[1]))
        wall = (drng.uniform(0.6, 0.95), drng.uniform(0.6, 0.95), drng.uniform(0.6, 0.95), 1.0)
    else:
        floor = ((0.3, 0.3, 0.32), (0.75, 0.75, 0.78)); wall = (0.85, 0.85, 0.85, 1.0)
    if ena and rz.get("light", True):
        light = {"pos": (drng.uniform(-1.5, 1.5), drng.uniform(-1.5, 1.5), drng.uniform(2.0, 3.5)),
                 "diffuse": drng.uniform(0.5, 0.9), "ambient": drng.uniform(0.15, 0.45)}
    else:
        light = {"pos": (0.0, 0.0, 3.0), "diffuse": 0.7, "ambient": 0.3}
    mu = cfg["physics"]["friction"]
    if ena and rz.get("friction", True):
        mu *= drng.uniform(0.7, 1.3)
    lo, hi = rz.get("slip", [1.0, 1.0])
    slip = drng.uniform(lo, hi) if ena else 1.0
    return Layout(seed, start, cps, yaws, obs, floor, wall, light, mu, slip)
