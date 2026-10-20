"""物理AI实验场 · brand kit generator.
Text is converted to outlines (no font dependency in the SVG output).
"""
import math, os
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
import cairosvg

NOTO = "/usr/share/fonts/opentype/noto/"


class Face:
    def __init__(self, path, index=0):
        self.tt = TTFont(path, fontNumber=index)
        self.gs = self.tt.getGlyphSet()
        self.upem = self.tt["head"].unitsPerEm
        with open(path, "rb") as f:
            data = f.read()
        self.hbfont = hb.Font(hb.Face(data, index))
        self.hbfont.scale = (self.upem, self.upem)
        self.order = self.tt.getGlyphOrder()

    def shape(self, text, features=None):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hbfont, buf, features or {})
        return list(zip(buf.glyph_infos, buf.glyph_positions))

    def path(self, text, size, x, y, tracking=0.0):
        """Return (svg path d, bounds(xmin,ymin,xmax,ymax), advance width)."""
        s = size / self.upem
        pen, bpen = SVGPathPen(self.gs), BoundsPen(self.gs)
        cx = x
        for info, pos in self.shape(text):
            g = self.order[info.codepoint]
            t = (s, 0, 0, -s, cx + pos.x_offset * s, y - pos.y_offset * s)
            self.gs[g].draw(TransformPen(pen, t))
            self.gs[g].draw(TransformPen(bpen, t))
            cx += pos.x_advance * s + tracking
        return pen.getCommands(), bpen.bounds, cx - x


_faces = {}


def face(style):
    """style: serif-black | serif-semibold | serif-medium | serif-regular | sans-bold | sans-medium | sans-regular"""
    if style not in _faces:
        fam, wt = style.split("-")
        fn = {"serif": "NotoSerifCJK", "sans": "NotoSansCJK"}[fam]
        wt = {"black": "Black", "bold": "Bold", "semibold": "SemiBold", "medium": "Medium", "regular": "Regular"}[wt]
        _faces[style] = Face(f"{NOTO}{fn}-{wt}.ttc", index=2)  # 2 = SC
    return _faces[style]


# ---------------------------------------------------------------- palette
PAL = {
    "pool": "#0F2F32",   # 深潭 · background
    "paper": "#F4EFE4",  # 暖白 · ground / text
    "mist": "#8FD9CF",   # 雾青 · simulation rings
    "amber": "#FFB020",  # 琥珀 · the real run
}


