"""registry 失败关闭自测（内部工单 ⑧ 批次 D2，2026-10-10）：
未登记模型名、旧别名 oracle、models.yaml 行 tier／键缺省 → 一律报错退出（rc≠0），不回落默认代理或默认价。
只测 registry 与 run_batch 的入口检查，不调用任何模型、不碰 twin 物理；harness/ 计分逻辑不涉。"""
import copy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.agents import registry  # noqa: E402

MOTION = {"turn_deg": 30.0}
ROW = {"provider": "openai_compat", "model": "x", "thinking": "off", "endpoint": "official", "key_env": "X_KEY",
       "price_in": 0.1, "price_out": 0.2, "price_verified": True}


def test_oracle_alias_retired():
    assert registry.is_scripted("oracle") is False
    with pytest.raises(SystemExit, match="oracle 已作废"):
        registry.make_agent("oracle", MOTION, None, {"m": ROW})


def test_unknown_name_exits_not_fallback():
    with pytest.raises(SystemExit, match="未知模型"):
        registry.make_agent("no-such-row", MOTION, None, {"m": ROW})


def test_scripted_still_constructs():
    for nm in registry.SCRIPTED:
        assert registry.make_agent(nm, MOTION, None, {}) is not None


def test_row_missing_key_exits():
    for k in registry.REQUIRED_KEYS:
        row = {kk: v for kk, v in ROW.items() if kk != k}
        with pytest.raises(SystemExit, match="缺键"):
            registry.validate_model_row("m", row)


def test_unknown_provider_exits():
    row = dict(ROW, provider="mystery")
    with pytest.raises(SystemExit, match="provider"):
        registry.validate_model_row("m", row)


def test_tier_default_exits():
    row = copy.deepcopy(ROW)
    row["price_tiers"] = {"peak": {"price_in": 1, "price_out": 2}}                    # 缺 offpeak
    row["peak_hours_beijing"] = [[9, 12]]
    with pytest.raises(SystemExit, match="price_tiers"):
        registry.validate_model_row("m", row)
    row["price_tiers"]["offpeak"] = {"price_in": 0.5}                                 # 档缺 price_out
    with pytest.raises(SystemExit, match="price_tiers"):
        registry.validate_model_row("m", row)
    row["price_tiers"]["offpeak"]["price_out"] = 1
    row.pop("peak_hours_beijing")                                                     # 有峰谷表无时段
    with pytest.raises(SystemExit, match="peak_hours_beijing"):
        registry.validate_model_row("m", row)
    row["peak_hours_beijing"] = [[9, 12], [14, 18]]
    registry.validate_model_row("m", row)                                            # 齐全即通过


def test_shipped_models_yaml_rows_validate():
    """仓内 models.yaml 现有各行（含候选）均过完整性核；不构造 Agent、不读密钥。"""
    for nm, cfg in registry.load_models().items():
        registry.validate_model_row(nm, cfg)


@pytest.mark.parametrize("agents", ["oracle", "no-such-row", "astar,oracle"])
def test_run_batch_cli_rejects(agents):
    """命令行入口：故意传未登记名／旧别名 → rc≠0，且不产生 run 目录（在种子筛选之前退出）。"""
    out = ROOT / "episodes" / "runs" / "_pytest_should_not_exist"
    r = subprocess.run([sys.executable, "-m", "harness.run_batch", "--agents", agents, "--n", "1", "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0, r.stdout + r.stderr
    assert "oracle 已作废" in (r.stdout + r.stderr) if "oracle" in agents else "未知模型" in (r.stdout + r.stderr)
    assert not (out / "seeds.csv").exists()
    if out.exists():
        out.rmdir()
