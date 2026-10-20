#!/usr/bin/env python3
"""首期视频组装（内部工单 P1；runbook §5.1／docs/video-template.md §0 首期配置）：纯仿真渲染、无旁白、字幕卡，中英两版。

脚本＝首期讲法 v1 五句逐句展开（notes.md「首期讲法 v1」节原文，不另立口径）；素材只取 `episodes/runs/2026-09-25-pilot01`
与三条脚本基线 `…-baselines` 的回合，由 `tools/replay_frames.py` 按日志回放出送模帧＋俯视帧；画面内表格数字只读流水线产物
（results.csv／summary.csv／failure-modes csv／(a) 批 summary.csv），不手打。

结构（§5.1）：头条结论 → 同布局五路俯视同步回放（三家＋A*＋random，seed 1000）→ 三家最高分与中位回合双画框
→ 讲法②③（＋三分类表）④⑤（＋基线与天花板表）→ 真机列「待锚（第二期）」＋征集入口 → 片尾站点链接。
X 剪辑＝头条 → 五路同步 → 待锚＋征集＋链接。

选段规则（§0）：每家取中位仿真分回合一个（降序第 15 位）、最高分回合一个，同分取种子号小者，两处都跳过 seed 1000；A*／random 与五路同步段取 seed 1000（同布局）。
选法与种子号写入 `<edition>/video-cut.md`（候选段表随附，交主理人定剪）。

用法（仓根）：
  .venv/bin/python tools/make_edition_video.py --edition 2026-10-21-pilot01 [--lang zh,en] [--step-seconds 0.15] [--skip-replay]
      [--run-models episodes/runs/<批>] [--run-baselines episodes/runs/<基线批>]      # v1 落地后换 run，回合表按规则自动重算（补丁1 B）
文字卡停留＝按字数算（中文 ≤5 字/s、英文 ≤3 词/s，取整秒、下限 6 s）；主片 120–180 s、X 剪辑 30–45 s 为硬限，越界即退出。
站点地址唯一真源＝site/config.json site_url（页脚与片尾读此；posts/ 四篇与 notes 两版须一致，工具自检不符即退出）。
产物（不入仓，`episodes/editions/*/video/` 在 .gitignore）：<edition>/video/<edition>_main_<lang>.mp4、<edition>_x_<lang>.mp4、
  frames/、seg/、cards/、subtitles/、selection.json；入仓件只有 <edition>/video-cut.md（本工具写候选段表）。
"""
from __future__ import annotations

import argparse
import csv
import re
import importlib.util
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


cv = _load("compose_video")
rf = _load("replay_frames")

W, H, BG = 1920, 1080, "#121211"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
MODELS = ["qwen3-vl-plus--nothink--official", "glm-5v-turbo--nothink--official", "deepseek-flash--nothink--official"]
SHORT = {"qwen3-vl-plus--nothink--official": "qwen3-vl-plus", "glm-5v-turbo--nothink--official": "glm-5v-turbo",
         "deepseek-flash--nothink--official": "deepseek-flash", "astar": "A*", "random": "random", "greedy": "greedy"}
RUN_MODELS = "episodes/runs/2026-09-25-pilot01"
RUN_BASE = "episodes/runs/2026-09-25-pilot01-baselines"
RUN_HINT = "audits/first-issue-due-diligence/runs/a-hint-oracle-20261010"
FM_CSV = "audits/first-issue-due-diligence/failure-modes-2026-09-25-pilot01.csv"
SITE_URL = json.load(open(ROOT / "site/config.json", encoding="utf-8"))["site_url"]   # 唯一真源（补丁1 C）
MAIN_LIMIT, X_LIMIT = (120.0, 180.0), (30.0, 45.0)                                      # 2～3 分钟硬限、X 30～45 s
READ_ZH, READ_EN, CARD_MIN = 5.0, 3.0, 6.0                                             # 中文 ≤5 字/s、英文 ≤3 词/s、下限 6 s

