"""Golden-case oracle for the real course (internal work order E; frozen by protocol/real-v0.md).

A scripted, open-loop shortest-path policy over the *known* L1 coordinates (measured values when the course is
registered, else the twin's): the twin's A* planner (same discrete actions, same margins) plans the five legs once
under nominal conditions, and the agent replays that action list step by step without looking at any image or
pose. It calibrates the path-ratio denominator and reachability on the real floor; it is run once (N=10) and is not
a leaderboard row.

Usage (repo root):  .venv/bin/python -m real.oracle [--layout real/course/L1.yaml]   # prints the plan
"""
from __future__ import annotations

import argparse
import math
import time
from pathlib import Path
from typing import Any

from harness.interface import Action, Decision, Observation
from real.course.register import load_course

ROOT = Path(__file__).resolve().parents[1]


def plan_actions(layout: Path = ROOT / "real" / "course" / "L1.yaml") -> dict[str, Any]:
    """Nominal A* plan over the L1 coordinates: {"actions": [...], "legs": [...], "source": twin|measured, "solvable": bool}."""
    import yaml
    from twin.arena import sample_layout
    from twin.planner import GOAL_MARGIN_M, AStarPlanner, World

    lay = yaml.safe_load(open(layout, encoding="utf-8"))
    course = load_course(layout)
    cfg = yaml.safe_load(open(ROOT / lay["twin"]["config"], encoding="utf-8"))
    twin_layout = sample_layout(cfg, lay["twin"]["seed"])
    # Known coordinates: the registered (measured) ones override the twin's sample; obstacle sizes and yaws stay nominal.
    twin_layout.start = (course["start"][0], course["start"][1], math.radians(course["start_yaw_deg"]))
    twin_layout.checkpoints = [tuple(p) for p in course["checkpoints"]]
    if course["source"] == "measured":
        measured = yaml.safe_load(open(layout.with_name(layout.stem + "-measured.yaml"), encoding="utf-8"))
        for o, m in zip(twin_layout.obstacles, measured["obstacles"]):
            o["x"], o["y"] = m["x"], m["y"]
    world = World.from_layout(cfg, twin_layout)
    m = cfg["motion"]
    planner = AStarPlanner(world, m["forward_m"], m["turn_deg"])
    goal_r = cfg["checkpoints"]["reach_radius_m"] - GOAL_MARGIN_M
    x, y, yaw = twin_layout.start
    actions: list[Action] = []
    legs: list[int] = []
    for i, cp in enumerate(twin_layout.checkpoints, start=1):
        acts = planner.plan(x, y, yaw, cp, goal_r)
        if acts is None:
            return {"actions": actions, "legs": legs, "source": course["source"], "solvable": False, "reason": f"no_path_leg{i}"}
        (x, y, yaw), _ = planner.simulate(x, y, yaw, acts)
        actions += acts
        legs.append(len(acts))
    return {"actions": actions, "legs": legs, "source": course["source"], "solvable": len(actions) <= cfg["episode"]["max_steps"],
            "reason": "" if len(actions) <= cfg["episode"]["max_steps"] else "exceeds_max_steps", "seed": lay["twin"]["seed"]}


class OpenLoopOracle:
    """Agent: replays the planned action list, then stops. Never reads the image, pose or ground truth."""
    name = "oracle-L1"
    model_id = "scripted/oracle-L1-openloop"
    needs_gt = False

    def __init__(self, actions: list[Action]):
        self.actions = list(actions)
        self._k = 0

    def start_episode(self, instruction: str, seed: int) -> None:
        self._k = 0

    def decide(self, obs: Observation) -> Decision:
        t = time.perf_counter()
        a = self.actions[self._k] if self._k < len(self.actions) else Action.STOP
        self._k += 1
        return Decision(a, time.perf_counter() - t, 0.0, self.model_id, raw_text=a.value, extra={"planned_step": self._k, "planned_total": len(self.actions)})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layout", default=str(ROOT / "real" / "course" / "L1.yaml"))
    args = ap.parse_args(argv)
    plan = plan_actions(Path(args.layout))
    print(f"L1 seed {plan.get('seed')} coordinates={plan['source']} solvable={plan['solvable']} {plan['reason']} legs={plan['legs']} total={len(plan['actions'])}")
    print(" ".join(a.value for a in plan["actions"]))
    return 0 if plan["solvable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
