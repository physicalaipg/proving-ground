#!/usr/bin/env python3
"""(a) ② 动作映射（c174ad7 批 F3 回合）＋ ③ 判据与步长（单步位移分布、glm F2 原始输出判读）—— 只读 c174ad7 正式批日志（内部工单 ②③；会话二 2026-10-10）。

读：episodes/runs/2026-09-25-pilot01/{results.csv,logs/<agent>/seed<N>.jsonl}、基线批 random 日志（如在）、
    audits/first-issue-due-diligence/failure-modes-2026-09-25-pilot01.csv（内部工单 三分类）。不改任何输入。
写（本目录）：a2-action-mapping-c174ad7.csv、a3-step-displacement.csv、a3-glm-f2-review.csv，并打印摘要。
② 口径：每家取补丁13 分类为 F3 的回合、按种子升序前 5 个；逐步「模型输出原文（日志 raw_text，c174ad7 批最长 233 字，未截断）→ Action.parse 解析动作 → 日志 action（实际执行）」；
   一致＝解析动作==执行动作（解析为 None 时执行应为 stop）。
③ 口径：单步位移＝日志相邻位姿欧氏距离（第 1 步起；第 0 步无起点行，不计），按 agent×动作×是否碰撞分组；比值＝该组中位数／0.40。
   glm F2 回合：全部 11 个列出，抽检 3 个＝种子升序前 3；判读由机械规则给出：invalid 步数 >0 → 「空解析」；末步 action==stop 且 JSON 有效 → 「模型自行 stop」；否则 → 「仅原地转向」。
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from harness.interface import Action  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# 缺省＝c174ad7 批；10-20 起可用环境变量换批重跑（公开批 v1：A_RUN=2026-10-15-v1 A_FM=failure-modes-2026-10-15-v1.csv A_SUFFIX=2026-10-15-v1），输入文件只读
RUN_NAME = os.environ.get("A_RUN", "2026-09-25-pilot01")
RUN = os.path.join(ROOT, "episodes", "runs", RUN_NAME)
BASE = os.path.join(ROOT, "episodes", "runs", "2026-09-25-pilot01-baselines")
FM = os.path.join(HERE, os.environ.get("A_FM", "failure-modes-2026-09-25-pilot01.csv"))
SUFFIX = os.environ.get("A_SUFFIX", "c174ad7")
A3_TAG = "" if SUFFIX == "c174ad7" else f"-{SUFFIX}"
THRESH = 0.40


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def pct(xs, q):
    xs = sorted(xs); k = (len(xs) - 1) * q; f = math.floor(k); c = math.ceil(k)
    return xs[f] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)


def main() -> int:
    fm = {(r["agent"], int(r["seed"])): r for r in csv.DictReader(open(FM, encoding="utf-8"))}
    agents = sorted({a for (a, _), r in fm.items() if r["run"].endswith(RUN_NAME) and not a.endswith(("astar", "greedy", "random"))})
    # ---------- ② ----------
    a2 = []; inc_total = 0
    for ag in agents:
        f3 = sorted(s for (a, s), r in fm.items() if a == ag and r["cls"] == "F3")[:5]
        for seed in f3:
            for r in read_jsonl(os.path.join(RUN, "logs", ag, f"seed{seed}.jsonl")):
                p = Action.parse(r["raw_text"]); pa = p.value if p else None
                expect = pa if r["decision_valid"] else "stop"
                ok = expect == r["action"]
                inc_total += (not ok)
                a2.append({"agent": ag, "seed": seed, "step": r["step"], "raw_text_80": r["raw_text"][:80].replace("\n", " "), "raw_len": len(r["raw_text"]),
                           "parsed_action": pa, "decision_valid": r["decision_valid"], "executed_action": r["action"], "consistent": "一致" if ok else "不一致"})
    with open(os.path.join(HERE, f"a2-action-mapping-{SUFFIX}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(a2[0].keys())); w.writeheader(); w.writerows(a2)
    for ag in agents:
        sub = [r for r in a2 if r["agent"] == ag]
        print(f"② {ag}: F3 抽 5 回合 seeds={sorted({r['seed'] for r in sub})} 步数={len(sub)} 不一致={sum(r['consistent'] != '一致' for r in sub)} 原文最长={max(r['raw_len'] for r in sub)} 字")
    # ---------- ③ 单步位移 ----------
    groups = collections.defaultdict(list)
    sources = [(ag, os.path.join(RUN, "logs", ag)) for ag in agents]
    if os.path.isdir(os.path.join(BASE, "logs", "random")):
        sources.append(("random", os.path.join(BASE, "logs", "random")))
    for ag, d in sources:
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".jsonl"):
                continue
            rows = read_jsonl(os.path.join(d, fn))
            for a, b in zip(rows, rows[1:]):
                if not (isinstance(a.get("pose"), dict) and isinstance(b.get("pose"), dict)):
                    continue
                dxy = math.hypot(b["pose"]["x"] - a["pose"]["x"], b["pose"]["y"] - a["pose"]["y"])
                groups[(ag, b["action"], bool(b["collided"]))].append(dxy)
                groups[(ag, "all", None)].append(dxy)
                groups[("合计", b["action"], bool(b["collided"]))].append(dxy)
                groups[("合计", "all", None)].append(dxy)
    a3 = []
    for (ag, act, col), xs in sorted(groups.items(), key=lambda kv: (kv[0][0] == "合计", kv[0][0], kv[0][1], str(kv[0][2]))):
        med = statistics.median(xs)
        a3.append({"agent": ag, "action": act, "collided": "" if col is None else int(col), "n": len(xs), "mean_m": round(statistics.fmean(xs), 4),
                   "p10_m": round(pct(xs, 0.10), 4), "median_m": round(med, 4), "p90_m": round(pct(xs, 0.90), 4), "min_m": round(min(xs), 4), "max_m": round(max(xs), 4),
                   "median_over_0.40": round(med / THRESH, 3), "mean_over_0.40": round(statistics.fmean(xs) / THRESH, 3)})
    with open(os.path.join(HERE, f"a3-step-displacement{A3_TAG}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(a3[0].keys())); w.writeheader(); w.writerows(a3)
    for r in a3:
        if r["agent"] == "合计" or r["action"] == "all":
            print(f"③ {r['agent']:8s} {r['action']:8s} coll={r['collided']!s:5s} n={r['n']:5d} mean={r['mean_m']:.4f} P10={r['p10_m']:.4f} P50={r['median_m']:.4f} P90={r['p90_m']:.4f} "
                  f"min={r['min_m']:.4f} max={r['max_m']:.4f} P50/0.40={r['median_over_0.40']}")
    # ---------- ③ glm F2 ----------
    glm = [a for a in agents if a.startswith("glm")][0]
    f2 = sorted(s for (a, s), r in fm.items() if a == glm and r["cls"] == "F2")
    rev = []
    for i, seed in enumerate(f2):
        rows = read_jsonl(os.path.join(RUN, "logs", glm, f"seed{seed}.jsonl"))
        acts = collections.Counter(r["action"] for r in rows)
        invalid = sum(1 for r in rows if not r["decision_valid"])
        last = rows[-1]
        if invalid > 0:
            judge = "空解析（存在不可解析步）"
        elif last["action"] == "stop" and last["decision_valid"]:
            judge = "模型自行 stop（输出有效 JSON，action=stop）"
        else:
            judge = "仅原地转向（无 stop、无不可解析步，前进步 ≤2）"
        rev.append({"seed": seed, "sampled_3": "抽检" if i < 3 else "", "steps": len(rows), "traveled_m": fm[(glm, seed)]["traveled_m"], "invalid_steps": invalid,
                    "forward": acts.get("forward", 0), "left": acts.get("left", 0), "right": acts.get("right", 0), "stop": acts.get("stop", 0),
                    "stop_step": (last["step"] if last["action"] == "stop" else ""), "reached": last["reached"],
                    "last_raw_text": last["raw_text"].replace("\n", " "), "judgment": judge})
    with open(os.path.join(HERE, f"a3-glm-f2-review{A3_TAG}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rev[0].keys())); w.writeheader(); w.writerows(rev)
    for r in rev:
        print(f"③ glm F2 seed {r['seed']} {r['sampled_3']:2s} steps={r['steps']:2d} traveled={r['traveled_m']} invalid={r['invalid_steps']} f/l/r/s={r['forward']}/{r['left']}/{r['right']}/{r['stop']} "
              f"reached={r['reached']} → {r['judgment']}")
    print(f"== 写出 a2-action-mapping-{SUFFIX}.csv（{len(a2)} 行，不一致 {inc_total}）、a3-step-displacement{A3_TAG}.csv（{len(a3)} 行）、a3-glm-f2-review{A3_TAG}.csv（{len(rev)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
