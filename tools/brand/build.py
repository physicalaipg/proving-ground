"""Build the 物理AI实验场 account kit, five registers: flat / cute (第二版) / cute-pro (第二版Pro) / lounge (第三版) / lounge-pro (第三版Pro). Usage: python3 build.py [outdir]
Deps: fontTools, uharfbuzz, cairosvg, Pillow; Noto CJK at /usr/share/fonts/opentype/noto/; fonts/ next to brand.py."""
import sys, os, hashlib
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import brand as B
out = sys.argv[1] if len(sys.argv) > 1 else "kit"
# v3.3: the two flat banners lead with the English name (英主中副); primary="zh" gives back the v3.2 banners
PRIMARY = "en"
flat = {
    "avatar-800": (B.svg(800, 800, B.mark_final(bg=B.PAL["pool"])), 800, 800),
    "banner-youtube-2560x1440": (B.banner_youtube2(typo="serif", primary=PRIMARY), 2560, 1440),
    "header-x-1500x500": (B.header_x2(typo="serif", primary=PRIMARY), 1500, 500),
}
LETTER = "M"
# 第二版: v2 seated (round eyes, ω mouth), byte-identical to the 09-29 v2 kit
yt_c, bb_c = B.banner_youtube_shiba(letter=LETTER); x_c, bx_c = B.header_x_shiba(letter=LETTER)
cute = {
    "avatar-800": (B.svg(800, 800, B.mark_shiba(bg=B.PAL["pool"], letter=LETTER)), 800, 800),
    "banner-youtube-2560x1440": (yt_c, 2560, 1440),
    "header-x-1500x500": (x_c, 1500, 500),
}
# 第二版Pro: v3 seated — the shiba smile, head cocked 8°
EXPR, TILT = "smile", -8
yt_cp, bb_cp = B.banner_youtube_shiba(letter=LETTER, expr=EXPR, tilt=TILT); x_cp, bx_cp = B.header_x_shiba(letter=LETTER, expr=EXPR, tilt=TILT)
cute_pro = {
    "avatar-800": (B.svg(800, 800, B.mark_shiba(bg=B.PAL["pool"], letter=LETTER, expr=EXPR, tilt=TILT)), 800, 800),
    "banner-youtube-2560x1440": (yt_cp, 2560, 1440),
    "header-x-1500x500": (x_cp, 1500, 500),
}
# 第三版: v2 贵妃躺 (side-lying, half-lidded), kept live
yt_l, bb_l = B.banner_youtube_lounge_v2(letter=LETTER); x_l, bx_l = B.header_x_lounge_v2(letter=LETTER)
lounge = {
    "avatar-800": (B.svg(800, 800, B.mark_lounge_v2(bg=B.PAL["pool"], letter=LETTER)), 800, 800),
    "banner-youtube-2560x1440": (yt_l, 2560, 1440),
    "header-x-1500x500": (x_l, 1500, 500),
}
# 第三版Pro: v3 仰躺 (belly-up, the shiba smile)
yt_p, bb_p = B.banner_youtube_lounge(letter=LETTER); x_p, bx_p = B.header_x_lounge(letter=LETTER)
lounge_pro = {
    "avatar-800": (B.svg(800, 800, B.mark_lounge(bg=B.PAL["pool"], letter=LETTER)), 800, 800),
    "banner-youtube-2560x1440": (yt_p, 2560, 1440),
    "header-x-1500x500": (x_p, 1500, 500),
}
REGS = (("flat", flat), ("cute", cute), ("cute-pro", cute_pro), ("lounge", lounge), ("lounge-pro", lounge_pro))
for reg, files in REGS:
    os.makedirs(f"{out}/{reg}", exist_ok=True)
    for name, (svg, w, h) in files.items():
        open(f"{out}/{reg}/{name}.svg", "w").write(svg)
        B.render(svg, f"{out}/{reg}/{name}.png", w, h)
# safe-zone checks
_, bb, _ = B.lockup2(*B.LOCKUP2["yt"][PRIMARY], primary=PRIMARY)
_, bx, _ = B.lockup2(*B.LOCKUP2["x"][PRIMARY], primary=PRIMARY)
for tag, b in (("flat-yt", bb), ("cute-yt", bb_c), ("cute-pro-yt", bb_cp), ("lounge-yt", bb_l), ("lounge-pro-yt", bb_p)):
    assert 507 <= b[0] and b[2] <= 2053 and 508 <= b[1] and b[3] <= 931, (tag, b)
for tag, b in (("flat-x", bx), ("cute-x", bx_c), ("cute-pro-x", bx_cp), ("lounge-x", bx_l), ("lounge-pro-x", bx_p)):
    assert b[0] >= 380 or b[3] <= 320, (tag, b)
print("flat yt", [round(v) for v in bb], "x", [round(v) for v in bx])
print("cute yt", [round(v) for v in bb_c], "x", [round(v) for v in bx_c])
print("cute-pro yt", [round(v) for v in bb_cp], "x", [round(v) for v in bx_cp])
print("lounge yt", [round(v) for v in bb_l], "x", [round(v) for v in bx_l])
print("lounge-pro yt", [round(v) for v in bb_p], "x", [round(v) for v in bx_p])
for reg, _ in REGS:
    for name in flat:
        p = f"{out}/{reg}/{name}.png"
        print(hashlib.sha256(open(p, "rb").read()).hexdigest()[:16], os.path.getsize(p), p)
