#!/usr/bin/env python3
"""失败模式三分类表（内部工单，预登记 2026-10-09）。

只读：读 run 目录的 results.csv 与 logs/<agent>/seed<N>.jsonl，不改 harness/、twin/、episodes/；不入 prereg 监视件。
对象：c174ad7 正式批（episodes/runs/2026-09-25-pilot01，三模型各 N=30）；random 基线同列作参照
（episodes/runs/2026-09-25-pilot01-baselines，只取 random）。若 (a) 走 v1 退路，对 v1 正式批跑同一脚本。

判定（成功回合单列「完成」，不进三类；失败回合按顺序互斥、取第一个命中）：
  完成 : results.csv success == 1（协议 §5：5 个检查点全部到达）。
  F1 解析或格式失败 : 日志里 decision_valid == false 的步数 ≥ 该回合总步数的一半（invalid*2 >= steps）。
  F2 未动           : 不属 F1，且回合累计位移 < DISP_MIN_M（= 到达半径常量 0.40 m，twin/configs/course01.yaml）。
                      累计位移取 results.csv 的 traveled_m（harness 逐步累加，含第 0 步；日志里的 pose 是动作后位姿、无起点，
                      由日志相邻位姿累加会少第 0 步 ≤ 0.20 m，故只作交叉核对列 disp_log_m）。
                      日志无位姿且 results.csv 无 traveled_m → 位移记「不可得」，改按有效前进动作数 == 0 判
                      （decision_valid 且 action == forward 的步数），表注写明。
  F3 行进后碰撞或超步 : 其余失败回合。
阈值事后不改；要改另出 v2 表，两表并列（文件名带 -v2）。

用法（仓根）：
  python3 tools/failure_modes.py --run episodes/runs/2026-09-25-pilot01 \
      --baseline episodes/runs/2026-09-25-pilot01-baselines --baseline-agent random \
      --out-dir audits/first-issue-due-diligence
产物：<out-dir>/failure-modes-<run 名>.csv（逐回合）＋ failure-modes-<run 名>.md（汇总表＋表注）。
"""
from __future__ import annotations
import argparse, csv, json, math, os, sys

DISP_MIN_M = 0.40          # 到达半径常量（course01.yaml reach_radius_m）
F1_FRACTION = 0.5          # 无效步占比阈值（≥ 一半）
FORWARD_ACTIONS = {"forward"}

