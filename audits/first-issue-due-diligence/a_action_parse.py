#!/usr/bin/env python3
"""首期尽调 (a) 动作解析对照 ＋ ① 图像送达 ＋ ② 动作映射 ＋ 送达探针（内部工单）—— **调用侧**脚本（会话二，2026-10-10）。

只读调用 harness（`twin/`、`harness/`、协议、提示词、种子一字不改；监视件不动，`prereg_check.sh` 前后零差异）。一切记录在调用侧（内部工单 ⑤）：
  - `HintedAgent` 包装模型 Agent：每步先用 harness 的 `AStarAgent` 从孪生真值算「oracle 下一步动作」（每步从当前真实位姿重规划），
    把它附在指令文本末尾送模型（(a) 口径「提示附 oracle 下一步动作文本」）；真值只用于算提示，送模型的 Observation 仍经 `for_model()` 剥离。
  - HTTP 层钩子（openai SDK 的 httpx 客户端 `event_hooks["request"]`）：读请求体里的图像 data URL，记尺寸／字节数／编码／sha256，
    与该步渲染帧按 harness 同参数（`encode_jpeg(img, 512)`，JPEG q85）重编码的结果逐字节比对（① 图像送达）；**只记元数据，不记请求头，不记密钥**。
  - 调用侧逐步日志 `calls/<agent>/seed<N>.jsonl`：hint／模型输出原文全文／解析动作／有效否／token／美元（② 动作映射与花费的原始依据；
    harness 自身日志 `logs/<agent>/seed<N>.jsonl` 记实际执行动作，两者按 (seed, step) 对接）。
子命令：
  run     跑批：--agents 行名（models.yaml 键）--n 10 --hint oracle|none --max-steps（默认取配置）--models-file（覆盖模型表）--out 目录
  probe   送达探针：取首回合（种子集第 1 个）首帧，只问「图中可见几个有色检查点牌、各什么颜色」；真值＝分割渲染里各牌面像素数
  tables  由 run 目录生成 a1（图像送达）与 a2（动作映射）表
用法（仓根）：
  .venv/bin/python audits/first-issue-due-diligence/a_action_parse.py run --agents <三行名> --n 10 --hint oracle --out audits/first-issue-due-diligence/runs/<名>
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from harness.agents import load_models, load_settings, make_agent  # noqa: E402
from harness.agents.llm import encode_jpeg  # noqa: E402
from harness.agents.scripted import AStarAgent  # noqa: E402
from harness.agents.registry import SCRIPTED  # noqa: E402
from harness.episode import run_episode  # noqa: E402
from harness.interface import Action, Decision, Observation  # noqa: E402
from harness.run_batch import EP_FIELDS, SEED_FIELDS, _sha, load_env_file, screen_seeds, summarize  # noqa: E402
from harness.task import PROMPT_PATH, SIGN_COLOR_NAMES, load_task  # noqa: E402
from twin.config import load_config  # noqa: E402
from twin.robot_twin import TwinRobot  # noqa: E402

# (a) 口径：提示附 oracle 下一步动作文本（只在本尽调脚本里拼接；协议提示词文件不动）
HINT_TPL = ('\nNavigation aid for this diagnostic run: a map-aware planner has computed that the correct next action '
            'from the robot\'s current position is "{action}". Use exactly this action for this step '
            '(still answer in the required one-line JSON).')
# 送达探针（补丁13）：只问可见几个有色检查点牌及颜色；不带 system 提示
PROBE_TEXT = ('This is one photo from a small robot\'s forward camera. How many checkpoint signs with a colored border '
              'are visible in this photo, and what is the border color of each visible sign? Answer in one short line.')


def sha12(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


# ---------- HTTP 层钩子：只记图像元数据，不记头、不记密钥 ----------
def attach_request_hook(llm, ctx: dict, sink: list) -> None:
    hc = getattr(getattr(llm, "client", None), "_client", None)
    hooks = getattr(hc, "event_hooks", None)
    if hooks is None or "request" not in hooks:
        raise SystemExit(f"{llm.name}: 无法在调用侧挂 HTTP 钩子（客户端无 event_hooks）；按补丁3 ⑤ 停工报 CSO")

    def on_request(request) -> None:
        rec = {k: ctx.get(k) for k in ("agent", "seed", "step", "attempt", "phase")}
        rec["t"] = time.time()
        try:
            body = json.loads(bytes(request.content))
            rec["model"] = body.get("model")
            imgs, texts = [], []
            for m in body.get("messages", []):
                c = m.get("content")
                if isinstance(c, list):
                    for part in c:
                        if part.get("type") == "image_url":
                            imgs.append(part["image_url"]["url"])
                        elif part.get("type") == "text":
                            texts.append(part.get("text", ""))
            rec["n_images"] = len(imgs)
            if imgs:
                url = imgs[0]
                head, _, b64 = url.partition(",")
                rec["encoding"] = head                      # 例：data:image/jpeg;base64
                raw = base64.b64decode(b64)
                rec["bytes"] = len(raw)
                rec["jpeg_sha12"] = sha12(raw)
                try:
                    from PIL import Image
                    im = Image.open(io.BytesIO(raw))
                    rec["width"], rec["height"], rec["format"] = im.width, im.height, im.format
                except Exception as e:  # 解码失败也记
                    rec["decode_error"] = repr(e)[:80]
                rec["b64_match_expected"] = (b64 == ctx.get("expected_b64"))
            rec["text_match_expected"] = (texts[-1] == ctx.get("expected_text")) if texts else None
            rec["text_len"] = len(texts[-1]) if texts else 0
        except Exception as e:
            rec["hook_error"] = repr(e)[:120]
        sink.append(rec)

    hooks["request"].append(on_request)


# ---------- 包装 Agent：附 oracle 提示 ＋ 调用侧逐步日志 ----------
class HintedAgent:
    needs_gt = True   # 只为算提示读真值；送模型前仍 for_model() 剥离（见 decide）

    def __init__(self, llm, hint_mode: str, calls_dir: str):
        self.llm = llm
        self.name = llm.name
        self.model_id = llm.model_id
        self.price_verified = getattr(llm, "price_verified", True)
        self.hint_mode = hint_mode
        self.calls_dir = calls_dir
        self.ctx: dict = {"agent": llm.name, "phase": "run"}
        self.sink: list = []
        attach_request_hook(llm, self.ctx, self.sink)
        self._astar = AStarAgent()
        self._seed = None
        self._last_step = None
        self._attempt = 0
        self._logf = None
        self.steps_hint_followed = 0
        self.steps_total = 0

    def start_episode(self, instruction: str, seed: int) -> None:
        self.llm.start_episode(instruction, seed)
        self._astar = AStarAgent(); self._astar.start_episode(instruction, seed)
        self._seed = seed; self._last_step = None; self._attempt = 0
        if self._logf:
            self._logf.close()
        os.makedirs(os.path.join(self.calls_dir, self.name), exist_ok=True)
        self._logf = open(os.path.join(self.calls_dir, self.name, f"seed{seed}.jsonl"), "w", encoding="utf-8")

    def close(self) -> None:
        if self._logf:
            self._logf.close(); self._logf = None

    def decide(self, obs: Observation) -> Decision:
        step = obs.step
        self._attempt = self._attempt + 1 if step == self._last_step else 0
        self._last_step = step
        hint = None
        if self.hint_mode == "oracle":
            self._astar._plan = []                      # 每步从当前真实位姿重规划（不复用余下计划）
            hd = self._astar.decide(obs)                # 读 obs.extra["gt"]（真值只到这里）
            hint = hd.action.value
        mobs = obs.for_model()                          # 剥离真值
        if hint:
            mobs.instruction = obs.instruction + HINT_TPL.replace("{action}", hint)
        expected_b64 = encode_jpeg(obs.image, self.llm.image_max_w)
        frame_sha = sha12(np.ascontiguousarray(obs.image).tobytes())
        self.ctx.update(seed=self._seed, step=step, attempt=self._attempt, expected_b64=expected_b64,
                        expected_text=self.llm.instruction_text(mobs))
        n0 = len(self.sink)
        dec = self.llm.decide(mobs)
        http = self.sink[n0:]
        parsed = dec.action.value if dec.action else None
        row = {"seed": self._seed, "step": step, "attempt": self._attempt, "next_checkpoint": obs.extra.get("next_checkpoint"),
               "hint": hint, "raw_text": dec.raw_text, "parsed_action": parsed, "valid": dec.valid,
               "error": dec.extra.get("error"), "finish_reason": dec.extra.get("finish_reason") or dec.extra.get("stop_reason"),
               "tokens_in": dec.tokens_in, "tokens_out": dec.tokens_out, "usd": round(dec.usd_cost, 6), "price_tier": dec.extra.get("price_tier"),
               "latency_s": round(dec.latency_s, 4),
               "frame_hw": [int(obs.image.shape[0]), int(obs.image.shape[1])], "frame_sha12": frame_sha,
               "expected_jpeg_sha12": sha12(base64.b64decode(expected_b64)),
               "http": [{k: v for k, v in h.items() if k not in ("agent", "seed", "step", "attempt", "phase")} for h in http]}
        self._logf.write(json.dumps(row, ensure_ascii=False) + "\n"); self._logf.flush()
        if hint and self._attempt == 0:
            self.steps_total += 1
            self.steps_hint_followed += int(parsed == hint)
        return dec


# ---------- 公共：配置、种子、模型 ----------
def setup(a):
    cfg = load_config(a.config)
    n_env = load_env_file(a.env_file)
    models = load_models(a.models_file) if a.models_file else load_models()
    settings = load_settings(a.models_file) if a.models_file else load_settings()
    if a.models_file:   # 覆盖文件可省略 key_env（私有仓审计词表不记变量名）：按同名行自 harness/models.yaml 取，其余字段以覆盖文件为准
        base = load_models()
        for nm, row in models.items():
            if "key_env" not in row and nm in base and "key_env" in base[nm]:
                row["key_env"] = base[nm]["key_env"]; row["_key_env_from_pg_row"] = True
    fx = float(settings.get("fx_cny_per_usd", 7.1))
    names = [s.strip() for s in a.agents.split(",") if s.strip()]
    for nm in names:
        if nm not in models:
            raise SystemExit(f"未知模型行 {nm}；可选：{', '.join(models)}")
        if nm in SCRIPTED or nm == "oracle":
            raise SystemExit("本脚本只跑模型行；脚本基线用 harness.run_batch（oracle 已作废为代理名）")
    print(f"== (a) 调用侧  env_file_loaded={n_env}  config={cfg['_path']}  models_file={a.models_file or 'harness/models.yaml'}"
          + ("  key_env_from_pg_row=" + ",".join(nm for nm, r in models.items() if r.get("_key_env_from_pg_row")) if any(r.get("_key_env_from_pg_row") for r in models.values()) else ""))
    for nm in names:   # 红线：批次前打印 provider+model
        m = models[nm]
        print(f"   agent {nm:40s} provider={m['provider']}  model={m['model']}  thinking={m.get('thinking')}  endpoint={m.get('endpoint')}  "
              f"key_env={m['key_env']}({'set' if os.environ.get(m['key_env']) else 'MISSING'})  price_verified={m.get('price_verified')}")
    return cfg, models, fx, names


def frozen_seeds(cfg, n: int, seed0: int = 1000, screen_n: int = 30):
    """冻结种子集＝从 seed0 起筛到 30 个可解（与 c174ad7／基线批同法，剔 1005、1019）；取前 n 个。"""
    used, rows = screen_seeds(cfg, seed0, screen_n, int(cfg["episode"]["max_steps"]))
    take = used[:n]
    for r in rows:
        r["used"] = int(r["seed"] in take)
    return take, rows


def write_seeds(out: str, rows: list[dict]) -> None:
    with open(os.path.join(out, "seeds.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SEED_FIELDS); w.writeheader()
        for r in rows:
            w.writerow({"seed": r["seed"], "solvable": int(r["solvable"]), "reason": r["reason"], "astar_steps": r["steps"],
                        "legs": "/".join(str(x) for x in r["legs"]), "used": r["used"]})


# ---------- run ----------
def cmd_run(a) -> int:
    cfg, models, fx, names = setup(a)
    max_steps = a.max_steps or int(cfg["episode"]["max_steps"])
    out = a.out; os.makedirs(out, exist_ok=True)
    seeds, seed_rows = frozen_seeds(cfg, a.n)
    write_seeds(out, seed_rows)
    print(f"   seeds: used={seeds}（冻结种子集前 {a.n} 个；筛 {len(seed_rows)} 得 30 可解，剔 {[r['seed'] for r in seed_rows if not r['solvable']]}）")
    task = load_task(cfg["motion"], cfg["checkpoints"]["reach_radius_m"], cfg["checkpoints"]["count"])
    robot = TwinRobot(cfg=cfg)
    meta = {"started": datetime.now().isoformat(timespec="seconds"), "purpose": a.purpose, "hint": a.hint, "hint_template": HINT_TPL if a.hint == "oracle" else None,
            "n": a.n, "seed0": 1000, "max_steps": max_steps, "config": os.path.relpath(cfg["_path"], ROOT), "config_sha256": _sha(cfg["_path"]),
            "prompt_sha256": _sha(PROMPT_PATH), "models_file": a.models_file or "harness/models.yaml", "key_env_from_pg_row": [nm for nm in names if models[nm].get("_key_env_from_pg_row")], "agents": names, "seeds": seeds,
            "randomization": cfg["randomization"], "budget_usd": a.budget_usd, "fx_cny_per_usd": fx, "script": os.path.relpath(__file__, ROOT),
            "agents_identity": {nm: {k: models[nm].get(k, "") for k in ("model", "thinking", "endpoint", "vendor", "row_name_zh", "row_name_en")} for nm in names}}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    calls_dir = os.path.join(out, "calls")
    agents = {nm: HintedAgent(make_agent(nm, cfg["motion"], task, models), a.hint, calls_dir) for nm in names}
    spent = 0.0; stop = None; summaries = []; t_all = time.time()
    with open(os.path.join(out, "results.csv"), "w", newline="", encoding="utf-8") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=EP_FIELDS); w.writeheader()
        for nm in names:
            if stop:
                break
            ag = agents[nm]; rows = []; t0 = time.time()
            for i, seed in enumerate(seeds):
                log = os.path.join(out, "logs", nm, f"seed{seed}.jsonl"); os.makedirs(os.path.dirname(log), exist_ok=True)
                frames = os.path.join(out, "frames", nm) if i < a.frames else None
                s = run_episode(robot, ag, seed, max_steps, task, log_path=log, frames_dir=frames)
                row = {k: s[k] for k in EP_FIELDS}; rows.append(row); w.writerow(row); fcsv.flush()
                spent += row["usd_cost"]
                print(f"   {nm}: seed {seed} ({i + 1}/{len(seeds)}) success={row['success']} cp={row['checkpoints_reached']} steps={row['steps']} "
                      f"coll_ev={row['collision_events']} usd={row['usd_cost']:.4f} spent_total={spent:.4f} {time.time() - t0:.0f}s", flush=True)
                if a.budget_usd is not None and spent >= a.budget_usd:
                    stop = "hard_cap"; print(f"!! 预算护栏：已花 ${spent:.4f} ≥ 上限 ${a.budget_usd}，停跑"); break
            ag.close()
            summ = summarize(rows, not ag.price_verified, len(seeds), fx, meta["agents_identity"].get(nm), int(cfg["checkpoints"]["count"]))
            summ["wall_s"] = round(time.time() - t0, 1)
            summ["hint_followed_steps"] = ag.steps_hint_followed; summ["hint_steps"] = ag.steps_total
            summ["hint_follow_rate"] = round(ag.steps_hint_followed / ag.steps_total, 4) if ag.steps_total else ""
            summaries.append(summ)
    with open(os.path.join(out, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0].keys())); w.writeheader(); w.writerows(summaries)
    meta.update(finished=datetime.now().isoformat(timespec="seconds"), wall_s=round(time.time() - t_all, 1), usd_total=round(spent, 4),
                budget_stop=stop)
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    robot.close()
    print(f"== {'STOPPED (budget)' if stop else 'done'}  {out}  wall={meta['wall_s']}s  usd_total={meta['usd_total']}  hint={a.hint}")
    for s_ in summaries:
        print(f"   {s_['agent']:40s} n={s_['n']:3d} sim_score={s_['sim_score_mean']:.3f}±{s_['sim_score_ci95']:.3f} success={s_['success_rate']:.2f} "
              f"reached_frac={s_['reached_frac_mean']:.3f} coll_events={s_['collision_events_mean']:.1f} steps={s_['steps_mean']} "
              f"hint_follow={s_['hint_follow_rate']} usd={s_['usd_total']} tier={s_['price_tier'] or '-'} invalid={s_['invalid_outputs_total']} api_err={s_['api_errors_total']}")
    return 3 if stop else 0


# ---------- probe ----------
def sign_visibility(robot: TwinRobot) -> dict:
    """分割渲染真值：各检查点牌面（sign_{i}f／b 两片平面）与柱体在当前帧里的像素数。"""
    import mujoco
    r = robot.renderer
    r.enable_segmentation_rendering()
    try:
        r.update_scene(robot.data, camera="eye")
        seg = r.render()
    finally:
        r.disable_segmentation_rendering()
    ids = seg[:, :, 0]
    out = {}
    for i in range(1, int(robot.cfg["checkpoints"]["count"]) + 1):
        px = 0
        for nm in (f"sign_{i}f", f"sign_{i}b"):
            gid = mujoco.mj_name2id(robot.model, mujoco.mjtObj.mjOBJ_GEOM, nm)
            if gid >= 0:
                px += int((ids == gid).sum())
        pid = mujoco.mj_name2id(robot.model, mujoco.mjtObj.mjOBJ_GEOM, f"post_{i}")
        out[i] = {"color": SIGN_COLOR_NAMES.get(i), "sign_px": px, "post_px": int((ids == pid).sum()) if pid >= 0 else 0}
    return out


def cmd_probe(a) -> int:
    cfg, models, fx, names = setup(a)
    out = a.out; os.makedirs(out, exist_ok=True)
    seeds, _ = frozen_seeds(cfg, 1)
    seed = seeds[0]
    task = load_task(cfg["motion"], cfg["checkpoints"]["reach_radius_m"], cfg["checkpoints"]["count"])
    robot = TwinRobot(cfg=cfg)
    obs = robot.reset(seed, task.render(1))
    truth = sign_visibility(robot)
    b64 = encode_jpeg(obs.image, 512)
    jpeg = base64.b64decode(b64)
    open(os.path.join(out, f"probe-seed{seed}-t000.jpg"), "wb").write(jpeg)
    visible = [f"{i}:{v['color']}" for i, v in truth.items() if v["sign_px"] >= a.min_px]
    print(f"   frame seed={seed} step=0 {obs.image.shape[1]}x{obs.image.shape[0]} → jpeg {len(jpeg)} B sha12={sha12(jpeg)}; 真值牌面像素 {truth}; 可见(≥{a.min_px}px)={visible}")
    results = []
    for nm in names:
        llm = make_agent(nm, cfg["motion"], task, models)
        ctx = {"agent": nm, "seed": seed, "step": 0, "attempt": 0, "phase": "probe", "expected_b64": b64, "expected_text": PROBE_TEXT}
        sink: list = []
        attach_request_hook(llm, ctx, sink)
        kw = {"max_tokens": 256}; kw.update(llm.request_kwargs)
        if kw.pop("omit_max_tokens", False):
            kw.pop("max_tokens", None)
        t = time.perf_counter(); err = None; txt = ""; tin = tout = 0; finish = None
        try:
            r = llm.client.chat.completions.create(model=llm.model_id, **kw, messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}, {"type": "text", "text": PROBE_TEXT}]}])
            txt = (r.choices[0].message.content or "") if r.choices else ""
            tin, tout = (r.usage.prompt_tokens if r.usage else 0), (r.usage.completion_tokens if r.usage else 0)
            finish = r.choices[0].finish_reason if r.choices else None
        except Exception as e:
            err = repr(e)[:200]
        lat = time.perf_counter() - t
        tier = llm.price_tier_now(); usd = llm.cost(tin, tout, tier)
        rec = {"agent": nm, "model": llm.model_id, "seed": seed, "step": 0, "prompt": PROBE_TEXT, "raw_answer": txt, "error": err, "finish_reason": finish,
               "tokens_in": tin, "tokens_out": tout, "usd": round(usd, 6), "cny": round(usd * fx, 6), "price_tier": tier, "latency_s": round(lat, 3),
               "http": [{k: v for k, v in h.items() if k not in ("agent", "seed", "step", "attempt", "phase")} for h in sink]}
        results.append(rec)
        print(f"   {nm}: answer={txt!r} in={tin} out={tout} usd={usd:.5f} lat={lat:.2f}s err={err} http={rec['http']}")
    robot.close()
    json.dump({"seed": seed, "frame": f"probe-seed{seed}-t000.jpg", "frame_hw": [int(obs.image.shape[0]), int(obs.image.shape[1])], "jpeg_bytes": len(jpeg),
               "jpeg_sha12": sha12(jpeg), "truth_min_px": a.min_px, "truth": truth, "visible": visible, "prompt": PROBE_TEXT, "results": results,
               "ran": datetime.now().isoformat(timespec="seconds")}, open(os.path.join(out, "probe.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"== probe done → {out}/probe.json")
    return 0


# ---------- tables ----------
def read_jsonl(p: str) -> list[dict]:
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def cmd_tables(a) -> int:
    run = a.run
    meta = json.load(open(os.path.join(run, "meta.json"), encoding="utf-8"))
    agents = meta["agents"]; seeds = meta["seeds"]
    a1_rows, a2_rows, a1_sum = [], [], []
    for nm in agents:
        per_ep = []
        for k, seed in enumerate(seeds):
            cp = os.path.join(run, "calls", nm, f"seed{seed}.jsonl"); hp = os.path.join(run, "logs", nm, f"seed{seed}.jsonl")
            if not (os.path.exists(cp) and os.path.exists(hp)):
                continue
            calls = read_jsonl(cp); hlog = {r["step"]: r for r in read_jsonl(hp)}
            n_match = n_http = 0
            for c in calls:
                for h in c["http"]:
                    n_http += 1; n_match += int(h.get("b64_match_expected") is True)
                    if k < 3:   # ① 每家抽 3 回合（种子集前 3 个），逐步落表
                        a1_rows.append({"agent": nm, "seed": seed, "step": c["step"], "attempt": c["attempt"], "size": f"{h.get('width')}x{h.get('height')}",
                                        "bytes": h.get("bytes"), "encoding": f"{h.get('encoding')}/{h.get('format')}", "jpeg_sha12": h.get("jpeg_sha12"),
                                        "expected_jpeg_sha12": c["expected_jpeg_sha12"], "frame_sha12": c["frame_sha12"], "frame_hw": "x".join(map(str, c["frame_hw"][::-1])),
                                        "image_match": "一致" if h.get("b64_match_expected") else "不一致", "text_match": h.get("text_match_expected"),
                                        "hook_error": h.get("hook_error", "")})
                # ②：最后一次尝试的解析动作 → harness 执行动作
                last = [x for x in calls if x["step"] == c["step"]][-1]
                if c is last:
                    hr = hlog.get(c["step"], {})
                    executed = hr.get("action")
                    parsed = c["parsed_action"]
                    expect_exec = parsed if c["valid"] else "stop"
                    a2_rows.append({"agent": nm, "seed": seed, "step": c["step"], "hint": c["hint"], "raw_text_80": (c["raw_text"] or "")[:80].replace("\n", " "),
                                    "parsed_action": parsed, "executed_action": executed, "parse_exec_consistent": "一致" if expect_exec == executed else "不一致",
                                    "executed_eq_hint": ("" if c["hint"] is None else ("是" if executed == c["hint"] else "否")),
                                    "valid": c["valid"], "attempts": c["attempt"] + 1, "error": c.get("error") or ""})
            per_ep.append((seed, len(calls), n_http, n_match))
        a1_sum.append({"agent": nm, "episodes": len(per_ep), "calls": sum(x[1] for x in per_ep), "http_requests": sum(x[2] for x in per_ep),
                       "image_match": sum(x[3] for x in per_ep), "image_mismatch": sum(x[2] - x[3] for x in per_ep)})
    with open(os.path.join(run, "a1-image-delivery.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(a1_rows[0].keys())); w.writeheader(); w.writerows(a1_rows)
    with open(os.path.join(run, "a1-image-delivery-summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(a1_sum[0].keys())); w.writeheader(); w.writerows(a1_sum)
    with open(os.path.join(run, "a2-action-mapping.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(a2_rows[0].keys())); w.writeheader(); w.writerows(a2_rows)
    for s in a1_sum:
        print(f"   ① {s['agent']}: episodes={s['episodes']} calls={s['calls']} http={s['http_requests']} image_match={s['image_match']} mismatch={s['image_mismatch']}")
    for nm in agents:
        sub = [r for r in a2_rows if r["agent"] == nm]
        inc = [r for r in sub if r["parse_exec_consistent"] != "一致"]
        fol = [r for r in sub if r["executed_eq_hint"] == "是"]
        print(f"   ② {nm}: steps={len(sub)} parse→exec 不一致={len(inc)} executed==hint={len(fol)}/{len(sub)}")
    print(f"== tables → {run}/a1-image-delivery.csv（{len(a1_rows)} 行）、a1-image-delivery-summary.csv、a2-action-mapping.csv（{len(a2_rows)} 行）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--agents", required=True)
    common.add_argument("--config", default=None)
    common.add_argument("--models-file", default=None, help="覆盖模型表（如 (c) 的私有覆盖文件）；默认 harness/models.yaml")
    common.add_argument("--env-file", default=os.path.join(ROOT, ".env"))
    common.add_argument("--out", required=True)
    r = sub.add_parser("run", parents=[common]); r.add_argument("--n", type=int, default=10); r.add_argument("--hint", choices=["oracle", "none"], required=True)   # 无默认：是否附真值提示必须显式写出（内部工单 ⑧ 批次 D1「关死」）
    r.add_argument("--max-steps", type=int, default=None); r.add_argument("--frames", type=int, default=0); r.add_argument("--budget-usd", type=float, default=None)
    r.add_argument("--purpose", default="")
    p = sub.add_parser("probe", parents=[common]); p.add_argument("--min-px", type=int, default=100)
    t = sub.add_parser("tables"); t.add_argument("--run", required=True)
    a = ap.parse_args(argv)
    return {"run": cmd_run, "probe": cmd_probe, "tables": cmd_tables}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
