#!/usr/bin/env bash
# push_gate.sh —— 推送闸唯一入口（内部工单 §4）：凭证审计 → gitleaks 全史 → push，任一步非零即停。
# 起因：2026-09-26、09-27 两次手工把检查器接到管道后面，取到的是管道末端的退出码，命中没有拦住推送。
#       此后推送只走本入口；不手工串 audit／gitleaks／push，不把检查器的输出接管道。
# 本文件在 内部治理仓（00_portfolio/tools/）与 proving-ground（tools/）逐字相同；同目录须有 audit_push.py。
# 用法（任意目录执行，自动切到本脚本所在仓的仓根）：
#   bash push_gate.sh [远端 [分支]]   # 缺省 origin 与当前分支；两步检查全过才推，推后打印远端分支哈希
#   bash push_gate.sh --check         # 只跑两步检查，不推
#   bash push_gate.sh --self-test     # 自测：临时仓里放伪命中，闸须拦住；临时仓用完即删，不入库
# 退出码：0 检查通过（--check）或已推送；10 凭证审计未过；11 gitleaks 未过；12 推送失败；
#         2 用法或环境错误；3 自测失败。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIT="$HERE/audit_push.py"

need() {
  [ -f "$AUDIT" ] || { echo "✘ 推送闸：缺 $AUDIT"; return 2; }
  command -v python3 >/dev/null || { echo "✘ 推送闸：缺 python3"; return 2; }
  command -v gitleaks >/dev/null || { echo "✘ 推送闸：缺 gitleaks"; return 2; }
}

# 在当前目录所属的仓里跑两步检查。每步单独取退出码，检查器输出不经管道。
checks() {
  local rc
  python3 "$AUDIT" --ref HEAD; rc=$?
  if [ "$rc" -ne 0 ]; then echo "✘ 推送闸：凭证审计 rc=${rc}，停"; return 10; fi
  gitleaks detect --no-banner --redact; rc=$?
  if [ "$rc" -ne 0 ]; then echo "✘ 推送闸：gitleaks rc=${rc}，停"; return 11; fi
  echo "✔ 推送闸：凭证审计 rc 0、gitleaks rc 0"
}

# 自测三例：干净仓须过；只有 gitleaks 认的伪命中须停在 11；只有审计认的词表词须停在 10。
# 伪命中用 printf 拼出，免得本文件自己命中。
self_test() {
  local tmp fails=0 rc name want
  tmp="$(mktemp -d)" || return 2
  new_repo() {
    git init -q "$tmp/$1" && cd "$tmp/$1" || return 2
    [ -n "${2:-}" ] && printf "$2" "${@:3}" > sample.txt
    git add -A
    git -c user.name=gate -c user.email=gate@invalid commit -q --allow-empty -m sample
  }
  for name in clean leak word; do
    case "$name" in
      clean) want=0;  ( new_repo clean && checks >/dev/null 2>&1 ); rc=$? ;;
      leak)  want=11; ( new_repo leak 'client_%s = "%s%s"\n' key a1B2c3D4e5F6 g7H8i9J0k1L2 && checks >/dev/null 2>&1 ); rc=$? ;;
      word)  want=10; ( new_repo word 'pass%s: 见保险箱\n' word && checks >/dev/null 2>&1 ); rc=$? ;;
    esac
    if [ "$rc" -eq "$want" ]; then echo "  ✅ ${name}：rc=${rc}（应为 ${want}）"; else echo "  ❌ ${name}：rc=${rc}（应为 ${want}）"; fails=1; fi
  done
  rm -rf "$tmp"
  [ "$fails" -eq 0 ] || return 3
}

need || exit $?
case "${1:-}" in
  --self-test) self_test; exit $? ;;
  --check) MODE=check; shift ;;
  -*) echo "未知参数 $1（用法见文件头）"; exit 2 ;;
  *) MODE=push ;;
esac
cd "$(git -C "$HERE" rev-parse --show-toplevel)" || exit 2
checks || exit $?
[ "$MODE" = check ] && exit 0
REMOTE="${1:-origin}"
BRANCH="${2:-$(git rev-parse --abbrev-ref HEAD)}"
git push "$REMOTE" "$BRANCH"; rc=$?
if [ "$rc" -ne 0 ]; then echo "✘ 推送闸：git push rc=$rc"; exit 12; fi
git ls-remote "$REMOTE" "refs/heads/$BRANCH"
