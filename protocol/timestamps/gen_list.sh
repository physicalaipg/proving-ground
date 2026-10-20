#!/usr/bin/env bash
# 生成 protocol/timestamps/protocol-v0-prereg.txt（ONE-028 补丁2 修订2 段二 2；在 pg 仓根执行）
# 三段：a) tag 对象与所指提交 hash；b) 现行 prereg_check 监视清单逐文件 tag 内内容 sha256（shasum 原生行格式，按路径排序，tag 内不存在记「无」）；c) git／ots 版本与生成命令（仓内相对路径）
set -uo pipefail
TAG="protocol-v0-prereg"
BASE_RUN="episodes/runs/2026-09-25-pilot01-baselines"
RULES_TEXT=(protocol/v0.md protocol/prompt_v0.md "$BASE_RUN/seeds.csv" "$BASE_RUN/meta.json")
OUT="protocol/timestamps/protocol-v0-prereg.txt"
mkdir -p protocol/timestamps
{
  echo "# protocol-v0-prereg · 预注册锚点外部时间戳清单（OpenTimestamps）"
  echo "# 口径：OTS 凭证只证明「内容不晚于凭证所载区块时间已存在」；tag 的 2026-09-25 为 git 自报日期，第三方时间证据自本次盖章起算（dream-os DEC-20261010-02）。"
  echo
  echo "[a] tag 与提交"
  echo "tag_object   $(git rev-parse "$TAG")   # git rev-parse $TAG"
  echo "tag_commit   $(git rev-parse "$TAG^{commit}")   # git rev-parse '$TAG^{commit}'"
  echo
  echo "[b] prereg_check 监视清单（twin/、harness/ 全部跟踪文件 ∪ 四件规则文本）逐文件 tag 内内容 sha256；shasum 原生行格式；按路径排序；tag 内不存在记「无」"
  { git ls-tree -r --name-only "$TAG" -- twin harness; git ls-files twin harness; git ls-files --others --exclude-standard twin harness; printf '%s\n' "${RULES_TEXT[@]}"; } | grep -v '/\.gitkeep$' | sort -u | while IFS= read -r f; do
    if git cat-file -e "$TAG:$f" 2>/dev/null; then printf '%s  %s\n' "$(git show "$TAG:$f" | shasum -a 256 | cut -c1-64)" "$f"; else printf '%s  %s\n' "无" "$f"; fi
  done
  echo
  echo "[c] 工具与命令"
  echo "git   $(git --version)"
  echo "ots   $(ots --version 2>&1 | head -1)"
  echo "generated_by   bash protocol/timestamps/gen_list.sh   # 等价于本文件 [b] 段的 git ls-tree/ls-files ∪ RULES_TEXT 管道（与 tools/prereg_check.sh 的 MONITORED 同一表达式）"
  echo "stamp   ots stamp protocol/timestamps/protocol-v0-prereg.txt   # 产出同名 .ots，满 12 小时后 ots upgrade"
} > "$OUT"
echo "wrote $OUT ($(wc -l < "$OUT" | tr -d ' ') lines)"
