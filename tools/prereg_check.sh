#!/usr/bin/env bash
# prereg_check.sh —— 预注册核对（内部工单 P3；内部工单 P1 扩展监视表＋三基线逐位比对）。
# 目的：真模型批次开跑前，证明「测量仪器」与 tag protocol-v0-prereg 一致：
#   ① 监视表（见 MONITORED）逐文件与 tag 比 sha256；
#   ② 有差异的文件必须在 CHANGELOG.md 登记（行内含该路径与其**当前**登记态 sha256），否则判「规则改了＝v1 新一季」；
#   ③ 末尾重跑 astar／greedy／random 三基线（N=30、冻结种子集、成本 0、≈20 s），与 tag 时的 summary.csv／results.csv 数值列**逐位**比对
#     （09-25 实测两次重跑与 tag 全同，故用零容差；若日后出现非确定性，改 --tolerance 并在回执说明）。
# 监视表：twin/ 全部跟踪文件、harness/ 全部跟踪文件（含 scoring.py、interface.py、models.yaml）、protocol/v0.md 规则区
#        （去掉 <!-- results:begin --> … <!-- results:end -->）、protocol/prompt_v0.md、episodes/runs/2026-09-25-pilot01-baselines/{seeds.csv,meta.json}。
# 明确不入监视：protocol/v0.en.md（便利译本）、site/（发布栈）、docs/（执行文件）。
# 用法（仓根）：bash tools/prereg_check.sh [--tag T] [--no-rerun] [--tolerance 1e-9] [--hash FILE]
#   --hash FILE   只打印 FILE 的登记态 sha256（v0.md 取规则区），供写 CHANGELOG 行用
#   --no-rerun    跳过三基线重跑（只做 ①②；结论不算「可开跑」）
# 退出码：0 通过；1 未登记差异或三基线数字不一致；2 tag 不存在；3 重跑无法执行（缺 .venv／mujoco）。
set -uo pipefail
TAG="protocol-v0-prereg"; RERUN=1; TOL=""; HASH_ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2;;
    --no-rerun) RERUN=0; shift;;
    --tolerance) TOL="$2"; shift 2;;
    --hash) HASH_ONLY="$2"; shift 2;;
    -*) echo "未知参数 $1"; exit 2;;
    *) TAG="$1"; shift;;   # 兼容旧用法：第一个位置参数＝tag
  esac
done
cd "$(dirname "$0")/.." || exit 2
CHANGELOG="CHANGELOG.md"
BASE_RUN="episodes/runs/2026-09-25-pilot01-baselines"
RULES_TEXT=(protocol/v0.md protocol/prompt_v0.md "$BASE_RUN/seeds.csv" "$BASE_RUN/meta.json")
NOT_MONITORED="protocol/v0.en.md site/ docs/"

strip_results() { awk '/<!-- results:begin -->/{skip=1} !skip{print} /<!-- results:end -->/{skip=0}'; }
sha() { shasum -a 256 | cut -c1-64; }
# 登记态哈希：v0.md 取规则区，其余整文件原样字节；$1=路径 $2=来源（work | tag）
reg_hash() {
  local f="$1" src="$2"
  if [ "$f" = "protocol/v0.md" ]; then
    if [ "$src" = tag ]; then git show "$TAG:$f" | strip_results | sha; else strip_results < "$f" | sha; fi
  else
    if [ "$src" = tag ]; then git show "$TAG:$f" | sha; else sha < "$f"; fi
  fi
}

if [ -n "$HASH_ONLY" ]; then reg_hash "$HASH_ONLY" work; exit 0; fi
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { echo "✘ tag $TAG 不存在"; exit 2; }

