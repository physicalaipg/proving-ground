"""Fill real/config/camera.yaml from measurements (internal work order B). Nothing here touches the twin.

  .venv/bin/python -m real.camera_measure list                      # cameras with VID:PID (macOS system_profiler)
  .venv/bin/python -m real.camera_measure fov --distance D --width W [--height Hv] [--write]
  .venv/bin/python -m real.camera_measure mount --height-m H [--forward-m F] [--pitch-deg P] [--write]
  .venv/bin/python -m real.camera_measure select --vid-pid 1234:abcd [--product NAME] [--write]
  .venv/bin/python -m real.camera_measure readback --vid-pid 1234:abcd [--write]   # uvc-util -o … stored verbatim
  .venv/bin/python -m real.camera_measure delta [--write]            # measured − twin assumed
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "real" / "config" / "camera.yaml"


def hfov_deg(distance_m: float, width_m: float) -> float:
    """Horizontal field of view from a tape of visible width W at distance D (README「视场实测法」)."""
    if distance_m <= 0 or width_m <= 0:
        raise ValueError("distance and width must be positive")
    return math.degrees(2 * math.atan(width_m / (2 * distance_m)))


def vid_pid_hex(model_id: str) -> str | None:
    m = re.search(r"VendorID_(\d+) ProductID_(\d+)", model_id or "")
    return "%04x:%04x" % (int(m[1]), int(m[2])) if m else None


def cameras() -> list[dict]:
    from real.camera import list_cameras
    return [{"name": d.get("_name"), "model_id": d.get("spcamera_model-id"), "vid_pid": vid_pid_hex(d.get("spcamera_model-id", "")),
             "unique_id": d.get("spcamera_unique-id")} for d in list_cameras()]


def delta(cfg: dict) -> dict:
    cam, tw = cfg["camera"], cfg["twin_assumed"]
    out = {}
    for key, measured in (("height_m", cam["mount"]["height_m"]), ("forward_offset_m", cam["mount"]["forward_offset_m"]), ("hfov_deg", cam["fov"]["hfov_deg"])):
        out[key] = None if measured is None else round(float(measured) - float(tw[key]), 4)
    return out


def _load():
    import yaml
    return yaml.safe_load(open(CONFIG, encoding="utf-8"))


def _save(cfg: dict) -> None:
    """Rewrite values in place, keeping the file's comments: only scalar lines whose key matches are replaced."""
    import yaml
    text = CONFIG.read_text(encoding="utf-8")
    flat = {"vid_pid": cfg["camera"]["selector"]["vid_pid"], "product": cfg["camera"]["selector"]["product"],
            "height_m": cfg["camera"]["mount"]["height_m"], "forward_offset_m": cfg["camera"]["mount"]["forward_offset_m"],
            "pitch_deg": cfg["camera"]["mount"]["pitch_deg"], "hfov_deg": cfg["camera"]["fov"]["hfov_deg"], "vfov_deg": cfg["camera"]["fov"]["vfov_deg"],
            "method": cfg["camera"]["fov"]["method"], "exposure": cfg["camera"]["uvc_lock"]["exposure"],
            "wb_temperature": cfg["camera"]["uvc_lock"]["wb_temperature"], "readback": cfg["camera"]["uvc_lock"]["readback"], "delta": cfg["delta"]}
    lines = []
    for line in text.splitlines():
        m = re.match(r"^(\s*)([a-z_]+):\s*(.*?)(\s+#.*)?$", line)
        if m and m[2] in flat and not line.lstrip().startswith("#") and m[1] != "":
            value = yaml.safe_dump(flat[m[2]], default_flow_style=True, allow_unicode=True, width=10**6).strip().rstrip(".")
            if value.endswith("\n..."):
                value = value[:-4]
            line = f"{m[1]}{m[2]}: {value}{m[4] or ''}"
        elif m and m[2] == "delta" and m[1] == "":
            value = yaml.safe_dump(flat["delta"], default_flow_style=True, allow_unicode=True, width=10**6).strip().rstrip(".")
            line = f"delta: {value}{m[4] or ''}"
        lines.append(line)
    CONFIG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("fov"); f.add_argument("--distance", type=float, required=True); f.add_argument("--width", type=float, required=True)
    f.add_argument("--height", type=float); f.add_argument("--write", action="store_true")
    m = sub.add_parser("mount"); m.add_argument("--height-m", type=float, required=True); m.add_argument("--forward-m", type=float)
    m.add_argument("--pitch-deg", type=float); m.add_argument("--write", action="store_true")
    s = sub.add_parser("select"); s.add_argument("--vid-pid", required=True); s.add_argument("--product"); s.add_argument("--write", action="store_true")
    r = sub.add_parser("readback"); r.add_argument("--vid-pid", required=True); r.add_argument("--write", action="store_true")
    d = sub.add_parser("delta"); d.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    cfg = _load()
    if args.cmd == "list":
        for c in cameras():
            print(f"{c['vid_pid'] or '----:----'}  {c['name']}  [{c['model_id']}]")
        return 0
    if args.cmd == "fov":
        h = hfov_deg(args.distance, args.width)
        v = hfov_deg(args.distance, args.height) if args.height else None
        print(f"hfov {h:.1f}°" + (f"  vfov {v:.1f}°" if v else "") + f"  (D={args.distance} m, W={args.width} m)")
        cfg["camera"]["fov"].update(hfov_deg=round(h, 1), vfov_deg=None if v is None else round(v, 1),
                                    method={"distance_m": args.distance, "width_m": args.width, "height_m": args.height, "measured_at": time.strftime("%Y-%m-%d")})
    elif args.cmd == "mount":
        cfg["camera"]["mount"].update(height_m=args.height_m)
        if args.forward_m is not None: cfg["camera"]["mount"]["forward_offset_m"] = args.forward_m
        if args.pitch_deg is not None: cfg["camera"]["mount"]["pitch_deg"] = args.pitch_deg
        print(cfg["camera"]["mount"])
    elif args.cmd == "select":
        if not re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{4}", args.vid_pid):
            raise SystemExit("--vid-pid must be four hex digits : four hex digits")
        cfg["camera"]["selector"].update(vid_pid=args.vid_pid.lower(), product=args.product)
        print(cfg["camera"]["selector"])
    elif args.cmd == "readback":
        from real.camera import uvc_target
        res = subprocess.run(["uvc-util", "-V", uvc_target(args.vid_pid), "-o", "auto-exposure-mode", "-o", "exposure-time-abs",
                              "-o", "auto-white-balance-temp", "-o", "white-balance-temp"], capture_output=True, text=True)
        names = ("auto-exposure-mode", "exposure-time-abs", "auto-white-balance-temp", "white-balance-temp")
        values = res.stdout.split()
        text = " ".join("%s=%s" % nv for nv in zip(names, values)) + " (uvc-util %s)" % time.strftime("%Y-%m-%d %H:%M") if len(values) == 4 else (res.stdout + res.stderr).strip().replace("\n", " | ")
        print(text or f"uvc-util rc {res.returncode}, no output")
        cfg["camera"]["uvc_lock"]["readback"] = text or None
    cfg["delta"] = delta(cfg)
    if args.cmd == "delta" or True:
        print("delta (measured − twin assumed):", cfg["delta"])
    if getattr(args, "write", False):
        _save(cfg)
        print(f"→ {CONFIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
