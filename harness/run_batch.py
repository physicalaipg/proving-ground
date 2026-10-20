"""批量跑测（PG-001 P5；补丁 3 Q1／Q4）：一条命令跑 M 个 Agent × N 回合，同一组**经可解性筛选**的种子配对，
逐回合 CSV ＋ 每模型汇总 CSV ＋ 种子筛选记录。

用法：
  python -m harness.run_batch --agents astar,greedy,random --n 30                                   # 成本 0：天花板／贪心／随机基线
  python -m harness.run_batch --agents qwen3-vl-plus,claude-opus-5,gemini-3.8-flash --n 30 --budget-usd 60 --preflight
密钥：只从环境变量读（harness/models.yaml 的 key_env）；项目根目录若有 .env（已 gitignore）则自动载入其中尚未设置的变量，不打印值。
开跑前 runner 打印 provider+model（红线：评测批次前 runner 打印 provider+model）。
预算护栏（Q4「不超 $60，逼近即停并报告」）：--budget-usd 为硬上限；累计花费 ≥90% 上限、或按本模型最贵一回合估算再跑一回合会越界，
即停：已完成回合照常汇总，meta.json 记 budget_stop，退出码 3。价格未核实（price_verified=false）的模型成本记 0、护栏失效，故默认拒跑。
种子筛选（Q1）：从 seed0 起逐个做可解性判定（twin/planner.course_plan），取前 N 个可解种子给所有 Agent 共用；
被剔除的种子与理由、剔除率写入 seeds.csv 与 meta.json。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from harness.agents import is_scripted, load_models, load_settings, make_agent, reject_unknown, validate_model_row
from harness.episode import run_episode
from harness.task import PROMPT_PATH, load_task
from twin.arena import sample_layout
from twin.config import load_config
from twin.planner import course_plan
from twin.robot_twin import TwinRobot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_FIELDS = ["agent", "model_id", "seed", "success", "checkpoints_reached", "checkpoint_score", "collisions", "collision_events", "penalty",
             "total_score", "sim_score", "path_ratio", "traveled_m", "ideal_path_m", "steps", "usd_cost", "price_tier", "api_latency_mean_s",
             "api_latency_p95_s", "tokens_in", "tokens_out", "invalid_outputs", "api_errors", "stopped_by_agent", "wall_s"]
SEED_FIELDS = ["seed", "solvable", "reason", "astar_steps", "legs", "used"]


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_env_file(path: str) -> int:
    """极简 .env 读取：KEY=VALUE 行（可带 export 前缀与引号），只填尚未设置的变量；返回载入条数。"""
    if not os.path.exists(path):
        return 0
    n = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


def screen_seeds(cfg: dict, seed0: int, n: int, max_steps: int, max_tries: int | None = None) -> tuple[list[int], list[dict]]:
    """从 seed0 起逐个判可解，凑够 n 个；返回 (采用的种子, 全部筛选记录)。"""
    max_tries = max_tries or max(5 * n, 20)
    used, rows = [], []
    s = seed0
    while len(used) < n and len(rows) < max_tries:
        r = course_plan(cfg, sample_layout(cfg, s), max_steps)
        r["used"] = int(r["solvable"] and len(used) < n)
        rows.append(r)
        if r["solvable"]:
            used.append(s)
        s += 1
    if len(used) < n:
        raise RuntimeError(f"筛选 {len(rows)} 个种子只得 {len(used)} 个可解（需 {n}）：布局参数过紧，见 seeds 记录")
    return used, rows


def summarize(rows: list[dict], cost_unknown: bool, n_planned: int, fx: float = 7.1, ident: dict | None = None, n_checkpoints: int = 5) -> dict:
    """每模型一行。sim_score_mean＝榜单「仿真分」（协议 §仿真分，[0,1]）；total_score_mean 为旧口径对照列。人民币＝美元×fx。
    reached_frac_mean＝到达占比（到达检查点数÷检查点数 的均值；补丁 3 P3 站点辅助列，站点只读不算）。"""
    n = len(rows)
    ident = ident or {}
    f = lambda k: float(np.mean([r[k] for r in rows])) if n else 0.0
    succ = sum(r["success"] for r in rows); usd = sum(r["usd_cost"] for r in rows)
    lat = [r["api_latency_mean_s"] for r in rows]
    sims = [r["sim_score"] for r in rows]
    ci = 1.96 * float(np.std(sims, ddof=1)) / (n ** 0.5) if n > 1 else 0.0
    tiers = sorted({t for r in rows for t in str(r.get("price_tier", "")).split("+") if t})
    return {"agent": rows[0]["agent"] if n else "", "model_id": rows[0]["model_id"] if n else "",
            "vendor": ident.get("vendor", ""), "thinking": ident.get("thinking", ""), "endpoint": ident.get("endpoint", ""),
            "n": n, "n_planned": n_planned, "partial": int(n < n_planned),
            "sim_score_mean": round(f("sim_score"), 4), "sim_score_ci95": round(ci, 4),
            "success_rate": round(succ / n, 4) if n else 0, "reached_frac_mean": round(f("checkpoints_reached") / max(n_checkpoints, 1), 4),
            "checkpoint_score_mean": round(f("checkpoint_score"), 4),
            "collisions_mean": round(f("collisions"), 4), "collision_events_mean": round(f("collision_events"), 4),
            "total_score_mean": round(f("total_score"), 4),
            "path_ratio_mean_success": round(float(np.mean([r["path_ratio"] for r in rows if r["success"]])), 4) if succ else "",
            "usd_total": round(usd, 4), "usd_per_success": round(usd / succ, 4) if succ else "",
            "usd_per_episode": round(usd / n, 4) if n else 0,
            "cny_total": round(usd * fx, 4), "cny_per_success": round(usd * fx / succ, 4) if succ else "",
            "cny_per_episode": round(usd * fx / n, 4) if n else 0, "price_tier": "+".join(tiers),
            "api_latency_mean_s": round(float(np.mean(lat)), 4) if lat else 0,
            "api_latency_p95_s": round(float(np.percentile([r["api_latency_p95_s"] for r in rows], 95)), 4) if rows else 0,
            "steps_mean": round(f("steps"), 2), "invalid_outputs_total": sum(r["invalid_outputs"] for r in rows),
            "api_errors_total": sum(r["api_errors"] for r in rows), "cost_unknown": int(cost_unknown)}


def _resolve_repo_path(p: str | None) -> str | None:
    """冻结件 meta.json 记的是写入时的绝对路径；仓迁移后按仓根重解析——取该路径在 ROOT 下能命中的最长尾部
    （如 …/twin/configs/course01.yaml）。解析不到返回 None，由调用方**报错退出**、不退默认配置（DEC-20260925-24 补丁 2 P4）。
    冻结件本身不动。"""
    if not p:
        return None
    if os.path.exists(p):
        return p
    parts = [x for x in p.replace("\\", "/").split("/") if x]
    for i in range(len(parts)):
        cand = os.path.join(ROOT, *parts[i:])
        if os.path.exists(cand):
            return cand
    return None


def resummarize(run_dir: str, config: str | None = None) -> int:
    """只重算 summary.csv（补丁 3 P3）：从 results.csv＋meta.json 重建每模型汇总行，wall_s／cost_unknown 沿用旧 summary.csv。
    不重跑回合、不动 seeds.csv／meta.json（冻结件）；配置只取 meta.config（仓根重解析）或显式 --config，解析失败即退出（补丁 2 P4）；旧列数值须逐位不变，只允许新增列（prereg_check.sh 三基线比对为证）。"""
    res = os.path.join(run_dir, "results.csv"); old_p = os.path.join(run_dir, "summary.csv")
    meta = json.load(open(os.path.join(run_dir, "meta.json"), encoding="utf-8"))
    # 配置来源二选一：显式 --config（须存在），否则 meta.config 按仓根重解析；两者都拿不到 → 报错退出，禁止静默退默认配置
    if config is not None:
        if not os.path.isfile(config):
            print(f"✘ --config 不存在：{config}", file=sys.stderr); return 2
        cfg_path = config
    else:
        cfg_path = _resolve_repo_path(meta.get("config"))
        if not cfg_path:
            print(f"✘ meta.config 无法解析（原值 {meta.get('config')!r}）；请显式给 --config <路径> 重跑，不退默认配置", file=sys.stderr); return 2
    cfg = load_config(cfg_path)
    n_cp = int(cfg["checkpoints"]["count"])
    fx = float(meta.get("fx_cny_per_usd", 7.1)); n_planned = int(meta.get("n", 0))
    int_f = {"success", "checkpoints_reached", "collisions", "collision_events", "steps", "tokens_in", "tokens_out", "invalid_outputs", "api_errors", "stopped_by_agent"}
    rows_by = {}
    for r in csv.DictReader(open(res, newline="", encoding="utf-8")):
        row = dict(r)
        for k in EP_FIELDS:
            if k in ("agent", "model_id", "price_tier"):
                continue
            row[k] = int(row[k]) if k in int_f else float(row[k])
        rows_by.setdefault(row["agent"], []).append(row)
    old = {r["agent"]: r for r in csv.DictReader(open(old_p, newline="", encoding="utf-8"))} if os.path.exists(old_p) else {}
    summaries = []
    for nm, rows in rows_by.items():
        o = old.get(nm, {})
        summ = summarize(rows, bool(int(o.get("cost_unknown", 0) or 0)), n_planned or len(rows), fx, (meta.get("agents_identity") or {}).get(nm), n_cp)
        summ["wall_s"] = o.get("wall_s", "")
        summaries.append(summ)
    with open(old_p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0].keys())); w.writeheader(); w.writerows(summaries)
    print(f"== resummarized {old_p}：{len(summaries)} 行（列 {len(summaries[0])}）")
    return 0


def preflight(agent, robot: TwinRobot, task, seed: int) -> dict:
    """真模型探活：用 seed 的首帧真实调用 1 次，报 token／美元／时延／是否可解析。花费计入总额。"""
    obs = robot.reset(seed, task.render(1))
    obs.extra["next_checkpoint"] = 1
    agent.start_episode(obs.instruction, seed)
    dec = agent.decide(obs.for_model())
    info = {"agent": agent.name, "model_id": agent.model_id, "valid": dec.valid, "action": dec.action.value if dec.action else None,
            "tokens_in": dec.tokens_in, "tokens_out": dec.tokens_out, "usd": round(dec.usd_cost, 6), "latency_s": round(dec.latency_s, 3),
            "error": dec.extra.get("error"), "stop_reason": dec.extra.get("stop_reason") or dec.extra.get("finish_reason"),
            "raw": (dec.raw_text or "")[:160]}
    print(f"   preflight {agent.name:18s} valid={info['valid']} action={info['action']} in={info['tokens_in']} out={info['tokens_out']} "
          f"usd={info['usd']:.5f} lat={info['latency_s']:.2f}s stop={info['stop_reason']}" + (f" ERROR={info['error']}" if info["error"] else ""))
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Twin-01 批量跑测")
    ap.add_argument("--agents", required=False, default="", help="逗号分隔：astar,greedy,random 或 models.yaml 里的名字")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed0", type=int, default=1000, help="从此种子起筛可解种子，各 Agent 共用同一组（配对比较）")
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default=None, help="输出目录；默认 episodes/runs/<时间戳>")
    ap.add_argument("--frames", type=int, default=2, help="前几回合保存相机帧（每模型）")
    ap.add_argument("--no-randomization", action="store_true")
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--budget-usd", type=float, default=None, help="花费硬上限（美元）；≥90%% 或再跑一回合会越界即停")
    ap.add_argument("--allow-unpriced", action="store_true", help="允许 price_verified=false 的模型（成本记 0、护栏失效）")
    ap.add_argument("--preflight", action="store_true", help="批次前每个真模型先真实调用 1 次探活并计费")
    ap.add_argument("--preflight-only", action="store_true", help="只探活不跑批")
    ap.add_argument("--env-file", default=os.path.join(ROOT, ".env"), help="密钥文件（默认项目根目录 .env；不存在则跳过）")
    ap.add_argument("--resummarize", metavar="RUN_DIR", help="只按 results.csv 重算该 run 的 summary.csv（新增汇总列用；不重跑）")
    a = ap.parse_args(argv)
    if a.resummarize:
        return resummarize(a.resummarize, a.config)
    if not a.agents:
        ap.error("--agents 必填（或用 --resummarize RUN_DIR）")

    cfg = load_config(a.config)
    if a.no_randomization:
        cfg["randomization"]["enabled"] = False
    max_steps = a.max_steps or cfg["episode"]["max_steps"]
    out = a.out or os.path.join("episodes", "runs", datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out, exist_ok=True)
    n_env = load_env_file(a.env_file)
    models = load_models()
    settings = load_settings()
    fx = float(settings.get("fx_cny_per_usd", 7.1))
    names = [s.strip() for s in a.agents.split(",") if s.strip()]
    llm_names = [nm for nm in names if not is_scripted(nm)]
    for nm in llm_names:
        reject_unknown(nm, models)          # 未登记名／旧别名 oracle → 报错退出，不回落默认代理（ONE-027 ⑧ 批次）
        validate_model_row(nm, models[nm])  # 行必备键／provider／峰谷表缺省 → 报错退出，不回落默认价
    unpriced = [nm for nm in llm_names if not models[nm].get("price_verified", False)]
    if unpriced and not a.allow_unpriced:
        raise SystemExit(f"拒跑：{', '.join(unpriced)} 的单价未核实（price_verified=false），成本记 0 会让预算护栏失效；查官网价填入 models.yaml，或 --allow-unpriced")
    if llm_names and a.budget_usd is None:
        print("!! 警告：真模型批次未设 --budget-usd，无花费护栏")

    # 红线：批次前打印 provider+model；密钥只从环境变量读
    print(f"== Twin-01 batch  n={a.n}  seed0={a.seed0}  max_steps={max_steps}  randomization={cfg['randomization']['enabled']}  "
          f"budget_usd={a.budget_usd}  env_file_loaded={n_env}")
    for nm in names:
        if is_scripted(nm):
            print(f"   agent {nm:18s} provider=scripted  model={nm}  cost=0")
        else:
            m = models[nm]
            tiers = m.get("price_tiers") or {}
            price = (" ".join(f"{k}=${v['price_in']}/{v['price_out']}" for k, v in tiers.items()) if tiers
                     else f"${m.get('price_in', 0)}/${m.get('price_out', 0)}")
            print(f"   agent {nm:36s} provider={m['provider']}  model={m['model']}  thinking={m.get('thinking', '?')}  endpoint={m.get('endpoint', '?')}  "
                  f"key_env={m['key_env']}({'set' if os.environ.get(m['key_env']) else 'MISSING'})  price(in/out per MTok)={price}  price_verified={m.get('price_verified', False)}")

    # 种子筛选（Q1）
    t_scr = time.time()
    seeds, seed_rows = screen_seeds(cfg, a.seed0, a.n, max_steps)
    rejected = [r for r in seed_rows if not r["solvable"]]
    with open(os.path.join(out, "seeds.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SEED_FIELDS); w.writeheader()
        for r in seed_rows:
            w.writerow({"seed": r["seed"], "solvable": int(r["solvable"]), "reason": r["reason"], "astar_steps": r["steps"],
                        "legs": "/".join(str(x) for x in r["legs"]), "used": r["used"]})
    print(f"   seeds: screened={len(seed_rows)} solvable={len(seed_rows) - len(rejected)} rejected={len(rejected)} "
          f"rejection_rate={len(rejected) / len(seed_rows):.3f} used={seeds[0]}..{seeds[-1]} ({time.time() - t_scr:.1f}s)"
          + (f"  rejected_seeds={[(r['seed'], r['reason']) for r in rejected]}" if rejected else ""))
    meta = {"started": datetime.now().isoformat(timespec="seconds"), "n": a.n, "seed0": a.seed0, "max_steps": max_steps,
            "config": cfg["_path"], "config_sha256": _sha(cfg["_path"]), "prompt_sha256": _sha(PROMPT_PATH),
            "agents": names, "randomization": cfg["randomization"], "budget_usd": a.budget_usd, "fx_cny_per_usd": fx,
            "agents_identity": {nm: ({"model": nm, "thinking": "n/a", "endpoint": "scripted", "vendor": "scripted", "reads_ground_truth": nm != "random"} if is_scripted(nm)
                                     else {k: models[nm].get(k, "") for k in ("model", "thinking", "endpoint", "vendor", "row_name_zh", "row_name_en")}) for nm in names},
            "seeds": seeds, "seeds_screened": len(seed_rows), "seeds_rejected": [(r["seed"], r["reason"]) for r in rejected],
            "rejection_rate": round(len(rejected) / len(seed_rows), 4),
            "astar_steps_nominal_mean": round(float(np.mean([r["steps"] for r in seed_rows if r["used"]])), 2)}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    robot = TwinRobot(cfg=cfg)
    task = load_task(cfg["motion"], cfg["checkpoints"]["reach_radius_m"], cfg["checkpoints"]["count"])
    agents = {nm: make_agent(nm, cfg["motion"], task, models) for nm in names}
    spent = 0.0

    # 探活（真模型）
    if (a.preflight or a.preflight_only) and llm_names:
        print("== preflight（每模型真实调用 1 次，计入花费）")
        meta["preflight"] = []
        for nm in llm_names:
            info = preflight(agents[nm], robot, task, seeds[0])
            spent += info["usd"]; meta["preflight"].append(info)
        meta["preflight_usd"] = round(spent, 6)
        json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        bad = [p["agent"] for p in meta["preflight"] if p["error"] or not p["valid"]]
        if bad:
            print(f"!! 探活失败：{bad}；不开跑。")
            robot.close(); return 2
        if a.preflight_only:
            print(f"== preflight only  usd={spent:.5f}  {out}"); robot.close(); return 0

    def budget_state(model_rows: list[dict]) -> str | None:
        if a.budget_usd is None:
            return None
        if spent >= a.budget_usd:
            return "hard_cap"
        if spent >= 0.9 * a.budget_usd:
            return "approaching_90pct"
        worst = max((r["usd_cost"] for r in model_rows), default=0.0)
        if worst and spent + worst > a.budget_usd:
            return "next_episode_would_exceed"
        return None

    all_rows, summaries, stop = [], [], None
    t_all = time.time()
    with open(os.path.join(out, "results.csv"), "w", newline="", encoding="utf-8") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=EP_FIELDS); w.writeheader()
        for nm in names:
            if stop:
                break
            agent = agents[nm]
            rows = []; t0 = time.time()
            for i, seed in enumerate(seeds):
                log = os.path.join(out, "logs", nm, f"seed{seed}.jsonl")
                os.makedirs(os.path.dirname(log), exist_ok=True)
                frames = os.path.join(out, "frames", nm) if i < a.frames else None
                s = run_episode(robot, agent, seed, max_steps, task, log_path=log, frames_dir=frames)
                row = {k: s[k] for k in EP_FIELDS}; rows.append(row); w.writerow(row); fcsv.flush()
                spent += row["usd_cost"]
                if (i + 1) % 10 == 0 or i == len(seeds) - 1:
                    print(f"   {nm}: {i + 1}/{len(seeds)}  success={sum(r['success'] for r in rows)}  usd={sum(r['usd_cost'] for r in rows):.4f}  "
                          f"spent_total={spent:.4f}  {time.time() - t0:.0f}s")
                stop = budget_state(rows)
                if stop:
                    print(f"!! 预算护栏触发（{stop}）：已花 ${spent:.4f} / 上限 ${a.budget_usd}，{nm} 完成 {len(rows)}/{len(seeds)}，停跑")
                    break
            cost_unknown = bool(getattr(agent, "price_verified", True) is False)
            summ = summarize(rows, cost_unknown, len(seeds), fx, meta["agents_identity"].get(nm), int(cfg["checkpoints"]["count"])); summ["wall_s"] = round(time.time() - t0, 1)
            summaries.append(summ); all_rows += rows
    with open(os.path.join(out, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0].keys())); w.writeheader(); w.writerows(summaries)
    meta["finished"] = datetime.now().isoformat(timespec="seconds"); meta["wall_s"] = round(time.time() - t_all, 1)
    meta["usd_total"] = round(spent, 4)
    if stop:
        meta["budget_stop"] = {"reason": stop, "spent_usd": round(spent, 4), "budget_usd": a.budget_usd,
                               "completed": {s_["agent"]: s_["n"] for s_ in summaries}, "not_started": [nm for nm in names if nm not in {s_["agent"] for s_ in summaries}]}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    robot.close()
    print(f"== {'STOPPED (budget)' if stop else 'done'}  {out}  wall={meta['wall_s']}s  usd_total={meta['usd_total']}  rejection_rate={meta['rejection_rate']}")
    for s_ in summaries:
        print(f"   {s_['agent']:36s} n={s_['n']:3d}{'*' if s_['partial'] else ' '} sim_score={s_['sim_score_mean']:.3f}±{s_['sim_score_ci95']:.3f} "
              f"success={s_['success_rate']:.2f} cp={s_['checkpoint_score_mean']:.2f} coll_steps={s_['collisions_mean']:.1f} coll_events={s_['collision_events_mean']:.1f} "
              f"total(old)={s_['total_score_mean']:.2f} path_ratio={s_['path_ratio_mean_success']} usd/episode={s_['usd_per_episode']} "
              f"cny/episode={s_['cny_per_episode']} tier={s_['price_tier'] or '-'} lat={s_['api_latency_mean_s']:.3f}s{'  [cost_unknown]' if s_['cost_unknown'] else ''}")
    return 3 if stop else 0


if __name__ == "__main__":
    sys.exit(main())
