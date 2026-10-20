"""模型在环 Agent。两类后端：anthropic（官方 SDK）与 openai_compat（openai SDK，指向各家兼容端点）。

每步：图像→JPEG base64→单轮请求（无对话历史；停-看-想-动每步独立）→解析 JSON 动作→记时延、token、美元成本。
密钥只从环境变量读；缺失即抛错，不猜。
"""
from __future__ import annotations

import base64
import io
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from ..interface import Action, Decision, Observation

from ..task import Task


def encode_jpeg(img: np.ndarray, max_w: int = 512, quality: int = 85) -> str:
    from PIL import Image
    im = Image.fromarray(img)
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    buf = io.BytesIO(); im.save(buf, format="JPEG", quality=quality)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


class _LLMBase:
    provider = "?"

    def __init__(self, name: str, cfg: dict[str, Any], task: Task, image_max_w: int = 512):
        self.name = name; self.cfg = cfg; self.model_id = cfg["model"]; self.task = task
        key = os.environ.get(cfg["key_env"], "")
        if not key:
            raise RuntimeError(f"环境变量 {cfg['key_env']} 未设置（模型 {name}）；密钥只从环境变量读，不入仓")
        self._key = key
        self.system = task.system; self.prompt_sha = task.prompt_sha256
        self.image_max_w = image_max_w
        self.price_in = float(cfg.get("price_in", 0)); self.price_out = float(cfg.get("price_out", 0))
        self.price_verified = bool(cfg.get("price_verified", False))
        # 峰谷两档（如 DeepSeek）：price_tiers {peak:{price_in,price_out}, offpeak:{...}}，高峰时段按北京时间判定
        self.price_tiers: dict[str, dict[str, float]] = dict(cfg.get("price_tiers") or {})
        self.peak_hours = [tuple(h) for h in (cfg.get("peak_hours_beijing") or [])]
        self.peak_weekdays_only = bool(cfg.get("peak_weekdays_only", True))
        self.thinking = str(cfg.get("thinking", "")); self.endpoint = str(cfg.get("endpoint", ""))
        self.request_kwargs: dict[str, Any] = dict(cfg.get("request_kwargs") or {})
        self._notes: list[str] = []

    def start_episode(self, instruction: str, seed: int) -> None:
        self._notes = []

    def instruction_text(self, obs: Observation) -> str:
        txt = obs.instruction
        if self.task.memory_notes and self._notes:
            txt += "\nYour notes from previous steps (oldest first): " + " | ".join(self._notes[-self.task.memory_notes:])
        return txt

    def _remember(self, raw: str) -> None:
        import json, re
        m = re.search(r"\{[^{}]*\}", raw or "")
        if m:
            try:
                n = json.loads(m.group(0)).get("note")
                if isinstance(n, str) and n.strip():
                    self._notes.append(n.strip()[:120])
            except Exception:
                pass

    def price_tier_now(self) -> str:
        """当前计价档：无峰谷表→'flat'；否则按北京时间判 peak／offpeak（法定节假日按工作日计，保守多计费）。"""
        if not self.price_tiers:
            return "flat"
        now = datetime.now(timezone(timedelta(hours=8)))
        if self.peak_weekdays_only and now.weekday() >= 5:
            return "offpeak"
        return "peak" if any(a <= now.hour < b for a, b in self.peak_hours) else "offpeak"

    def cost(self, tin: int, tout: int, tier: str | None = None) -> float:
        tier = tier or self.price_tier_now()
        if tier in self.price_tiers:
            p = self.price_tiers[tier]
            return (tin * float(p["price_in"]) + tout * float(p["price_out"])) / 1e6
        return (tin * self.price_in + tout * self.price_out) / 1e6

    def _call(self, b64: str, text: str) -> tuple[str, int, int, dict]:
        raise NotImplementedError

    def decide(self, obs: Observation) -> Decision:
        b64 = encode_jpeg(obs.image, self.image_max_w)
        text = self.instruction_text(obs)
        t = time.perf_counter(); err = None
        try:
            raw, tin, tout, extra = self._call(b64, text)
        except Exception as e:      # 网络/限流等：记错误，本步视为不可解析
            raw, tin, tout, extra, err = "", 0, 0, {}, repr(e)[:200]
        lat = time.perf_counter() - t
        a = Action.parse(raw)
        if a is not None:
            self._remember(raw)
        tier = self.price_tier_now()
        return Decision(a, lat, self.cost(tin, tout, tier), self.model_id, raw, tin, tout,
                        {"provider": self.provider, "error": err, "prompt_sha": self.prompt_sha[:12], "cost_unknown": not self.price_verified,
                         "price_tier": tier, **extra})


class AnthropicAgent(_LLMBase):
    provider = "anthropic"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        import anthropic
        self.client = anthropic.Anthropic(api_key=self._key, max_retries=2, timeout=120.0)
        self.effort = self.cfg.get("effort", "low")

    def _call(self, b64: str, text: str):
        kw: dict[str, Any] = {"max_tokens": 2048}          # 思考默认开启，给思考留量；答案本身只有一行 JSON
        if self.effort:
            kw["output_config"] = {"effort": self.effort}
        kw.update(self.request_kwargs)
        r = self.client.messages.create(
            model=self.model_id, system=self.system,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": text}]}],
            **kw)
        if r.stop_reason == "refusal":    # 评测不接 fallback：拒答就记拒答
            return "", r.usage.input_tokens, r.usage.output_tokens, {"stop_reason": "refusal"}
        txt = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return txt, r.usage.input_tokens, r.usage.output_tokens, {"stop_reason": r.stop_reason}


class OpenAICompatAgent(_LLMBase):
    provider = "openai_compat"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        from openai import OpenAI
        self.client = OpenAI(api_key=self._key, base_url=self.cfg.get("base_url"), max_retries=2, timeout=120.0)

    def _call(self, b64: str, text: str):
        kw: dict[str, Any] = {"max_tokens": 256}
        kw.update(self.request_kwargs)                       # 例：gpt-5 类需 {max_completion_tokens: 2048} 并去掉 max_tokens
        if kw.pop("omit_max_tokens", False):
            kw.pop("max_tokens", None)
        r = self.client.chat.completions.create(
            model=self.model_id, **kw,
            messages=[{"role": "system", "content": self.system},
                      {"role": "user", "content": [
                          {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                          {"type": "text", "text": text}]}])
        txt = (r.choices[0].message.content or "") if r.choices else ""
        u = r.usage
        return txt, (u.prompt_tokens if u else 0), (u.completion_tokens if u else 0), {"finish_reason": r.choices[0].finish_reason if r.choices else None}