# ---------------------------------------------------------------- the mark
def bez(p0, p1, p2, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def mark(ground="ruler", rings="mist", n_rings=3, bg=None, pal=PAL, ring_w=13):
    """Mark in an 800x800 design space. bbox ~ x 120-680, y 187-620.
    Meaning: wireframe rings (simulation trials) glide in and land as one
    solid amber disc (the real-robot run) on a measured ground."""
    p = pal
    out = []
    if bg:
        out.append(f'<rect width="800" height="800" fill="{bg}"/>')
    # ground
    if ground == "ruler":
        gy = 580
        out.append(f'<path d="M120 {gy}H680" stroke="{p["paper"]}" stroke-width="22" stroke-linecap="round" fill="none"/>')
        ticks = []
        xs = list(range(150, 651, 50))
        for i, x in enumerate(xs):
            ln = 30 if i % 2 == 0 else 17
            ticks.append(f'M{x} {gy+11}v{ln}')
        out.append(f'<path d="{" ".join(ticks)}" stroke="{p["paper"]}" stroke-width="10" stroke-linecap="round" fill="none" opacity="0.85"/>')
        disc_cy = gy - 11 - 68
    elif ground == "checker":
        top, cell, cols, rows = 560, 40, 14, 2
        cells = []
        for r in range(rows):
            for c in range(cols):
                if (r + c) % 2 == 0:
                    cells.append(f'<rect x="{120 + c*cell}" y="{top + r*cell}" width="{cell}" height="{cell}"/>')
        out.append(f'<g fill="{p["paper"]}">{"".join(cells)}</g>')
        disc_cy = top - 68
    elif ground == "line":
        gy = 580
        out.append(f'<path d="M120 {gy}H680" stroke="{p["paper"]}" stroke-width="22" stroke-linecap="round" fill="none"/>')
        disc_cy = gy - 11 - 68
    # trail rings
    P0, P1, P2 = (150, 360), (290, 40), (560, disc_cy)
    if n_rings == 3:
        ts, rs, ops = [0.04, 0.42, 0.76], [30, 42, 54], [0.38, 0.58, 0.82]
    else:
        ts, rs, ops = [0.02, 0.30, 0.56, 0.80], [26, 34, 44, 54], [0.32, 0.48, 0.64, 0.85]
    rc = p["mist"] if rings == "mist" else p["paper"]
    circ = []
    for t, r, o in zip(ts, rs, ops):
        x, y = bez(P0, P1, P2, t)
        circ.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" opacity="{o}"/>')
    out.append(f'<g fill="none" stroke="{rc}" stroke-width="{ring_w}">{"".join(circ)}</g>')
    # the real run
    out.append(f'<circle cx="560" cy="{disc_cy}" r="68" fill="{p["amber"]}"/>')
    return "\n".join(out)


MARK_BBOX = (120, 187, 680, 620)  # x0,y0,x1,y1 in design space (ruler variant)


def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n{body}\n</svg>'


def avatar(**kw):
    kw.setdefault("bg", PAL["pool"])
    return svg(800, 800, mark(**kw))


# ---------------------------------------------------------------- lockups
NAME_ZH, NAME_EN = "物理AI实验场", "Physical AI Proving Ground"
TAGLINE_ZH = "仿真为主，真机为锚"
TAGLINE_EN = "Simulation first, anchored by real-robot runs"  # second sentence of the public English bio, full stop dropped


def text_block(x, y, zh_size, en_size, tag_size, typo="serif", pal=PAL, gap1=None, gap2=None, tagline=True, primary="zh"):
    """Left-aligned bilingual block. Returns (svg, bbox).
    primary="en" (v3.3): English name leads at zh_size, 中文名 second at en_size, tagline in English."""
    p = pal
    if typo == "serif":
        f_zh, f_en, f_tag = face("serif-black"), face("serif-semibold"), face("serif-regular")
    else:
        f_zh, f_en, f_tag = face("sans-bold"), face("sans-medium"), face("sans-regular")
    gap1 = gap1 if gap1 is not None else en_size * 0.55
    gap2 = gap2 if gap2 is not None else tag_size * 0.9
    parts, boxes = [], []
    if primary == "en":
        # line 1 · English (descenders hang below the baseline, so the gap is measured from them)
        d, b, _ = f_zh.path(NAME_EN, zh_size, x, y, tracking=zh_size * 0.01)
        parts.append(f'<path d="{d}" fill="{p["paper"]}"/>'); boxes.append(b)
        # line 2 · 中文名
        y2 = b[3] + gap1 + en_size * 0.86
        d, b, _ = f_en.path(NAME_ZH, en_size, x, y2, tracking=en_size * 0.04)
        parts.append(f'<path d="{d}" fill="{p["paper"]}"/>'); boxes.append(b)
        # line 3 · tagline
        if tagline:
            y3 = b[3] + gap2 + tag_size * 0.72
            d, b, adv = f_tag.path(TAGLINE_EN, tag_size, x, y3, tracking=tag_size * 0.01)
            parts.append(f'<path d="{d}" fill="{p["paper"]}" opacity="0.8"/>'); boxes.append(b)
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        return "\n".join(parts), (x0, y0, x1, y1)
    # line 1 · 中文名
    d, b, _ = f_zh.path(NAME_ZH, zh_size, x, y, tracking=zh_size * 0.02)
    parts.append(f'<path d="{d}" fill="{p["paper"]}"/>'); boxes.append(b)
    # line 2 · English
    y2 = y + gap1 + en_size * 0.72
    d, b, _ = f_en.path(NAME_EN, en_size, x, y2, tracking=en_size * 0.01)
    parts.append(f'<path d="{d}" fill="{p["paper"]}"/>'); boxes.append(b)
    # line 3 · tagline
    if tagline:
        y3 = y2 + gap2 + tag_size * 0.85
        d, b, adv = f_tag.path(TAGLINE_ZH, tag_size, x, y3)
        parts.append(f'<path d="{d}" fill="{p["paper"]}" opacity="0.8"/>'); boxes.append(b)
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    return "\n".join(parts), (x0, y0, x1, y1)


def lockup(cx, cy, s, zh, en, tag, gap, typo="serif", pal=PAL, ground="ruler", rings="mist", n_rings=3):
    """Mark left, text right, centred on (cx, cy). Returns svg string."""
    m = mark(ground=ground, rings=rings, n_rings=n_rings, pal=pal)
    bx0, by0, bx1, by1 = MARK_BBOX
    mw, mh = (bx1 - bx0) * s, (by1 - by0) * s
    # measure text at origin
    _, tb = text_block(0, 0, zh, en, tag, typo=typo, pal=pal)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    total = mw + gap + tw
    mx = cx - total / 2                       # mark left edge
    my = cy - mh / 2                          # mark top edge
    tx = mx + mw + gap - tb[0]                # text left
    ty = cy - th / 2 - tb[1]                  # baseline of line 1
    g = f'<g transform="translate({mx - bx0*s:.2f},{my - by0*s:.2f}) scale({s})">{m}</g>'
    t, _ = text_block(tx, ty, zh, en, tag, typo=typo, pal=pal)
    return g + "\n" + t, (mx, my, mx + total, my + max(mh, th))


def ruler_band(w, y, pal=PAL, step=50, opacity=0.13, x0=0, x1=None):
    """Faint measuring baseline across the full width (decorative, may crop)."""
    x1 = w if x1 is None else x1
    d = [f'M{x0} {y}H{x1}']
    ticks = []
    i = 0
    x = x0 + step
    while x < x1:
        ticks.append(f'M{x} {y+4}v{16 if i % 2 == 0 else 9}')
        x += step; i += 1
    return (f'<g stroke="{pal["paper"]}" stroke-linecap="round" fill="none" opacity="{opacity}">'
            f'<path d="{" ".join(d)}" stroke-width="3"/><path d="{" ".join(ticks)}" stroke-width="3"/></g>')


def banner_youtube(typo="serif", pal=PAL, band=True, **mk):
    W, H = 2560, 1440
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    lk, bb = lockup(1280, 720, 0.56, 124, 54, 30, 70, typo=typo, pal=pal, **mk)
    if band:
        gy = bb[3] - (620 - 580) * 0.56 - 11 * 0.56 + 6  # align with the mark's ground line
        body.append(ruler_band(W, gy, pal, step=56, opacity=0.10))
    body.append(lk)
    return svg(W, H, "\n".join(body))


def header_x(typo="serif", pal=PAL, band=True, **mk):
    W, H = 1500, 500
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    lk, bb = lockup(790, 232, 0.36, 80, 35, 20, 44, typo=typo, pal=pal, **mk)
    if band:
        gy = bb[3] - (620 - 580) * 0.36 - 11 * 0.36 + 4
        body.append(ruler_band(W, gy, pal, step=50, opacity=0.10))
    body.append(lk)
    return svg(W, H, "\n".join(body))


def render(svg_str, png_path, w=None, h=None):
    cairosvg.svg2png(bytestring=svg_str.encode(), write_to=png_path, output_width=w, output_height=h)


if __name__ == "__main__":
    os.makedirs("out", exist_ok=True)
    render(avatar(), "out/avatar.png")


TRAIL_P0 = (135, 180)
# ---------------------------------------------------------------- mark v2 · 落地 on a sim grid floor
def mark2(bg=None, pal=PAL, floor="paper", trail="dots", p1=(330, 230), n_dots=7,
          vp=(400, 310), ybot=632, ytop=462, xl=140, xr=660, disc=(470, 540), r=62,
          shadow=False, halo=True):
    """The floor is a wireframe perspective grid (the simulator's ground plane);
    a trail of simulated attempts glides in and lands as one solid amber disc (the real run)."""
    p = pal
    out = []
    if bg:
        out.append(f'<rect width="800" height="800" fill="{bg}"/>')
    fc = p["paper"] if floor == "paper" else p["mist"]
    def xat(xb, y):  # x on the line from (xb, ybot) toward vp at height y
        t = (ybot - y) / (ybot - vp[1])
        return xb + (vp[0] - xb) * t
    L, R = xat(xl, ytop), xat(xr, ytop)
    # outer trapezoid
    out.append(f'<path d="M{xl} {ybot}L{L:.1f} {ytop}H{R:.1f}L{xr} {ybot}Z" fill="none" stroke="{fc}" stroke-width="18" stroke-linejoin="round"/>')
    # inner grid
    inner = []
    for xb in (xl + (xr - xl) * 0.25, 400, xl + (xr - xl) * 0.75):
        inner.append(f'M{xb:.1f} {ybot}L{xat(xb, ytop):.1f} {ytop}')
    for y in (ybot - (ybot - ytop) * 0.40, ybot - (ybot - ytop) * 0.70):
        inner.append(f'M{xat(xl, y):.1f} {y:.1f}H{xat(xr, y):.1f}')
    out.append(f'<path d="{" ".join(inner)}" fill="none" stroke="{fc}" stroke-width="8" stroke-linecap="round" opacity="0.55"/>')
    # trail
    P0, P1, P2 = TRAIL_P0, p1, disc
    if trail == "dots":
        dots = []
        for i in range(n_dots):
            t = 0.02 + 0.74 * i / (n_dots - 1)
            x, y = bez(P0, P1, P2, t)
            rr = 6 + 16 * i / (n_dots - 1)
            o = 0.45 + 0.5 * i / (n_dots - 1)
            dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr:.1f}" opacity="{o:.2f}"/>')
        out.append(f'<g fill="{p["mist"]}">{"".join(dots)}</g>')
    elif trail == "rings":
        rings = []
        for t, rr, o in zip([0.05, 0.40, 0.70], [26, 36, 46], [0.4, 0.6, 0.85]):
            x, y = bez(P0, P1, P2, t)
            rings.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr}" opacity="{o}"/>')
        out.append(f'<g fill="none" stroke="{p["mist"]}" stroke-width="12">{"".join(rings)}</g>')
    elif trail == "dotted":
        # dotted bezier ending short of the disc
        out.append(f'<path d="M{P0[0]} {P0[1]}Q{P1[0]} {P1[1]} {P2[0]} {P2[1]}" fill="none" stroke="{p["mist"]}" stroke-width="13" stroke-linecap="round" stroke-dasharray="0.1 30" opacity="0.9"/>')
    # the real run
    if shadow:
        out.append(f'<ellipse cx="{disc[0]}" cy="{disc[1]+r+10}" rx="{r*1.05:.0f}" ry="{r*0.22:.0f}" fill="{fc}" opacity="0.25"/>')
    if halo:
        out.append(f'<circle cx="{disc[0]}" cy="{disc[1]}" r="{r+13}" fill="{bg or p["pool"]}"/>')
    out.append(f'<circle cx="{disc[0]}" cy="{disc[1]}" r="{r}" fill="{p["amber"]}"/>')
    return "\n".join(out)


