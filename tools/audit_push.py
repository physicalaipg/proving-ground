#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_push.py —— proving-ground 推送前凭证审计（内部工单 §3；仅标准库）。
复制自 内部治理仓 00_portfolio/tools/audit_push.py（内部工单 §1，sha256 前 16 位 d6703c01cae7751b）；只改了 allowlist 路径与本说明里的路径。

词表沿用 FORGE 仓 tools/audit_secrets.py；差别在 allowlist 口径：
  条目＝「路径<TAB>行内容哈希<TAB>命中词」，三者同时吻合才排除；**行内容一变哈希即变，条目自动失效、须重审**。
  只有「词表词」（制度条文、变量名、示例占位里的普通词）可入 allowlist；
  「密钥形态」命中（AIza…／sk-…／AKIA…／ghp_…／Bearer 长串／PRIVATE KEY）永不可排除，只能改文件。

用法（任意目录下执行，自动切到仓根）：
  python3 tools/audit_push.py               # 扫工作树（已跟踪＋未忽略的未跟踪）
  python3 tools/audit_push.py --ref <ref>   # 扫某提交的已跟踪文件
  python3 tools/audit_push.py --propose     # 把剩余的词表词命中打印成 allowlist 候选行（不写文件）
  python3 tools/audit_push.py --review      # 逐条列出 allowlist 现行条目对应的 路径:行号｜命中词｜行文，供主理人过目
  python3 tools/audit_push.py --self-test   # 三条自测：假密钥必拦／形态命中不可排除／行变即失效
退出码：0＝零剩余命中；1＝有剩余命中；2＝用法错误或自测失败。
"""
import hashlib, os, re, subprocess, sys

SHAPE = re.compile(
    r"AIza[0-9A-Za-z_\-]{10,}"
    r"|(?<![A-Za-z0-9_])sk-[A-Za-z0-9_\-]{6,}"
    r"|(?<![A-Za-z0-9_])AKIA[0-9A-Z]{12,}"
    r"|(?<![A-Za-z0-9_])ghp_[A-Za-z0-9]{10,}"
    r"|Bearer\s+[A-Za-z0-9._\-]{10,}"
    r"|BEGIN [A-Z ]*PRIVATE KEY")
WORD = re.compile(
    r"api_key|GEMINI_API_KEY|OPENAI_API_KEY|DEEPSEEK_API_KEY"
    r"|authorization|x-goog|secret|password|token\s*=", re.IGNORECASE)
ALLOWLIST = "tools/audit_allowlist.tsv"   # 本文件整体豁免（第三列必然含词表词）


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def line_hash(line):
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]


def norm_word(w):
    return re.sub(r"\s+", "", w.lower())


def load_allowlist(path=ALLOWLIST):
    rules = set()
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            ln = ln.rstrip("\n")
            if ln and not ln.startswith("#") and ln.count("\t") == 2:
                rules.add(tuple(ln.split("\t")))
    return rules


def scan_blob(path, data, rules, hits, used):
    """hits 追加 (路径, 行号, 类别, 命中词, 行文)；used 记下被用到的 allowlist 条目。"""
    if path == ALLOWLIST or b"\x00" in data[:8192]:
        return
    for i, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
        for m in SHAPE.finditer(line):
            hits.append((path, i, "形态", m.group(0)[:12] + "…", line))
        for w in sorted({norm_word(m.group(0)) for m in WORD.finditer(line)}):
            key = (path, line_hash(line), w)
            if key in rules:
                used.add(key)
            else:
                hits.append((path, i, "词表", w, line))


def scan(ref, rules):
    hits, used = [], set()
    if ref:
        for entry in sh("git", "ls-tree", "-r", "-z", ref).split("\0"):
            if entry:
                meta, path = entry.split("\t", 1)
                data = subprocess.run(["git", "cat-file", "blob", meta.split()[2]],
                                      capture_output=True, check=True).stdout
                scan_blob(path, data, rules, hits, used)
    else:
        for path in sh("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0"):
            if path and os.path.isfile(path) and not os.path.islink(path):   # 软链不跟读：与 --ref 口径一致（git 只存链接路径，目标文件按本名另扫）
                with open(path, "rb") as f:
                    scan_blob(path, f.read(), rules, hits, used)
    return hits, used


def report(hits, used, rules, label):
    stale = len(rules - used)
    if stale:
        print(f"提示：allowlist 有 {stale} 条已失效（行已改或已删），可清理")
    if not hits:
        print(f"AUDIT PASS — 零剩余命中（{label}；allowlist 生效 {len(used)} 条）")
        return 0
    shape = sum(1 for h in hits if h[2] == "形态")
    print(f"AUDIT FAIL — {len(hits)} 处剩余命中（{label}；其中密钥形态 {shape} 处），拒绝推送：")
    for p, i, kind, w, _ in hits[:60]:
        print(f"  {p}:{i}: [{kind}] {w}")
    return 1


def self_test():
    fake = "k = " + "sk-" + "test-abcdefghijklmnop"          # 拼接，免得本文件自己命中形态
    line = "pass" + "word: 见保险箱"
    ok = []
    hits, used = [], set()
    scan_blob("t.txt", (fake + "\n" + line + "\n").encode(), set(), hits, used)
    ok.append(("假密钥与词表词均被拦", len(hits) == 2))
    rules = {("t.txt", line_hash(fake), "sk-"), ("t.txt", line_hash(line), "password")}
    hits, used = [], set()
    scan_blob("t.txt", (fake + "\n" + line + "\n").encode(), rules, hits, used)
    ok.append(("形态命中不可排除、词表词可排除", [h[2] for h in hits] == ["形态"]))
    hits, used = [], set()
    scan_blob("t.txt", (line + "！\n").encode(), rules, hits, used)
    ok.append(("行内容一变条目即失效", len(hits) == 1 and not used))
    for name, good in ok:
        print(f"  {'✅' if good else '❌'} {name}")
    return 0 if all(g for _, g in ok) else 2


def main(argv):
    os.chdir(sh("git", "rev-parse", "--show-toplevel").strip())
    if argv[:1] == ["--self-test"]:
        return self_test()
    rules = load_allowlist()
    if argv[:1] == ["--ref"] and len(argv) == 2:
        return report(*scan(argv[1], rules), rules, f"ref {argv[1][:12]}")
    if argv[:1] == ["--propose"]:
        hits, _ = scan(None, rules)
        for p, _, kind, w, line in hits:
            if kind == "词表":
                print(f"{p}\t{line_hash(line)}\t{w}")
        skipped = sum(1 for h in hits if h[2] == "形态")
        if skipped:
            sys.stderr.write(f"另有 {skipped} 处密钥形态命中，不可入 allowlist\n")
        return 0
    if argv[:1] == ["--review"]:
        hits, _ = scan(None, set())
        for p, i, kind, w, line in hits:
            if kind == "词表" and (p, line_hash(line), w) in rules:
                print(f"{p}:{i}｜{w}｜{line.strip()[:140]}")
        return 0
    if not argv:
        return report(*scan(None, rules), rules, "worktree")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
