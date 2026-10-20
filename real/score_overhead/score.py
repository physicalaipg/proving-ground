"""track.csv → episode score in the twin's format (internal work order D).

Usage (repo root):
  .venv/bin/python -m real.score_overhead.score track.csv [--layout real/course/L1.yaml] [--log logs/ep01.jsonl --t0 <epoch of frame 0>] [--out score.json]
Judgements (same constants as the twin, from the layout file): a checkpoint is reached when the car centre enters
reach_radius_m of the *next* checkpoint; contact = the car footprint (rectangle, yaw from the marker) overlaps an
obstacle footprint dilated by collision_margin_m, or leaves the 2×2 boundary (the twin's walls); path = sum of centre
displacements above a jitter deadband. With an episode log and the wall time of frame 0 (--t0), frames are grouped by
step (one ActResult per step → `collisions` = contact steps, comparable with the twin); without it every sampled frame
is one update (`collisions` = contact frames, not comparable; `collision_events`, arrivals, sim_score and path are).
Scoring itself is harness.scoring.ScoreState — the single scoring source.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from harness.interface import Action, ActResult, Pose
from harness.scoring import ScoreState
from real.course.register import load_course
from real.score_overhead.track import read_track

ROOT = Path(__file__).resolve().parents[2]
JITTER_M = 0.005  # centre displacements below this are marker noise, not travel


def rect_corners(x: float, y: float, yaw_rad: float, length: float, width: float) -> list[tuple[float, float]]:
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    hl, hw = length / 2, width / 2
    return [(x + c * dx - s * dy, y + s * dx + c * dy) for dx, dy in ((hl, hw), (hl, -hw), (-hl, -hw), (-hl, hw))]


def _axes(poly):
    out = []
    for i in range(len(poly)):
        ax, ay = poly[i][0] - poly[i - 1][0], poly[i][1] - poly[i - 1][1]
        n = math.hypot(ax, ay) or 1.0
        out.append((-ay / n, ax / n))
    return out


def polys_overlap(a, b) -> bool:
    """Separating axis theorem for two convex polygons."""
    for nx, ny in _axes(a) + _axes(b):
        pa = [nx * x + ny * y for x, y in a]; pb = [nx * x + ny * y for x, y in b]
        if max(pa) < min(pb) or max(pb) < min(pa):
            return False
    return True


def poly_circle_overlap(poly, cx: float, cy: float, r: float) -> bool:
    inside = True
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i - 1], poly[i]
        ex, ey = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((cx - x1) * ex + (cy - y1) * ey) / ((ex * ex + ey * ey) or 1.0)))
        if math.hypot(x1 + t * ex - cx, y1 + t * ey - cy) <= r:
            return True
        if (ex * (cy - y1) - ey * (cx - x1)) < 0:
            inside = False
    return inside


class ContactJudge:
    def __init__(self, course: dict, length_m: float, width_m: float, margin_m: float):
        self.length, self.width, self.margin = length_m, width_m, margin_m
        self.half = course["arena_size_m"] / 2
        self.obstacles = course["obstacles"]

    def contact(self, x: float, y: float, yaw_deg: float) -> str:
        """'' when free; else 'wall' or 'O<n>' for the first obstacle hit."""
        car = rect_corners(x, y, math.radians(yaw_deg), self.length, self.width)
        if any(abs(px) > self.half or abs(py) > self.half for px, py in car):
            return "wall"
        for o in self.obstacles:
            r = o["size_m"] / 2 + self.margin
            if o["kind"] == "cylinder":
                if poly_circle_overlap(car, o["x"], o["y"], r):
                    return f"O{o['n']}"
            else:
                box = rect_corners(o["x"], o["y"], math.radians(o["yaw_deg"]), 2 * r, 2 * r)
                if polys_overlap(car, box):
                    return f"O{o['n']}"
        return ""


def group_by_steps(track: list[dict], log_rows: list[dict], t0: float) -> list[list[dict]]:
    """Frames of each step: from that step's decision time to the next step's (log 't' is wall time, track 't_s' is video time)."""
    bounds = [r["t"] - t0 for r in log_rows] + [math.inf]
    groups: list[list[dict]] = [[] for _ in log_rows]
    for f in track:
        for k in range(len(log_rows)):
            if bounds[k] <= f["t_s"] < bounds[k + 1]:
                groups[k].append(f); break
    return groups


def score_track(track: list[dict], course: dict, *, length_m: float, width_m: float, margin_m: float,
                log_rows: list[dict] | None = None, t0: float | None = None) -> dict:
    judge = ContactJudge(course, length_m, width_m, margin_m)
    state = ScoreState(course["checkpoints"], course["start"], course["reach_radius_m"])
    seen = [f for f in track if f["detected"]]
    if not seen:
        raise ValueError("car marker never detected")
    # travel with a jitter deadband, contact per frame
    last = (course["start"][0], course["start"][1])
    contacts: list[str] = []
    for f in seen:
        f["_contact"] = judge.contact(f["x"], f["y"], f["yaw_deg"])
        contacts.append(f["_contact"])
    groups = group_by_steps(seen, log_rows, t0) if log_rows is not None and t0 is not None else [[f] for f in seen]
    hit_log = []
    for k, g in enumerate(groups):
        if not g:
            state.update(ActResult(Action.STOP, 0.0, False, None)); continue   # step with no frame: pose unknown, no contact evidence
        end = g[-1]
        contact = next((f["_contact"] for f in g if f["_contact"]), "")
        if contact:
            hit_log.append({"step": k + 1, "frame": next(f["frame"] for f in g if f["_contact"]), "with": contact})
        state.update(ActResult(Action.FORWARD, 0.0, bool(contact), Pose(end["x"], end["y"], math.radians(end["yaw_deg"]))))
    # replace the per-update travel with the deadbanded one (ScoreState sums raw displacements)
    travel = 0.0
    for f in seen:
        d = math.hypot(f["x"] - last[0], f["y"] - last[1])
        if d >= JITTER_M:
            travel += d; last = (f["x"], f["y"])
    state.traveled_m = travel
    out = state.summary()
    out.update(source="overhead", layout_seed=course["layout_seed"], course_source=course["source"],
               step_aligned=bool(log_rows is not None and t0 is not None), frames=len(track), frames_detected=len(seen),
               contact_frames=sum(1 for c in contacts if c), contacts=hit_log[:50],
               footprint={"length_m": length_m, "width_m": width_m, "margin_m": margin_m}, events=state.events)
    return out


def main(argv: list[str] | None = None) -> int:
    import yaml
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("track"); ap.add_argument("--layout", default=str(ROOT / "real" / "course" / "L1.yaml"))
    ap.add_argument("--log", help="episode jsonl (harness.episode) to align frames to steps")
    ap.add_argument("--t0", type=float, help="wall time (epoch seconds) of video frame 0")
    ap.add_argument("--out", help="score.json path (default: next to the track)")
    args = ap.parse_args(argv)
    lay = yaml.safe_load(open(args.layout, encoding="utf-8"))
    rb = lay["physical"]["robot"]
    course = load_course(Path(args.layout))
    log_rows = None
    if args.log:
        log_rows = [json.loads(l) for l in Path(args.log).read_text(encoding="utf-8").splitlines() if l.strip()]
        log_rows = [r for r in log_rows if "step" in r and "t" in r]
        if args.t0 is None:
            raise SystemExit("--t0 (wall time of frame 0) is required with --log")
    res = score_track(read_track(Path(args.track)), course, length_m=float(rb["footprint_length_m"]), width_m=float(rb["footprint_width_m"]),
                      margin_m=float(lay["physical"].get("collision_margin_m", 0.02)), log_rows=log_rows, t0=args.t0)
    out = Path(args.out) if args.out else Path(args.track).with_suffix(".score.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("checkpoints_reached", "collision_events", "collisions", "sim_score", "path_ratio", "success", "steps", "step_aligned")}))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
