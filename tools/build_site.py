#!/usr/bin/env python3
"""站点数据构建（内部工单）：只读 episodes/ 下的 CSV／meta.json，生成 site/data/；站点不手填数字。

用法（在仓根执行）：
  python3 tools/build_site.py           # 写 site/data/leaderboard.json、site/data/runs/<run>/{seeds,results,summary}.csv+meta.json、site/data/build-info.json
  python3 tools/build_site.py --check   # 重建到临时目录并与 site/data 逐文件比对，不一致退出 1（CI／pre-commit 用：防手改、防忘重建）

口径（计分单一真源＝harness/scoring.py，本脚本只读列不算公式；改口径先改协议再改 harness）：
  分     ＝ summary.csv 的 sim_score_mean（协议 §5「仿真分」∈[0,1]：到达占比 − 封顶碰撞事件扣分；true 真机 run 同列＝真机分）
           旧口径 total_score_mean 只作对照列带出，不排序
  行身份 ＝ runs.csv 的 model（＝models.yaml 键＝模型 ID＋思考档＋端点）；endpoint／thinking／vendor 取自该 run summary.csv；
           verified ∈ rerun（操作方已复跑）| self-reported（自报）取自 runs.csv
  成本   ＝ usd_* 与 cny_*（人民币＝美元×meta.fx_cny_per_usd）并列；price_tier 注明峰谷时段
  迁移差／孪生保真度 ＝ 调 harness/scoring.py 的 transfer_gap／fidelity（补丁 3 P7 迁入；本脚本不再自带公式）：
           迁移差＝真机分 − 仿真分（负值＝真机比仿真差），成功率差同理；保真度＝各模型 |迁移差| 均值，模型数 ≥5 另给 Spearman
  辅助列（补丁 3 P3，取 summary.csv 现成列不新算）＝ 到达占比 reached_frac_mean、接触事件/回合 collision_events_mean
  每次成功美元 ＝ usd_per_success；每步延迟 ＝ api_latency_mean_s（P95 一并带出）
输入：
  episodes/editions.csv                    期索引（一行一期；status ∈ planned|quick|formal）
  episodes/editions/<期>/runs.csv          model, sim_run, real_run（相对 episodes/ 的 run 目录），verified, note
  episodes/editions/<期>/video.csv         未剪辑视频索引（原样带入）
  episodes/<run>/summary.csv|meta.json     run_batch 产出；真机 run 同 schema（内部工单）
仅用标准库（harness/scoring.py 运行期不依赖 numpy／mujoco）；CI 无需装 mujoco。
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.scoring import fidelity, transfer_gap  # noqa: E402  计分单一真源：跨 run 派生量也只在 harness 实现

EPISODES = ROOT / "episodes"
SITE_DATA = ROOT / "site" / "data"
SCORE_COL = "sim_score_mean"
OLD_SCORE_COL = "total_score_mean"
VERIFIED = ("rerun", "self-reported")
RUN_COPY = ("seeds.csv", "results.csv", "summary.csv", "meta.json")


def _relativize_paths(obj):
    """递归：字符串值若为本机绝对路径（写入时史实），改成相对仓根的路径（取在 ROOT 下能命中的最长尾部）；
    解析不到则只去掉 ROOT 前缀之外的机器路径、保留文件名尾部。站点数据不落任何 /Users/… 私有路径。"""
    if isinstance(obj, dict):
        return {k: _relativize_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_relativize_paths(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("/"):
        parts = [x for x in obj.split("/") if x]
        for i in range(len(parts)):
            if (ROOT / Path(*parts[i:])).exists():
                return "/".join(parts[i:])
        return parts[-1] if parts else obj
    return obj
SUMMARY_NUM = (
    "n", "n_planned", "partial", "sim_score_mean", "sim_score_ci95", "success_rate", "reached_frac_mean", "checkpoint_score_mean", "collisions_mean",
    "collision_events_mean", "total_score_mean", "path_ratio_mean_success", "usd_total", "usd_per_success", "usd_per_episode",
    "cny_total", "cny_per_success", "cny_per_episode", "api_latency_mean_s",
    "api_latency_p95_s", "steps_mean", "invalid_outputs_total", "api_errors_total", "cost_unknown", "wall_s",
)
EDITION_NUM = ("n_sim", "n_real", "human_hours")
STATUSES = ("planned", "quick", "formal")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def num(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if f.is_integer() and "." not in v else f


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def repo_url() -> str:
    try:
        url = subprocess.check_output(["git", "-C", str(ROOT), "remote", "get-url", "origin"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    return url[:-4] if url.endswith(".git") else url


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def parse_dt(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone(__import__("datetime").timedelta(hours=8)))



class Builder:
    def __init__(self, out: Path):
        self.out = out
        self.sources: dict[str, str] = {}
        self.runs_meta: dict[str, dict] = {}

    def src(self, path: Path) -> Path:
        self.sources[path.relative_to(ROOT).as_posix()] = sha256(path)
        return path

    def load_run(self, run_rel: str) -> tuple[dict[str, dict], dict]:
        """返回 {agent: summary 行}, meta 摘要；并把 run 的四个文件复制到 site/data/runs/<run 名>/。"""
        run_rel = run_rel.strip().strip("/")
        d = EPISODES / run_rel
        if not (d / "summary.csv").is_file():
            raise SystemExit(f"✘ run 目录缺 summary.csv：episodes/{run_rel}")
        rows = {}
        for r in read_csv(self.src(d / "summary.csv")):
            rows[r["agent"]] = {k: (num(v) if k in SUMMARY_NUM else v) for k, v in r.items()}
        meta = {}; m = {}
        if (d / "meta.json").is_file():
            m = json.loads(self.src(d / "meta.json").read_text(encoding="utf-8"))
            meta = {k: m.get(k) for k in ("started", "finished", "n", "seed0", "max_steps", "config_sha256",
                                          "prompt_sha256", "rejection_rate", "seeds_screened", "usd_total",
                                          "budget_usd", "budget_stop", "platform", "randomization", "fx_cny_per_usd")}
            meta["seeds_rejected"] = len(m.get("seeds_rejected") or [])
        meta["platform"] = meta.get("platform") or ("real" if run_rel.startswith("real/") else "twin")
        dst = self.out / "runs" / run_rel.replace("/", "__")
        dst.mkdir(parents=True, exist_ok=True)
        for name in RUN_COPY:
            if (d / name).is_file():
                if name == "meta.json":
                    # 站点副本里的绝对路径字段改为仓根相对（冻结件 episodes/ 内原件不动；裁定 2026-09-25-24 补丁 2 P4b）
                    (dst / name).write_text(json.dumps(_relativize_paths(m), ensure_ascii=False, indent=1), encoding="utf-8")
                else:
                    shutil.copyfile(d / name, dst / name)
                self.src(d / name)
        meta["copy"] = f"data/runs/{dst.name}/"
        self.runs_meta[run_rel] = meta
        return rows, meta

    def edition(self, row: dict) -> dict:
        eid = row["edition_id"].strip()
        status = (row.get("status") or "planned").strip()
        if status not in STATUSES:
            raise SystemExit(f"✘ editions.csv 期 {eid} 的 status={status!r} 不在 {STATUSES}")
        ed_dir = EPISODES / "editions" / eid
        e = {
            "id": eid, "status": status, "course": row.get("course", ""), "protocol_version": row.get("protocol_version", ""),
            "title": {"zh": row.get("title_zh", ""), "en": row.get("title_en", "")},
            "trigger_model": row.get("trigger_model", ""), "trigger_released_at": row.get("trigger_released_at", ""),
            "published_at": row.get("published_at", ""), "hours_to_publish": None,
            "notes": {"zh": row.get("notes_zh", ""), "en": row.get("notes_en", "")},
            "models": [], "fidelity": None, "baselines": [], "baseline_run": (row.get("baseline_run") or "").strip(),
            "baseline_meta": None, "video": [], "usd_total": 0.0,
            "paths": {"dir": f"episodes/editions/{eid}", "logs": f"episodes/editions/{eid}/logs",
                      "manifest": f"episodes/editions/{eid}/SHA256SUMS", "video_index": f"episodes/editions/{eid}/video.csv",
                      "runs_index": f"episodes/editions/{eid}/runs.csv", "notes": f"episodes/editions/{eid}/notes.md"},
        }
        for k in EDITION_NUM:
            e[k] = num(row.get(k))
        t0, t1 = parse_dt(e["trigger_released_at"]), parse_dt(e["published_at"])
        if t0 and t1:
            e["hours_to_publish"] = round((t1 - t0).total_seconds() / 3600, 1)
        runs_csv = ed_dir / "runs.csv"
        if runs_csv.is_file():
            for r in read_csv(self.src(runs_csv)):
                model = (r.get("model") or "").strip()
                if not model:
                    continue
                verified = (r.get("verified") or "self-reported").strip()
                if verified not in VERIFIED:
                    raise SystemExit(f"✘ {runs_csv.relative_to(ROOT)} 行 {model} 的 verified={verified!r} 不在 {VERIFIED}")
                m = {"model": model, "note": r.get("note", ""), "verified": verified, "sim_run": (r.get("sim_run") or "").strip(),
                     "real_run": (r.get("real_run") or "").strip(), "sim": None, "real": None, "gap": None,
                     "vendor": "", "thinking": "", "endpoint": ""}
                for side in ("sim", "real"):
                    if m[f"{side}_run"]:
                        rows, _ = self.load_run(m[f"{side}_run"])
                        if model not in rows:
                            raise SystemExit(f"✘ episodes/{m[side + '_run']}/summary.csv 里没有 agent={model}")
                        m[side] = rows[model]
                        e["usd_total"] += float(rows[model].get("usd_total") or 0)
                        for k in ("vendor", "thinking", "endpoint"):
                            m[k] = m[k] or str(rows[model].get(k) or "")
                if m["sim"] and m["real"]:
                    m["gap"] = {
                        "score": transfer_gap(m["real"][SCORE_COL], m["sim"][SCORE_COL]),
                        "success_rate": transfer_gap(m["real"]["success_rate"], m["sim"]["success_rate"]),
                    }
                e["models"].append(m)
        paired = [m for m in e["models"] if m["gap"]]
        if paired:
            e["fidelity"] = fidelity([float(m["sim"][SCORE_COL]) for m in paired], [float(m["real"][SCORE_COL]) for m in paired])
        if e["baseline_run"]:
            rows, meta = self.load_run(e["baseline_run"])
            e["baselines"] = [{"agent": k, **v} for k, v in rows.items()]
            e["baseline_meta"] = meta
        video_csv = ed_dir / "video.csv"
        if video_csv.is_file():
            e["video"] = read_csv(self.src(video_csv))
        e["usd_total"] = round(e["usd_total"], 4)
        return e

    def build(self) -> dict:
        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "runs").mkdir(parents=True)
        editions = [self.edition(r) for r in read_csv(self.src(EPISODES / "editions.csv")) if (r.get("edition_id") or "").strip()]
        editions.sort(key=lambda e: e["id"], reverse=True)
        published = [e for e in editions if e["status"] != "planned"]
        data = {
            "schema": 2, "score_col": SCORE_COL, "old_score_col": OLD_SCORE_COL, "repo_url": repo_url(),
            "latest": (published or editions)[0]["id"] if editions else None,
            "editions": editions, "runs_meta": self.runs_meta,
            "sources": dict(sorted(self.sources.items())),
        }
        (self.out / "leaderboard.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return data


def tree_digest(d: Path) -> dict[str, str]:
    return {p.relative_to(d).as_posix(): sha256(p) for p in sorted(d.rglob("*")) if p.is_file() and p.name != "build-info.json"}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    if check:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Builder(Path(tmp) / "data").build()
            a, b = tree_digest(Path(tmp) / "data"), tree_digest(SITE_DATA) if SITE_DATA.is_dir() else {}
            if a == b:
                print(f"✔ site/data 与 episodes/ 一致（{len(a)} 个文件，{len(fresh['editions'])} 期）")
                return 0
            for k in sorted(set(a) | set(b)):
                if a.get(k) != b.get(k):
                    print(f"✘ 不一致：{k}（{'缺' if k not in b else '多' if k not in a else '内容不同'}）")
            print("→ 运行 python3 tools/build_site.py 重建；site/data 不手改")
            return 1
    data = Builder(SITE_DATA).build()
    (SITE_DATA / "build-info.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(), "tool": "tools/build_site.py", "sources": len(data["sources"]),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"✔ site/data：{len(data['editions'])} 期、{len(data['runs_meta'])} 个 run、{len(data['sources'])} 个源文件")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
