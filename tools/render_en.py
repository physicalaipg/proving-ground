#!/usr/bin/env python3
"""双语渲染流水线（内部工单；裁定 2026-09-25-12「一个真源、两个渲染」）
中文 Markdown 真源 → 分块 → 翻译记忆 → 术语表核对 → 英文 Markdown（带人工校对标记）。

步骤：
  status     把真源切块（标题／段落／列表项／表格／引用／代码块各一块，块键＝内容 sha256 前 12 位；改一字即换键、旧译自动失效），
             对照翻译记忆 <dir>/i18n/<名>.tm.json，把缺译块写入 <dir>/i18n/<名>.todo.json（AI 或人填 en 后 import）
  translate  （可选，付费）项目 .env 有 ANTHROPIC_API_KEY 时逐块调用 Claude 填 todo；须带 --spend
  import     把 todo 中填好的 en 合入翻译记忆（reviewed=false，记译者与日期）
  build      写英文文件 <名>.en.md：未校对块前置 <!-- MT-UNREVIEWED 键 -->；缺译块保留中文并标 <!-- MT-MISSING 键 -->；
             术语表核对不过标 <!-- GLOSSARY 键: 中文→English -->；文首有可见的状态说明
  review     人工校对：直接改 .en.md 里标记块下的英文，再跑 review --from-en --by <名>（读回改文并置 reviewed）；或 --all／--key 只置标记
纯 ASCII 块与代码块直通（en＝zh，视为已校对）。术语表 protocol/glossary.csv（zh,en,check,note；en 可用 | 列同义项；check=no 不核对）。

用法（仓根）：
  python3 tools/render_en.py status  protocol/v0.md
  python3 tools/render_en.py import  protocol/v0.md [--by claude-code]
  python3 tools/render_en.py build   protocol/v0.md [--out protocol/v0.en.md]
  python3 tools/render_en.py review  protocol/v0.md --from-en --by <名>   |  --all --by <名>  |  --key k1 k2 --by <名>
  python3 tools/render_en.py translate protocol/v0.md --spend [--model claude-sonnet-5]
退出码：0 正常；1 build 时仍有缺译或术语不符（文件照写，便于逐步补）；2 用法错误。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "protocol" / "glossary.csv"
CJK = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]")
FENCE = re.compile(r"^(```|~~~)")
LIST_TOP = re.compile(r"^([-*+]\s|\d+[.)]\s)")
LIST_ANY = re.compile(r"^\s*([-*+]\s|\d+[.)]\s)")
MARK = re.compile(r"^<!-- (MT-UNREVIEWED|MT-MISSING) ([0-9a-f]{12}) -->\s*$")


def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def key_of(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:12]


def paths(src: Path):
    d = src.parent / "i18n"
    return d / f"{src.stem}.tm.json", d / f"{src.stem}.todo.json", src.with_name(f"{src.stem}.en.md")


def split_blocks(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks: list[dict] = []
    buf: list[str] = []
    kind: str | None = None

    def flush():
        nonlocal buf, kind
        if buf:
            t = "\n".join(buf).rstrip()
            blocks.append({"key": key_of(t), "type": kind or "para", "zh": t})
        buf, kind = [], None

    i = 0
    while i < len(lines):
        ln = lines[i]
        m = FENCE.match(ln)
        if m:
            flush()
            fence, kind, buf = m.group(1), "code", [ln]
            i += 1
            while i < len(lines):
                buf.append(lines[i])
                i += 1
                if lines[i - 1].startswith(fence):
                    break
            flush()
            continue
        if not ln.strip():
            flush(); i += 1; continue
        if ln.startswith("#"):
            flush(); buf, kind = [ln], "heading"; flush(); i += 1; continue
        if ln.startswith("|"):
            if kind != "table":
                flush(); kind = "table"
            buf.append(ln); i += 1; continue
        if ln.startswith(">"):
            if kind != "quote":
                flush(); kind = "quote"
            buf.append(ln); i += 1; continue
        if LIST_ANY.match(ln):
            if LIST_TOP.match(ln) or kind != "item":
                flush(); kind = "item"
            buf.append(ln); i += 1; continue
        if kind == "item" and ln[:1] in (" ", "\t"):
            buf.append(ln); i += 1; continue
        if kind in ("table", "quote", "item"):
            flush()
        kind = kind or "para"
        buf.append(ln); i += 1
    flush()
    return blocks


def load_glossary() -> list[dict]:
    if not GLOSSARY.is_file():
        return []
    with open(GLOSSARY, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if (r.get("zh") or "").strip()]


def glossary_flags(zh: str, en: str, glossary: list[dict]) -> list[tuple[str, str]]:
    low = en.lower()
    flags = []
    for g in glossary:
        if (g.get("check") or "yes").strip().lower() == "no" or g["zh"] not in zh:
            continue
        alts = [a.strip().lower() for a in g["en"].split("|") if a.strip()]
        if not any(a in low for a in alts):
            flags.append((g["zh"], g["en"].split("|")[0]))
    return flags


def load_tm(tm_path: Path, src: Path) -> dict:
    if tm_path.is_file():
        return json.loads(tm_path.read_text(encoding="utf-8"))
    return {"source": rel(src), "blocks": {}}


def save_tm(tm_path: Path, tm: dict):
    tm_path.parent.mkdir(parents=True, exist_ok=True)
    tm_path.write_text(json.dumps(tm, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def passthrough(b: dict) -> bool:
    return b["type"] == "code" or not CJK.search(b["zh"])


def classify(blocks: list[dict], tm: dict):
    """每块 → (状态, 记录)：pass｜reviewed｜unreviewed｜missing"""
    out = []
    for b in blocks:
        if passthrough(b):
            out.append(("pass", {"en": b["zh"], "reviewed": True})); continue
        r = tm["blocks"].get(b["key"])
        if not r or not (r.get("en") or "").strip():
            out.append(("missing", None))
        else:
            out.append(("reviewed" if r.get("reviewed") else "unreviewed", r))
    return out


def cmd_status(src: Path, args) -> int:
    tm_path, todo_path, _ = paths(src)
    tm = load_tm(tm_path, src)
    blocks = split_blocks(src.read_text(encoding="utf-8"))
    st = classify(blocks, tm)
    counts = {k: sum(1 for s, _ in st if s == k) for k in ("pass", "reviewed", "unreviewed", "missing")}
    stale = [k for k in tm["blocks"] if k not in {b["key"] for b in blocks}]
    print(f"{rel(src)}：{len(blocks)} 块｜直通 {counts['pass']}｜已校对 {counts['reviewed']}｜机译未校 {counts['unreviewed']}｜缺译 {counts['missing']}｜记忆中已失效 {len(stale)}")
    todo = [{"key": b["key"], "type": b["type"], "zh": b["zh"], "en": ""} for b, (s, _) in zip(blocks, st) if s == "missing"]
    if todo:
        todo_path.parent.mkdir(parents=True, exist_ok=True)
        todo_path.write_text(json.dumps({
            "source": rel(src),
            "instructions": "Translate each block's zh into en. Keep Markdown structure exactly (headings, tables, list markers, inline code, bold). Use protocol/glossary.csv terms. Do not add, omit or reorder content. Leave code spans and file paths as-is.",
            "glossary": [{"zh": g["zh"], "en": g["en"]} for g in load_glossary()],
            "blocks": todo,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"→ 缺译块已写 {rel(todo_path)}（填 en 后 import）")
        if args.verbose:
            for b in todo:
                print(f"  [{b['key']}] {b['type']:7s} {b['zh'][:60].replace(chr(10), ' ')}")
    elif todo_path.is_file():
        todo_path.unlink()
    return 0


def cmd_import(src: Path, args) -> int:
    tm_path, todo_path, _ = paths(src)
    if not todo_path.is_file():
        print(f"✘ 没有 {rel(todo_path)}；先跑 status", file=sys.stderr); return 2
    tm = load_tm(tm_path, src)
    todo = json.loads(todo_path.read_text(encoding="utf-8"))
    n = 0
    for b in todo["blocks"]:
        if (b.get("en") or "").strip():
            tm["blocks"][b["key"]] = {"type": b["type"], "zh": b["zh"], "en": b["en"].rstrip(), "reviewed": False,
                                      "translator": args.by, "translated_at": date.today().isoformat(),
                                      "reviewed_by": None, "reviewed_at": None}
            n += 1
    save_tm(tm_path, tm)
    left = [b for b in todo["blocks"] if not (b.get("en") or "").strip()]
    if left:
        todo["blocks"] = left
        todo_path.write_text(json.dumps(todo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    else:
        todo_path.unlink()
    print(f"✔ 合入 {n} 块 → {rel(tm_path)}；仍缺译 {len(left)}")
    return 0


def cmd_build(src: Path, args) -> int:
    tm_path, _, out = paths(src)
    out = Path(args.out) if args.out else out
    tm = load_tm(tm_path, src)
    glossary = load_glossary()
    text = src.read_text(encoding="utf-8")
    blocks = split_blocks(text)
    st = classify(blocks, tm)
    src_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    parts, n_unrev, n_missing, n_gloss = [], 0, 0, 0
    for b, (s, r) in zip(blocks, st):
        if s == "missing":
            n_missing += 1
            parts.append(f"<!-- MT-MISSING {b['key']} -->\n{b['zh']}")
            continue
        en = r["en"]
        pre = []
        if s != "pass":
            for zh_t, en_t in glossary_flags(b["zh"], en, glossary):
                n_gloss += 1
                pre.append(f"<!-- GLOSSARY {b['key']}: {zh_t}→{en_t} -->")
        if s == "unreviewed":
            n_unrev += 1
            pre.append(f"<!-- MT-UNREVIEWED {b['key']} -->")
        parts.append("\n".join(pre + [en]))
    banner = [
        f"<!-- GENERATED FILE — rendered from {rel(src)} (sha256 {src_sha[:16]}…) by tools/render_en.py on {date.today().isoformat()}. "
        f"Do not edit the text here except under a review mark; edit the Chinese source and rerun. -->",
        "",
        f"> **Chinese version governs; English is a convenience translation.** 中文为准；英文为便利译本。Where the two differ, `{rel(src)}` applies.",
        ">",
        f"> **English rendering.** The source of truth is the Chinese file `{rel(src)}`; this file is produced by `tools/render_en.py` "
        f"(Chinese → machine translation → glossary check → human review). A block preceded by `<!-- MT-UNREVIEWED … -->` is machine-translated "
        f"and not yet human-reviewed; `<!-- MT-MISSING … -->` marks a block still in Chinese; `<!-- GLOSSARY … -->` flags a term that "
        f"does not follow `protocol/glossary.csv`. Status: {len(blocks)} blocks · {n_unrev} unreviewed · {n_missing} missing · {n_gloss} glossary flags.",
        "",
    ]
    out.write_text("\n".join(banner) + "\n\n".join(parts) + "\n", encoding="utf-8")
    print(f"{'✔' if not (n_missing or n_gloss) else '⚠'} {rel(out)}：{len(blocks)} 块｜未校对 {n_unrev}｜缺译 {n_missing}｜术语标记 {n_gloss}")
    return 1 if (n_missing or n_gloss) else 0


def cmd_review(src: Path, args) -> int:
    tm_path, _, en_path = paths(src)
    tm = load_tm(tm_path, src)
    if not args.by:
        print("✘ review 须 --by <校对人>", file=sys.stderr); return 2
    keys: list[str] = []
    if args.from_en:
        if not en_path.is_file():
            print(f"✘ 没有 {rel(en_path)}", file=sys.stderr); return 2
        lines = en_path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            m = MARK.match(lines[i])
            if not m or m.group(1) != "MT-UNREVIEWED":
                i += 1; continue
            key = m.group(2)
            i += 1
            buf = []
            if i < len(lines) and FENCE.match(lines[i]):
                fence = FENCE.match(lines[i]).group(1)
                buf.append(lines[i]); i += 1
                while i < len(lines):
                    buf.append(lines[i]); i += 1
                    if lines[i - 1].startswith(fence):
                        break
            else:
                while i < len(lines) and lines[i].strip() and not MARK.match(lines[i]) and not lines[i].startswith("<!-- GLOSSARY"):
                    buf.append(lines[i]); i += 1
            if key in tm["blocks"] and buf:
                tm["blocks"][key]["en"] = "\n".join(buf).rstrip()
                keys.append(key)
    elif args.all:
        keys = [k for k, r in tm["blocks"].items() if not r.get("reviewed")]
    else:
        keys = list(args.key or [])
    for k in keys:
        r = tm["blocks"].get(k)
        if r:
            r.update(reviewed=True, reviewed_by=args.by, reviewed_at=date.today().isoformat())
    save_tm(tm_path, tm)
    print(f"✔ 置已校对 {len(keys)} 块（{args.by}）；再跑 build 去标记")
    return 0


def _load_dotenv():
    p = ROOT / ".env"
    if p.is_file():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cmd_translate(src: Path, args) -> int:
    _, todo_path, _ = paths(src)
    if not todo_path.is_file():
        print("✔ 没有缺译块（先跑 status）"); return 0
    if not args.spend:
        print("✘ translate 调用付费 API，须带 --spend（付费属主理人四类，裁定 2026-09-25-16）", file=sys.stderr); return 2
    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("✘ 项目 .env 无 ANTHROPIC_API_KEY；改由 Claude Code 会话填 todo 后 import", file=sys.stderr); return 2
    try:
        import anthropic  # type: ignore
    except ImportError:
        print("✘ 未装 anthropic SDK（pip install anthropic）", file=sys.stderr); return 2
    todo = json.loads(todo_path.read_text(encoding="utf-8"))
    gl = "\n".join(f"- {g['zh']} → {g['en']}" for g in todo.get("glossary", []))
    system = ("You translate Chinese technical Markdown into precise English for a robotics evaluation protocol. Preserve Markdown structure "
              "exactly (headings, tables, list markers, inline code, bold). Use these glossary terms verbatim:\n" + gl +
              "\nDo not add, omit or reorder content. Output only the translated block.")
    client = anthropic.Anthropic()
    print(f"provider=anthropic model={args.model} blocks={len(todo['blocks'])}")
    for b in todo["blocks"]:
        if (b.get("en") or "").strip():
            continue
        msg = client.messages.create(model=args.model, max_tokens=4000, system=system,
                                     messages=[{"role": "user", "content": b["zh"]}])
        b["en"] = "".join(getattr(c, "text", "") for c in msg.content).strip()
        print(f"  [{b['key']}] in={msg.usage.input_tokens} out={msg.usage.output_tokens}")
    todo_path.write_text(json.dumps(todo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"✔ 已填 {rel(todo_path)}；接着 import --by {args.model}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["status", "import", "build", "review", "translate"])
    ap.add_argument("source", help="中文真源 Markdown")
    ap.add_argument("--out"); ap.add_argument("--by", default="claude-code")
    ap.add_argument("--all", action="store_true"); ap.add_argument("--key", nargs="*")
    ap.add_argument("--from-en", action="store_true"); ap.add_argument("--spend", action="store_true")
    ap.add_argument("--model", default="claude-sonnet-5"); ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    src = Path(a.source)
    if not src.is_file():
        print(f"✘ 找不到 {src}", file=sys.stderr); return 2
    return {"status": cmd_status, "import": cmd_import, "build": cmd_build, "review": cmd_review, "translate": cmd_translate}[a.cmd](src, a)


if __name__ == "__main__":
    sys.exit(main())
