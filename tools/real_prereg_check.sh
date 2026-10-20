#!/usr/bin/env bash
# real_prereg_check.sh —— 真机段预注册核对（内部工单 C，裁定 2026-10-05-06）。
#   bash tools/real_prereg_check.sh            # 冻结件逐文件与 tag real-v0-prereg 比 sha256；rc 0 全同 / 1 有差 / 2 tag 不存在
#   bash tools/real_prereg_check.sh --freeze   # 不比 tag，只打印工作树各冻结件的 sha256（打 tag 前记入 protocol/real-v0.md）
set -uo pipefail
TAG="real-v0-prereg"; MODE="check"
[ "${1:-}" = "--freeze" ] && MODE="freeze"
cd "$(dirname "$0")/.." || exit 2
FROZEN=(protocol/real-v0.md real/course/L1.yaml real/course/L1-measured.yaml real/config/camera.yaml real/oracle.py
        real/score_overhead/score.py real/score_overhead/track.py harness/models.yaml harness/interface.py protocol/prompt_v0.md)
sha() { shasum -a 256 | cut -c1-64; }
if [ "$MODE" = freeze ]; then
  for f in "${FROZEN[@]}"; do
    if [ -f "$f" ]; then printf '%s  %s\n' "$(sha < "$f")" "$f"; else printf '%s  %s\n' "（缺）" "$f"; fi
  done; exit 0
fi
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { echo "✘ tag $TAG 不存在（候 C 段打）"; exit 2; }
bad=0
for f in "${FROZEN[@]}"; do
  a="$( [ "$(git cat-file -t "$TAG:$f" 2>/dev/null)" = blob ] && git show "$TAG:$f" | sha || echo '-' )"
  b="$( [ -f "$f" ] && sha < "$f" || echo '-' )"
  if [ "$a" = "$b" ]; then echo "✔ $f"; else echo "✘ $f  tag=${a:0:12} work=${b:0:12}"; bad=1; fi
done
[ $bad -eq 0 ] && echo "== 真机段冻结件与 $TAG 全同" || echo "== 有差异：tag 后真机跑测前不得改（改＝v1 另期）"
exit $bad