# 讲法五句＝notes.md「首期讲法 v1」节原文（裁定 2026-10-10-05）；英文＝notes.en.md 经 render_en 流水线的译文逐字（10-14 对齐）
T = {
 "title": {"zh": "首期榜 · 2026-10-21-pilot01 · Course 01「看图走路」· 协议 v0", "en": "Edition 01 · 2026-10-21-pilot01 · Course 01 Look-and-Go · protocol v0"},
 "s1": {"zh": "① 三家模型在协议 v0 冻结跑批中完成 0～2/30，这个数不来自通路：图像逐字节送达（930/930）、动作「原文→解析→执行」0 不一致（4134 步）、每步附真值规划提示即 10/10（三家，碰撞 0）。",
        "en": "① In the frozen protocol v0 batch the three models completed 0–2/30, and that number does not come from the pipeline: images delivered byte-for-byte (930/930), action \"raw text → parsed → executed\" 0 mismatches (4134 steps), and with a planning hint computed from ground truth attached at every step it is 10/10 (all three, 0 collisions)."},
 "s2": {"zh": "② 单帧探针（定性，1 种子×3 模型）：三家都答对首帧可见检查点牌的数量与颜色——看得见牌，看不懂路；失败落在跨步空间推理与路径决策，不在感知前端、不在 harness。",
        "en": "② Single-frame probe (qualitative, 1 seed × 3 models): all three correctly answered the number and colours of the checkpoint signs visible in the first frame — they can see the signs, they cannot read the route; the failure lies in multi-step spatial reasoning and path decisions, not in the perception front end and not in the harness."},
 "s3": {"zh": "③ 判据脚注：0.40 m 位移门≈两步（未碰前进单步中位 0.186 m）；F2＝模型自行 stop 或原地转向，F3＝碰撞或超步。",
        "en": "③ Criteria footnote: the 0.40 m displacement gate ≈ two steps (median single forward step without contact 0.186 m); F2 = the model stops on its own or turns in place, F3 = collision or step cap exceeded."},
 "s4": {"zh": "④ 80 步预算不是主瓶颈：160 步观察只让 deepseek 多到达 8 次、完成 +1，qwen/glm 新增 0（观察项，不进榜）。",
        "en": "④ The 80-step budget is not the main bottleneck: the 160-step observation only let deepseek reach 8 more checkpoints and complete +1; qwen/glm added 0 (observation item, not on the leaderboard)."},
 "s5": {"zh": "⑤ 「附真值提示 10/10」与三条读真值脚本同列「基线与天花板（读真值·非视觉）」，不进模型榜。",
        "en": "⑤ \"Ground-truth hint 10/10\" sits in the same column as the three ground-truth-reading scripts, \"Baselines & ceiling (reads ground truth · non-visual)\", and is not on the model leaderboard."},
 "sync": {"zh": "同一布局（seed 1000）· 五路俯视同步回放 · 每步 {spf} s", "en": "Same layout (seed 1000) · five overhead replays in sync · {spf} s per step"},
 "fm_title": {"zh": "失败模式三分类（预登记判据；N=30）", "en": "Failure modes, three classes (pre-registered criteria; N=30)"},
 "fm_cols": {"zh": ["模型", "完成", "F1 解析或格式失败", "F2 未动", "F3 行进后碰撞或超步"], "en": ["model", "done", "F1 parse/format", "F2 no displacement", "F3 collision/step limit"]},
 "bl_title": {"zh": "基线与天花板（读真值·非视觉）· 不进模型榜", "en": "Baselines & ceiling (reads ground truth · non-visual) · not on the model board"},
 "bl_cols": {"zh": ["行", "N", "完成", "到达占比", "仿真分"], "en": ["row", "N", "done", "reached frac.", "sim score"]},
 "hint_row": {"zh": "附真值提示（三家各 10，诊断跑批）", "en": "with ground-truth hint (3 × 10, diagnostic)"},
 "real": {"zh": "真机列：待锚（第二期）\n目标窗 11 月底～12 月初，11-02 定日\n\n公开征集：仿真按协议复跑（protocol-v0-prereg）＋真机复跑意向登记；\n真机协议 v0 第二期前发布",
          "en": "Real-robot column: anchor pending (Edition 02)\nTarget window late Nov – early Dec; date set on Nov 2\n\nOpen call: sim re-runs under the protocol (protocol-v0-prereg) + registration of intent for real-robot re-runs;\nreal-robot protocol v0 published before Edition 02"},
 "x_end": {"zh": "真机列：待锚（第二期）· 公开征集见站点\n{url}", "en": "Real-robot column: anchor pending (Edition 02) · open call on the site\n{url}"},
 "end": {"zh": "榜单 · 协议 · 逐步日志 · 原始数据\n{url}\n\n无旁白 · 双语字幕 · 纯仿真渲染 · 失败回合未剪", "en": "Board · protocol · step logs · raw data\n{url}\n\nNo narration · bilingual subtitles · simulation-only render · failures not cut"},
 "ep": {"zh": "{short} · seed {seed} · {kind} · 到达 {cp}/5 · 碰撞事件 {ce} · {steps} 步 · 仿真分 {score}",
        "en": "{short} · seed {seed} · {kind} · reached {cp}/5 · collision events {ce} · {steps} steps · sim {score}"},
 "kind": {"zh": {"best": "最高分回合", "median": "中位回合", "sync": "同布局对照"}, "en": {"best": "best episode", "median": "median episode", "sync": "same-layout reference"}},
 "caption": {"zh": "停-看-想-动 · 无旁白 · 双语字幕 · 日志与原片随发", "en": "stop · look · think · act  |  no narration · bilingual subtitles  |  raw logs & unedited video published"},
}


