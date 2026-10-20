"""Field registration of a real course from one overhead photo (internal work order A3).

Two steps, both from the repo root:

  .venv/bin/python -m real.course.register points <photo.jpg> [--layout real/course/L1.yaml] [--out points.json]
      Opens the photo; click, in order, the four boundary corners A(-1,-1) B(+1,-1) C(+1,+1) D(-1,+1), then the
      start cross S and the tip of its heading strip, then checkpoints 1..5 at the cross under each post, then
      obstacles O1..On at the cross under each. Keys: u = undo last click, q = abort, Enter/space = finish.
      Click floor-contact points only (the tape crosses), never the top of a post.

  .venv/bin/python -m real.course.register solve points.json [--layout real/course/L1.yaml] [--write]
      Homography from the four corners (exact 4-point perspective transform, floor plane), world coordinates of
      every click, deviation from the twin layout. All deviations <= registration.tolerance_m (0.05) → with
      --write, saves real/course/<layout>-measured.yaml (the measured values become the real-course constants);
      any deviation above → exit 1 and the items to move are listed; the twin is never changed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORNERS = (("A", (-1.0, -1.0)), ("B", (1.0, -1.0)), ("C", (1.0, 1.0)), ("D", (-1.0, 1.0)))


def click_order(lay: dict) -> list[str]:
    names = [f"corner {n}({x:+.0f},{y:+.0f})" for n, (x, y) in CORNERS]
    names += ["start S (cross centre)", "start heading tip"]
    names += [f"checkpoint {p['n']} ({p['color']})" for p in lay["twin"]["checkpoints"]]
    names += [f"obstacle O{o['n']} ({o['kind']})" for o in lay["twin"]["obstacles"]]
    return names


def homography_from_corners(px: list[tuple[float, float]], size_m: float) -> "np.ndarray":
    import cv2
    import numpy as np

    h = size_m / 2
    src = np.array(px, dtype=np.float64).reshape(4, 2)
    dst = np.array([(-h, -h), (h, -h), (h, h), (-h, h)], dtype=np.float64)
    return cv2.getPerspectiveTransform(src.astype(np.float32), dst.astype(np.float32)).astype(np.float64)


def apply_h(H: "np.ndarray", p: tuple[float, float]) -> tuple[float, float]:
    x, y, w = H @ (p[0], p[1], 1.0)
    return (float(x / w), float(y / w))


def solve(points: dict, lay: dict) -> dict:
    """Pure computation: pixel clicks → world coordinates and deviations. Returns a report dict."""
    tw = lay["twin"]
    clicks = points["clicks"]
    names = click_order(lay)
    if len(clicks) != len(names):
        raise ValueError(f"expected {len(names)} clicks ({names[0]} … {names[-1]}), got {len(clicks)}")
    H = homography_from_corners(clicks[:4], tw["arena_size_m"])
    world = [apply_h(H, tuple(c)) for c in clicks]
    s_xy, s_tip = world[4], world[5]
    yaw = math.degrees(math.atan2(s_tip[1] - s_xy[1], s_tip[0] - s_xy[0]))
    tol = float(lay["registration"]["tolerance_m"])
    items = []

    def add(kind: str, n, meas: tuple[float, float], ref: tuple[float, float], extra: dict | None = None) -> None:
        dev = math.hypot(meas[0] - ref[0], meas[1] - ref[1])
        items.append({"kind": kind, "n": n, "x": round(meas[0], 3), "y": round(meas[1], 3),
                      "ref_x": ref[0], "ref_y": ref[1], "dev_m": round(dev, 3), "ok": dev <= tol, **(extra or {})})

    st = tw["start"]
    dyaw = (yaw - st["yaw_deg"] + 180) % 360 - 180
    add("start", "S", s_xy, (st["x"], st["y"]), {"yaw_deg": round(yaw, 1), "ref_yaw_deg": st["yaw_deg"], "dyaw_deg": round(dyaw, 1)})
    k = 6
    for p in tw["checkpoints"]:
        add("checkpoint", p["n"], world[k], (p["x"], p["y"])); k += 1
    for o in tw["obstacles"]:
        add("obstacle", o["n"], world[k], (o["x"], o["y"])); k += 1
    max_dev = max(i["dev_m"] for i in items)
    # Residual of the corner mapping itself is zero by construction (4-point transform); report the corner pixels.
    return {"layout_seed": tw["seed"], "photo": points.get("photo"), "tolerance_m": tol, "items": items,
            "max_dev_m": max_dev, "all_ok": all(i["ok"] for i in items),
            "start_yaw_tolerance_deg": 10.0, "yaw_ok": abs(dyaw) <= 10.0,
            "homography": [[round(v, 8) for v in row] for row in H.tolist()],
            "corner_px": [list(map(float, c)) for c in clicks[:4]]}


def measured_block(report: dict) -> dict:
    items = report["items"]
    st = next(i for i in items if i["kind"] == "start")
    return {"layout_seed": report["layout_seed"], "photo": report["photo"], "registered_at": time.strftime("%Y-%m-%d %H:%M"),
            "tolerance_m": report["tolerance_m"], "max_dev_m": report["max_dev_m"],
            "start": {"x": st["x"], "y": st["y"], "yaw_deg": st["yaw_deg"]},
            "checkpoints": [{"n": i["n"], "x": i["x"], "y": i["y"], "dev_m": i["dev_m"]} for i in items if i["kind"] == "checkpoint"],
            "obstacles": [{"n": i["n"], "x": i["x"], "y": i["y"], "dev_m": i["dev_m"]} for i in items if i["kind"] == "obstacle"],
            "homography": report["homography"], "corner_px": report["corner_px"]}


def measured_path(layout: Path) -> Path:
    return layout.with_name(layout.stem + "-measured.yaml")


def load_course(layout: Path = ROOT / "real" / "course" / "L1.yaml") -> dict:
    """Course dict for Robot.course(): measured coordinates when registered, else the twin's; reach radius from the twin."""
    import yaml

    lay = yaml.safe_load(open(layout, encoding="utf-8"))
    tw = lay["twin"]
    mp = measured_path(layout)
    source, src = "twin", tw
    if mp.exists():
        src = yaml.safe_load(open(mp, encoding="utf-8"))
        if src.get("layout_seed") != tw["seed"]:
            raise ValueError(f"{mp} registers seed {src.get('layout_seed')}, layout is seed {tw['seed']}")
        source = "measured"
    return {"checkpoints": [(p["x"], p["y"]) for p in src["checkpoints"]], "start": (src["start"]["x"], src["start"]["y"]),
            "start_yaw_deg": src["start"]["yaw_deg"], "reach_radius_m": tw["constants"]["reach_radius_m"],
            "obstacles": [dict(o) for o in tw["obstacles"]], "arena_size_m": tw["arena_size_m"],
            "layout_seed": tw["seed"], "source": source}