# 监视表＝tag 里的 twin/ harness/ 文件 ∪ 工作树跟踪＋未忽略的新文件 ∪ 规则文本四件
MONITORED="$( { git ls-tree -r --name-only "$TAG" -- twin harness; git ls-files twin harness; git ls-files --others --exclude-standard twin harness; printf '%s\n' "${RULES_TEXT[@]}"; } | grep -v '/\.gitkeep$' | sort -u )"
echo "== prereg_check  tag=$TAG  监视 $(printf '%s\n' "$MONITORED" | grep -c .) 件；不入监视：$NOT_MONITORED"
bad=0; changed=0; code_changed=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  a="$( [ "$(git cat-file -t "$TAG:$f" 2>/dev/null)" = blob ] && reg_hash "$f" tag || echo "-" )"
  b="$( [ -f "$f" ] && reg_hash "$f" work || echo "-" )"
  if [ "$a" = "$b" ]; then echo "✔ $f"; continue; fi
  changed=1
  case "$f" in twin/*|harness/*) code_changed=1;; esac
  if [ -f "$CHANGELOG" ] && [ "$b" != "-" ] && grep -F -- "$f" "$CHANGELOG" | grep -q -- "$b"; then
    ln="$(grep -n -F -- "$f" "$CHANGELOG" | grep -- "$b" | head -1 | cut -d: -f1)"
    echo "△ $f 与 $TAG 不同，已在 ${CHANGELOG} 第 $ln 行登记（sha256 ${b:0:12}…）"
  else
    echo "✘ $f 与 $TAG 不同且未在 ${CHANGELOG} 登记当前哈希 ${b:0:12}…（规则改了＝新一季 v1，不得按 v0 开跑；勘误须先登记）"; bad=1
  fi
done <<< "$MONITORED"

if [ "$bad" -ne 0 ]; then echo "✘ 有未登记差异"; exit 1; fi
if [ "$RERUN" -eq 0 ]; then
  echo "△ --no-rerun：跳过三基线重跑；本结论只证明文本一致，不算「可开跑」"
  [ "$code_changed" -eq 1 ] && echo "△ 监视代码有已登记改动，须跑一次不带 --no-rerun 的核对以证三基线逐位不变"
  exit 0
fi

# ③ 三基线重跑并逐位比对（tag 时数字＝git show $TAG:$BASE_RUN/{summary,results,seeds}.csv）
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
"$PY" -c "import mujoco, numpy" 2>/dev/null || { echo "✘ $PY 缺 mujoco／numpy，无法重跑三基线（装 .venv 或设 PYTHON=）"; exit 3; }
TMP="$(mktemp -d "${TMPDIR:-/tmp}/prereg.XXXXXX")"; trap 'rm -rf "$TMP"' EXIT
echo "== 重跑三基线 astar,greedy,random N=30（冻结种子集，成本 0）→ $TMP"
"$PY" -m harness.run_batch --agents astar,greedy,random --n 30 --frames 0 --out "$TMP/rerun" >"$TMP/rerun.log" 2>&1 || { echo "✘ 重跑失败："; tail -5 "$TMP/rerun.log"; exit 3; }
git show "$TAG:$BASE_RUN/summary.csv" > "$TMP/summary_tag.csv"
git show "$TAG:$BASE_RUN/results.csv" > "$TMP/results_tag.csv"
git show "$TAG:$BASE_RUN/seeds.csv" > "$TMP/seeds_tag.csv"
"$PY" - "$TMP" "$TOL" <<'EOF'
import csv, sys
tmp, tol = sys.argv[1], sys.argv[2]
tol = float(tol) if tol else None
S_COLS = ["n", "sim_score_mean", "sim_score_ci95", "success_rate", "checkpoint_score_mean", "collisions_mean", "collision_events_mean",
          "total_score_mean", "path_ratio_mean_success", "steps_mean"]
R_COLS = ["seed", "success", "checkpoints_reached", "checkpoint_score", "collisions", "collision_events", "penalty", "total_score",
          "sim_score", "path_ratio", "traveled_m", "ideal_path_m", "steps"]
def same(x, y):
    if x == y: return True
    if tol is None: return False
    try: return abs(float(x) - float(y)) <= tol
    except (ValueError, TypeError): return False
bad = []
a = {r["agent"]: r for r in csv.DictReader(open(f"{tmp}/summary_tag.csv"))}
b = {r["agent"]: r for r in csv.DictReader(open(f"{tmp}/rerun/summary.csv"))}
for k in a:
    if k not in b: bad.append(f"summary 缺 {k}"); continue
    bad += [f"summary {k}.{c}: tag={a[k][c]} now={b[k].get(c)}" for c in S_COLS if not same(a[k][c], b[k].get(c))]
ra = list(csv.DictReader(open(f"{tmp}/results_tag.csv"))); rb = list(csv.DictReader(open(f"{tmp}/rerun/results.csv")))
if len(ra) != len(rb): bad.append(f"results 行数 tag={len(ra)} now={len(rb)}")
for x, y in zip(ra, rb):
    bad += [f"results {x['agent']} seed{x['seed']}.{c}: tag={x[c]} now={y.get(c)}" for c in R_COLS if not same(x[c], y.get(c))]
sa = open(f"{tmp}/seeds_tag.csv").read(); sb = open(f"{tmp}/rerun/seeds.csv").read()
if sa != sb: bad.append("seeds.csv 与 tag 不同（种子筛选结果变了）")
if bad:
    print("✘ 三基线与 tag 时数字不一致（前 20 条）："); print("\n".join(bad[:20])); sys.exit(1)
mode = "零容差逐位" if tol is None else f"容差 {tol}"
print(f"✔ 三基线 {len(rb)} 回合 × {len(R_COLS)} 列、汇总 {len(a)} 行 × {len(S_COLS)} 列、seeds.csv 与 tag {mode}一致："
      + "  ".join(f"{k} {b[k]['sim_score_mean']}" for k in a))
EOF
rc=$?
[ $rc -ne 0 ] && exit 1
if [ "$changed" -eq 0 ]; then echo "✔ 监视表与 $TAG 零差异、三基线逐位一致，可按协议 v0 开跑"
else echo "✔ 监视表差异均已登记 ${CHANGELOG}（勘误／不改数字的代码改动），三基线逐位一致，可按协议 v0 开跑"; fi
exit 0
