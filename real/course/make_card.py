"""Render the one-page layout card for a real course (internal work order A2).

Usage (repo root):
  .venv/bin/python -m real.course.make_card                      # writes real/course/L1-card.html and ~/Downloads/internal work order-layout-card.pdf
  .venv/bin/python -m real.course.make_card --layout real/course/L1.yaml --pdf /path/out.pdf --no-pdf
The PDF is printed by Google Chrome headless (macOS path below; override with --chrome). The HTML is the reviewable source.
"""
from __future__ import annotations

import argparse
import html
import math
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SIGN_HEX = {"red": "#d81e1e", "green": "#1e9e3a", "blue": "#1f55d8", "yellow": "#e3c400", "purple": "#7a1fb8"}


def _svg_top_view(lay: dict, side_px: float = 470.0) -> str:
    """Top view: x right, y up, origin at the arena centre; `side_px` is the drawn size of the 2 m square."""
    tw = lay["twin"]
    half = tw["arena_size_m"] / 2
    s = side_px / tw["arena_size_m"]               # px per metre
    pad = 40
    W = H = side_px + 2 * pad

    def X(x: float) -> float:
        return pad + (x + half) * s

    def Y(y: float) -> float:
        return pad + (half - y) * s

    c = tw["constants"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" font-family="Helvetica, Arial, sans-serif">']
    out.append(f'<rect x="{pad}" y="{pad}" width="{side_px}" height="{side_px}" fill="#fbfbf8" stroke="#222" stroke-width="2.5"/>')
    # 0.5 m grid and axis labels
    for v in (-0.5, 0.0, 0.5):
        out.append(f'<line x1="{X(v):.1f}" y1="{pad}" x2="{X(v):.1f}" y2="{pad + side_px}" stroke="#ccc" stroke-width="0.8" stroke-dasharray="4 4"/>')
        out.append(f'<line x1="{pad}" y1="{Y(v):.1f}" x2="{pad + side_px}" y2="{Y(v):.1f}" stroke="#ccc" stroke-width="0.8" stroke-dasharray="4 4"/>')
    for v in (-1.0, -0.5, 0.0, 0.5, 1.0):
        out.append(f'<text x="{X(v):.1f}" y="{pad + side_px + 14}" font-size="10" text-anchor="middle" fill="#444">x={v:+.1f}</text>')
        out.append(f'<text x="{pad - 4}" y="{Y(v) + 3:.1f}" font-size="10" text-anchor="end" fill="#444">y={v:+.1f}</text>')
    # corner labels (registration photo order)
    for name, (cx, cy) in {"A(-1,-1)": (-1, -1), "B(+1,-1)": (1, -1), "C(+1,+1)": (1, 1), "D(-1,+1)": (-1, 1)}.items():
        dx = 5 if cx < 0 else -5
        anchor = "start" if cx < 0 else "end"
        out.append(f'<text x="{X(cx) + dx:.1f}" y="{Y(cy) + (-5 if cy < 0 else 12):.1f}" font-size="10" font-weight="bold" text-anchor="{anchor}" fill="#222">{name}</text>')
    # obstacles
    for o in tw["obstacles"]:
        cx, cy, r = X(o["x"]), Y(o["y"]), o["size_m"] * s / 2
        if o["kind"] == "box":
            out.append(f'<rect x="{cx - r:.1f}" y="{cy - r:.1f}" width="{2 * r:.1f}" height="{2 * r:.1f}" fill="#b9a58a" stroke="#5a4a36" stroke-width="1.5" transform="rotate({-o["yaw_deg"]:.1f} {cx:.1f} {cy:.1f})"/>')
        else:
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="#b9a58a" stroke="#5a4a36" stroke-width="1.5"/>')
        out.append(f'<text x="{cx:.1f}" y="{cy + 4:.1f}" font-size="11" font-weight="bold" text-anchor="middle" fill="#3a2d1e">O{o["n"]}</text>')
    # checkpoints: reach circle, post, number, sign facing
    for p in tw["checkpoints"]:
        cx, cy = X(p["x"]), Y(p["y"])
        col = SIGN_HEX[p["color"]]
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{c["reach_radius_m"] * s:.1f}" fill="none" stroke="{col}" stroke-width="1" stroke-dasharray="5 4" opacity="0.7"/>')
        a = math.radians(p["sign_yaw_deg"])
        out.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx + 0.22 * s * math.cos(a):.1f}" y2="{cy - 0.22 * s * math.sin(a):.1f}" stroke="{col}" stroke-width="2"/>')
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{max(c["post_radius_m"] * s, 7):.1f}" fill="#fff" stroke="{col}" stroke-width="3.5"/>')
        out.append(f'<text x="{cx:.1f}" y="{cy + 4.5:.1f}" font-size="12" font-weight="bold" text-anchor="middle" fill="#111">{p["n"]}</text>')
    # start pose: robot outline (turn-width square for the old car) and heading arrow
    st = tw["start"]
    rb = lay["physical"]["robot"]
    L, Wd = 0.20, 0.17  # drawn chassis outline of YB-EET01 (approx.; the pose refers to the centre)
    cx, cy, a = X(st["x"]), Y(st["y"]), math.radians(st["yaw_deg"])
    out.append(f'<g transform="translate({cx:.1f} {cy:.1f}) rotate({-st["yaw_deg"]:.1f})">'
               f'<rect x="{-L * s / 2:.1f}" y="{-Wd * s / 2:.1f}" width="{L * s:.1f}" height="{Wd * s:.1f}" fill="#dfe8f5" stroke="#1d4f91" stroke-width="2"/>'
               f'<line x1="0" y1="0" x2="{0.3 * s:.1f}" y2="0" stroke="#1d4f91" stroke-width="2.5"/>'
               f'<polygon points="{0.3 * s:.1f},0 {0.3 * s - 8:.1f},-5 {0.3 * s - 8:.1f},5" fill="#1d4f91"/></g>')
    out.append(f'<text x="{cx:.1f}" y="{cy + 26:.1f}" font-size="10" font-weight="bold" text-anchor="middle" fill="#1d4f91">S 起点 yaw {st["yaw_deg"]:+.1f}°</text>')
    # camera marks
    out.append(f'<text x="{X(0):.1f}" y="{Y(0) - 8:.1f}" font-size="9" text-anchor="middle" fill="#777">⌾ 俯拍机位：中心正上方</text>')
    out.append(f'<text x="{X(1.0) - 4:.1f}" y="{Y(1.0) - 20:.1f}" font-size="9" text-anchor="end" fill="#777">▣ Pocket 3：C 角外 0.3 m、高 0.9 m、望向 S</text>')
    out.append("</svg>")
    return "\n".join(out)


