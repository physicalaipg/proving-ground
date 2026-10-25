#!/usr/bin/env python3
"""双画框合成（内部工单）：俯拍＋机载画面并排，顶部信息条，底部双语字幕烧录，无旁白。只拼 ffmpeg 命令；--dry-run 或本机无 ffmpeg 时只打印。

ffmpeg 须含 libass（subtitles 滤镜）与 freetype（drawtext 滤镜）：Homebrew 瘦身版 `ffmpeg` 公式两者都没有。本机（brew 前缀 ~/.brew，Tier 3 无 bottle）
`brew install ffmpeg-full` 会从源码编 47 个依赖且 09-25 实测下载 libthai 失败；改用 ffmpeg 官方源码只编精简版到 ~/.local/ffmpeg-libass
（configure --enable-gpl --enable-libx264 --enable-libass --enable-libfreetype --enable-libfontconfig，依赖用 brew 已装的 libass/freetype/x264）；
步骤已脚本化为 tools/setup_ffmpeg.sh（内部工单），换机 `bash tools/setup_ffmpeg.sh` 即重建，`--check` 只核对。
本脚本按 --ffmpeg → $FFMPEG → PATH 里的 ffmpeg → ~/.local/ffmpeg-libass/bin/ffmpeg → `brew --prefix ffmpeg-full`/bin/ffmpeg 的顺序找，并核对滤镜存在。
示例产物（基线批 greedy seed1003 真实日志，非 dry-run）：docs/examples/pilot01-baselines_greedy_seed1003_dual.mp4（内部工单 P4）。

画布 1920×1080：左 俯拍 1080×1080（等比放大后居中裁成方；场地为 2×2 m 方形）；右 机载 800×600（4:3，居中留黑边）位于 (1100, 240)；
右上信息条（期 · 模型 · 种子 · 协议）；字幕由 `subtitles` 滤镜（libass）烧录在右列底部；音轨默认取俯拍机位环境音，--mute 静音。
用法（仓根）：
  python3 tools/compose_video.py --overhead ov.mp4 --onboard ob.mp4 --srt sub.srt --title "<期> · <模型> · seed 1000 · v0" --out dual.mp4
  python3 tools/compose_video.py --onboard-frames 'episodes/runs/<run>/frames/<模型>/s<种子>_t*.png' --fps 0.4 --srt sub.srt --title ... --out demo.mp4   # 孪生：PNG 帧序列当机载（目录或带通配符的模式），俯拍用色块占位
  实拍色彩（内部工单，默认关＝旧行为不变）：--real-color dlogm --lut <官方 D-Log M to Rec.709 .cube> [--master-out 母版.mp4]
      只作用于 --overhead（实拍机位）。顺序：10-bit 解码 → gbrp16le → lut3d 四面体插值 → lanczos 缩放 → yuv420p（误差扩散抖动）→ 全片标 bt709／tv；
      机载（仿真）侧同按 bt709 转换与标注，两侧在同一色彩空间合成。LUT 不入仓：路径取 --lut 或 $PG_DLOGM_LUT，sha256 不符即报错退出 2。
      --master-out 另出 LUT 后 4K 10-bit HEVC Rec.709 交付副本（二级母版；hevc_videotoolbox，仅 macOS），并在同目录 SHA256SUMS 记一行。发布前过 tools/color_gate.py。
      一级母版＝相机原片原样归档（不经本工具）。二级副本码率不低于原片：--master-bitrate 缺省取 ffprobe 读到的原片视频码率，另给的值低于原片时抬到原片（内部工单验收单 P2）。
  加 --dry-run 只打印命令；--font／--font-name 指定字体（macOS 默认 Hiragino Sans GB，Linux 请给 Noto Sans CJK 路径与名字）。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

W, H = 1920, 1080
OV = 1080
OB_W, OB_H, OB_X, OB_Y = 800, 600, 1100, 240
BG = "0x121211"
# libass 把 SRT 当 PlayResX×PlayResY＝384×288 的脚本处理：force_style 里的 Margin／FontSize 都是这个坐标系的单位，
# 直接写 1080p 像素会把字幕推出画面（09-25 实测：MarginL=1100 → 整条不可见）。下面按比例换算。
ASS_RES_X, ASS_RES_Y = 384, 288
SUB_PX = 30          # 字幕字高（1080p 像素）
INFO_W = W - OB_X - 20   # 信息条可用宽度


# 大疆官网 Osmo Pocket 3 下载中心「DJI OSMO Pocket 3 D-Log M to Rec.709 V1.cube」（2026-10-01 取件）；文件本体不入仓
OFFICIAL_LUT_SHA256 = "b18162854ab47702068410c33afa98a8cb6eef159fc5a04ce0e65fad0fd8947e"
SET709 = "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
TO709 = f"scale=out_color_matrix=bt709:out_range=tv:sws_dither=ed,format=yuv420p,{SET709}"   # 降到 8-bit，误差扩散抖动
TAGS709 = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_lut(a) -> None:
    """LUT 须存在且 sha256 与预期一致（默认＝官方 V1；自测用恒等 LUT 时以 --lut-sha256 另给）。"""
    if not a.lut:
        raise SystemExit("✘ --real-color dlogm 需要 --lut 或环境变量 PG_DLOGM_LUT 指向官方 LUT（不入仓）")
    if not Path(a.lut).is_file():
        raise SystemExit(f"✘ LUT 不存在：{a.lut}")
    got = sha256_file(a.lut)
    if got != a.lut_sha256:
        print(f"✘ LUT sha256 不符：{a.lut}\n  实得 {got}\n  预期 {a.lut_sha256}", file=sys.stderr)
        raise SystemExit(2)


def real_rgb(a) -> str:
    """实拍分支前半：按 bt709 矩阵转 16-bit 平面 RGB，再过 LUT（四面体插值）。"""
    return f"scale=in_color_matrix=bt709:in_range=tv,format=gbrp16le,lut3d=file='{q(a.lut)}':interp=tetrahedral"


def parse_rate(s: str) -> int:
    """ffmpeg 码率写法（60M／800k／纯数字）→ bit/s。"""
    mult = {"k": 1_000, "m": 1_000_000}.get(s[-1].lower())
    return int(float(s[:-1]) * mult) if mult else int(float(s))


def src_bitrate(ffmpeg: str, path: str) -> int:
    """原片视频码率（bit/s）：先取视频流 bit_rate，没有再取容器 bit_rate；都读不到即退出。"""
    ffprobe = str(Path(ffmpeg).with_name("ffprobe"))
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=bit_rate:format=bit_rate",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True).stdout
    for tok in out.split():
        if tok.isdigit() and int(tok) > 0:
            return int(tok)
    raise SystemExit(f"✘ 读不到原片码率：{path}（请用 --master-bitrate 明给，且不低于原片）")


def master_rate(a, ffmpeg: str) -> str:
    """二级母版码率参数：不低于原片。缺省＝原片码率；另给的值低于原片则抬到原片并提示。"""
    src = src_bitrate(ffmpeg, a.overhead)
    if a.master_bitrate and parse_rate(a.master_bitrate) >= src:
        return a.master_bitrate
    if a.master_bitrate:
        print(f"⚠ --master-bitrate {a.master_bitrate} 低于原片 {src} bit/s，按原片取值", file=sys.stderr)
    return str(src)


def build_master(a, ffmpeg: str = "ffmpeg") -> list[str]:
    """二级母版：LUT 后原分辨率 10-bit HEVC Rec.709 交付副本；音轨原样复制。"""
    vf = f"{real_rgb(a)},scale=out_color_matrix=bt709:out_range=tv,format=p010le,{SET709}"
    return [ffmpeg, "-y", "-i", a.overhead, "-vf", vf, "-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-b:v", a.master_bitrate,
            "-tag:v", "hvc1", *TAGS709, "-c:a", "copy", "-movflags", "+faststart", a.master_out]


def ass_x(px: float) -> int:
    return round(px * ASS_RES_X / W)


def ass_y(px: float) -> int:
    return round(px * ASS_RES_Y / H)


def fit_size(text: str, max_size: int, width: int = INFO_W, min_size: int = 14) -> int:
    """drawtext 没有自动换行／缩放：按 CJK 1.0、其他 0.55 个字高估算宽度，缩到不超出信息条宽度。"""
    eff = sum(1.0 if ord(ch) > 0x2E7F else 0.55 for ch in text) or 1
    return max(min_size, min(max_size, int(width / eff)))


def find_ffmpeg(explicit: str | None) -> tuple[str | None, str]:
    """返回 (可用的 ffmpeg 路径或 None, 说明)。候选依次：--ffmpeg、$FFMPEG、PATH、brew --prefix ffmpeg-full；须同时有 subtitles 与 drawtext 滤镜。"""
    cands = [c for c in (explicit, os.environ.get("FFMPEG"), shutil.which("ffmpeg"), str(Path.home() / ".local/ffmpeg-libass/bin/ffmpeg")) if c]
    try:
        prefix = subprocess.run(["brew", "--prefix", "ffmpeg-full"], capture_output=True, text=True, timeout=20).stdout.strip()
        if prefix:
            cands.append(str(Path(prefix) / "bin" / "ffmpeg"))
    except Exception:
        pass
    seen, why = set(), []
    for c in cands:
        if c in seen or not Path(c).is_file():
            continue
        seen.add(c)
        try:
            out = subprocess.run([c, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30).stdout
        except Exception as e:  # noqa: BLE001
            why.append(f"{c}: {e}"); continue
        missing = [f for f in ("subtitles", "drawtext") if f" {f} " not in out]
        if not missing:
            return c, f"ffmpeg={c}"
        why.append(f"{c} 缺滤镜 {'/'.join(missing)}（需 libass／freetype，brew install ffmpeg-full）")
    return None, "；".join(why) or "本机无 ffmpeg（brew install ffmpeg-full）"


def q(s: str) -> str:
    """ffmpeg 滤镜参数转义（冒号、单引号、反斜杠）。"""
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build(a, ffmpeg: str = "ffmpeg") -> list[str]:
    cmd = [ffmpeg, "-y"]
    inputs = 0
    if a.overhead:
        cmd += ["-i", a.overhead]; ov_idx = inputs; inputs += 1
    else:
        ov_idx = None
    if a.onboard:
        cmd += ["-i", a.onboard]; ob_idx = inputs; inputs += 1
    elif a.onboard_frames:
        pat = a.onboard_frames if any(ch in a.onboard_frames for ch in "*?[") else str(Path(a.onboard_frames) / "*.png")   # 目录 → 全部 png；带通配符 → 只取该种子，如 frames/greedy/s1003_t*.png
        cmd += ["-framerate", str(a.fps), "-pattern_type", "glob", "-i", pat]
        ob_idx = inputs; inputs += 1
    else:
        raise SystemExit("✘ 需要 --onboard 或 --onboard-frames")
    f = []
    color = getattr(a, "real_color", "off") != "off"
    if color and ov_idx is None:
        raise SystemExit("✘ --real-color 只作用于 --overhead 实拍输入")
    if color:
        f.append(f"[{ov_idx}:v]{real_rgb(a)},scale={OV}:{OV}:force_original_aspect_ratio=increase:flags=lanczos,crop={OV}:{OV},{TO709},setsar=1[ov]")
    elif ov_idx is not None:
        f.append(f"[{ov_idx}:v]scale={OV}:{OV}:force_original_aspect_ratio=increase,crop={OV}:{OV},setsar=1[ov]")
    else:
        f.append(f"color=c={BG}:s={OV}x{OV}:r=30,drawtext=fontfile='{q(a.font)}':text='{q('overhead: n/a (twin)')}':x=(w-tw)/2:y=(h-th)/2:fontsize=40:fontcolor=0x8f8e86[ov]")
    ob709 = f":out_color_matrix=bt709:out_range=tv,format=yuv420p,{SET709}" if color else ""   # 仿真侧同标 bt709
    f.append(f"[{ob_idx}:v]scale={OB_W}:{OB_H}:force_original_aspect_ratio=decrease{ob709},pad={OB_W}:{OB_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30[ob]")
    f.append(f"color=c={BG}:s={W}x{H}:r=30" + (f",format=yuv420p,{SET709}" if color else "") + "[bg]")
    f.append("[bg][ov]overlay=0:0:shortest=1[t1]")
    f.append(f"[t1][ob]overlay={OB_X}:{OB_Y}:shortest=1[t2]")
    f.append(f"[t2]drawtext=fontfile='{q(a.font)}':text='{q(a.title)}':x={OB_X}:y=120:fontsize={fit_size(a.title, 36)}:fontcolor=white[t3]")
    f.append(f"[t3]drawtext=fontfile='{q(a.font)}':text='{q(a.caption)}':x={OB_X}:y=170:fontsize={fit_size(a.caption, 22)}:fontcolor=0xc3c2b7[t4]")
    style = (f"FontName={a.font_name},FontSize={ass_y(SUB_PX)},Alignment=2,MarginV={ass_y(60)},MarginL={ass_x(OB_X)},MarginR={ass_x(60)},"
             "Outline=1,Shadow=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000")
    sub = f"[t4]subtitles='{q(a.srt)}':force_style='{q(style)}'"
    if a.fontsdir:
        sub += f":fontsdir='{q(a.fontsdir)}'"
    f.append(sub + "[v]")
    cmd += ["-filter_complex", ";".join(f), "-map", "[v]"]
    if a.mute or ov_idx is None:
        cmd += ["-an"]
    else:
        cmd += ["-map", f"{ov_idx}:a?", "-c:a", "aac", "-b:a", "96k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]
    if color:
        cmd += TAGS709
    cmd += ["-movflags", "+faststart", a.out]
    return cmd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--overhead"); ap.add_argument("--onboard"); ap.add_argument("--onboard-frames")
    ap.add_argument("--fps", type=float, default=0.4, help="帧序列的帧率（孪生每步 1 帧 → 0.4 ≈ 每步 2.5 s）")
    ap.add_argument("--srt", required=True); ap.add_argument("--title", required=True)
    ap.add_argument("--caption", default="stop · look · think · act  |  no narration · bilingual subtitles  |  raw logs & unedited video published")
    ap.add_argument("--out", required=True); ap.add_argument("--mute", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--font", default="/System/Library/Fonts/Hiragino Sans GB.ttc", help="drawtext 字体文件（macOS 公开路径；PingFang 在 AssetsV2 私有资产目录，libass 打不开其 UI 变体）")
    ap.add_argument("--font-name", default="Hiragino Sans GB", help="字幕字体名（libass 经 CoreText 解析）"); ap.add_argument("--fontsdir", help="额外字体目录（如 fc-list 查到的 PingFang.ttc 所在目录）")
    ap.add_argument("--ffmpeg", help="ffmpeg 可执行文件（默认按 $FFMPEG → PATH → brew --prefix ffmpeg-full 查找）")
    ap.add_argument("--real-color", choices=["off", "dlogm"], default="off", help="实拍色彩转换：off＝不转换（默认，旧行为）；dlogm＝D-Log M 10-bit 经官方 LUT 转 Rec.709")
    ap.add_argument("--lut", default=os.environ.get("PG_DLOGM_LUT"), help="LUT 路径（默认取 $PG_DLOGM_LUT；文件不入仓）")
    ap.add_argument("--lut-sha256", default=OFFICIAL_LUT_SHA256, help="LUT 预期 sha256（默认＝官方 V1）")
    ap.add_argument("--master-out", help="另出 LUT 后 10-bit HEVC Rec.709 母版（须 --real-color dlogm；存本机素材目录，不入仓）")
    ap.add_argument("--master-bitrate", help="二级母版码率参数（缺省＝原片视频码率；低于原片时抬到原片）")
    a = ap.parse_args(argv)
    if a.master_out and a.real_color == "off":
        ap.error("--master-out 须配 --real-color dlogm")
    if a.real_color != "off" and not a.dry_run:
        check_lut(a)
    ffmpeg, why = (None, "dry-run") if a.dry_run else find_ffmpeg(a.ffmpeg)
    cmd = build(a, ffmpeg or "ffmpeg")
    printable = " ".join(f"'{c}'" if any(ch in c for ch in " ;[]()|'") else c for c in cmd)
    if a.dry_run or not ffmpeg:
        if not a.dry_run:
            print(f"⚠ 没有可用的 ffmpeg：{why}；只打印命令：", file=sys.stderr)
        print(printable)
        return 0 if a.dry_run else 1
    print(f"# {why}\n{printable}")
    if a.master_out:
        a.master_bitrate = master_rate(a, ffmpeg)
        mcmd = build_master(a, ffmpeg)
        print(" ".join(f"'{c}'" if any(ch in c for ch in " ;[]()|'") else c for c in mcmd))
        rc = subprocess.call(mcmd)
        if rc:
            return rc
        with open(Path(a.master_out).parent / "SHA256SUMS", "a", encoding="utf-8") as fh:   # shasum 原生行格式
            fh.write(f"{sha256_file(a.master_out)}  {Path(a.master_out).name}\n")
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
