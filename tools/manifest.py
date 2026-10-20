#!/usr/bin/env python3
"""SHA256 清单（内部工单）：为发布目录生成／校验 SHA256SUMS。

路径一律相对仓根，因此可用系统工具复核：`cd <仓根> && shasum -a 256 -c episodes/editions/<期>/SHA256SUMS`。

用法（在仓根执行）：
  python3 tools/manifest.py gen episodes/editions/<期>           # 生成 <期>/SHA256SUMS；runs.csv 所引 run 目录的 CSV／meta 一并列入；只列 git 跟踪文件
  python3 tools/manifest.py verify episodes/editions/<期>/SHA256SUMS
  python3 tools/manifest.py hash <文件>...                         # 打印 sha256、字节数（填 video.csv 用）
退出码：0 通过；1 校验不过（缺文件或哈希不符）；2 用法错误。
"""
from __future__ import annotations

import csv
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMS = "SHA256SUMS"
SKIP_NAMES = {SUMS, ".DS_Store", ".gitkeep"}
RUN_FILES = ("seeds.csv", "results.csv", "summary.csv", "meta.json", "human-hours.csv")


def tracked() -> set[str]:
    """git ls-files 口径（10-20 起）：清单只列入仓文件，gitignored 的 runs/*/logs 不再列入，公开后 shasum -c 不报缺失。"""
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
    return {p for p in out.split("\0") if p}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def files_under(d: Path):
    for p in sorted(d.rglob("*")):
        parts = p.relative_to(d).parts
        if parts and parts[0] == "video":          # 成片本体不入仓（.gitignore `episodes/editions/*/video/`），只入 video.csv 索引（video-template §4）
            continue
        if p.is_file() and p.name not in SKIP_NAMES and not any(part.startswith(".") for part in parts):
            yield p


def run_dir_files(run_rel: str):
    """run 目录（相对 episodes/）里应随发的文件：四个 CSV/JSON ＋ 逐步日志（若在本机）。"""
    d = ROOT / "episodes" / run_rel
    if not d.is_dir():
        return
    for name in RUN_FILES:
        if (d / name).is_file():
            yield d / name
    logs = d / "logs"
    if logs.is_dir():
        yield from (p for p in sorted(logs.rglob("*.jsonl")) if p.is_file())


def gen(edition_dir: Path) -> int:
    if not edition_dir.is_dir():
        print(f"✘ 不是目录：{edition_dir}", file=sys.stderr)
        return 2
    paths = list(files_under(edition_dir))
    runs_csv = edition_dir / "runs.csv"
    if runs_csv.is_file():
        with open(runs_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for col in ("sim_run", "real_run"):
                    if (row.get(col) or "").strip():
                        paths.extend(run_dir_files(row[col].strip()))
    seen, lines = set(), []
    keep = tracked()
    for p in paths:
        rel = _rel(p)
        if rel in seen or rel not in keep:
            continue
        seen.add(rel)
        lines.append(f"{sha256(p)}  {rel}\n")
    lines.sort(key=lambda s: s.split("  ", 1)[1])
    out = edition_dir / SUMS
    out.write_text("".join(lines), encoding="utf-8")
    print(f"✔ {_rel(out)}：{len(lines)} 个文件")
    return 0


def verify(sums: Path) -> int:
    if not sums.is_file():
        print(f"✘ 找不到清单：{sums}", file=sys.stderr)
        return 2
    ok = bad = missing = 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        p = ROOT / rel
        if not p.is_file():
            missing += 1
            print(f"✘ 缺文件  {rel}")
        elif sha256(p) != digest:
            bad += 1
            print(f"✘ 哈希不符 {rel}")
        else:
            ok += 1
    print(f"{'✔' if not (bad or missing) else '✘'} 通过 {ok}｜不符 {bad}｜缺失 {missing}（{_rel(sums)}）")
    return 0 if not (bad or missing) else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "gen" and len(args) == 1:
        return gen(Path(args[0]))
    if cmd == "verify" and len(args) == 1:
        return verify(Path(args[0]))
    if cmd == "hash":
        for a in args:
            p = Path(a)
            print(f"{sha256(p)}  {p.stat().st_size}  {a}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