def _cmd_points(args: argparse.Namespace) -> int:
    import cv2
    import yaml

    lay = yaml.safe_load(open(args.layout, encoding="utf-8"))
    names = click_order(lay)
    img = cv2.imread(args.photo)
    if img is None:
        print(f"cannot read {args.photo}"); return 2
    h, w = img.shape[:2]
    scale = min(1.0, 1500 / w, 900 / h)
    view = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img.copy()
    clicks: list[list[float]] = []

    def redraw() -> None:
        canvas = view.copy()
        for i, (x, y) in enumerate(clicks):
            cv2.circle(canvas, (int(x * scale), int(y * scale)), 5, (0, 0, 255), 2)
            cv2.putText(canvas, names[i].split(" (")[0], (int(x * scale) + 6, int(y * scale) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        nxt = names[len(clicks)] if len(clicks) < len(names) else "done: press Enter"
        cv2.putText(canvas, f"[{len(clicks)}/{len(names)}] click: {nxt}   (u undo, q abort)", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 3)
        cv2.putText(canvas, f"[{len(clicks)}/{len(names)}] click: {nxt}   (u undo, q abort)", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
        cv2.imshow("register", canvas)

    def on_mouse(event, x, y, flags, param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < len(names):
            clicks.append([x / scale, y / scale]); redraw()

    cv2.namedWindow("register"); cv2.setMouseCallback("register", on_mouse); redraw()
    while True:
        key = cv2.waitKey(50) & 0xFF
        if key == ord("q"):
            cv2.destroyAllWindows(); print("aborted"); return 1
        if key == ord("u") and clicks:
            clicks.pop(); redraw()
        if key in (13, 32) and len(clicks) == len(names):
            break
    cv2.destroyAllWindows()
    out = Path(args.out)
    out.write_text(json.dumps({"photo": str(Path(args.photo).resolve()), "layout": str(args.layout), "order": names,
                               "clicks": clicks, "image_size": [w, h]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"points → {out}")
    return 0


def _cmd_solve(args: argparse.Namespace) -> int:
    import yaml

    layout = Path(args.layout)
    lay = yaml.safe_load(open(layout, encoding="utf-8"))
    points = json.loads(Path(args.points).read_text(encoding="utf-8"))
    rep = solve(points, lay)
    print(f"L1 seed {rep['layout_seed']}  tolerance {rep['tolerance_m']:.2f} m  photo {rep['photo']}")
    print(f"{'item':16s}{'x':>8s}{'y':>8s}{'ref_x':>8s}{'ref_y':>8s}{'dev_m':>7s}  ok")
    for i in rep["items"]:
        print(f"{i['kind'] + ' ' + str(i['n']):16s}{i['x']:8.3f}{i['y']:8.3f}{i['ref_x']:8.3f}{i['ref_y']:8.3f}{i['dev_m']:7.3f}  {'✔' if i['ok'] else '✘ move'}")
    st = rep["items"][0]
    print(f"start yaw {st['yaw_deg']:+.1f}° (ref {st['ref_yaw_deg']:+.1f}°, Δ {st['dyaw_deg']:+.1f}°, tolerance ±{rep['start_yaw_tolerance_deg']:.0f}°) {'✔' if rep['yaw_ok'] else '✘ turn'}")
    print(f"max deviation {rep['max_dev_m']:.3f} m → {'REGISTERED' if rep['all_ok'] and rep['yaw_ok'] else 'NOT registered: move the ✘ items and re-shoot'}")
    if not (rep["all_ok"] and rep["yaw_ok"]):
        return 1
    if args.write:
        mp = measured_path(layout)
        mp.write_text("# 真机常量（实测值即常量）：register.py solve --write 产出，源照片与像素点见本文件；tag real-v0-prereg 后不得改。\n"
                      + yaml.safe_dump(measured_block(rep), allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"measured → {mp}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("points"); p.add_argument("photo"); p.add_argument("--layout", default=str(ROOT / "real" / "course" / "L1.yaml")); p.add_argument("--out", default="points.json")
    s = sub.add_parser("solve"); s.add_argument("points"); s.add_argument("--layout", default=str(ROOT / "real" / "course" / "L1.yaml")); s.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    return _cmd_points(args) if args.cmd == "points" else _cmd_solve(args)


if __name__ == "__main__":
    sys.exit(main())