def _svg_cross(side: int = 130) -> str:
    """The return mark drawn under every item: two 10 cm tape strips crossing at the item's centre; start adds a heading strip."""
    c = side / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" width="{side}" height="{side}" font-family="Helvetica, Arial, sans-serif">'
            f'<circle cx="{c}" cy="{c}" r="{side * 0.33:.0f}" fill="none" stroke="#999" stroke-dasharray="4 3"/>'
            f'<rect x="{c - side * 0.3:.0f}" y="{c - 4}" width="{side * 0.6:.0f}" height="8" fill="#f2c200" stroke="#7a6300"/>'
            f'<rect x="{c - 4}" y="{c - side * 0.3:.0f}" width="8" height="{side * 0.6:.0f}" fill="#f2c200" stroke="#7a6300"/>'
            f'<line x1="{c}" y1="{c}" x2="{c + side * 0.42:.0f}" y2="{c - side * 0.24:.0f}" stroke="#1d4f91" stroke-width="5" stroke-dasharray="6 3"/>'
            f'<text x="{c:.0f}" y="{side - 4}" font-size="8.5" text-anchor="middle" fill="#333">十字臂 10 cm，交点＝中心</text>'
            f'<text x="{c + 10:.0f}" y="{c - side * 0.33:.0f}" font-size="8.5" fill="#1d4f91">起点加朝向线</text>'
            f'<text x="4" y="11" font-size="8.5" fill="#333">虚线圈＝物件底面</text></svg>')