# ---------- 读流水线产物 ----------
def read_csv(p: str) -> list[dict]:
    with open(ROOT / p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def results(run: str) -> list[dict]:
    return read_csv(f"{run}/results.csv")


def select() -> dict:
    """§0 规则（内部工单 C 补定义，10-14）：每家中位分回合一个＋最高分回合一个；中位＝N=30 取 sim_score 降序第 15 位的分值，
    同分取种子号小者；最高分若为 seed 1000 取次高分者；seed 1000 只在五路同步段出现（中位与最高分两处都跳过它）；astar／random 取 seed 1000。"""
    sel = {}
    rows = results(RUN_MODELS)
    for m in MODELS:
        rs = sorted(((float(r["sim_score"]), int(r["seed"]), r) for r in rows if r["agent"] == m), key=lambda x: (-x[0], x[1]))  # 降序＋种子升序
        med = rs[14][0]                                                     # 降序第 15 位（1-based）的分值；N=30 含 seed 1000
        med_row = next(r for s, sd, r in rs if abs(s - med) < 1e-12 and sd != 1000)   # 同分取种子号小者，跳过 seed 1000
        best_row = next(r for s, sd, r in rs if sd != 1000)                 # 最高分（同分取小）；若为 seed 1000 取次高分者
        sel[m] = {"median": med_row, "best": best_row, "median_score": med}
    base = results(RUN_BASE)
    for b in ("astar", "random"):
        sel[b] = {"sync": next(r for r in base if r["agent"] == b and int(r["seed"]) == 1000)}
    for m in MODELS:
        sel[m]["sync"] = next(r for r in rows if r["agent"] == m and int(r["seed"]) == 1000)
    return sel


def check_site_url(ed: Path) -> None:
    """站点地址唯一真源自检：posts/ 四篇与 notes 两版里出现的 github.io 地址须全等于 site/config.json（补丁1 C）。"""
    bad = []
    for p in sorted(list((ed / "posts").glob("*.md")) + [ed / "notes.md", ed / "notes.en.md"]):
        if not p.exists():
            continue
        for u in set(re.findall(r"https://[\w.-]+\.github\.io/[\w./-]*", p.read_text(encoding="utf-8"))):
            if u.rstrip("/") != SITE_URL.rstrip("/"):
                bad.append(f"{p.relative_to(ROOT)}: {u}")
    if bad:
        raise SystemExit("✘ 站点地址与 site/config.json 不一致：\n  " + "\n  ".join(bad))


# ---------- ffmpeg 基元 ----------
def run(cmd: list[str], log: Path | None = None) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if log:
        log.write_text(" ".join(cmd) + "\n\n" + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"✘ ffmpeg rc {r.returncode}: {cmd[:3]} … {cmd[-1]}")


def n_frames(d: Path, seed: int) -> int:
    return len(list(d.glob(f"s{seed:04d}_t*.png")))


def card_png(lines: list[tuple[str, int, str]], out: Path, header: str | None = None, footer: str | None = None) -> Path:
    """文字卡：lines＝[(文本, 字号, 颜色)]，自动换行居中。"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    def wrap(text: str, font, maxw: int) -> list[str]:
        out_lines = []
        for para in text.split("\n"):
            cur = ""
            for ch in para:
                if d.textlength(cur + ch, font=font) > maxw and cur:
                    # 英文按词回退
                    if ch != " " and " " in cur and not ("一" <= ch <= "鿿"):
                        head, _, tail = cur.rpartition(" ")
                        out_lines.append(head); cur = tail + ch
                    else:
                        out_lines.append(cur); cur = ch.lstrip()
                else:
                    cur += ch
            out_lines.append(cur)
        return out_lines
    blocks = []
    for text, size, color in lines:
        font = ImageFont.truetype(FONT, size)
        for ln in wrap(text, font, 1600):
            blocks.append((ln, font, color, int(size * 1.45)))
        blocks.append(("", font, color, int(size * 0.6)))
    total = sum(b[3] for b in blocks)
    y = (H - total) // 2
    for ln, font, color, lh in blocks:
        if ln:
            d.text(((W - d.textlength(ln, font=font)) / 2, y), ln, font=font, fill=color)
        y += lh
    small = ImageFont.truetype(FONT, 26)
    if header:
        d.text((80, 50), header, font=small, fill="#8f8e86")
    if footer:
        d.text((80, H - 80), footer, font=small, fill="#8f8e86")
    out.parent.mkdir(parents=True, exist_ok=True); img.save(out)
    return out


def table_png(title: str, cols: list[str], rows: list[list[str]], out: Path, header: str, footer: str | None = None) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    ft = ImageFont.truetype(FONT, 44); fh = ImageFont.truetype(FONT, 30); fc = ImageFont.truetype(FONT, 32); fs = ImageFont.truetype(FONT, 26)
    d.text((80, 50), header, font=fs, fill="#8f8e86")
    d.text(((W - d.textlength(title, font=ft)) / 2, 150), title, font=ft, fill="white")
    n = len(cols); x0, x1 = 160, W - 160; y = 300; rh = 78
    share = [2.0] + [1.0] * (n - 1)                      # 首列（行名）加宽
    xs = [x0 + (x1 - x0) * sum(share[:j]) / sum(share) for j in range(n)]
    for j, c in enumerate(cols):
        d.text((xs[j] + 20, y), c, font=fh, fill="#c3c2b7")
    y += rh; d.line((x0, y - 12, x1, y - 12), fill="#3a3a38", width=2)
    for r in rows:
        for j, c in enumerate(r):
            d.text((xs[j] + 20, y), str(c), font=fc, fill="white")
        y += rh; d.line((x0, y - 12, x1, y - 12), fill="#2a2a28", width=1)
    if footer:
        d.text((80, H - 80), footer, font=fs, fill="#8f8e86")
    out.parent.mkdir(parents=True, exist_ok=True); img.save(out)
    return out


def read_secs(text: str, lang: str) -> float:
    """停留时长：中文按非空白字符数 /5、英文按词数 /3，向上取整秒，下限 6 s（补丁1 C）。"""
    import math as _m
    if lang == "zh":
        cjk = len(re.findall(r"[\u3000-\u9fff\uff00-\uffef]", text))              # 中文字（含全角标点）按 5 字/s
        latin = len(re.sub(r"[\u3000-\u9fff\uff00-\uffef]", " ", text).split())  # 夹杂的数字／代码／网址按 3 词/s
        secs = cjk / READ_ZH + latin / READ_EN
    else:
        secs = len(text.split()) / READ_EN
    return float(max(CARD_MIN, _m.ceil(secs)))


def png_to_seg(ffmpeg: str, png: Path, secs: float, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg, "-y", "-loop", "1", "-framerate", "30", "-i", str(png), "-t", f"{secs:.2f}", "-vf", "format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30", "-an", "-movflags", "+faststart", str(out)])
    return out


def q(s: str) -> str:
    return cv.q(s)


def sync_seg(ffmpeg: str, frames: Path, agents: list[str], seed: int, fps: float, lang: str, sel: dict, out: Path, hold: float = 1.0) -> tuple[Path, float]:
    """五路俯视同步：3＋2 栅格，每格 480×480＋40 px 标签带；短回合末帧停帧到最长者＋hold。"""
    durs = [n_frames(frames / f"{a}__s{seed}" / "overhead", seed) / fps for a in agents]
    total = max(durs) + hold
    cmd = [ffmpeg, "-y"]
    for a in agents:
        cmd += ["-framerate", str(fps), "-pattern_type", "glob", "-i", str(frames / f"{a}__s{seed}" / "overhead" / f"s{seed:04d}_t*.png")]
    from PIL import ImageFont
    P, BAND, GAP = 468, 60, 8                      # 格宽、标题带高、行距；3＋2 栅格 2×(P+BAND)+GAP ≤ 1080
    def fit(text: str, max_size: int, min_size: int = 14) -> int:
        """按实际字体量宽，缩到本格宽内；缩到下限仍超宽＝渲染失败（补丁1 C 自检）。"""
        for s in range(max_size, min_size - 1, -1):
            if ImageFont.truetype(FONT, s).getlength(text) <= P - 16:
                return s
        raise SystemExit(f"✘ 五路同步段标题超出格宽（{P} px）：{text!r}")
    f = []
    for i, (a, dur) in enumerate(zip(agents, durs)):
        r = sel[a]["sync"]
        full = T["ep"][lang].format(short=SHORT[a], seed=seed, kind=T["kind"][lang]["sync"], cp=r["checkpoints_reached"], ce=r["collision_events"], steps=r["steps"], score=r["sim_score"])
        line1 = SHORT[a]
        line2 = full.split(" · ", 3)[3]            # 去掉「名 · seed · 种类」，只留结果四项
        s1, s2 = fit(line1, 26), fit(line2, 20)
        f.append(f"[{i}:v]scale={P}:{P},setsar=1,tpad=stop_mode=clone:stop_duration={total - dur:.3f},pad={P}:{P + BAND}:0:{BAND}:color={BG},"
                 f"drawtext=fontfile='{q(FONT)}':text='{q(line1)}':x=(w-tw)/2:y=4:fontsize={s1}:fontcolor=white,"
                 f"drawtext=fontfile='{q(FONT)}':text='{q(line2)}':x=(w-tw)/2:y={BAND - s2 - 6}:fontsize={s2}:fontcolor=0xc3c2b7[p{i}]")
    x3 = (W - 3 * P) // 2; x2 = (W - 2 * P) // 2; y2 = GAP + P + BAND + GAP
    layout = f"{x3}_{GAP}|{x3 + P}_{GAP}|{x3 + 2 * P}_{GAP}|{x2}_{y2}|{x2 + P}_{y2}"
    f.append("".join(f"[p{i}]" for i in range(5)) + f"xstack=inputs=5:layout={layout}:fill={BG.replace('#', '0x')}[g]")
    f.append(f"[g]pad={W}:{H}:0:0:color={BG},fps=30[v]")
    run(cmd + ["-filter_complex", ";".join(f), "-map", "[v]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(out)], out.with_suffix(".log"))
    return out, total


def dual_seg(ffmpeg: str, frames: Path, agent: str, seed: int, fps: float, lang: str, row: dict, kind: str, edition: str,
             subs_dir: Path, out: Path, hold: float = 1.0, min_secs: float = 3.0) -> tuple[Path, float]:
    """双画框：左俯视 1080²、右机载 800×600（与 compose_video.py 同布局）、信息条、底部双语字幕（make_subtitles 产物烧录）。"""
    d = frames / f"{agent}__s{seed}"
    n = n_frames(d / "eye", seed)
    base = n / fps
    total = max(base + hold, min_secs)
    srt = subs_dir / f"{agent}_s{seed}"
    log = ROOT / ("%s/logs/%s/seed%d.jsonl" % (RUN_BASE if agent in ("astar", "random", "greedy") else RUN_MODELS, agent, seed))
    subprocess.run([sys.executable, str(ROOT / "tools/make_subtitles.py"), str(log), "--model", agent, "--edition", edition, "--protocol", "v0",
                    "--step-seconds", str(1 / fps), "--intro", "0", "--tail", str(total - base), "--out", str(srt)], check=True, capture_output=True)
    title = f"{edition} · {SHORT[agent]} · seed {seed} · v0"
    sub_line = T["ep"][lang].format(short=SHORT[agent], seed=seed, kind=T["kind"][lang][kind], cp=row["checkpoints_reached"], ce=row["collision_events"], steps=row["steps"], score=row["sim_score"])
    style = (f"FontName=Hiragino Sans GB,FontSize={cv.ass_y(cv.SUB_PX)},Alignment=2,MarginV={cv.ass_y(60)},MarginL={cv.ass_x(cv.OB_X)},MarginR={cv.ass_x(60)},"
             "Outline=1,Shadow=0,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000")
    srt_file = srt.with_suffix(".srt") if lang == "zh" else srt.with_suffix(".en.srt")
    f = [f"[0:v]scale={cv.OV}:{cv.OV},setsar=1,tpad=stop_mode=clone:stop_duration={total - base:.3f}[ov]",
         f"[1:v]scale={cv.OB_W}:{cv.OB_H}:force_original_aspect_ratio=decrease,pad={cv.OB_W}:{cv.OB_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,tpad=stop_mode=clone:stop_duration={total - base:.3f}[ob]",
         f"color=c={cv.BG}:s={W}x{H}:r=30[bg]", "[bg][ov]overlay=0:0:shortest=1[t1]", f"[t1][ob]overlay={cv.OB_X}:{cv.OB_Y}:shortest=1[t2]",
         f"[t2]drawtext=fontfile='{q(FONT)}':text='{q(title)}':x={cv.OB_X}:y=120:fontsize={cv.fit_size(title, 36)}:fontcolor=white[t3]",
         f"[t3]drawtext=fontfile='{q(FONT)}':text='{q(T['caption'][lang])}':x={cv.OB_X}:y=170:fontsize={cv.fit_size(T['caption'][lang], 22)}:fontcolor=0xc3c2b7[t4]",
         f"[t4]drawtext=fontfile='{q(FONT)}':text='{q(sub_line)}':x={cv.OB_X}:y=860:fontsize={cv.fit_size(sub_line, 24)}:fontcolor=0xc3c2b7[t5]",
         f"[t5]subtitles='{q(str(srt_file))}':force_style='{q(style)}',fps=30[v]"]
    cmd = [ffmpeg, "-y", "-framerate", str(fps), "-pattern_type", "glob", "-i", str(d / "overhead" / f"s{seed:04d}_t*.png"),
           "-framerate", str(fps), "-pattern_type", "glob", "-i", str(d / "eye" / f"s{seed:04d}_t*.png"),
           "-filter_complex", ";".join(f), "-map", "[v]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(out)]
    run(cmd, out.with_suffix(".log"))
    return out, total


def concat(ffmpeg: str, segs: list[Path], out: Path) -> None:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p}'\n" for p in segs), encoding="utf-8")
    run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out)])


def fmt_t(s: float) -> str:
    return f"{int(s // 60):02d}:{s % 60:05.2f}"


# ---------- 主流程 ----------
def main(argv=None) -> int:
    global RUN_MODELS, RUN_BASE
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--edition", required=True); ap.add_argument("--lang", default="zh,en")
    ap.add_argument("--step-seconds", type=float, default=0.15); ap.add_argument("--skip-replay", action="store_true")
    ap.add_argument("--ffmpeg"); ap.add_argument("--run-models", default=RUN_MODELS); ap.add_argument("--run-baselines", default=RUN_BASE)
    a = ap.parse_args(argv)
    RUN_MODELS, RUN_BASE = a.run_models.strip("/"), a.run_baselines.strip("/")
    check_site_url(ROOT / "episodes/editions" / a.edition)
    ffmpeg, why = cv.find_ffmpeg(a.ffmpeg)
    if not ffmpeg:
        raise SystemExit("✘ " + why)
    ed = ROOT / "episodes/editions" / a.edition
    vd = ed / "video"; frames = vd / "frames"; seg = vd / "seg"; cards = vd / "cards"; subs = vd / "subtitles"
    for p in (frames, seg, cards, subs):
        p.mkdir(parents=True, exist_ok=True)
    fps = 1 / a.step_seconds
    sel = select()
    json.dump({k: {kk: (vv if not isinstance(vv, dict) else {"seed": vv["seed"], "sim_score": vv["sim_score"], "steps": vv["steps"]}) for kk, vv in v.items()} for k, v in sel.items()},
              open(vd / "selection.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 1 回放出帧
    need = [(m, int(sel[m][k]["seed"]), RUN_MODELS) for m in MODELS for k in ("best", "median")] + [(m, 1000, RUN_MODELS) for m in MODELS] + [(b, 1000, RUN_BASE) for b in ("astar", "random")]
    seen = set()
    for agent, seed, runp in need:
        if (agent, seed) in seen:
            continue
        seen.add((agent, seed))
        out = frames / f"{agent}__s{seed}"
        if a.skip_replay and (out / "replay.json").exists():
            continue
        rc = rf.replay(str(ROOT / runp), agent, seed, str(out), overhead=True, overhead_size=1080, verify_frames=True)
        if rc != 0:
            raise SystemExit(f"✘ 回放失败 rc {rc}: {agent} seed {seed}")

    # 2 表格数据（只读流水线产物）
    fm = read_csv(FM_CSV)
    def fm_row(agent):
        rs = [r for r in fm if r["agent"] == agent]
        return [SHORT[agent], sum(r["cls"] == "完成" for r in rs), sum(r["cls"] == "F1" for r in rs), sum(r["cls"] == "F2" for r in rs), sum(r["cls"] == "F3" for r in rs)]
    fm_rows = [fm_row(m) for m in MODELS] + [fm_row("random")]
    base_sum = {r["agent"]: r for r in read_csv(f"{RUN_BASE}/summary.csv")}
    base_res = results(RUN_BASE)
    def bl_row(agent):
        s = base_sum[agent]; done = sum(int(r["success"]) for r in base_res if r["agent"] == agent)
        return [SHORT[agent], s["n"], done, f"{float(s['reached_frac_mean']):.3f}", f"{float(s['sim_score_mean']):.4f}"]
    hint = read_csv(f"{RUN_HINT}/summary.csv"); hint_res = results(RUN_HINT)
    hint_done = sum(int(r["success"]) for r in hint_res); hint_n = sum(int(r["n"]) for r in hint)
    bl_rows = [bl_row(b) for b in ("astar", "greedy", "random")]

    report = {}
    for lang in a.lang.split(","):
        hdr = T["title"][lang]; foot = SITE_URL
        C = cards / lang
        def card(name, text, size=40):
            secs = read_secs(text, lang)
            png = card_png([(text, size, "white")], C / f"{name}.png", header=hdr, footer=foot)
            return png_to_seg(ffmpeg, png, secs, seg / f"{lang}_{name}.mp4"), secs
        timeline: list[tuple[str, Path, float]] = []
        def add(name, pathdur):
            timeline.append((name, pathdur[0], pathdur[1]))
        add("s1", card("s1", T["s1"][lang]))
        add("sync", sync_seg(ffmpeg, frames, MODELS + ["astar", "random"], 1000, fps, lang, sel, seg / f"{lang}_sync.mp4"))
        for kind in ("best", "median"):
            for m in MODELS:
                r = sel[m][kind]
                add(f"{kind}_{SHORT[m]}", dual_seg(ffmpeg, frames, m, int(r["seed"]), fps, lang, r, kind, a.edition, subs, seg / f"{lang}_{kind}_{SHORT[m]}.mp4"))
        add("s2", card("s2", T["s2"][lang]))
        add("s3", card("s3", T["s3"][lang]))
        png = table_png(T["fm_title"][lang], T["fm_cols"][lang], [[str(x) for x in r] for r in fm_rows], C / "fm.png", hdr)
        add("fm", (png_to_seg(ffmpeg, png, 8, seg / f"{lang}_fm.mp4"), 8))
        add("s4", card("s4", T["s4"][lang]))
        add("s5", card("s5", T["s5"][lang]))
        png = table_png(T["bl_title"][lang], T["bl_cols"][lang], [[str(x) for x in r] for r in bl_rows] + [[T["hint_row"][lang], str(hint_n), str(hint_done), "1.000", "1.0000"]], C / "bl.png", hdr)
        add("bl", (png_to_seg(ffmpeg, png, 8, seg / f"{lang}_bl.mp4"), 8))
        add("real", card("real", T["real"][lang], 36))
        add("end", card("end", T["end"][lang].format(url=SITE_URL), 36))
        xe = card("x_end", T["x_end"][lang].format(url=SITE_URL), 36)
        xcut = [timeline[0], timeline[1], ("x_end", xe[0], xe[1])]
        tm, tx = sum(d for _, _, d in timeline), sum(d for _, _, d in xcut)
        if not (MAIN_LIMIT[0] <= tm <= MAIN_LIMIT[1]) or not (X_LIMIT[0] <= tx <= X_LIMIT[1]):
            raise SystemExit(f"✘ 时长越界：main {tm:.1f} s（限 {MAIN_LIMIT}）／x {tx:.1f} s（限 {X_LIMIT}）；调 --step-seconds 或拆卡")
        concat(ffmpeg, [p for _, p, _ in timeline], vd / f"{a.edition}_main_{lang}.mp4")
        concat(ffmpeg, [p for _, p, _ in xcut], vd / f"{a.edition}_x_{lang}.mp4")
        report[lang] = {"main": [(n, d) for n, _, d in timeline], "x": [(n, d) for n, _, d in xcut]}
        print(f"✔ {lang}: main {tm:.1f} s（{len(timeline)} 段）, x {tx:.1f} s")

    # 3 候选段表（入仓件）：栏一＝规则（主理人拍板对象，补丁1 B／裁定 2026-10-14-02）；栏二＝当前批次按规则算出的回合表（自动）
    import hashlib as _h
    def sha12(p):
        return _h.sha256((ROOT / p).read_bytes()).hexdigest()[:12]
    lines = [f"# 首期视频选段（内部工单 B；工具 `tools/make_edition_video.py`，每步 {a.step_seconds} s）", "",
             "## 栏一 · 选段规则（定剪对象＝本栏六条＋版式；状态：**已定 10-14**——主理人 10-14 委托 CSO 裁「准」，裁定 2026-10-14-05 ①；CSO 复核若有改以补丁出，不重拍、不改日期；裁定 2026-10-14-02；CSO 复核补丁＝内部工单 C（10-14）：第 1 条两处半句）", "",
             "1. 每家取**中位仿真分回合一个**（中位＝N=30 取 `sim_score` 降序第 15 位，同分取种子号小者）＋**最高分回合一个**（若最高分回合即 seed 1000，取次高分者；seed 1000 只在五路同步段出现），同分取种子号小者（`results.csv` `sim_score`）。",
             "2. **五路同步段**（俯视、3＋2 栅格）取 **seed 1000**：三家＋A*＋random，同布局横向可比。",
             "3. 备选按**次高分**各列三个（去掉已选与 seed 1000），只供替换同类段。",
             "4. 版式：讲法①卡 → 五路同步 → 三家最高分（双画框）→ 三家中位（双画框）→ ②③卡＋三分类表 → ④⑤卡＋基线表 → 真机待锚＋征集卡 → 片尾链接；X 剪辑＝①卡＋五路同步＋待锚一句＋链接。",
             "5. 文字卡停留＝中文 ≤5 字/s、英文 ≤3 词/s 取整秒、下限 6 s；主片 120–180 s、X 30–45 s 硬限；表格数字只读流水线 CSV。",
             "6. 素材只取当前批次与其基线批（见栏二批次标识），由 `tools/replay_frames.py` 按日志回放（位姿与既有帧逐字节核对）；**v1 落地后换 `--run-models`／`--run-baselines` 重跑本工具，栏二自动重算**，成片按规则自动产出，主理人只留否决权。",
             "7. 讲法五句的数字位随公开批（v1）重填，与流水线产物同源、不手写（来源表见 `notes.md`「五句数字位来源」）；句式、顺序、结论不改；10-21 不再拍数字；v1 使任一结论反转（胜者换位、差距符号反转、未达门槛）即停、报 CSO 裁，不自改结论句（裁定 2026-10-14-06）。", "",
             f"## 栏二 · 当前批次按规则算出的回合表（自动；批次＝`{RUN_MODELS}`（results.csv `{sha12(RUN_MODELS + '/results.csv')}`）＋ `{RUN_BASE}`（`{sha12(RUN_BASE + '/results.csv')}`））", "",
             "| 段 | run | agent | seed | 仿真分 | 到达 | 碰撞事件 | 步数 | 主片时间码（zh） | 主片时间码（en） |", "|---|---|---|---|---|---|---|---|---|---|"]
    tcs = {}
    for lang in report:
        t0 = 0.0; tcs[lang] = {}
        for n, d in report[lang]["main"]:
            tcs[lang][n] = (t0, t0 + d); t0 += d
    def tc(n):
        return " | ".join(f"{fmt_t(tcs[l][n][0])}–{fmt_t(tcs[l][n][1])}" if l in tcs else "—" for l in ("zh", "en"))
    for kind in ("best", "median"):
        for m in MODELS:
            r = sel[m][kind]; n = f"{kind}_{SHORT[m]}"
            lines.append(f"| {T['kind']['zh'][kind]} | {Path(RUN_MODELS).name} | {m} | {r['seed']} | {r['sim_score']} | {r['checkpoints_reached']}/5 | {r['collision_events']} | {r['steps']} | {tc(n)} |")
    for ag in MODELS + ["astar", "random"]:
        r = sel[ag]["sync"]
        lines.append(f"| 五路同步（俯视） | {Path(RUN_BASE).name if ag in ('astar', 'random') else Path(RUN_MODELS).name} | {ag} | 1000 | {r['sim_score']} | {r['checkpoints_reached']}/5 | {r['collision_events']} | {r['steps']} | {tc('sync')} |")
    for lang in report:
        lines += ["", f"### 主片分段（{lang}）", "", "| 段 | 起 | 止 | 时长 s |", "|---|---|---|---|"]
        for n, d in report[lang]["main"]:
            lines.append(f"| {n} | {fmt_t(tcs[lang][n][0])} | {fmt_t(tcs[lang][n][1])} | {d:.1f} |")
        lines.append(f"\n合计 {sum(d for _, d in report[lang]['main']):.1f} s；X 剪辑＝{'＋'.join(n for n, _ in report[lang]['x'])}＝{sum(d for _, d in report[lang]['x']):.1f} s。")
    lines += ["", "### 其余候选（次高分各三，未入成片，可替换同类段）", "", "| run | agent | seed | 仿真分 | 到达 | 步数 |", "|---|---|---|---|---|---|"]
    rows = results(RUN_MODELS)
    for m in MODELS:
        rs = sorted((r for r in rows if r["agent"] == m), key=lambda r: (-float(r["sim_score"]), -int(r["checkpoints_reached"]), int(r["seed"])))
        used = {int(sel[m]["best"]["seed"]), int(sel[m]["median"]["seed"]), 1000}
        for r in [x for x in rs if int(x["seed"]) not in used][:3]:
            lines.append(f"| {Path(RUN_MODELS).name} | {m} | {r['seed']} | {r['sim_score']} | {r['checkpoints_reached']}/5 | {r['steps']} |")
    (ed / "video-cut.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"→ {ed / 'video-cut.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
