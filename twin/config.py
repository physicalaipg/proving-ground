"""配置读取：YAML → 嵌套 dict（保持简单，键名即文档）。"""
from __future__ import annotations

import os
from typing import Any

import yaml

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", "course01.yaml")


def load_config(path: str | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_path"] = path or DEFAULT_CONFIG
    return cfg