def render_html(lay: dict) -> str:
    tw, ph, cam, c = lay["twin"], lay["physical"], lay["cameras"], lay["twin"]["constants"]
    e = html.escape
    cp_rows = "".join(
        f'<tr><td><b style="color:{SIGN_HEX[p["color"]]}">{p["n"]}</b></td><td>{p["x"]:+.3f}</td><td>{p["y"]:+.3f}</td>'
        f'<td>{p["n"]} {p["color"]}</td><td>{p["sign_yaw_deg"]:+.1f}°</td></tr>' for p in tw["checkpoints"])
    ob_rows = "".join(
        f'<tr><td>O{o["n"]}</td><td>{"方箱" if o["kind"] == "box" else "圆柱"}</td><td>{o["x"]:+.3f}</td><td>{o["y"]:+.3f}</td>'
        f'<td>{o["size_m"] * 100:.1f} cm</td><td>{o["height_m"] * 100:.0f} cm</td><td>{o["yaw_deg"] if o["kind"] == "box" else "—"}{"°" if o["kind"] == "box" else ""}</td></tr>'
        for o in tw["obstacles"])
    st = tw["start"]
    diag = tw["arena_size_m"] * math.sqrt(2)
    sign_px = c["sign_size_m"] / diag * 640 / math.radians(70) if False else 640 * (c["sign_size_m"] / diag) / (2 * math.tan(math.radians(35)))
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>内部工单 L1 布局卡</title>
<style>
@page {{ size: A4 landscape; margin: 7mm; }}
body {{ font-family: "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", Arial, sans-serif; font-size: 7.9pt; color: #111; margin: 0; }}
h1 {{ font-size: 11.5pt; margin: 0 0 2px 0; }}
h2 {{ font-size: 8.6pt; margin: 4px 0 1px 0; border-bottom: 1px solid #999; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #bbb; padding: 1px 4px; text-align: left; white-space: nowrap; }}
th {{ background: #eee; }}
.row {{ display: flex; gap: 8px; }}
.left {{ flex: 0 0 auto; }}
.right {{ flex: 1 1 auto; min-width: 0; }}
.small {{ font-size: 7.2pt; color: #333; }}
ul {{ margin: 2px 0 2px 14px; padding: 0; }}
li {{ margin: 0; }}
</style></head><body>
<h1>内部工单 布局卡 · 真机固定布局 L1（Twin-01 种子 {tw["seed"]}）　<span class="small" style="font-weight:normal">坐标系：场地中心为原点，x 向右（东）、y 向上（北），单位 m；yaw 自 +x 逆时针为正。2×2 m 边界＝胶带线。到达半径 {c["reach_radius_m"]:.2f} m（虚线圈），前进步长 {c["forward_m"]:.2f} m，转向 {c["turn_deg"]:.0f}°，回合上限 {c["max_steps"]} 步。真源 real/course/L1.yaml</span></h1>
<div class="row">
<div class="left">{_svg_top_view(lay)}</div>
<div class="right">
<h2>起点 S（车体中心）：x {st["x"]:+.3f}，y {st["y"]:+.3f}，yaw {st["yaw_deg"]:+.1f}°（车头＝相机所装的一头）</h2>
<h2>检查点（立柱 ⌀{ph["checkpoint_post"]["diameter_m"] * 100:.0f} cm × 高 {ph["checkpoint_post"]["height_m"] * 100:.0f} cm，中性灰；柱顶数字牌 {c["sign_size_m"] * 100:.0f}×{c["sign_size_m"] * 100:.0f} cm 白底黑数字、双面、边框宽 {ph["checkpoint_sign"]["border_width_m"] * 100:.1f} cm、数字高约 {ph["checkpoint_sign"]["digit_height_m"] * 100:.0f} cm，牌中心离地 38 cm）</h2>
<table><tr><th>号</th><th>x</th><th>y</th><th>外观词（与提示词逐字一致）</th><th>牌面朝向</th></tr>{cp_rows}</table>
<div class="small">提示词原句：<i>Checkpoints are vertical posts with a numbered sign (1–5); each sign has a distinctive border color: 1 red, 2 green, 3 blue, 4 yellow, 5 purple.</i>　边框色用哑光饱和色；按 0.15 m 相机、70°、640×480，对角 {diag:.2f} m 处 16 cm 牌约 {sign_px:.0f} px、边框约 {sign_px / 10:.0f} px，颜色可辨、数字勉强可辨。牌面朝向＝面向上一检查点（1 号面向起点）。两两间距 ≥ {c["min_gap_m"]:.2f} m、距边界 ≥ {c["wall_margin_m"]:.2f} m（已按种子满足）。</div>
<h2>障碍（中性色：纸箱本色／灰；高 {c["obstacle_height_m"] * 100:.0f} cm；方箱按 yaw 转，圆柱不分朝向；距检查点与起点 ≥ {c["obstacle_clearance_m"]:.2f} m）</h2>
<table><tr><th>号</th><th>形</th><th>x</th><th>y</th><th>边长／直径</th><th>高</th><th>yaw</th></tr>{ob_rows}</table>
<div class="row" style="margin-top:4px">
<div style="flex:0 0 auto">{_svg_cross()}</div>
<div class="small" style="flex:1 1 auto">
<h2>回位标记（每件脚下）</h2>
<ul><li>每根柱、每个障碍、起点各一个胶带十字：两条 10 cm 胶带，交点＝该件中心坐标；起点另自交点沿 yaw {st["yaw_deg"]:+.1f}° 贴 15 cm 朝向线。</li>
<li>回位＝把物件底面中心对回十字交点（人工，首季不做自动回位，裁定 2026-10-05-05）。</li></ul>
<h2>机位建议</h2>
<ul><li>俯拍（测量链）：{e(cam["overhead"]["where"])}，高 {e(str(cam["overhead"]["height_m"]))} m；{e(cam["overhead"]["note"])}。登记照与跑测视频同机位。</li>
<li>Pocket 3（展示）：{e(cam["pocket3"]["where"])}，高 {cam["pocket3"]["height_m"]} m，{e(cam["pocket3"]["facing"])}；{e(cam["pocket3"]["note"])}。</li></ul>
<h2>登记照（A3）</h2>
<ul><li>铺好后从俯拍机位拍一张：边界四角 A(-1,-1) B(+1,-1) C(+1,+1) D(-1,+1) 全部入画，卷尺沿一条边展开入画（量程可读）。</li>
<li>CC 以四角做单应量各物实际坐标：偏差 ≤ 5 cm 登记为真机常量（实测值即常量）；超阈报移位重拍，不改孪生。</li></ul>
</div></div>
</div></div>
</body></html>"""


def main() -> int:
    import yaml

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layout", default=str(ROOT / "real" / "course" / "L1.yaml"))
    ap.add_argument("--html", default=None, help="HTML output (default: next to the layout, <name>-card.html)")
    ap.add_argument("--pdf", default=os.path.expanduser("~/Downloads/internal work order-layout-card.pdf"))
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--chrome", default=CHROME)
    args = ap.parse_args()
    layout = Path(args.layout)
    lay = yaml.safe_load(open(layout, encoding="utf-8"))
    out_html = Path(args.html) if args.html else layout.with_name(layout.stem + "-card.html")
    out_html.write_text(render_html(lay), encoding="utf-8")
    print(f"html → {out_html}")
    if args.no_pdf:
        return 0
    pdf = Path(args.pdf).expanduser()
    pdf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [args.chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-margins",
           f"--print-to-pdf={pdf}", out_html.resolve().as_uri()]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if res.returncode != 0 or not pdf.exists():
        print(res.stderr[-800:])
        return 1
    print(f"pdf  → {pdf} ({pdf.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
