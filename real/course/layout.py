"""Export a Twin-01 layout (one seed) as the real-course constants block (internal work order A1).

Usage (repo root):  .venv/bin/python -m real.course.layout --seed 1017
Prints YAML; the stored copy lives in real/course/L1.yaml under the key `twin`, and
tests/real/test_course.py pins that copy to this function's output (changing the seed = a new layout name).
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "twin" / "configs" / "course01.yaml"
# Sign colour words exactly as protocol/prompt_v0.md sends them to the model (1 red … 5 purple).
SIGN_COLOR_WORDS = {1: "red", 2: "green", 3: "blue", 4: "yellow", 5: "purple"}


def _r(v: float, n: int = 3) -> float:
    return round(float(v) + 0.0, n)


def export_layout(seed: int, config: Path = CONFIG) -> dict[str, Any]:
    import yaml
    from twin.arena import sample_layout

    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    lay = sample_layout(cfg, seed)
    cp = cfg["checkpoints"]
    return {
        "seed": seed,
        "config": str(config.relative_to(ROOT)),
        "arena_size_m": cfg["arena"]["size_m"],
        "start": {"x": _r(lay.start[0]), "y": _r(lay.start[1]), "yaw_deg": _r(math.degrees(lay.start[2]), 1)},
        "checkpoints": [
            {"n": i, "x": _r(p[0]), "y": _r(p[1]), "sign_yaw_deg": _r(math.degrees(y), 1), "color": SIGN_COLOR_WORDS[i]}
            for i, (p, y) in enumerate(zip(lay.checkpoints, lay.sign_yaws), start=1)
        ],
        "obstacles": [
            {"n": i, "kind": o["kind"], "x": _r(o["x"]), "y": _r(o["y"]), "size_m": _r(o["size"]),
             "height_m": _r(o["height"]), "yaw_deg": _r(math.degrees(o["yaw"]), 1)}
            for i, o in enumerate(lay.obstacles, start=1)
        ],
        "constants": {
            "reach_radius_m": cp["reach_radius_m"], "min_gap_m": cp["min_gap_m"], "wall_margin_m": cp["wall_margin_m"],
            "post_radius_m": cp["post_radius_m"], "post_height_m": cp["post_height_m"], "sign_size_m": cp["sign_size_m"],
            "obstacle_clearance_m": cfg["obstacles"]["clearance_m"], "obstacle_height_m": cfg["obstacles"]["height_m"],
            "forward_m": cfg["motion"]["forward_m"], "turn_deg": cfg["motion"]["turn_deg"],
            "max_steps": cfg["episode"]["max_steps"],
        },
    }


def main() -> int:
    import yaml

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, required=True)
    args = ap.parse_args()
    print(yaml.safe_dump({"twin": export_layout(args.seed)}, allow_unicode=True, sort_keys=False), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