# ---------------------------------------------------------------- final mark params
MK = dict(floor="paper", trail="dots", p1=(330, 190), n_dots=7,
          vp=(400, 280), ybot=622, ytop=440, xl=125, xr=675, disc=(475, 528), r=66)

def mark_final(bg=None, pal=PAL, **over):
    kw = dict(MK); kw.update(over)
    # patch trail start via closure over module-level P0 used in mark2
    return mark2(bg=bg, pal=pal, **kw)


def mark_bbox(kw=MK):
    xl, xr, ybot = kw["xl"], kw["xr"], kw["ybot"]
    return (xl - 8, TRAIL_P0[1] - 8, xr + 8, ybot + 8)


# ---------------------------------------------------------------- lockups (v2)
def lockup2(cx, cy, s, zh, en, tag, gap, typo="serif", pal=PAL, tagline=True, primary="zh"):
    m = mark_final(pal=pal)
    bx0, by0, bx1, by1 = mark_bbox()
    mw, mh = (bx1 - bx0) * s, (by1 - by0) * s
    _, tb = text_block(0, 0, zh, en, tag, typo=typo, pal=pal, tagline=tagline, primary=primary)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    total = mw + gap + tw
    mx = cx - total / 2
    my = cy - mh / 2
    tx = mx + mw + gap - tb[0]
    ty = cy - th / 2 - tb[1]
    g = f'<g transform="translate({mx - bx0*s:.2f},{my - by0*s:.2f}) scale({s})">{m}</g>'
    t, _ = text_block(tx, ty, zh, en, tag, typo=typo, pal=pal, tagline=tagline, primary=primary)
    floor_y = my + (MK["ybot"] - by0) * s   # y of the floor's bottom edge on canvas
    return g + "\n" + t, (mx, my, mx + total, my + max(mh, th)), floor_y


# lockup2 arguments (cx, cy, s, line 1, line 2, tagline, gap) per banner and primary language; "en" = v3.3
LOCKUP2 = {
    "yt": {"zh": (1280, 720, 0.56, 124, 54, 34, 76), "en": (1280, 720, 0.56, 72, 54, 34, 72)},
    "x": {"zh": (812, 226, 0.36, 80, 35, 22, 48), "en": (812, 226, 0.36, 47, 35, 22, 46)},
}


def banner_youtube2(typo="serif", pal=PAL, band=True, tagline=True, primary="zh"):
    W, H = 2560, 1440
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    lk, bb, fy = lockup2(*LOCKUP2["yt"][primary], typo=typo, pal=pal, tagline=tagline, primary=primary)
    if band:
        body.append(ruler_band(W, fy, pal, step=56, opacity=0.14))
    body.append(lk)
    return svg(W, H, "\n".join(body))


def header_x2(typo="serif", pal=PAL, band=True, tagline=True, primary="zh"):
    W, H = 1500, 500
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    lk, bb, fy = lockup2(*LOCKUP2["x"][primary], typo=typo, pal=pal, tagline=tagline, primary=primary)
    if band:
        body.append(ruler_band(W, fy, pal, step=50, opacity=0.14))
    body.append(lk)
    return svg(W, H, "\n".join(body))


# ---------------------------------------------------------------- alternates (avatar only)
def mark_gate(bg=PAL["pool"], pal=PAL):
    """过门: simulated attempts approach from the left, pass the hard gate, one solid run beyond it."""
    p = pal; out = [f'<rect width="800" height="800" fill="{bg}"/>']
    gy = 600
    out.append(f'<path d="M110 {gy}H690" stroke="{p["paper"]}" stroke-width="20" stroke-linecap="round" fill="none"/>')
    out.append(f'<path d="M350 {gy-10}V300 M450 {gy-10}V300" stroke="{p["paper"]}" stroke-width="24" stroke-linecap="round" fill="none"/>')
    out.append(f'<path d="M350 300H450" stroke="{p["paper"]}" stroke-width="24" stroke-linecap="round" fill="none" opacity="0.55"/>')
    P0, P1, P2 = (120, 430), (300, 480), (560, 470)
    dots = []
    for i in range(6):
        t = 0.02 + 0.62 * i / 5
        x, y = bez(P0, P1, P2, t)
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{7 + 14*i/5:.1f}" opacity="{0.45+0.5*i/5:.2f}"/>')
    out.append(f'<g fill="{p["mist"]}">{"".join(dots)}</g>')
    out.append(f'<circle cx="590" cy="480" r="62" fill="{p["amber"]}"/>')
    return "\n".join(out)


def mark_loop(bg=PAL["pool"], pal=PAL):
    """环: a test track from above; dashed laps are simulation, the solid amber lap is the real run."""
    p = pal; out = [f'<rect width="800" height="800" fill="{bg}"/>']
    # stadium path: start at right-middle, go clockwise
    x0, x1, y0, y1, r = 150, 650, 260, 560, 150
    d = (f'M{x1} {y0+r} A{r} {r} 0 0 1 {x1-r} {y1} H{x0+r} A{r} {r} 0 0 1 {x0} {y1-r} '
         f'V{y0+r} A{r} {r} 0 0 1 {x0+r} {y0} H{x1-r} A{r} {r} 0 0 1 {x1} {y0+r}')
    out.append(f'<path d="{d}" fill="none" stroke="{p["mist"]}" stroke-width="18" stroke-linecap="round" stroke-dasharray="4 44" opacity="0.85"/>')
    # solid amber lap segment: right end, from top-right along the arc to the right-middle
    out.append(f'<path d="M{x1-r} {y0} A{r} {r} 0 0 1 {x1} {y0+r}" fill="none" stroke="{p["amber"]}" stroke-width="30" stroke-linecap="round"/>')
    out.append(f'<circle cx="{x1}" cy="{y0+r}" r="60" fill="{p["amber"]}"/>')
    # start/finish line
    out.append(f'<path d="M{x1-r} {y0-30}V{y0+30}" stroke="{p["paper"]}" stroke-width="20" stroke-linecap="round"/>')
    return "\n".join(out)


# ================================================================ 萌版 · cartoon register
INK = "#0A1C1E"
BLUSH = "#FF7A5A"


def face_file(path):
    key = "file:" + path
    if key not in _faces:
        _faces[key] = Face(path, 0)
    return _faces[key]


