#!/usr/bin/env python3
"""色彩发布门（内部工单：Normal 8-bit 直出、相对一致性制；裁定 2026-10-01-30／裁定 2026-10-02-01）。

对象＝相机原片（原片即母版）或双画框成片的实拍区。阈值全部在 tools/color_gate.yaml，代码不写死；
yaml 里为 null 的项＝未定稿：只报原始值、不判，整体退出码 3（不得作发布依据）。任一项 FAIL 退出码 1。

  预检：样帧直方图呈 log 形态（黑位抬高＋低对比／灰平）→ 直接 FAIL 标「profile 误用」，五项不跑
  ① 中性度：灰区（--gray-rect）直出 Lab 的 |a*|、|b*| ≤ 上限
  ② 曝光：同一灰区 L* 在区间内
  ③ 一致性：固定场景锚点区（--anchor-rect）与基准片段（yaml reference.path 或 --ref-video）同区的 ΔE2000 ≤ 上限；
            基准片段 sha256 与 yaml 不符即 FAIL
  ④ 裁切：样帧 Y ≥ 235 占比 ≤ 上限（高光）；Y ≤ 16 占比只报数（内部工单定义不动）
  ⑤ 码率：视频流码率 ≥ 下限（null＝只报数）；并核原片 sha256 已记在账本（默认＝同目录 SHA256SUMS）

坐标都是实拍区内的归一化值（0–1），矩形写法 "x,y,w,h"。实拍区默认＝整帧；双画框成片给 --crop 1080:1080:0:0。
另导出样帧波形图＋矢量图 PNG 与 ffprobe 标签到报告目录（只记录，不作门项）。
用法（仓根）：
  python3 tools/color_gate.py --video <原片.mp4> [<原片2.mp4> …] --t 3 --gray-rect "0.45,0.80,0.10,0.08" --anchor-rect "0.10,0.10,0.08,0.08" --out-dir <报告目录>
  python3 tools/color_gate.py --selftest      # 合成 Normal 片＋log 形态片＋偏色片＋基准片，核预检与五项
依赖：ffmpeg／ffprobe（查找顺序同 compose_video.py）、pyyaml、Python 标准库。
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose_video import find_ffmpeg, sha256_file  # noqa: E402

DEFAULT_CONFIG = Path(__file__).with_name("color_gate.yaml")
TAG_KEYS = ("codec_name", "width", "height", "pix_fmt", "color_range", "color_space", "color_transfer", "color_primaries", "bit_rate")
RC_FAIL, RC_ERR, RC_UNSET = 1, 2, 3


def srgb_to_lab(rgb) -> tuple[float, float, float]:
    """8-bit sRGB（Rec.709 原色，D65）→ CIE Lab。"""
    lin = [((c / 255) / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4) for c in rgb]
    x = (0.4124564 * lin[0] + 0.3575761 * lin[1] + 0.1804375 * lin[2]) / 0.95047
    y = 0.2126729 * lin[0] + 0.7151522 * lin[1] + 0.0721750 * lin[2]
    z = (0.0193339 * lin[0] + 0.1191920 * lin[1] + 0.9503041 * lin[2]) / 1.08883
    fx, fy, fz = [(v ** (1 / 3) if v > 216 / 24389 else (24389 / 27 * v + 16) / 116) for v in (x, y, z)]
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def de2000(lab1, lab2) -> float:
    """CIEDE2000（kL=kC=kH=1）。"""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    cm = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(cm ** 7 / (cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0
    dlp, dcp = L2 - L1, c2p - c1p
    if c1p * c2p == 0:
        dhp, hm = 0.0, h1p + h2p
    else:
        dhp = h2p - h1p
        dhp = dhp - 360 if dhp > 180 else dhp + 360 if dhp < -180 else dhp
        hm = (h1p + h2p) / 2 if abs(h1p - h2p) <= 180 else ((h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2)
    dhh = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))
    lm, cpm = (L1 + L2) / 2, (c1p + c2p) / 2
    t = (1 - 0.17 * math.cos(math.radians(hm - 30)) + 0.24 * math.cos(math.radians(2 * hm))
         + 0.32 * math.cos(math.radians(3 * hm + 6)) - 0.20 * math.cos(math.radians(4 * hm - 63)))
    rc = 2 * math.sqrt(cpm ** 7 / (cpm ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (lm - 50) ** 2 / math.sqrt(20 + (lm - 50) ** 2)
    sc, sh = 1 + 0.045 * cpm, 1 + 0.015 * cpm * t
    rt = -math.sin(math.radians(60 * math.exp(-(((hm - 275) / 25) ** 2)))) * rc
    return math.sqrt((dlp / sl) ** 2 + (dcp / sc) ** 2 + (dhh / sh) ** 2 + rt * (dcp / sc) * (dhh / sh))


def probe(ffprobe: str, path: str) -> dict:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=" + ",".join(TAG_KEYS) + ":format=bit_rate",
                          "-of", "json", path], capture_output=True, text=True).stdout
    try:
        d = json.loads(out)
        st = d["streams"][0]
        st.setdefault("bit_rate", d.get("format", {}).get("bit_rate"))   # 流没写码率时退到容器码率
        return st
    except Exception:  # noqa: BLE001
        return {}


def grab(ffmpeg: str, path: str, t: float, crop: str | None, fmt: str, scale: str | None = None) -> bytes:
    """取 t 秒一帧实拍区原始字节：fmt＝rgb24（按 bt709 矩阵还原）或 y（yuv420p 的 Y 平面，tv 范围不换算）。scale＝可选缩放（预检用）。"""
    chain = [f"crop={crop}"] if crop else []
    if scale:
        chain.append(f"scale={scale}")
    chain.append("scale=in_color_matrix=bt709:in_range=tv,format=rgb24" if fmt == "rgb24" else "format=yuv420p")
    r = subprocess.run([ffmpeg, "-v", "error", "-ss", str(t), "-i", path, "-frames:v", "1", "-vf", ",".join(chain), "-f", "rawvideo", "-"],
                       capture_output=True)
    return r.stdout if fmt == "rgb24" else r.stdout[: len(r.stdout) * 2 // 3]   # yuv420p：前 2/3 为 Y 平面


def frame_size(ffprobe: str, path: str, crop: str | None) -> tuple[int, int]:
    if crop:
        w, h = [int(v) for v in crop.split(":")[:2]]
        return w, h
    st = probe(ffprobe, path)
    return int(st.get("width", 0)), int(st.get("height", 0))


def mean_rgb(buf: bytes, w: int, h: int, rect: str) -> tuple[float, float, float]:
    """归一化矩形 "x,y,w,h" 内取 9×9 个点求均值。"""
    x0, y0, rw, rh = [float(v) for v in rect.split(",")]
    acc = [0, 0, 0]
    for i in range(9):
        for j in range(9):
            px = min(w - 1, max(0, int((x0 + rw * (i + 0.5) / 9) * w)))
            py = min(h - 1, max(0, int((y0 + rh * (j + 0.5) / 9) * h)))
            o = (py * w + px) * 3
            for k in range(3):
                acc[k] += buf[o + k]
    return acc[0] / 81, acc[1] / 81, acc[2] / 81


def percentile(counter: collections.Counter, total: int, p: float) -> int:
    need, seen = total * p, 0
    for v in sorted(counter):
        seen += counter[v]
        if seen >= need:
            return v
    return 255


def judge(value: float | None, limit, op: str) -> str:
    """op：le＝value ≤ limit；ge＝value ≥ limit。limit 为 None → UNSET（未定稿只报数）。"""
    if value is None:
        return "FAIL"
    if limit is None:
        return "UNSET"
    return "PASS" if (value <= limit if op == "le" else value >= limit) else "FAIL"


def fmt_lim(limit, suffix: str = "") -> str:
    return f"阈 {limit:g}{suffix}" if limit is not None else "未定稿·只报数"


def gate_one(a, cfg: dict, ffmpeg: str, video: str, out_dir: Path) -> tuple[int, dict]:
    """单片过门。返回 (退出码, 报告)。"""
    ffprobe = str(Path(ffmpeg).with_name("ffprobe"))
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = frame_size(ffprobe, video, a.crop)
    rep: dict = {"video": video, "config": str(a.config), "config_status": cfg.get("status"), "tags": probe(ffprobe, video)}
    res: dict[str, str] = {}
    print(f"== {video}")

    # 预检：log 形态
    pf = cfg["preflight"]
    gray = grab(ffmpeg, video, a.t, a.crop, "y", scale="320:-2")
    rgb_s = grab(ffmpeg, video, a.t, a.crop, "rgb24", scale="320:-2")
    if not gray or not rgb_s:
        print("✘ 预检 FAIL：取不到样帧（核对 --t 与 --crop）")
        rep["result"] = {"preflight": "FAIL"}
        return RC_FAIL, rep
    hist = collections.Counter(gray)
    p1, p99 = percentile(hist, len(gray), 0.01), percentile(hist, len(gray), 0.99)
    n = len(rgb_s) // 3
    chroma = sum(math.hypot(*srgb_to_lab(rgb_s[i * 3:i * 3 + 3])[1:]) for i in range(n)) / n
    lifted, flat, gray_ish = p1 >= pf["y_p1_min"], (p99 - p1) <= pf["y_spread_max"], chroma <= pf["chroma_max"]
    is_log = lifted and (flat or gray_ish)
    rep["preflight"] = {"y_p1": p1, "y_p99": p99, "chroma_mean": chroma, "log_profile": is_log}
    res["preflight"] = "FAIL" if is_log else "PASS"
    print(f"预检 {res['preflight']}：Y P1 {p1}（log 判据 ≥{pf['y_p1_min']}）、P99−P1 {p99 - p1}（≤{pf['y_spread_max']}）、平均彩度 {chroma:.1f}（≤{pf['chroma_max']}）"
          + ("　→ 直方图呈 log 形态：profile 误用（D-Log M／HLG 误切），五项不跑" if is_log else ""))
    if is_log:
        rep["result"] = res
        (out_dir / "color_gate.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✘ 色彩门未过（profile 误用），不得发布（报告 {out_dir / 'color_gate.json'}）")
        return RC_FAIL, rep

    rgb = grab(ffmpeg, video, a.t, a.crop, "rgb24")
    if len(rgb) != w * h * 3:
        print("✘ 取不到全分辨率样帧（核对 --t 与 --crop）")
        rep["result"] = res | {"frame": "FAIL"}
        return RC_FAIL, rep

    # ① 中性度 ② 曝光（同一灰区）
    ne, ex = cfg["neutral"], cfg["exposure"]
    if a.gray_rect:
        L, A, B = srgb_to_lab(mean_rgb(rgb, w, h, a.gray_rect))
        res["1_neutral"] = "FAIL" if "FAIL" in (judge(abs(A), ne["a_abs_max"], "le"), judge(abs(B), ne["b_abs_max"], "le")) else \
            ("UNSET" if ne["a_abs_max"] is None or ne["b_abs_max"] is None else "PASS")
        lo, hi = judge(L, ex["L_min"], "ge"), judge(L, ex["L_max"], "le")
        res["2_exposure"] = "FAIL" if "FAIL" in (lo, hi) else ("UNSET" if "UNSET" in (lo, hi) else "PASS")
        rep["gray"] = {"rect": a.gray_rect, "lab": [L, A, B]}
        print(f"① 中性度 {res['1_neutral']}：灰区 a* {A:+.2f}（{fmt_lim(ne['a_abs_max'])}）、b* {B:+.2f}（{fmt_lim(ne['b_abs_max'])}）")
        print(f"② 曝光 {res['2_exposure']}：灰区 L* {L:.1f}（区间 {ex['L_min']}–{ex['L_max']}" + ("）" if ex["L_min"] is not None and ex["L_max"] is not None else "，未定稿·只报数）"))
    else:
        res["1_neutral"] = res["2_exposure"] = "FAIL"
        print("① 中性度／② 曝光 FAIL：未给 --gray-rect（灰卡／中性灰区）")

    # ③ 一致性
    co, ref = cfg["consistency"], cfg.get("reference") or {}
    ref_video = a.ref_video or ref.get("path")
    if not a.anchor_rect:
        res["3_consistency"] = "FAIL"
        print("③ 一致性 FAIL：未给 --anchor-rect（固定场景锚点区）")
    elif not ref_video or not Path(ref_video).is_file():
        res["3_consistency"] = "UNSET" if co["de2000_max"] is None and not ref_video else "FAIL"
        rep["consistency"] = {"anchor_rect": a.anchor_rect, "reference": ref_video, "lab": list(srgb_to_lab(mean_rgb(rgb, w, h, a.anchor_rect)))}
        print(f"③ 一致性 {res['3_consistency']}：基准片段{'未定（10-04 定稿）' if not ref_video else '不存在：' + ref_video}；锚点区 Lab 已记报告")
    else:
        want = ref.get("sha256") if not a.ref_video else None
        got = sha256_file(ref_video) if want else None
        rt = a.ref_t if a.ref_t is not None else (ref.get("t") if ref.get("t") is not None else a.t)
        rw, rh = frame_size(ffprobe, ref_video, a.crop)
        rbuf = grab(ffmpeg, ref_video, rt, a.crop, "rgb24")
        if want and got != want:
            res["3_consistency"] = "FAIL"
            print(f"③ 一致性 FAIL：基准片段 sha256 不符（实得 {got[:16]}… 预期 {want[:16]}…）")
        elif len(rbuf) != rw * rh * 3:
            res["3_consistency"] = "FAIL"
            print("③ 一致性 FAIL：基准片段取不到样帧（核对 reference.t／--ref-t）")
        else:
            lab_a, lab_r = srgb_to_lab(mean_rgb(rgb, w, h, a.anchor_rect)), srgb_to_lab(mean_rgb(rbuf, rw, rh, a.anchor_rect))
            de = de2000(lab_a, lab_r)
            res["3_consistency"] = judge(de, co["de2000_max"], "le")
            rep["consistency"] = {"anchor_rect": a.anchor_rect, "reference": ref_video, "reference_sha256": got, "lab": list(lab_a), "ref_lab": list(lab_r), "de2000": de}
            print(f"③ 一致性 {res['3_consistency']}：锚点区对基准 ΔE2000 {de:.2f}（{fmt_lim(co['de2000_max'])}）")

    # ④ 裁切
    cl = cfg["clip"]
    yfull = grab(ffmpeg, video, a.t, a.crop, "y")
    hist = collections.Counter(yfull)
    hi_frac, lo_frac = sum(c for v, c in hist.items() if v >= 235) / len(yfull), sum(c for v, c in hist.items() if v <= 16) / len(yfull)
    res["4_clip"] = judge(hi_frac, cl["highlight_max"], "le")
    rep["clip"] = {"highlight": hi_frac, "shadow": lo_frac, "y_min": min(hist), "y_max": max(hist)}
    print(f"④ 裁切 {res['4_clip']}：高光 {hi_frac:.4%}（{fmt_lim(cl['highlight_max'] * 100 if cl['highlight_max'] is not None else None, '%')}）、暗部 {lo_frac:.4%}（只报数）；YMIN {min(hist)} YMAX {max(hist)}")

    # ⑤ 码率＋账本
    br = cfg["bitrate"]
    bps = int(rep["tags"].get("bit_rate") or 0) or None
    digest = sha256_file(video)
    ledger = Path(a.ledger) if a.ledger else Path(video).parent / "SHA256SUMS"
    lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.is_file() else []
    in_ledger = any(ln.split()[:1] == [digest] and ln.endswith(Path(video).name) for ln in lines)
    br_res = judge(bps, br["min_bps"], "ge")
    res["5_bitrate"] = "FAIL" if (not in_ledger or br_res == "FAIL") else br_res
    rep["bitrate"] = {"bps": bps, "sha256": digest, "ledger": str(ledger), "in_ledger": in_ledger}
    print(f"⑤ 码率 {res['5_bitrate']}：{bps if bps else '读不到'} bit/s（{fmt_lim(br['min_bps'])}）；原片 sha256 {digest[:16]}… {'在' if in_ledger else '不在'}账本 {ledger}")

    # 示波 PNG（只记录）
    flt = {"waveform": "waveform=mode=column:display=overlay:graticule=green:flags=numbers+dots,format=rgb24",
           "vectorscope": "format=yuv444p,vectorscope=mode=color3:graticule=color,format=rgb24"}
    for name, f in flt.items():
        subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", str(a.t), "-i", video, "-frames:v", "1", "-vf", (f"crop={a.crop}," if a.crop else "") + f, str(out_dir / f"{name}.png")])
    rep["scopes"] = {k: str(out_dir / f"{k}.png") for k in flt}

    rep["result"] = res
    (out_dir / "color_gate.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    vals = set(res.values())
    rc = RC_FAIL if "FAIL" in vals else RC_UNSET if "UNSET" in vals else 0
    print({0: "✔ 色彩门通过", RC_FAIL: "✘ 色彩门未过，不得发布", RC_UNSET: "⚠ 阈值未定稿：只报数，不得作发布依据"}[rc] + f"（报告 {out_dir / 'color_gate.json'}）")
    return rc, rep


def run_gate(a) -> int:
    ffmpeg, why = find_ffmpeg(a.ffmpeg)
    if not ffmpeg:
        print(f"✘ 没有可用的 ffmpeg：{why}", file=sys.stderr)
        return RC_ERR
    cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))
    out_dir = Path(a.out_dir)
    rcs = {}
    for v in a.video:
        sub = out_dir / Path(v).stem if len(a.video) > 1 else out_dir
        rcs[v], _ = gate_one(a, cfg, ffmpeg, v, sub)
    if len(a.video) > 1:
        cnt = collections.Counter({0: "PASS", RC_FAIL: "FAIL", RC_UNSET: "UNSET"}[r] for r in rcs.values())
        (out_dir / "summary.json").write_text(json.dumps({"config_status": cfg.get("status"), "results": {v: {0: "PASS", 1: "FAIL", 3: "UNSET"}[r] for v, r in rcs.items()}}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"== 汇总 {len(rcs)} 片：PASS {cnt['PASS']}／FAIL {cnt['FAIL']}／未定稿 {cnt['UNSET']}（{out_dir / 'summary.json'}）")
    return max(rcs.values())


def selftest(a) -> int:
    """合成片自测：Normal 形态片（含真黑、真白、彩块、灰区、锚点）＋三个派生片，核预检与五项的判定方向。"""
    assert abs(de2000((50, 2.6772, -79.7751), (50, 0, -82.7485)) - 2.0425) < 1e-3, "CIEDE2000 公式自检不过"
    ffmpeg, why = find_ffmpeg(a.ffmpeg)
    if not ffmpeg:
        print(f"✘ 没有可用的 ffmpeg：{why}", file=sys.stderr)
        return RC_ERR
    tmp = Path(a.out_dir) if a.out_dir != "color-gate-report" else Path(tempfile.mkdtemp(prefix="pg-color-selftest-"))
    tmp.mkdir(parents=True, exist_ok=True)
    w, h = 3840, 2160
    # 画面：左 3% 黑条（P1 落在真黑上）、右 0.5% 白条（高光裁切 <1%），中部六块彩色占约一半，底部灰区（118）与左上锚点（棕）
    palette = [(214, 126, 44), (80, 91, 166), (193, 90, 99), (157, 188, 64), (56, 61, 150), (70, 148, 73)]
    bg, gray_v, anchor_v = (90, 90, 90), (118, 118, 118), (160, 100, 60)
    xb, xw = int(w * 0.03), int(w * 0.995)
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            if x < xb:
                px = (0, 0, 0)
            elif x >= xw:
                px = (255, 255, 255)
            elif 0.25 * h <= y < 0.70 * h and 0.05 * w <= x < 0.95 * w:
                px = palette[int((x - 0.05 * w) / (0.90 * w) * 6)]
            elif 0.80 * h <= y < 0.95 * h and 0.40 * w <= x < 0.60 * w:
                px = gray_v
            elif 0.05 * h <= y < 0.18 * h and 0.05 * w <= x < 0.15 * w:
                px = anchor_v
            else:
                px = bg
            row += bytes(px)
        rows.append(bytes(row))
    frame = b"".join(rows)
    normal = tmp / "normal_4k_hevc8.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-framerate", "30", "-i", "-", "-vf",
                    "loop=loop=89:size=1,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "hevc_videotoolbox", "-b:v", "60M",
                    "-tag:v", "hvc1", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", str(normal)],
                   input=frame, check=True)
    variants = {"logstyle": "colorlevels=romin=0.2:gomin=0.2:bomin=0.2:romax=0.65:gomax=0.65:bomax=0.65,hue=s=0.4",   # 黑位抬到 ~20%、白压到 65%、减饱和 → 应触发预检
                "warmcast": "colorchannelmixer=rr=1.12:bb=0.88",            # 偏暖 → ① 应 FAIL
                "brighter": "eq=brightness=0.02"}                           # 微亮 → 对基准 ΔE 小而非零
    for name, vf in variants.items():
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(normal), "-vf", vf, "-c:v", "hevc_videotoolbox", "-b:v", "60M", "-tag:v", "hvc1",
                        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", str(tmp / f"{name}.mp4")], check=True)
    (tmp / "SHA256SUMS").write_text("".join(f"{sha256_file(str(tmp / f))}  {f}\n" for f in ("normal_4k_hevc8.mp4", "brighter.mp4")), encoding="utf-8")
    cfg = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    test_cfg = tmp / "selftest.yaml"
    filled = dict(cfg, status="selftest", reference={"path": str(normal), "sha256": sha256_file(str(normal)), "t": None},
                  neutral={"a_abs_max": 2.0, "b_abs_max": 2.0}, exposure={"L_min": 44.0, "L_max": 54.0}, consistency={"de2000_max": 3.0},
                  clip={"highlight_max": 0.01, "shadow_max": None}, bitrate={"min_bps": 100_000})   # 合成静帧码率很低，自测下限只核「读得到且在账本」
    test_cfg.write_text(yaml.safe_dump(filled, allow_unicode=True, sort_keys=False), encoding="utf-8")
    common = ["--t", "1", "--gray-rect", "0.42,0.82,0.16,0.11", "--anchor-rect", "0.06,0.06,0.08,0.10", "--ffmpeg", ffmpeg]

    def run(video: str, config: Path, out: str) -> tuple[int, dict]:
        rc = main(["--video", video, "--config", str(config), "--out-dir", str(tmp / out), *common])
        return rc, json.loads((tmp / out / "color_gate.json").read_text(encoding="utf-8"))

    checks = []
    rc, rep = run(str(normal), test_cfg, "r-normal")
    checks.append(("Normal 片五项全过（兼基准，ΔE 0）", rc == 0 and rep["consistency"]["de2000"] < 0.05))
    rc, rep = run(str(tmp / "logstyle.mp4"), test_cfg, "r-log")
    checks.append(("log 形态片被预检拦下", rc == RC_FAIL and rep["preflight"]["log_profile"] and "1_neutral" not in rep["result"]))
    rc, rep = run(str(tmp / "warmcast.mp4"), test_cfg, "r-warm")
    checks.append(("偏暖片 ① FAIL 且预检不误拦", rc == RC_FAIL and rep["result"]["preflight"] == "PASS" and rep["result"]["1_neutral"] == "FAIL"))
    checks.append(("偏暖片不在账本 → ⑤ FAIL", rep["result"]["5_bitrate"] == "FAIL"))
    rc, rep = run(str(tmp / "brighter.mp4"), test_cfg, "r-bright")
    checks.append(("微亮片 ③ ΔE 在 (0, 3] 内 PASS", rc == 0 and 0 < rep["consistency"]["de2000"] <= 3.0))
    rc, rep = run(str(normal), DEFAULT_CONFIG, "r-unset")
    checks.append(("在库 yaml 空阈值 → 退出码 3 只报数", rc == RC_UNSET and rep["result"]["1_neutral"] == "UNSET" and rep["result"]["4_clip"] == "PASS"))
    print(f"== 自测（{tmp}）")
    for name, okk in checks:
        print(f"  {'✔' if okk else '✘'} {name}")
    if not all(okk for _, okk in checks):
        print("✘ 色彩门自测不过")
        return RC_FAIL
    print("✔ 色彩门自测通过")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", nargs="+", help="原片（原片即母版）或双画框成片，可多个")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="阈值表 yaml（默认 tools/color_gate.yaml）")
    ap.add_argument("--t", type=float, default=1.0, help="样帧时间（秒）")
    ap.add_argument("--crop", help="实拍区 w:h:x:y（默认整帧；双画框成片用 1080:1080:0:0）")
    ap.add_argument("--gray-rect", help='灰卡／中性灰区 "x,y,w,h"（实拍区内归一化）→ ①②')
    ap.add_argument("--anchor-rect", help='固定场景锚点区 "x,y,w,h" → ③')
    ap.add_argument("--ref-video", help="基准片段（默认取 yaml reference.path，并核 sha256）")
    ap.add_argument("--ref-t", type=float, help="基准片段取样秒（默认 yaml reference.t，再默认同 --t）")
    ap.add_argument("--ledger", help="原片 sha256 账本（默认＝原片同目录 SHA256SUMS）")
    ap.add_argument("--out-dir", default="color-gate-report")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest(a)
    if not a.video:
        ap.error("需要 --video（或 --selftest）")
    return run_gate(a)


if __name__ == "__main__":
    sys.exit(main())
