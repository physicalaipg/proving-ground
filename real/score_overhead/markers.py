"""ArUco marker sheet for the overhead scorer (internal work order D).

Usage (repo root):  .venv/bin/python -m real.score_overhead.markers [--pdf ~/Downloads/internal work order-aruco.pdf] [--size-mm 80]
Dictionary DICT_4X4_50. id 0 = car top (centre on the chassis centre, arrow toward the camera end = the front);
ids 1–4 = arena corners A(-1,-1) B(+1,-1) C(+1,+1) D(-1,+1), each centred on the tape corner. Print at 100 %:
the 100 mm bar on each page must measure 100 mm. Marker size is also recorded in real/course/L1.yaml (markers.aruco).
"""
from __future__ import annotations

import argparse
import base64
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DICT_NAME = "DICT_4X4_50"
CAR_ID = 0
CORNER_IDS = {1: "A(-1,-1)", 2: "B(+1,-1)", 3: "C(+1,+1)", 4: "D(-1,+1)"}


def dictionary():
    import cv2
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICT_NAME))


def marker_png_b64(marker_id: int, px: int = 600) -> str:
    import cv2
    img = cv2.aruco.generateImageMarker(dictionary(), marker_id, px, borderBits=1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def render_html(size_mm: float) -> str:
    pages = []
    labels = {CAR_ID: "车顶 id 0 · 中心对准车体中心 · 箭头＝车头（相机所装的一头）"} | {i: f"场地角 id {i} · {n} · 中心对准胶带角点" for i, n in CORNER_IDS.items()}
    for mid, label in labels.items():
        arrow = ('<div style="position:absolute;left:50%;top:14mm;transform:translateX(-50%);font-size:9mm;font-weight:bold">▲ 车头 FRONT</div>'
                 if mid == CAR_ID else "")
        pages.append(f'''<section>
<div style="font-size:5mm;margin-bottom:6mm">内部工单 俯拍计分 ArUco（{DICT_NAME}）· {label} · 边长 {size_mm:.0f} mm，白边 ≥ 15 mm，哑光纸</div>
<div style="position:relative;height:{size_mm + 40:.0f}mm">{arrow}
<img src="data:image/png;base64,{marker_png_b64(mid)}" style="position:absolute;left:50%;top:28mm;transform:translateX(-50%);width:{size_mm:.0f}mm;height:{size_mm:.0f}mm;image-rendering:pixelated"/>
</div>
<div style="margin-top:10mm;font-size:4mm">打印校准：下方黑条应量得 100 mm（按 100 % 打印，不缩放）</div>
<div style="width:100mm;height:3mm;background:#000"></div>
<div style="font-size:4mm;margin-top:4mm">裁切时保留白边；车顶码贴平、不遮挡；角码压在胶带角上、码心＝角点。</div>
</section>''')
    return f'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>internal work order ArUco</title>
<style>@page {{ size: A4 portrait; margin: 12mm; }} body {{ font-family: "PingFang SC", Helvetica, Arial, sans-serif; margin:0; }}
section {{ page-break-after: always; }} section:last-child {{ page-break-after: auto; }}</style></head><body>{"".join(pages)}</body></html>'''


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", default=os.path.expanduser("~/Downloads/internal work order-aruco.pdf"))
    ap.add_argument("--html", default=str(ROOT / "real" / "score_overhead" / "aruco-sheet.html"))
    ap.add_argument("--size-mm", type=float, default=80.0)
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--chrome", default=CHROME)
    args = ap.parse_args(argv)
    html = Path(args.html)
    html.write_text(render_html(args.size_mm), encoding="utf-8")
    print(f"html → {html}")
    if args.no_pdf:
        return 0
    pdf = Path(args.pdf).expanduser()
    res = subprocess.run([args.chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", html.resolve().as_uri()],
                         capture_output=True, text=True, timeout=120)
    if res.returncode != 0 or not pdf.exists():
        print(res.stderr[-600:]); return 1
    print(f"pdf  → {pdf} ({pdf.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
