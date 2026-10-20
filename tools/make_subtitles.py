#!/usr/bin/env python3
"""双语字幕生成（内部工单）：从逐步日志 `logs/<模型>/seed<N>.jsonl` 生成无旁白视频的字幕。
字幕只陈述日志里有的事实（步号、目标检查点、动作、碰撞、重问、模型 note、结果），不写评论。

时间轴：默认取日志每步的 t（epoch 秒）减 --t0（录像起始 epoch 秒；真机录像取 video.csv 的 recorded_at 或录像文件元数据）；
        孪生演示或无可靠时间戳时用 --step-seconds 均匀铺（每步固定秒数）。
输出：<out>.srt（双语两行：中文在上、英文在下，烧录用）＋ <out>.zh.srt ＋ <out>.en.srt（平台分轨上传用）。
用法（仓根）：
  python3 tools/make_subtitles.py episodes/runs/<run>/logs/<模型>/seed1000.jsonl --model <模型> --edition <期> --protocol v0 \
      --step-seconds 2.5 --out episodes/editions/<期>/subtitles/<模型>_seed1000
  python3 tools/make_subtitles.py <jsonl> ... --t0 1790336097.0            # 真机：按日志时间戳对齐录像
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ACTION_ZH = {"forward": "前进", "left": "左转", "right": "右转", "stop": "停止"}
ACTION_EN = {"forward": "forward", "left": "turn left", "right": "turn right", "stop": "stop"}


def ts(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def note_of(raw: str) -> str:
    """模型原始输出若是 JSON，取其 note；否则空。"""
    if not raw:
        return ""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return ""
    try:
        return str(json.loads(m.group(0)).get("note") or "").strip()
    except Exception:
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl"); ap.add_argument("--model", required=True); ap.add_argument("--edition", required=True)
    ap.add_argument("--protocol", default="v0"); ap.add_argument("--out", required=True, help="输出前缀（不含扩展名）")
    ap.add_argument("--t0", type=float, help="录像起始 epoch 秒；给了就按日志 t 对齐")
    ap.add_argument("--step-seconds", type=float, default=2.5, help="无 --t0 时每步铺的秒数")
    ap.add_argument("--intro", type=float, default=3.0); ap.add_argument("--tail", type=float, default=4.0)
    ap.add_argument("--note-chars", type=int, default=70, help="英文行里模型 note 的最大字符数")
    a = ap.parse_args(argv)

    steps = [json.loads(ln) for ln in Path(a.jsonl).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not steps:
        print("✘ 空日志", file=sys.stderr); return 2
    seed = re.search(r"seed(\d+)", Path(a.jsonl).stem)
    seed = seed.group(1) if seed else "?"
    if a.t0 is not None:
        starts = [s["t"] - a.t0 for s in steps]
        if any(x < 0 for x in starts) or any(b < c for b, c in zip(starts[1:], starts)):
            print("✘ 日志时间戳早于 t0 或非单调；检查 --t0", file=sys.stderr); return 2
        ends = starts[1:] + [starts[-1] + a.tail]
        intro = (0.0, max(0.5, starts[0])) if starts[0] > 0.5 else None
    else:
        starts = [a.intro + i * a.step_seconds for i in range(len(steps))]
        ends = [x + a.step_seconds for x in starts]
        intro = (0.0, a.intro)

    cues = []  # (start, end, zh, en)
    if intro:
        cues.append((*intro, f"{a.edition} · {a.model} · 种子 {seed} · 协议 {a.protocol}",
                     f"{a.edition} · {a.model} · seed {seed} · protocol {a.protocol}"))
    reached = collisions = 0
    usd = 0.0
    for i, (s, st, et) in enumerate(zip(steps, starts, ends)):
        act = s.get("action") or "?"
        flags_zh, flags_en = [], []
        if s.get("collided"):
            collisions += 1; flags_zh.append("碰撞"); flags_en.append("collision")
        if s.get("decision_valid") is False:
            flags_zh.append("重问"); flags_en.append("re-ask")
        reached = max(reached, int(s.get("reached") or 0))
        usd += float(s.get("usd_cost") or 0)
        cp = s.get("next_checkpoint")
        zh = f"第 {i + 1} 步 · 目标 {cp} 号 · {ACTION_ZH.get(act, act)}" + "".join(f" · {f}" for f in flags_zh)
        en = f"Step {i + 1} · target #{cp} · {ACTION_EN.get(act, act)}" + "".join(f" · {f}" for f in flags_en)
        note = note_of(s.get("raw_text") or "")
        if note:
            note = note if len(note) <= a.note_chars else note[: a.note_chars - 1] + "…"
            en += f' · "{note}"'
        cues.append((st, et, zh, en))
    last_end = ends[-1]
    n_steps = len(steps)
    cues.append((last_end, last_end + a.tail,
                 f"结果：到达 {reached}/5 · 碰撞 {collisions} 次 · {n_steps} 步 · ${usd:.3f}",
                 f"Result: reached {reached}/5 · {collisions} collisions · {n_steps} steps · ${usd:.3f}"))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    def write(path: Path, pick):
        lines = []
        for n, (st, en, zh, e) in enumerate(cues, 1):
            lines += [str(n), f"{ts(st)} --> {ts(en)}", *pick(zh, e), ""]
        path.write_text("\n".join(lines), encoding="utf-8")

    write(out.with_suffix(".srt"), lambda zh, e: [zh, e])
    write(out.with_suffix(".zh.srt"), lambda zh, e: [zh])
    write(out.with_suffix(".en.srt"), lambda zh, e: [e])
    print(f"✔ {out}.srt / .zh.srt / .en.srt：{len(cues)} 条（{n_steps} 步，时长 ≈{last_end + a.tail:.0f} s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
