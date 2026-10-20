#!/usr/bin/env python3
"""开号备件出图（内部工单 §2）：头像 800×800、YouTube 横幅 2560×1440、X 头图 1500×500。

标识＝原创几何图形：方框（2×2 m 场地俯视）里一条折线路径连三个点，末点换色（到达的检查点）。
全部由本脚本的坐标画出，不引用任何图片素材；横幅上的字用开源字体（SIL OFL）渲染，字体文件不入仓。

用法（仓根）：
  .venv/bin/python tools/make_brand.py --font <NotoSansSC 可变字体 .ttf> [--out site/assets/brand] [--export ~/Desktop/pg-accounts-kit] [--verify <目录>]
  --verify  另出核对图（不入仓）：头像圆形裁切后缩到 40 px 贴在深、浅两种底上；横幅叠安全区框线
输出文件名固定：avatar-800.png、banner-youtube-2560x1440.png、header-x-1500x500.png
退出码：0 正常；1 尺寸或安全区核对不过；2 用法错误。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 配色：底色取中等明度，贴在白底和黑底上都分得开；主体白，末点琥珀
BG = (15, 118, 110)        # #0F766E
GRID = (28, 134, 126)      # 底纹网格线，比底色略亮
FG = (255, 255, 255)
ACCENT = (251, 191, 36)    # #FBBF24
SS = 4                     # 超采样倍数，画完缩回去抗锯齿

NAME_ZH = "物理AI实验场"
NAME_EN = "Physical AI Proving Ground"

# 安全区写成 (左, 上, 宽, 高)
YT_SIZE = (2560, 1440)
YT_SAFE = ((2560 - 1546) // 2, (1440 - 423) // 2, 1546, 423)   # YouTube 标注的全设备可见区，居中
X_SIZE = (1500, 500)
X_SAFE = (420, 80, 980, 340)   # 自留：上下各让 80（窄屏裁切）；左让 420（资料页头像压住头图左下角，位置是估的，以上传预览为准）、右让 100


def draw_mark(d: ImageDraw.ImageDraw, cx: float, cy: float, side: float) -> None:
    """以 (cx, cy) 为中心画标识，side＝方框外边长。线宽、点径都按 side 比例取。"""
    stroke = side * 0.095
    r = side * 0.085
    half = side / 2
    d.rounded_rectangle([cx - half, cy - half, cx + half, cy + half], radius=side * 0.12, outline=FG, width=round(stroke))
    inner = half - stroke - side * 0.13          # 点心到中心的最大偏移
    pts = [(cx - inner, cy + inner), (cx - inner * 0.1, cy - inner * 0.25), (cx + inner, cy - inner)]
    d.line(pts, fill=FG, width=round(stroke * 0.8), joint="curve")
    for i, (x, y) in enumerate(pts):
        rr = r * (1.25 if i == len(pts) - 1 else 1.0)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=ACCENT if i == len(pts) - 1 else FG)


def make_avatar() -> Image.Image:
    n = 800 * SS
    im = Image.new("RGB", (n, n), BG)
    draw_mark(ImageDraw.Draw(im), n / 2, n / 2, 460 * SS)
    return im.resize((800, 800), Image.LANCZOS)


def font(path: str, size: int, weight: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(path, size)
    f.set_variation_by_axes([weight])
    return f


def make_banner(size: tuple[int, int], safe: tuple[int, int, int, int], font_path: str) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """横幅：底纹网格＋在安全区内居中的「标识｜中文名／英文名」。返回图与内容外接框（未超采样坐标）。"""
    w, h = size
    im = Image.new("RGB", (w * SS, h * SS), BG)
    d = ImageDraw.Draw(im)
    step = round(h / 9) * SS
    for x in range(0, w * SS, step):
        d.line([(x, 0), (x, h * SS)], fill=GRID, width=SS * 2)
    for y in range(0, h * SS, step):
        d.line([(0, y), (w * SS, y)], fill=GRID, width=SS * 2)

    sx, sy, sw, sh = safe
    mark = sh * 0.78
    gap = mark * 0.30
    zh_size = round(sh * 0.40)
    while True:                                   # 中文名字号自适应：整块宽度不超安全区的 94%
        f_zh = font(font_path, zh_size * SS, 700)
        f_en = font(font_path, round(zh_size * 0.42) * SS, 500)
        zb = d.textbbox((0, 0), NAME_ZH, font=f_zh)
        eb = d.textbbox((0, 0), NAME_EN, font=f_en)
        text_w = max(zb[2] - zb[0], eb[2] - eb[0]) / SS
        if mark + gap + text_w <= sw * 0.94 or zh_size <= 20:
            break
        zh_size -= 2
    line_gap = zh_size * 0.22
    zh_h, en_h = (zb[3] - zb[1]) / SS, (eb[3] - eb[1]) / SS
    block_w = mark + gap + text_w
    block_h = max(mark, zh_h + line_gap + en_h)
    x0, y0 = sx + (sw - block_w) / 2, sy + (sh - block_h) / 2
    cy = sy + sh / 2
    # 底纹在内容块后面挖掉，字和标识不压网格线
    pad = mark * 0.18
    d.rectangle([(x0 - pad) * SS, (y0 - pad) * SS, (x0 + block_w + pad) * SS, (y0 + block_h + pad) * SS], fill=BG)
    draw_mark(d, (x0 + mark / 2) * SS, cy * SS, mark * SS)
    tx = x0 + mark + gap
    ty = cy - (zh_h + line_gap + en_h) / 2
    d.text((tx * SS - zb[0], ty * SS - zb[1]), NAME_ZH, font=f_zh, fill=FG)
    d.text((tx * SS - eb[0], (ty + zh_h + line_gap) * SS - eb[1]), NAME_EN, font=f_en, fill=FG)
    box = (round(x0), round(y0), round(x0 + block_w), round(y0 + block_h))
    return im.resize((w, h), Image.LANCZOS), box


def inside(box: tuple[int, int, int, int], safe: tuple[int, int, int, int]) -> bool:
    sx, sy, sw, sh = safe
    return box[0] >= sx and box[1] >= sy and box[2] <= sx + sw and box[3] <= sy + sh


def circle_crop(im: Image.Image, px: int, bg: tuple[int, int, int], canvas: int = 120, zoom: int = 6) -> Image.Image:
    """头像按圆裁切、缩到 px，贴在 bg 底上，再整数倍放大（最近邻）便于肉眼核对。"""
    n = im.size[0]
    mask = Image.new("L", (n * 2, n * 2), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, n * 2 - 1, n * 2 - 1], fill=255)
    mask = mask.resize((n, n), Image.LANCZOS)
    rgba = im.convert("RGBA")
    rgba.putalpha(mask)
    small = rgba.resize((px, px), Image.LANCZOS)
    base = Image.new("RGB", (canvas, canvas), bg)
    base.paste(small, ((canvas - px) // 2, (canvas - px) // 2), small)
    return base.resize((canvas * zoom, canvas * zoom), Image.NEAREST)


def overlay_safe(im: Image.Image, safe: tuple[int, int, int, int], box: tuple[int, int, int, int]) -> Image.Image:
    out = im.copy()
    d = ImageDraw.Draw(out)
    w = im.size[0]
    sx, sy, sw, sh = safe
    d.rectangle([sx, sy, sx + sw, sy + sh], outline=(255, 0, 0), width=max(2, w // 500))
    d.rectangle(list(box), outline=(255, 255, 0), width=max(2, w // 800))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="开号备件出图（头像／YouTube 横幅／X 头图）")
    ap.add_argument("--font", required=True, help="开源可变字体 .ttf（含中文；字体文件不入仓）")
    ap.add_argument("--out", default="site/assets/brand")
    ap.add_argument("--export", default=None, help="另拷一份到仓外目录（主理人取件处）")
    ap.add_argument("--verify", default=None, help="核对图输出目录（不入仓）")
    a = ap.parse_args()
    if not Path(a.font).is_file():
        print(f"✘ 字体不存在：{a.font}")
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    avatar = make_avatar()
    yt, yt_box = make_banner(YT_SIZE, YT_SAFE, a.font)
    xh, x_box = make_banner(X_SIZE, X_SAFE, a.font)
    files = {"avatar-800.png": avatar, "banner-youtube-2560x1440.png": yt, "header-x-1500x500.png": xh}
    for name, im in files.items():
        im.save(out / name, optimize=True)

    bad = 0
    for name, want in (("avatar-800.png", (800, 800)), ("banner-youtube-2560x1440.png", YT_SIZE), ("header-x-1500x500.png", X_SIZE)):
        got = Image.open(out / name).size
        ok = got == want
        bad += not ok
        print(f"{'✔' if ok else '✘'} {name}  {got[0]}×{got[1]}  {(out / name).stat().st_size} 字节")
    for label, box, safe in (("YouTube", yt_box, YT_SAFE), ("X", x_box, X_SAFE)):
        ok = inside(box, safe)
        bad += not ok
        print(f"{'✔' if ok else '✘'} {label} 内容外接框 {box[2] - box[0]}×{box[3] - box[1]}（左上角 {box[0]},{box[1]}）在安全区 {safe[2]}×{safe[3]}（左上角 {safe[0]},{safe[1]}）内：{ok}")
    # 头像主体外接圆半径（方框半对角线）须小于圆形裁切半径 400
    half_diag = 460 / 2 * 2 ** 0.5
    ok = half_diag < 400
    bad += not ok
    print(f"{'✔' if ok else '✘'} 头像主体半对角线 {half_diag:.0f} px < 圆形裁切半径 400 px：{ok}")

    if a.verify:
        v = Path(a.verify)
        v.mkdir(parents=True, exist_ok=True)
        sheet = Image.new("RGB", (720 * 2, 720), (128, 128, 128))
        sheet.paste(circle_crop(avatar, 40, (255, 255, 255)), (0, 0))
        sheet.paste(circle_crop(avatar, 40, (15, 15, 15)), (720, 0))
        sheet.save(v / "avatar-40px-light-dark.png")
        overlay_safe(yt, YT_SAFE, yt_box).resize((1280, 720), Image.LANCZOS).save(v / "banner-youtube-safe.png")
        overlay_safe(xh, X_SAFE, x_box).save(v / "header-x-safe.png")
        print(f"→ 核对图 3 张在 {v}")
    if a.export:
        e = Path(a.export).expanduser()
        e.mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copyfile(out / name, e / name)
        print(f"→ 已拷 {len(files)} 件到 {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