def mark_cute(bg=None, pal=PAL, style="sticker", ghosts=True, puffs=True,
              vp=(400, 280), ybot=622, ytop=440, xl=125, xr=675, cx=482, cy=442, r=132):
    """The amber disc of the flat mark grows a face and wheels: 小落（the one real run）.
    Dashed mist ghosts are the simulated attempts gliding in."""
    p = pal
    out = []
    if bg:
        out.append(f'<rect width="800" height="800" fill="{bg}"/>')
    fc = p["paper"]
    def xat(xb, y):
        t = (ybot - y) / (ybot - vp[1]); return xb + (vp[0] - xb) * t
    L, R = xat(xl, ytop), xat(xr, ytop)
    out.append(f'<path d="M{xl} {ybot}L{L:.1f} {ytop}H{R:.1f}L{xr} {ybot}Z" fill="none" stroke="{fc}" stroke-width="18" stroke-linejoin="round"/>')
    inner = []
    for xb in (xl + (xr - xl) * 0.25, 400, xl + (xr - xl) * 0.75):
        inner.append(f'M{xb:.1f} {ybot}L{xat(xb, ytop):.1f} {ytop}')
    for y in (ybot - (ybot - ytop) * 0.40, ybot - (ybot - ytop) * 0.70):
        inner.append(f'M{xat(xl, y):.1f} {y:.1f}H{xat(xr, y):.1f}')
    out.append(f'<path d="{" ".join(inner)}" fill="none" stroke="{fc}" stroke-width="8" stroke-linecap="round" opacity="0.55"/>')
    # ghosts (simulated attempts)
    P0, P1, P2 = (135, 175), (330, 185), (cx, cy)
    if ghosts:
        g = []
        for t, rr, o in [(0.05, 26, 0.45), (0.34, 38, 0.62), (0.60, 52, 0.85)]:
            x, y = bez(P0, P1, P2, t)
            g.append(f'<g opacity="{o}" transform="translate({x:.1f},{y:.1f})">'
                     f'<circle r="{rr}" fill="none" stroke="{p["mist"]}" stroke-width="7" stroke-dasharray="{rr*0.55:.0f} {rr*0.42:.0f}" stroke-linecap="round"/>'
                     f'<circle cx="{-rr*0.32:.1f}" cy="{-rr*0.12:.1f}" r="{rr*0.13:.1f}" fill="{p["mist"]}"/>'
                     f'<circle cx="{rr*0.28:.1f}" cy="{-rr*0.12:.1f}" r="{rr*0.13:.1f}" fill="{p["mist"]}"/>'
                     f'<path d="M{-rr*0.22:.1f} {rr*0.28:.1f}q{rr*0.22:.1f} {rr*0.22:.1f} {rr*0.44:.1f} 0" fill="none" stroke="{p["mist"]}" stroke-width="{max(4, rr*0.11):.1f}" stroke-linecap="round"/>'
                     f'</g>')
        out.append("".join(g))
    # the character
    ol = p["paper"] if style == "sticker" else INK   # outline colour
    ow = 14 if style == "sticker" else 11
    ch = [f'<g transform="translate({cx},{cy})">']
    # antenna
    ch.append(f'<path d="M0 {-r+4}V{-r-52}" stroke="{ol}" stroke-width="{ow}" stroke-linecap="round" fill="none"/>')
    ch.append(f'<circle cx="0" cy="{-r-62}" r="17" fill="{p["mist"]}" stroke="{ol}" stroke-width="{ow-4}"/>')
    # wheels (behind body)
    for wx in (-80, 80):
        ch.append(f'<circle cx="{wx}" cy="{r-8}" r="32" fill="{INK}" stroke="{ol}" stroke-width="{ow-4}"/>')
        ch.append(f'<circle cx="{wx}" cy="{r-8}" r="11" fill="{p["paper"]}" opacity="0.9"/>')
    # body
    ch.append(f'<circle r="{r}" fill="{p["amber"]}" stroke="{ol}" stroke-width="{ow}"/>')
    # cheeks
    ch.append(f'<ellipse cx="-94" cy="30" rx="21" ry="13" fill="{BLUSH}" opacity="0.6"/>')
    ch.append(f'<ellipse cx="94" cy="30" rx="21" ry="13" fill="{BLUSH}" opacity="0.6"/>')
    # eyes (looking up-left, toward the incoming ghosts)
    for ex in (-46, 44):
        ch.append(f'<ellipse cx="{ex}" cy="-16" rx="30" ry="36" fill="#FFFFFF" stroke="{INK}" stroke-width="7"/>')
        ch.append(f'<circle cx="{ex-8}" cy="-22" r="16" fill="{INK}"/>')
        ch.append(f'<circle cx="{ex-13}" cy="-29" r="6" fill="#FFFFFF"/>')
    # mouth
    ch.append(f'<path d="M-20 42Q0 64 20 42" fill="none" stroke="{INK}" stroke-width="8" stroke-linecap="round"/>')
    ch.append('</g>')
    out.append("".join(ch))
    if puffs:  # just landed
        out.append(f'<g stroke="{p["paper"]}" stroke-width="9" stroke-linecap="round" fill="none" opacity="0.9">'
                   f'<path d="M{cx-186} {cy+110}l-20 -12 M{cx-194} {cy+138}l-24 0 M{cx+186} {cy+110}l20 -12 M{cx+194} {cy+138}l24 0"/></g>')
    return "\n".join(out)


CUTE_BBOX = (117, 95, 683, 630)


def text_block_cute(x, y, zh_size, en_size, tag_size, pal=PAL, tagline=True):
    f_zh = face_file("fonts/ZCOOLKuaiLe-Regular.ttf")
    f_en = face_file("fonts/Fredoka-SemiBold.ttf")
    f_tag = face_file("fonts/ZCOOLKuaiLe-Regular.ttf")
    p = pal; parts, boxes = [], []
    d, b, _ = f_zh.path("物理AI实验场", zh_size, x, y, tracking=zh_size * 0.02)
    parts.append(f'<path d="{d}" fill="{p["paper"]}"/>'); boxes.append(b)
    y2 = y + en_size * 0.55 + en_size * 0.72
    d, b, _ = f_en.path("Physical AI Proving Ground", en_size, x, y2, tracking=en_size * 0.01)
    parts.append(f'<path d="{d}" fill="{p["paper"]}"/>'); boxes.append(b)
    if tagline:
        y3 = y2 + tag_size * 0.9 + tag_size * 0.85
        d, b, _ = f_tag.path("仿真为主，真机为锚", tag_size, x, y3, tracking=tag_size * 0.04)
        parts.append(f'<path d="{d}" fill="{p["paper"]}" opacity="0.8"/>'); boxes.append(b)
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    return "\n".join(parts), (x0, y0, x1, y1)


def lockup_cute(cx, cy, s, zh, en, tag, gap, pal=PAL, tagline=True):
    m = mark_cute(pal=pal)
    bx0, by0, bx1, by1 = CUTE_BBOX
    mw, mh = (bx1 - bx0) * s, (by1 - by0) * s
    _, tb = text_block_cute(0, 0, zh, en, tag, pal=pal, tagline=tagline)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    total = mw + gap + tw
    mx = cx - total / 2; my = cy - mh / 2
    tx = mx + mw + gap - tb[0]; ty = cy - th / 2 - tb[1]
    g = f'<g transform="translate({mx - bx0*s:.2f},{my - by0*s:.2f}) scale({s})">{m}</g>'
    t, _ = text_block_cute(tx, ty, zh, en, tag, pal=pal, tagline=tagline)
    floor_y = my + (622 - by0) * s
    return g + "\n" + t, (mx, my, mx + total, my + max(mh, th)), floor_y


def banner_youtube_cute(pal=PAL, tagline=True):
    W, H = 2560, 1440
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    lk, bb, fy = lockup_cute(1280, 720, 0.52, 128, 56, 36, 70, pal=pal, tagline=tagline)
    body.append(ruler_band(W, fy, pal, step=56, opacity=0.14)); body.append(lk)
    return svg(W, H, "\n".join(body)), bb