def read_results(run: str) -> dict:
    out = {}
    with open(os.path.join(run, "results.csv"), encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out[(r["agent"], int(r["seed"]))] = r
    return out

def read_log(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def classify(res: dict | None, log: list[dict]) -> dict:
    steps = len(log)
    invalid = sum(1 for r in log if not r.get("decision_valid", True))
    fwd_valid = sum(1 for r in log if r.get("decision_valid", True) and r.get("action") in FORWARD_ACTIONS)
    poses = [r["pose"] for r in log if isinstance(r.get("pose"), dict)]
    disp_log = None
    if len(poses) >= 1:
        disp_log = 0.0
        for a, b in zip(poses, poses[1:]):
            disp_log += math.hypot(b["x"] - a["x"], b["y"] - a["y"])
    traveled = None
    if res is not None and res.get("traveled_m", "") != "":
        traveled = float(res["traveled_m"])
    success = int(res["success"]) == 1 if res is not None else False
    collisions = int(float(res["collisions"])) if res is not None else None
    disp_source = "results.traveled_m" if traveled is not None else ("log.pose" if disp_log is not None else "不可得")
    disp = traveled if traveled is not None else disp_log
    if success:
        cls, why = "完成", "success=1"
    elif steps > 0 and invalid * 2 >= steps:
        cls, why = "F1", f"invalid {invalid}/{steps}"
    elif disp is not None and disp < DISP_MIN_M:
        cls, why = "F2", f"{disp_source} {disp:.3f} < {DISP_MIN_M}"
    elif disp is None and fwd_valid == 0:
        cls, why = "F2", "位移不可得；有效前进动作数 0"
    else:
        cls, why = "F3", f"collisions={collisions} steps={steps}"
    # 交叉核对：两种位移对阈值的判断是否一致（仅在两者都有时）
    cross = ""
    if traveled is not None and disp_log is not None:
        cross = "一致" if (traveled < DISP_MIN_M) == (disp_log < DISP_MIN_M) else "不一致"
    return dict(cls=cls, why=why, steps=steps, invalid_steps=invalid, forward_valid_steps=fwd_valid,
                traveled_m=("" if traveled is None else f"{traveled:.4f}"),
                disp_log_m=("" if disp_log is None else f"{disp_log:.4f}"),
                disp_source=disp_source, disp_cross_check=cross,
                collisions=("" if collisions is None else collisions),
                sim_score=(res.get("sim_score", "") if res else ""))

def run_dir_episodes(run: str, agents: list[str] | None):
    results = read_results(run)
    logs_root = os.path.join(run, "logs")
    found = sorted(os.listdir(logs_root))
    if agents:
        missing = [a for a in agents if a not in found]
        if missing:
            sys.exit(f"✘ {run} 缺日志目录：{missing}")
        found = [a for a in found if a in agents]
    for agent in found:
        d = os.path.join(logs_root, agent)
        for fn in sorted(os.listdir(d)):
            if not (fn.startswith("seed") and fn.endswith(".jsonl")):
                continue
            seed = int(fn[4:-6])
            yield agent, seed, results.get((agent, seed)), read_log(os.path.join(d, fn))

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="正式批 run 目录")
    ap.add_argument("--baseline", help="基线 run 目录（参照列）")
    ap.add_argument("--baseline-agent", default="random")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    tag = os.path.basename(os.path.normpath(a.run))
    rows = []
    for agent, seed, res, log in run_dir_episodes(a.run, None):
        rows.append(dict(run=tag, agent=agent, seed=seed, **classify(res, log)))
    if a.baseline:
        btag = os.path.basename(os.path.normpath(a.baseline))
        for agent, seed, res, log in run_dir_episodes(a.baseline, [a.baseline_agent]):
            rows.append(dict(run=btag, agent=agent, seed=seed, **classify(res, log)))
    cols = ["run", "agent", "seed", "cls", "why", "steps", "invalid_steps", "forward_valid_steps",
            "traveled_m", "disp_log_m", "disp_source", "disp_cross_check", "collisions", "sim_score"]
    csv_path = os.path.join(a.out_dir, f"failure-modes-{tag}.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    # 汇总
    agents = []
    for r in rows:
        k = (r["run"], r["agent"])
        if k not in agents: agents.append(k)
    lines = [f"# 失败模式三分类表 · {tag}（内部工单）", "",
             f"> 判据见 `tools/failure_modes.py` 文件头（预登记提交先于本表）；阈值 DISP_MIN_M={DISP_MIN_M}、F1 占比≥{F1_FRACTION}。逐回合明细 `failure-modes-{tag}.csv`。", "",
             "| run | agent | N | 完成 | F1 解析或格式失败 | F2 未动 | F3 行进后碰撞或超步 | 位移不可得回合 | 位移交叉核对不一致 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for run, agent in agents:
        sub = [r for r in rows if r["run"] == run and r["agent"] == agent]
        c = lambda k: sum(1 for r in sub if r["cls"] == k)
        na = sum(1 for r in sub if r["disp_source"] == "不可得")
        mis = sum(1 for r in sub if r["disp_cross_check"] == "不一致")
        lines.append(f"| {run} | {agent} | {len(sub)} | {c('完成')} | {c('F1')} | {c('F2')} | {c('F3')} | {na} | {mis} |")
    lines += ["", "表注：位移取 results.csv `traveled_m`（含第 0 步）；`disp_log_m` 由日志相邻位姿累加（无起点、少第 0 步），只作交叉核对；"
              "「不一致」＝两种位移对 0.40 m 阈值判断相反的回合数（有则逐回合在 csv 的 `disp_cross_check` 列可查）。位移不可得时按有效前进动作数 == 0 判 F2。"]
    md_path = os.path.join(a.out_dir, f"failure-modes-{tag}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[4:]))
    print(f"写出 {csv_path}（{len(rows)} 回合）、{md_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
