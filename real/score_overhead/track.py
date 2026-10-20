"""Overhead video → per-frame car pose in arena metres (internal work order D).

Usage (repo root):
  .venv/bin/python -m real.score_overhead.track <video.mp4> --out track.csv [--corners points.json] [--size-m 2.0] [--every 1]
Homography (floor plane): from the four corner markers (ids 1–4, centres = boundary corners; median over the
frames where all four are seen) or, with --corners, from the registration clicks (register.py points) — use that
when the markers are not in view; the camera must not move between the photo and the video.
Car: marker id 0, centre = chassis centre, arrow (marker top edge) = front. Output columns:
frame, t_s, detected, x, y, yaw_deg, px, py — x/y/yaw empty when the car marker is not seen.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from real.score_overhead.markers import CAR_ID, CORNER_IDS, dictionary

TRACK_FIELDS = ("frame", "t_s", "detected", "x", "y", "yaw_deg", "px", "py")


def detector():
    import cv2
    params = cv2.aruco.DetectorParameters()
    return cv2.aruco.ArucoDetector(dictionary(), params)


def detect(det, frame) -> dict[int, "np.ndarray"]:
    """{id: 4x2 corners (TL, TR, BR, BL in marker order)} for every marker in the frame."""
    corners, ids, _ = det.detectMarkers(frame)
    if ids is None:
        return {}
    return {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners)}


def corner_homography(corner_px: list[tuple[float, float]], size_m: float):
    """Pixel → world (metres, y up) from the four boundary corners A B C D in that order."""
    import cv2
    import numpy as np
    h = size_m / 2
    src = np.array(corner_px, dtype=np.float32).reshape(4, 2)
    dst = np.array([(-h, -h), (h, -h), (h, h), (-h, h)], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst).astype(float)


def to_world(H, p) -> tuple[float, float]:
    x, y, w = H @ (float(p[0]), float(p[1]), 1.0)
    return (x / w, y / w)


def pose_from_marker(H, quad) -> tuple[float, float, float]:
    """Car pose from the id-0 quad: centre → (x, y); front = midpoint of the top edge mapped through H → yaw."""
    centre = quad.mean(axis=0)
    front_px = (quad[0] + quad[1]) / 2       # TL, TR = the marker's top edge = the arrow end
    cx, cy = to_world(H, centre)
    fx, fy = to_world(H, front_px)
    return cx, cy, math.degrees(math.atan2(fy - cy, fx - cx))


def corners_from_markers(frames_markers: list[dict[int, "np.ndarray"]]) -> list[tuple[float, float]] | None:
    import numpy as np
    seen = {i: [] for i in CORNER_IDS}
    for m in frames_markers:
        if all(i in m for i in CORNER_IDS):
            for i in CORNER_IDS:
                seen[i].append(m[i].mean(axis=0))
    if not seen[1]:
        return None
    return [tuple(np.median(np.array(seen[i]), axis=0).tolist()) for i in sorted(CORNER_IDS)]


def track_video(video: str, *, corners_px: list[tuple[float, float]] | None = None, size_m: float = 2.0, every: int = 1) -> list[dict]:
    import cv2
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise OSError(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    det = detector()
    per_frame: list[tuple[int, dict]] = []
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if n % every == 0:
            per_frame.append((n, detect(det, frame)))
        n += 1
    cap.release()
    if corners_px is None:
        corners_px = corners_from_markers([m for _, m in per_frame])
        if corners_px is None:
            raise ValueError("corner markers 1–4 never all visible; pass --corners from register.py points")
    H = corner_homography(corners_px, size_m)
    rows = []
    for idx, m in per_frame:
        row = {"frame": idx, "t_s": round(idx / fps, 4), "detected": int(CAR_ID in m), "x": "", "y": "", "yaw_deg": "", "px": "", "py": ""}
        if CAR_ID in m:
            x, y, yaw = pose_from_marker(H, m[CAR_ID])
            c = m[CAR_ID].mean(axis=0)
            row.update(x=round(x, 4), y=round(y, 4), yaw_deg=round(yaw, 2), px=round(float(c[0]), 1), py=round(float(c[1]), 1))
        rows.append(row)
    return rows


def write_track(rows: list[dict], path: Path, meta: dict | None = None) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACK_FIELDS)
        w.writeheader(); w.writerows(rows)
    if meta is not None:
        Path(path).with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def read_track(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["frame"] = int(r["frame"]); r["t_s"] = float(r["t_s"]); r["detected"] = int(r["detected"])
        for k in ("x", "y", "yaw_deg"):
            r[k] = float(r[k]) if r[k] != "" else None
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video"); ap.add_argument("--out", required=True)
    ap.add_argument("--corners", help="points.json from register.py (first four clicks = A B C D)")
    ap.add_argument("--size-m", type=float, default=2.0); ap.add_argument("--every", type=int, default=1)
    args = ap.parse_args(argv)
    corners = None
    if args.corners:
        corners = [tuple(c) for c in json.loads(Path(args.corners).read_text(encoding="utf-8"))["clicks"][:4]]
    rows = track_video(args.video, corners_px=corners, size_m=args.size_m, every=args.every)
    write_track(rows, Path(args.out), {"video": str(Path(args.video).resolve()), "corners_source": "register.py" if corners else "markers 1-4",
                                       "size_m": args.size_m, "every": args.every, "frames": len(rows), "detected": sum(r["detected"] for r in rows)})
    print(f"{len(rows)} frames, car seen in {sum(r['detected'] for r in rows)} → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