def header_x_cute(pal=PAL, tagline=True):
    W, H = 1500, 500
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    lk, bb, fy = lockup_cute(812, 226, 0.34, 82, 36, 23, 44, pal=pal, tagline=tagline)
    body.append(ruler_band(W, fy, pal, step=50, opacity=0.14)); body.append(lk)
    return svg(W, H, "\n".join(body)), bb


# ================================================================ 萌版 v2 · 柴犬「小T／小M」
def _ghost_shiba(x, y, rr, o, p):
    """dashed shiba-head outline: the simulated attempts."""
    ear = rr * 0.62
    return (f'<g opacity="{o}" transform="translate({x:.1f},{y:.1f})" fill="none" stroke="{p["mist"]}" stroke-width="{max(5, rr*0.14):.1f}" stroke-linecap="round" stroke-linejoin="round">'
            f'<circle r="{rr}" stroke-dasharray="{rr*0.5:.0f} {rr*0.38:.0f}"/>'
            f'<path d="M{-rr*0.86:.1f} {-rr*0.5:.1f}L{-rr*0.78:.1f} {-rr-ear*0.55:.1f}L{-rr*0.2:.1f} {-rr*0.95:.1f}" stroke-dasharray="{rr*0.4:.0f} {rr*0.3:.0f}"/>'
            f'<path d="M{rr*0.86:.1f} {-rr*0.5:.1f}L{rr*0.78:.1f} {-rr-ear*0.55:.1f}L{rr*0.2:.1f} {-rr*0.95:.1f}" stroke-dasharray="{rr*0.4:.0f} {rr*0.3:.0f}"/>'
            f'<circle cx="{-rr*0.34:.1f}" cy="{-rr*0.12:.1f}" r="{rr*0.11:.1f}" fill="{p["mist"]}" stroke="none"/>'
            f'<circle cx="{rr*0.34:.1f}" cy="{-rr*0.12:.1f}" r="{rr*0.11:.1f}" fill="{p["mist"]}" stroke="none"/>'
            f'<circle cx="0" cy="{rr*0.28:.1f}" r="{rr*0.1:.1f}" fill="{p["mist"]}" stroke="none"/>'
            f'</g>')


def mark_shiba(bg=None, pal=PAL, letter="T", ghosts=True, wag=True, expr="alert", tilt=0,
               vp=(400, 280), ybot=622, ytop=440, xl=125, xr=675, cx=482, cy=412, r=126):
    p = pal
    out = []
    if bg:
        out.append(f'<rect width="800" height="800" fill="{bg}"/>')
    fc = p["paper"]
    def xat(xb, y):
        t = (ybot - y) / (ybot - vp[1]); return xb + (vp[0] - xb) * t
    L, R = xat(xl, ytop), xat(xr, ytop)
    out.append(f'<path d="M{xl} {ybot}L{L:.1f} {ytop}H{R:.1f}L{xr} {ybot}Z" fill="none" stroke="{fc}" stroke-width="18" stroke-linejoin="round"/>')
    inner = []
    for xb in (xl + (xr - xl) * 0.25, 400, xl + (xr - xl) * 0.75):
        inner.append(f'M{xb:.1f} {ybot}L{xat(xb, ytop):.1f} {ytop}')
    for y in (ybot - (ybot - ytop) * 0.40, ybot - (ybot - ytop) * 0.70):
        inner.append(f'M{xat(xl, y):.1f} {y:.1f}H{xat(xr, y):.1f}')
    out.append(f'<path d="{" ".join(inner)}" fill="none" stroke="{fc}" stroke-width="8" stroke-linecap="round" opacity="0.55"/>')
    # ghosts
    P0, P1, P2 = (135, 185), (330, 195), (cx, cy)
    if ghosts:
        for t, rr, o in [(0.05, 24, 0.45), (0.34, 34, 0.62), (0.58, 46, 0.85)]:
            x, y = bez(P0, P1, P2, t)
            out.append(_ghost_shiba(x, y, rr, o, p))
    ol, ow = p["paper"], 14
    ch = [f'<g transform="translate({cx},{cy})">']
    # tail (behind head), curled up to the right
    tail = f'M92 66Q204 48 150 -62'
    ch.append(f'<path d="{tail}" fill="none" stroke="{ol}" stroke-width="48" stroke-linecap="round"/>')
    ch.append(f'<path d="{tail}" fill="none" stroke="{p["amber"]}" stroke-width="30" stroke-linecap="round"/>')
    ch.append(f'<circle cx="150" cy="-62" r="15" fill="{ol}"/>')
    if wag:
        ch.append(f'<path d="M198 -80q20 10 28 36 M214 -106q12 6 20 18" fill="none" stroke="{ol}" stroke-width="8" stroke-linecap="round" opacity="0.9"/>')
    # collar (behind head)
    ch.append(f'<rect x="-100" y="{r-26}" width="200" height="52" rx="26" fill="{INK}" stroke="{ol}" stroke-width="{ow-4}"/>')
    # ears + head + face (shared module; expr picks the expression, tilt cocks the head)
    hd = _shiba_head(p, ol, ow, expr=expr)
    ch.append(f'<g transform="rotate({tilt})">{hd}</g>' if tilt else hd)
    # paws
    for sgn in (-1, 1):
        ch.append(f'<circle cx="{sgn*92}" cy="{r-2}" r="27" fill="{p["amber"]}" stroke="{ol}" stroke-width="{ow-4}"/>')
        ch.append(f'<path d="M{sgn*92-11} {r+8}v10 M{sgn*92} {r+10}v10 M{sgn*92+11} {r+8}v10" stroke="{INK}" stroke-width="5" stroke-linecap="round" opacity="0.8"/>')
    # tag with the letter, hanging from the collar
    ty = r + 14
    ch.append(f'<rect x="-25" y="{ty}" width="50" height="50" rx="12" fill="{p["mist"]}" stroke="{ol}" stroke-width="6"/>')
    d, b, _ = face_file("fonts/Fredoka-SemiBold.ttf").path(letter, 40, 0, 0)
    w = b[2] - b[0]; h = b[3] - b[1]
    ch.append(f'<path d="{d}" fill="{INK}" transform="translate({-b[0]-w/2:.1f},{ty+25-(b[1]+h/2):.1f})"/>')
    ch.append('</g>')
    out.append("".join(ch))
    return "\n".join(out)


SHIBA_BBOX = (117, 100, 683, 630)


def lockup_shiba(cx, cy, s, zh, en, tag, gap, pal=PAL, tagline=True, letter="T", expr="alert", tilt=0):
    m = mark_shiba(pal=pal, letter=letter, expr=expr, tilt=tilt)
    bx0, by0, bx1, by1 = SHIBA_BBOX
    mw, mh = (bx1 - bx0) * s, (by1 - by0) * s
    _, tb = text_block_cute(0, 0, zh, en, tag, pal=pal, tagline=tagline)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    total = mw + gap + tw
    mx = cx - total / 2; my = cy - mh / 2
    tx = mx + mw + gap - tb[0]; ty = cy - th / 2 - tb[1]
    g = f'<g transform="translate({mx - bx0*s:.2f},{my - by0*s:.2f}) scale({s})">{m}</g>'
    t, _ = text_block_cute(tx, ty, zh, en, tag, pal=pal, tagline=tagline)
    return g + "\n" + t, (mx, my, mx + total, my + max(mh, th)), my + (622 - by0) * s


