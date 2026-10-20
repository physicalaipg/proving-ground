"""按名字构造 Agent；模型表在 harness/models.yaml。"""
from __future__ import annotations

import os
from typing import Any

import yaml

from .scripted import AStarAgent, GreedyAgent, RandomAgent

MODELS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models.yaml")
SCRIPTED = ("astar", "greedy", "random")          # 成本 0；旧名 "oracle" 自 ONE-027 ⑧ 批次起作废为代理名（见 ORACLE_RETIRED）
ORACLE_RETIRED = "oracle 已作废为列名：天花板用 astar，贪心真值用 greedy"
PROVIDERS = ("anthropic", "openai_compat")
# 模型行必备键（配置即身份；缺任一键＝未登记完整，直接报错不回落默认）
REQUIRED_KEYS = ("provider", "model", "thinking", "endpoint", "key_env", "price_in", "price_out", "price_verified")


def is_scripted(name: str) -> bool:
    return name in SCRIPTED


def reject_unknown(name: str, models: dict[str, dict[str, Any]]) -> None:
    """未登记名／旧别名一律 SystemExit（rc≠0），不回落任何默认代理。"""
    if name == "oracle":
        raise SystemExit(ORACLE_RETIRED)
    if name not in models:
        raise SystemExit(f"未知模型 {name}；可选：{', '.join(SCRIPTED)}, {', '.join(models)}")


def validate_model_row(name: str, cfg: dict[str, Any]) -> None:
    """models.yaml 行完整性：必备键齐、provider 已知、峰谷表（若有）须含 peak／offpeak 两档且带北京时间高峰时段；缺省即报错退出。"""
    if not isinstance(cfg, dict):
        raise SystemExit(f"模型行 {name} 不是映射")
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise SystemExit(f"模型行 {name} 缺键 {', '.join(missing)}（配置即身份，不回落默认）")
    if cfg["provider"] not in PROVIDERS:
        raise SystemExit(f"模型行 {name} provider={cfg['provider']!r} 未登记；可选：{', '.join(PROVIDERS)}")
    tiers = cfg.get("price_tiers")
    if tiers is not None:
        if not isinstance(tiers, dict) or set(tiers) != {"peak", "offpeak"} or any(
                not isinstance(t, dict) or "price_in" not in t or "price_out" not in t for t in tiers.values()):
            raise SystemExit(f"模型行 {name} price_tiers 须且只须 peak／offpeak 两档、各含 price_in／price_out（tier 缺省不回落 price_in／price_out）")
        if not cfg.get("peak_hours_beijing"):
            raise SystemExit(f"模型行 {name} 有 price_tiers 但缺 peak_hours_beijing（无时段表则每次调用都会落到 offpeak，不允许）")


def load_models(path: str = MODELS_PATH) -> dict[str, dict[str, Any]]:
    """模型行（键＝行名＝厂商模型 ID＋思考档＋端点，配置即身份）；以下划线开头的键是设置，不算模型。"""
    with open(path, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_settings(path: str = MODELS_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    return dict(d.get("_settings") or {})


def make_agent(name: str, motion: dict[str, Any], task, models: dict[str, dict[str, Any]] | None = None):
    if name == "greedy":
        return GreedyAgent(turn_deg=motion["turn_deg"])
    if name == "astar":
        return AStarAgent()
    if name == "random":
        return RandomAgent()
    models = models or load_models()
    reject_unknown(name, models)
    cfg = models[name]
    validate_model_row(name, cfg)
    from .llm import AnthropicAgent, OpenAICompatAgent
    cls = {"anthropic": AnthropicAgent, "openai_compat": OpenAICompatAgent}[cfg["provider"]]
    return cls(name, cfg, task)
