#!/usr/bin/env python3
"""build_site.py 自测：在临时目录伪造 5 模型 × 仿真／真机 run，验证迁移差（仿真分 sim_score_mean）、保真度、Spearman（均经 harness/scoring.py）、辅助列到达占比、发布用时、基线表、verified 标与 --check 语义。
用法：python3 tools/selftest_site.py   （不碰仓内 episodes/ 与 site/data）"""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as bs  # noqa: E402

TEMPLATE = Path(__file__).resolve().parents[1] / "episodes/runs/2026-09-25-pilot01-baselines"


def write_run(d: Path, rows: list[dict], platform: str):
    d.mkdir(parents=True)
    with open(TEMPLATE / "summary.csv", newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    with open(d / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            base = {k: "0" for k in header}
            base.update({"model_id": r["agent"], "n": "10", "n_planned": "10", "partial": "0", "path_ratio_mean_success": "1.3",
                         "api_latency_mean_s": "1.5", "api_latency_p95_s": "3.0", "wall_s": "10"})
            base.update(r)
            w.writerow(base)
    meta = json.loads((TEMPLATE / "meta.json").read_text())
    meta["platform"] = platform
    (d / "meta.json").write_text(json.dumps(meta))
    for name in ("results.csv", "seeds.csv"):
        shutil.copyfile(TEMPLATE / name, d / name)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ep = root / "episodes"
        models = ["m1", "m2", "m3", "m4", "m5"]
        sim = [{"agent": m, "success_rate": s, "sim_score_mean": t, "reached_frac_mean": "0.95", "collisions_mean": "2", "usd_total": "1.0", "usd_per_success": "0.5", "endpoint": "official", "thinking": "off"}
               for m, s, t in zip(models, ["0.9", "0.8", "0.7", "0.6", "0.5"], ["0.9", "0.8", "0.7", "0.6", "0.5"])]
        real = [{"agent": m, "success_rate": s, "sim_score_mean": t, "collisions_mean": "5", "usd_total": "2.0", "usd_per_success": "1.0", "endpoint": "official", "thinking": "off"}
                for m, s, t in zip(models, ["0.7", "0.8", "0.4", "0.5", "0.1"], ["0.7", "0.84", "0.4", "0.48", "0.1"])]
        write_run(ep / "runs/2026-11-01-e02-sim", sim, "twin")
        write_run(ep / "real/2026-11-02-e02", real, "real")
        shutil.copytree(TEMPLATE, ep / "runs/base")
        ed = ep / "editions/2026-11-03-e02"
        ed.mkdir(parents=True)
        (ep / "editions.csv").write_text(
            "edition_id,status,course,protocol_version,title_zh,title_en,trigger_model,trigger_released_at,published_at,n_sim,n_real,human_hours,baseline_run,notes_zh,notes_en\n"
            "2026-11-03-e02,quick,course01,v0,第二期,Edition 02,m9,2026-11-01T10:00:00+08:00,2026-11-03T14:30:00+08:00,10,10,2.5,runs/base,,\n"
            "2026-12-01-e03,planned,course01,v0,第三期,Edition 03,,,,30,30,,,,\n", encoding="utf-8")
        (ed / "runs.csv").write_text("model,sim_run,real_run,verified,note\n" + "".join(f"{m},runs/2026-11-01-e02-sim,real/2026-11-02-e02,{'rerun' if i else 'self-reported'},\n" for i, m in enumerate(models)), encoding="utf-8")
        (ed / "video.csv").write_text("file,view,model,seed,platform,url,sha256,bytes,duration_s,recorded_at,note\na.mp4,overhead,m1,1000,youtube,https://x/y,deadbeef,1,60,,\n", encoding="utf-8")
        bs.ROOT, bs.EPISODES = root, ep
        out = root / "site/data"
        data = bs.Builder(out).build()
        e = next(x for x in data["editions"] if x["id"] == "2026-11-03-e02")
        assert data["latest"] == "2026-11-03-e02", data["latest"]                    # planned 不作 latest
        gaps = {m["model"]: m["gap"]["score"] for m in e["models"]}
        assert gaps == {"m1": -0.2, "m2": 0.04, "m3": -0.3, "m4": -0.12, "m5": -0.4}, gaps
        f = e["fidelity"]
        assert f["n_models"] == 5 and abs(f["mean_abs_gap"] - 0.212) < 1e-9, f
        assert [m["verified"] for m in e["models"]] == ["self-reported", "rerun", "rerun", "rerun", "rerun"]
        assert e["models"][0]["endpoint"] == "official" and e["models"][0]["thinking"] == "off"
        assert f["spearman"] == 0.8, f  # 仿真序 5,4,3,2,1 vs 真机 4,5,2,3,1：Σd²=4 → 1−24/120
        assert e["hours_to_publish"] == 52.5, e["hours_to_publish"]
        assert abs(e["usd_total"] - 15.0) < 1e-9, e["usd_total"]
        assert [b["agent"] for b in e["baselines"]] == ["astar", "greedy", "random"]
        assert e["baseline_meta"]["prompt_sha256"].startswith("b9006b83")
        assert len(e["video"]) == 1 and e["models"][0]["sim"]["n"] == 10
        assert e["models"][0]["sim"]["reached_frac_mean"] == 0.95 and e["baselines"][1]["reached_frac_mean"] == 0.9, "到达占比列须原样取自 summary.csv"
        assert bs.fidelity is not None and bs.transfer_gap(0.5, 0.7) == -0.2  # 派生量来自 harness/scoring.py
        assert (out / "runs/real__2026-11-02-e02/summary.csv").is_file()
        assert set(data["sources"]) >= {"episodes/editions.csv", "episodes/editions/2026-11-03-e02/runs.csv", "episodes/real/2026-11-02-e02/summary.csv"}
        # --check 语义：内容一致→相同摘要；手改一处→不同
        a = bs.tree_digest(out)
        (out / "leaderboard.json").write_text((out / "leaderboard.json").read_text().replace('"m1"', '"m1x"', 1))
        assert bs.tree_digest(out) != a
        # verified 非法值须报错
        (ed / "runs.csv").write_text("model,sim_run,real_run,verified,note\nm1,runs/2026-11-01-e02-sim,,maybe,\n", encoding="utf-8")
        try:
            bs.Builder(root / "site/data3").build()
        except SystemExit as ex:
            assert "verified" in str(ex)
        else:
            raise AssertionError("verified 非法值未报错")
        # 缺 agent 行须报错
        (ed / "runs.csv").write_text("model,sim_run,real_run,verified,note\nghost,runs/2026-11-01-e02-sim,,rerun,\n", encoding="utf-8")
        try:
            bs.Builder(root / "site/data2").build()
        except SystemExit as ex:
            assert "ghost" in str(ex)
        else:
            raise AssertionError("缺 agent 未报错")
    print("✔ selftest_site：13 项断言通过（仿真分迁移差／保真度／Spearman（harness 实现）／到达占比辅助列／发布用时／花费／基线／视频／副本／校验语义／verified 标／身份字段）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