def banner_youtube_shiba(pal=PAL, tagline=True, letter="T", expr="alert", tilt=0):
    W, H = 2560, 1440
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    lk, bb, fy = lockup_shiba(1280, 720, 0.52, 128, 56, 36, 70, pal=pal, tagline=tagline, letter=letter, expr=expr, tilt=tilt)
    body.append(ruler_band(W, fy, pal, step=56, opacity=0.14)); body.append(lk)
    return svg(W, H, "\n".join(body)), bb


def header_x_shiba(pal=PAL, tagline=True, letter="T", expr="alert", tilt=0):
    W, H = 1500, 500
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    lk, bb, fy = lockup_shiba(812, 226, 0.34, 82, 36, 23, 44, pal=pal, tagline=tagline, letter=letter, expr=expr, tilt=tilt)
    body.append(ruler_band(W, fy, pal, step=50, opacity=0.14)); body.append(lk)
    return svg(W, H, "\n".join(body)), bb


# ================================================================ 萌版 v3 · 贵妃躺
def _shiba_face(p, ol, ow, lids=False):
    """ears + head + face, in a local frame centred on the head (r=126)."""
    r = 126
    ch = []
    for sgn in (-1, 1):
        ch.append(f'<path d="M{sgn*112} -60L{sgn*98} -196L{sgn*28} -122Z" fill="{p["amber"]}" stroke="{ol}" stroke-width="{ow}" stroke-linejoin="round"/>')
        ch.append(f'<path d="M{sgn*96} -84L{sgn*90} -160L{sgn*50} -116Z" fill="{BLUSH}" opacity="0.55" stroke-linejoin="round"/>')
    ch.append(f'<circle r="{r}" fill="{p["amber"]}" stroke="{ol}" stroke-width="{ow}"/>')
    ch.append(f'<g fill="{p["paper"]}"><ellipse cx="-62" cy="56" rx="50" ry="42"/><ellipse cx="62" cy="56" rx="50" ry="42"/><ellipse cx="0" cy="84" rx="66" ry="40"/>'
              f'<ellipse cx="-50" cy="-80" rx="17" ry="11"/><ellipse cx="50" cy="-80" rx="17" ry="11"/></g>')
    ch.append(f'<ellipse cx="-88" cy="60" rx="19" ry="12" fill="{BLUSH}" opacity="0.6"/><ellipse cx="88" cy="60" rx="19" ry="12" fill="{BLUSH}" opacity="0.6"/>')
    for ex in (-50, 50):
        ch.append(f'<circle cx="{ex}" cy="-30" r="23" fill="{INK}"/>')
        if lids:
            ch.append(f'<ellipse cx="{ex}" cy="-53" rx="26" ry="14" fill="{p["amber"]}"/>')
            ch.append(f'<circle cx="{ex-8}" cy="-28" r="7" fill="#FFFFFF"/><circle cx="{ex+7}" cy="-16" r="4" fill="#FFFFFF"/>')
        else:
            ch.append(f'<circle cx="{ex-8}" cy="-38" r="8" fill="#FFFFFF"/><circle cx="{ex+7}" cy="-22" r="4" fill="#FFFFFF"/>')
    ch.append(f'<ellipse cx="0" cy="40" rx="18" ry="13" fill="{INK}"/><circle cx="-6" cy="36" r="4" fill="#FFFFFF" opacity="0.8"/>')
    ch.append(f'<path d="M0 53v10 M-28 62q14 20 28 1q14 19 28 -1" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
    return "".join(ch)


def _leg(x0, y0, x1, y1, p, ol, w=38, paw=24):
    return (f'<path d="M{x0} {y0}L{x1} {y1}" stroke="{ol}" stroke-width="{w+22}" stroke-linecap="round" fill="none"/>'
            f'<path d="M{x0} {y0}L{x1} {y1}" stroke="{p["amber"]}" stroke-width="{w}" stroke-linecap="round" fill="none"/>'
            f'<circle cx="{x1}" cy="{y1}" r="{paw}" fill="{p["amber"]}" stroke="{ol}" stroke-width="10"/>'
            f'<path d="M{x1-10} {y1+8}v9 M{x1} {y1+10}v9 M{x1+10} {y1+8}v9" stroke="{INK}" stroke-width="5" stroke-linecap="round" opacity="0.8"/>')


def mark_lounge_v2(bg=None, pal=PAL, letter="M", ghosts=True, wag=True,
                vp=(400, 280), ybot=622, ytop=440, xl=125, xr=675, k=0.84, pivot=(410, 604), lift=26, lids=True):
    """贵妃躺: lying on her side on the proving ground, head propped up, watching the ghosts drift in."""
    p = pal
    out = []
    if bg:
        out.append(f'<rect width="800" height="800" fill="{bg}"/>')
    fc = p["paper"]
    def xat(xb, y):
        t = (ybot - y) / (ybot - vp[1]); return xb + (vp[0] - xb) * t
    L, R = xat(xl, ytop), xat(xr, ytop)
    out.append(f'<path d="M{xl} {ybot}L{L:.1f} {ytop}H{R:.1f}L{xr} {ybot}Z" fill="none" stroke="{fc}" stroke-width="18" stroke-linejoin="round"/>')
    inner = []
    for xb in (xl + (xr - xl) * 0.25, 400, xl + (xr - xl) * 0.75):
        inner.append(f'M{xb:.1f} {ybot}L{xat(xb, ytop):.1f} {ytop}')
    for y in (ybot - (ybot - ytop) * 0.40, ybot - (ybot - ytop) * 0.70):
        inner.append(f'M{xat(xl, y):.1f} {y:.1f}H{xat(xr, y):.1f}')
    out.append(f'<path d="{" ".join(inner)}" fill="none" stroke="{fc}" stroke-width="8" stroke-linecap="round" opacity="0.55"/>')
    hx, hy, hs, hrot = 560, 400, 0.86, -10     # head centre / scale / tilt (pre-scale frame)
    # the whole character is scaled by k about pivot; ghosts aim at the scaled head
    HX, HY = pivot[0] + (hx - pivot[0]) * k, pivot[1] + (hy - pivot[1]) * k - lift
    P0, P1, P2 = (135, 185), (320, 175), (HX, HY)
    if ghosts:
        for t, rr, o in [(0.05, 24, 0.45), (0.36, 34, 0.62), (0.63, 44, 0.85)]:
            x, y = bez(P0, P1, P2, t)
            out.append(_ghost_shiba(x, y, rr, o, p))
    ol, ow = p["paper"], 14
    body = [f'<g transform="translate({pivot[0]},{pivot[1]-lift}) scale({k}) translate({-pivot[0]},{-pivot[1]})">']
    tail = 'M215 462Q128 430 158 366'
    body.append(f'<path d="{tail}" fill="none" stroke="{ol}" stroke-width="48" stroke-linecap="round"/>')
    body.append(f'<path d="{tail}" fill="none" stroke="{p["amber"]}" stroke-width="30" stroke-linecap="round"/>')
    body.append(f'<circle cx="158" cy="366" r="15" fill="{ol}"/>')
    if wag:
        body.append(f'<path d="M108 372q-6 -22 8 -40 M92 344q-2 -14 8 -24" fill="none" stroke="{ol}" stroke-width="8" stroke-linecap="round" opacity="0.9"/>')
    body.append(_leg(235, 562, 118, 596, p, ol, w=40, paw=25))
    body.append(f'<g transform="rotate(-8 340 520)"><ellipse cx="340" cy="520" rx="190" ry="94" fill="{p["amber"]}" stroke="{ol}" stroke-width="{ow}"/>'
                f'<ellipse cx="345" cy="548" rx="150" ry="54" fill="{p["paper"]}"/></g>')
    body.append(_leg(485, 548, 612, 578, p, ol))
    body.append(_leg(468, 572, 548, 602, p, ol))
    # head frame: collar arc hugging the neck (lower-left), then the face, then the tag
    d, b, _ = face_file("fonts/Fredoka-SemiBold.ttf").path(letter, 40, 0, 0)
    w = b[2] - b[0]; h = b[3] - b[1]
    body.append(f'<g transform="translate({hx},{hy}) rotate({hrot}) scale({hs})">'
                f'<path d="M-23.6 133.9A136 136 0 0 1 -133.9 23.6" fill="none" stroke="{ol}" stroke-width="48" stroke-linecap="round"/>'
                f'<path d="M-23.6 133.9A136 136 0 0 1 -133.9 23.6" fill="none" stroke="{INK}" stroke-width="30" stroke-linecap="round"/>'
                f'{_shiba_face(p, ol, ow, lids=lids)}'
                f'<g transform="translate(-118,108)"><rect x="-25" y="0" width="50" height="50" rx="12" fill="{p["mist"]}" stroke="{ol}" stroke-width="6"/>'
                f'<path d="{d}" fill="{INK}" transform="translate({-b[0]-w/2:.1f},{25-(b[1]+h/2):.1f})"/></g>'
                f'</g>')
    body.append('</g>')
    out.append("".join(body))
    return "\n".join(out)


LOUNGE_BBOX_V2 = (117, 150, 683, 631)


def lockup_generic(markfn, bbox, cx, cy, s, zh, en, tag, gap, pal=PAL, tagline=True):
    m = markfn(pal=pal)
    bx0, by0, bx1, by1 = bbox
    mw, mh = (bx1 - bx0) * s, (by1 - by0) * s
    _, tb = text_block_cute(0, 0, zh, en, tag, pal=pal, tagline=tagline)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    total = mw + gap + tw
    mx = cx - total / 2; my = cy - mh / 2
    tx = mx + mw + gap - tb[0]; ty = cy - th / 2 - tb[1]
    g = f'<g transform="translate({mx - bx0*s:.2f},{my - by0*s:.2f}) scale({s})">{m}</g>'
    t, _ = text_block_cute(tx, ty, zh, en, tag, pal=pal, tagline=tagline)
    return g + "\n" + t, (mx, my, mx + total, my + max(mh, th)), my + (622 - by0) * s


def banner_youtube_lounge(pal=PAL, tagline=True, letter="M"):
    W, H = 2560, 1440
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    fn = lambda pal: mark_lounge(pal=pal, letter=letter)
    lk, bb, fy = lockup_generic(fn, LOUNGE_BBOX, 1280, 720, 0.56, 128, 56, 36, 60, pal=pal, tagline=tagline)
    body.append(ruler_band(W, fy, pal, step=56, opacity=0.14)); body.append(lk)
    return svg(W, H, "\n".join(body)), bb


def header_x_lounge(pal=PAL, tagline=True, letter="M"):
    W, H = 1500, 500
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    fn = lambda pal: mark_lounge(pal=pal, letter=letter)
    lk, bb, fy = lockup_generic(fn, LOUNGE_BBOX, 812, 226, 0.36, 82, 36, 23, 40, pal=pal, tagline=tagline)
    body.append(ruler_band(W, fy, pal, step=50, opacity=0.14)); body.append(lk)
    return svg(W, H, "\n".join(body)), bb


def banner_youtube_lounge_v2(pal=PAL, tagline=True, letter="M"):
    """第三版（v2 贵妃躺·侧躺）— kept as a live register; byte-identical to the 09-29 v2 kit."""
    W, H = 2560, 1440
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    fn = lambda pal: mark_lounge_v2(pal=pal, letter=letter)
    lk, bb, fy = lockup_generic(fn, LOUNGE_BBOX_V2, 1280, 720, 0.56, 128, 56, 36, 60, pal=pal, tagline=tagline)
    body.append(ruler_band(W, fy, pal, step=56, opacity=0.14)); body.append(lk)
    return svg(W, H, "\n".join(body)), bb


def header_x_lounge_v2(pal=PAL, tagline=True, letter="M"):
    W, H = 1500, 500
    body = [f'<rect width="{W}" height="{H}" fill="{pal["pool"]}"/>']
    fn = lambda pal: mark_lounge_v2(pal=pal, letter=letter)
    lk, bb, fy = lockup_generic(fn, LOUNGE_BBOX_V2, 812, 226, 0.36, 82, 36, 23, 40, pal=pal, tagline=tagline)
    body.append(ruler_band(W, fy, pal, step=50, opacity=0.14)); body.append(lk)
    return svg(W, H, "\n".join(body)), bb


# ================================================================ 萌版 v3.1 · 笑脸 + 仰躺
TONGUE = BLUSH


def _ground(out, p, vp, ybot, ytop, xl, xr):
    fc = p["paper"]
    def xat(xb, y):
        t = (ybot - y) / (ybot - vp[1]); return xb + (vp[0] - xb) * t
    L, R = xat(xl, ytop), xat(xr, ytop)
    out.append(f'<path d="M{xl} {ybot}L{L:.1f} {ytop}H{R:.1f}L{xr} {ybot}Z" fill="none" stroke="{fc}" stroke-width="18" stroke-linejoin="round"/>')
    inner = []
    for xb in (xl + (xr - xl) * 0.25, 400, xl + (xr - xl) * 0.75):
        inner.append(f'M{xb:.1f} {ybot}L{xat(xb, ytop):.1f} {ytop}')
    for y in (ybot - (ybot - ytop) * 0.40, ybot - (ybot - ytop) * 0.70):
        inner.append(f'M{xat(xl, y):.1f} {y:.1f}H{xat(xr, y):.1f}')
    out.append(f'<path d="{" ".join(inner)}" fill="none" stroke="{fc}" stroke-width="8" stroke-linecap="round" opacity="0.55"/>')


def _shiba_head(p, ol, ow, expr="smile", tongue=True):
    """ears + head + face in a local frame centred on the head (r=126).
    expr: smile (the shiba smile: arched eyes, wide open grin, tongue) | alert (round eyes, ω mouth)."""
    r = 126
    ch = []
    for sgn in (-1, 1):
        ch.append(f'<path d="M{sgn*112} -60L{sgn*98} -196L{sgn*28} -122Z" fill="{p["amber"]}" stroke="{ol}" stroke-width="{ow}" stroke-linejoin="round"/>')
        ch.append(f'<path d="M{sgn*96} -84L{sgn*90} -160L{sgn*50} -116Z" fill="{BLUSH}" opacity="0.55" stroke-linejoin="round"/>')
    ch.append(f'<circle r="{r}" fill="{p["amber"]}" stroke="{ol}" stroke-width="{ow}"/>')
    if expr == "smile":
        # urajiro: puffed cheeks + muzzle + brow dots
        ch.append(f'<g fill="{p["paper"]}"><ellipse cx="-66" cy="52" rx="54" ry="48"/><ellipse cx="66" cy="52" rx="54" ry="48"/><ellipse cx="0" cy="82" rx="72" ry="44"/>'
                  f'<ellipse cx="-50" cy="-84" rx="17" ry="11"/><ellipse cx="50" cy="-84" rx="17" ry="11"/></g>')
        ch.append(f'<ellipse cx="-94" cy="54" rx="19" ry="12" fill="{BLUSH}" opacity="0.6"/><ellipse cx="94" cy="54" rx="19" ry="12" fill="{BLUSH}" opacity="0.6"/>')
        # happy eyes: two arches
        for ex in (-52, 52):
            ch.append(f'<path d="M{ex-25} -16A25 25 0 0 1 {ex+25} -16" fill="none" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>')
        # nose
        ch.append(f'<ellipse cx="0" cy="38" rx="18" ry="13" fill="{INK}"/><circle cx="-6" cy="34" r="4" fill="#FFFFFF" opacity="0.8"/>')
        # the grin: wide open mouth, corners pulled up into the cheeks
        mouth = 'M-54 50Q0 62 54 50Q48 106 0 106Q-48 106 -54 50Z'
        ch.append(f'<path d="{mouth}" fill="{INK}"/>')
        if tongue:
            ch.append(f'<ellipse cx="6" cy="96" rx="23" ry="24" fill="{TONGUE}"/><path d="M6 80v28" stroke="{INK}" stroke-width="3" stroke-linecap="round" opacity="0.45"/>')
        ch.append(f'<path d="M-54 50q-11 -5 -14 -18 M54 50q11 -5 14 -18" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>')
    else:
        ch.append(f'<g fill="{p["paper"]}"><ellipse cx="-62" cy="56" rx="50" ry="42"/><ellipse cx="62" cy="56" rx="50" ry="42"/><ellipse cx="0" cy="84" rx="66" ry="40"/>'
                  f'<ellipse cx="-50" cy="-80" rx="17" ry="11"/><ellipse cx="50" cy="-80" rx="17" ry="11"/></g>')
        ch.append(f'<ellipse cx="-88" cy="60" rx="19" ry="12" fill="{BLUSH}" opacity="0.6"/><ellipse cx="88" cy="60" rx="19" ry="12" fill="{BLUSH}" opacity="0.6"/>')
        for ex in (-50, 50):
            ch.append(f'<circle cx="{ex}" cy="-30" r="23" fill="{INK}"/>')
            ch.append(f'<circle cx="{ex-8}" cy="-38" r="8" fill="#FFFFFF"/><circle cx="{ex+7}" cy="-22" r="4" fill="#FFFFFF"/>')
        ch.append(f'<ellipse cx="0" cy="40" rx="18" ry="13" fill="{INK}"/><circle cx="-6" cy="36" r="4" fill="#FFFFFF" opacity="0.8"/>')
        ch.append(f'<path d="M0 53v10 M-28 62q14 20 28 1q14 19 28 -1" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
    return "".join(ch)


def _tag(p, ol, letter, x, y):
    d, b, _ = face_file("fonts/Fredoka-SemiBold.ttf").path(letter, 40, 0, 0)
    w = b[2] - b[0]; h = b[3] - b[1]
    return (f'<g transform="translate({x},{y})"><rect x="-25" y="-25" width="50" height="50" rx="12" fill="{p["mist"]}" stroke="{ol}" stroke-width="6"/>'
            f'<path d="{d}" fill="{INK}" transform="translate({-b[0]-w/2:.1f},{-(b[1]+h/2):.1f})"/></g>')


def mark_lounge(bg=None, pal=PAL, letter="M", ghosts=True, wag=True, expr="smile",
                vp=(400, 280), ybot=622, ytop=440, xl=125, xr=675,
                head=(546, 346), hs=0.95, hrot=-20, torso=(370, 498), trot=-34, tr=(118, 84), belly=(92, 58),
                hind=((246, 546, 232, 478), (262, 584, 206, 606)), fore=((456, 440), (508, 464)),
                tail='M244 596Q160 626 126 574', tip=(126, 574), wag_at=(90, 570), tag=(20, 172), collar=(170, 40)):
    """贵妃躺 v3.1: on her back on the proving ground, belly to the sky, head cocked, the shiba smile."""
    p = pal
    out = []
    if bg:
        out.append(f'<rect width="800" height="800" fill="{bg}"/>')
    _ground(out, p, vp, ybot, ytop, xl, xr)
    P0, P1, P2 = (135, 185), (320, 175), head
    if ghosts:
        for t, rr, o in [(0.05, 24, 0.45), (0.36, 34, 0.62), (0.63, 44, 0.85)]:
            x, y = bez(P0, P1, P2, t)
            out.append(_ghost_shiba(x, y, rr, o, p))
    ol, ow = p["paper"], 14
    b = []
    # tail: out along the ground from the rump, tip lifted, wagging
    b.append(f'<path d="{tail}" fill="none" stroke="{ol}" stroke-width="48" stroke-linecap="round"/>')
    b.append(f'<path d="{tail}" fill="none" stroke="{p["amber"]}" stroke-width="30" stroke-linecap="round"/>')
    b.append(f'<circle cx="{tip[0]}" cy="{tip[1]}" r="15" fill="{ol}"/>')
    if wag:
        wx, wy = wag_at
        b.append(f'<path d="M{wx} {wy}q-6 -22 8 -40 M{wx-16} {wy-28}q-2 -14 8 -24" fill="none" stroke="{ol}" stroke-width="8" stroke-linecap="round" opacity="0.9"/>')
    # hind legs, frog-splayed from the rump
    for (x0, y0, x1, y1) in hind:
        b.append(_leg(x0, y0, x1, y1, p, ol, w=40, paw=25))
    # torso on its back: amber shell, big cream belly
    tx, ty = torso
    b.append(f'<g transform="rotate({trot} {tx} {ty})"><ellipse cx="{tx}" cy="{ty}" rx="{tr[0]}" ry="{tr[1]}" fill="{p["amber"]}" stroke="{ol}" stroke-width="{ow}"/>'
             f'<ellipse cx="{tx-4}" cy="{ty+8}" rx="{belly[0]}" ry="{belly[1]}" fill="{p["paper"]}"/></g>')
    # head: collar arc behind, then the face
    hx, hy = head
    a0, a1 = math.radians(collar[0]), math.radians(collar[1])
    cx0, cy0 = 136 * math.cos(a0), 136 * math.sin(a0); cx1, cy1 = 136 * math.cos(a1), 136 * math.sin(a1)
    arc = f'M{cx0:.1f} {cy0:.1f}A136 136 0 0 0 {cx1:.1f} {cy1:.1f}'
    b.append(f'<g transform="translate({hx},{hy}) rotate({hrot}) scale({hs})">'
             f'<path d="{arc}" fill="none" stroke="{ol}" stroke-width="48" stroke-linecap="round"/>'
             f'<path d="{arc}" fill="none" stroke="{INK}" stroke-width="30" stroke-linecap="round"/>'
             f'{_shiba_head(p, ol, ow, expr=expr)}'
             f'{_tag(p, ol, letter, tag[0], tag[1])}'
             f'</g>')
    # forepaws held up under the chin (in front of the head)
    for (px, py) in fore:
        b.append(f'<circle cx="{px}" cy="{py}" r="27" fill="{p["amber"]}" stroke="{ol}" stroke-width="10"/>'
                 f'<path d="M{px-11} {py-4}v10 M{px} {py-6}v10 M{px+11} {py-4}v10" stroke="{INK}" stroke-width="5" stroke-linecap="round" opacity="0.8"/>')
    out.append("".join(b))
    return "\n".join(out)


LOUNGE_BBOX = (72, 132, 690, 636)  # measured alpha bbox of mark_lounge() at 800×800 (incl. ghosts and tail wag)
