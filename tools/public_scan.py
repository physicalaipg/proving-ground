#!/usr/bin/env python3
"""public_scan.py —— 公开仓文本扫描（内部治理词、内部编号形态、本机绝对路径；仅标准库）。

扫什么：
  内置形态（不含任何词面本身）：内部工单号 <前缀>-### ；裁定号（日期-序号形态与「待号」形态）；/Users/<名>/ 本机绝对路径。
  词表：环境变量 PG_WORDLIST 指向的文件（缺省 ~/.config/pg/p1-words.txt），一行一个正则，# 为注释。词表在仓外，仓内不出现词面。
  词表文件不存在：打印提示并只扫内置形态（公开协作者机器上即此态）。

用法（仓根）：
  python3 tools/public_scan.py                 # 扫 git ls-files 的文本文件（工作树内容）
  python3 tools/public_scan.py --ref HEAD      # 扫某提交的树
  python3 tools/public_scan.py --staged        # 扫暂存区（pre-commit 用）
  python3 tools/public_scan.py --exclude-list tools/public_scan_exclude.txt   # 清单内路径的命中单列为「声明残留」，不计入失败
退出码：0 零命中（声明残留不计）；1 有命中；2 用法或环境错误。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

BUILTIN = [
    ("order-id", re.compile(r"(?<![A-Za-z0-9])(?:ONE|GOLD|DUTY|PG|RIG|STUDIO|CSO|LAB|FORGE|PLAY|EXT|TWIN)-\d{3}(?!\d)")),
    ("ruling-id", re.compile(r"DEC-(?:\d{8}-\d{2}|待号)")),
    ("abs-home-path", re.compile(r"/Users/[A-Za-z0-9_.-]+/")),
]
SKIP_EXT = {".ots", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".ttf", ".otf", ".woff", ".woff2", ".pdf", ".bin", ".pyc"}


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def load_wordlist() -> list[tuple[str, re.Pattern]]:
    path = os.environ.get("PG_WORDLIST") or os.path.expanduser("~/.config/pg/p1-words.txt")
    if not os.path.isfile(path):
        print(f"提示：词表 {path} 不存在，只扫内置形态", file=sys.stderr)
        return []
    pats = []
    with open(path, encoding="utf-8") as f:
        for i, ln in enumerate(f, 1):
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                pats.append((f"word#{i}", re.compile(ln)))
    return pats


def blobs(ref: str | None, staged: bool):
    """产出 (路径, 字节)。"""
    if staged:
        for entry in sh("git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0"):
            if entry:
                data = subprocess.run(["git", "show", f":{entry}"], capture_output=True, check=True).stdout
                yield entry, data
    elif ref:
        for entry in sh("git", "ls-tree", "-r", "-z", ref).split("\0"):
            if entry:
                meta, path = entry.split("\t", 1)
                data = subprocess.run(["git", "cat-file", "blob", meta.split()[2]], capture_output=True, check=True).stdout
                yield path, data
    else:
        for path in sh("git", "ls-files", "-z").split("\0"):
            if path and os.path.isfile(path) and not os.path.islink(path):
                with open(path, "rb") as f:
                    yield path, f.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--exclude-list")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    excl = set()
    if a.exclude_list:
        if not os.path.isfile(a.exclude_list):
            print(f"✘ 清单不存在：{a.exclude_list}", file=sys.stderr)
            return 2
        excl = {ln.strip() for ln in open(a.exclude_list, encoding="utf-8") if ln.strip() and not ln.startswith("#")}
    pats = BUILTIN + load_wordlist()
    hits: list[tuple[str, int, str, str]] = []
    declared: list[tuple[str, int, str, str]] = []
    nfiles = 0
    for path, data in blobs(a.ref, a.staged):
        if os.path.splitext(path)[1].lower() in SKIP_EXT or b"\x00" in data[:8192]:
            continue
        nfiles += 1
        text = data.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for name, p in pats:
                m = p.search(line)
                if m:
                    rec = (path, i, name, m.group(0)[:40])
                    (declared if path in excl else hits).append(rec)
    by_file = {}
    for p, _, _, _ in hits:
        by_file[p] = by_file.get(p, 0) + 1
    label = "暂存区" if a.staged else (a.ref or "工作树")
    if declared and not a.quiet:
        dfiles = sorted({p for p, *_ in declared})
        print(f"声明残留（清单内，不计入失败）：{len(declared)} 行／{len(dfiles)} 文件")
        for p in dfiles:
            print(f"  {p}: {sum(1 for x in declared if x[0] == p)} 行")
    if not hits:
        print(f"PUBLIC-SCAN PASS — 零命中（{label}；{nfiles} 文件；{len(pats)} 条规则）")
        return 0
    print(f"PUBLIC-SCAN FAIL — {len(hits)} 行命中／{len(by_file)} 文件（{label}；{nfiles} 文件；{len(pats)} 条规则）")
    for p, i, name, w in hits[: (40 if a.quiet else 400)]:
        print(f"  {p}:{i}: [{name}] {w}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
