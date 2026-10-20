#!/usr/bin/env bash
# regen.sh —— 品牌图再生成（内部工单 §3）：装依赖 → 备 Noto Serif CJK 2.002 → 原样跑 build.py。
# 起因：build.py 在这台 Mac 上直接跑不起来（缺 uharfbuzz、cairosvg；brand.py 里 Noto 目录写的是 Linux 路径）。
#       build.py、brand.py 不改；本脚本在导入 brand 之后把 Noto 目录改指到本机，再执行 build.py。
# 用法（任意目录执行）：
#   bash tools/brand/regen.sh <输出目录>   # 出五语域，png 与 svg 共 30 个文件
#   bash tools/brand/regen.sh --check      # 出到临时目录，与 site/assets/brand/ 逐个比 sha256；
#                                          # 再核开号目录 names-and-bios.txt「图片」段列的每个文件真实存在（内部工单 §3）
# 环境变量：
#   BRAND_CACHE  虚拟环境与字体的存放处，缺省 ~/.cache/pg-brand（不在仓里）
#   NOTO_DIR     已有 Noto Serif CJK 的目录；给了就不下载，也不核字体哈希
#   KIT_DIR      开号目录，缺省 ~/Desktop/pg-accounts-kit；--check 时读其 names-and-bios.txt，目录不存在则跳过并提示
# 前提：python3、curl；系统装有 cairo（macOS：brew install cairo）。
# 字体版本：flat 的两张横幅只在 Noto Serif CJK 2.002 下与入库件逐字节相同（2.001、2.003 实测不同）。
# 退出码：0 正常（--check 时＝全部相同且图片段所列文件都在）；1 --check 有不同或图片段列了不存在的文件；2 用法或环境错误；3 字体哈希不符。
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CACHE="${BRAND_CACHE:-$HOME/.cache/pg-brand}"
NOTO_TAG="Serif2.002"
NOTO_URL="https://github.com/notofonts/noto-cjk/raw/$NOTO_TAG/Serif/OTC"
# 三个字重的 sha256（2026-09-29 自上面地址下载后实测）
NOTO_SUMS="f9ea56d72ca0f7fb6cbb550eb40b1002686f10fb9173bbca80210caa12e7b861  NotoSerifCJK-Black.ttc
b313b12c4ca6bffd67fced7ace2050bc70c9d6768327157636f8cef7d5aa2c8d  NotoSerifCJK-SemiBold.ttc
93069d8e9e45d515cc421c971a79e6a5777704b348e36a9ef86578bf58adef77  NotoSerifCJK-Regular.ttc"
# 依赖版本＝比对通过时所用的版本
DEPS="fonttools==4.66.0 uharfbuzz==0.56.2 cairosvg==2.9.1 pillow==12.3.0"

[ "$#" -eq 1 ] || { echo "用法：bash tools/brand/regen.sh <输出目录> ｜ --check"; exit 2; }
command -v python3 >/dev/null || { echo "✘ 缺 python3"; exit 2; }
command -v curl >/dev/null || { echo "✘ 缺 curl"; exit 2; }

# ① 依赖：装进缓存目录里的虚拟环境，不动系统 python
VENV="$CACHE/venv"
if [ ! -x "$VENV/bin/python" ]; then
  mkdir -p "$CACHE" && python3 -m venv "$VENV" || { echo "✘ 建虚拟环境失败：$VENV"; exit 2; }
fi
# shellcheck disable=SC2086
"$VENV/bin/pip" install -q --disable-pip-version-check $DEPS || { echo "✘ 装依赖失败"; exit 2; }

# ② cairo：Homebrew 不在缺省前缀时，动态库要另指路径
if command -v brew >/dev/null; then
  export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
fi

# ③ 字体：缺则下载，下完核哈希
if [ -n "${NOTO_DIR:-}" ]; then
  NOTO="$NOTO_DIR"
else
  NOTO="$CACHE/noto-$NOTO_TAG"; mkdir -p "$NOTO"
  for w in Black SemiBold Regular; do
    f="NotoSerifCJK-$w.ttc"
    [ -s "$NOTO/$f" ] || curl -sSL --fail -o "$NOTO/$f" "$NOTO_URL/$f" || { echo "✘ 下载失败：$f"; rm -f "$NOTO/$f"; exit 2; }
  done
  (cd "$NOTO" && printf '%s\n' "$NOTO_SUMS" | shasum -a 256 -c --quiet -) || { echo "✘ 字体哈希不符：$NOTO"; exit 3; }
fi

# ④ 出图：导入 brand 后改指 Noto 目录，再原样执行 build.py
if [ "$1" = "--check" ]; then OUT="$(mktemp -d)"; else mkdir -p "$1" && OUT="$(cd "$1" && pwd)" || exit 2; fi
"$VENV/bin/python" - "$HERE" "$NOTO" "$OUT" <<'PY' || { echo "✘ build.py 失败"; exit 2; }
import os, runpy, sys
here, noto, out = sys.argv[1:4]
sys.path.insert(0, here); os.chdir(here)
import brand
brand.NOTO = noto.rstrip("/") + "/"
sys.argv = [os.path.join(here, "build.py"), out]
runpy.run_path(sys.argv[0], run_name="__main__")
PY
echo "✔ 已出图：$OUT"
[ "$1" = "--check" ] || exit 0

# ⑤ 比对：产物与入库件逐个比 sha256
bad=0; n=0
while IFS= read -r f; do
  rel="${f#"$OUT"/}"; n=$((n + 1))
  a="$(shasum -a 256 "$f" | cut -c1-64)"
  b="$(shasum -a 256 "$REPO/site/assets/brand/$rel" 2>/dev/null | cut -c1-64)"
  [ "$a" = "$b" ] || { echo "✘ 不同：$rel"; bad=$((bad + 1)); }
done < <(find "$OUT" -type f \( -name '*.png' -o -name '*.svg' \) | sort)
rm -rf "$OUT"
if [ "$bad" -eq 0 ] && [ "$n" -gt 0 ]; then echo "✔ $n 个文件与 site/assets/brand/ 逐个相同"; else echo "✘ $n 个文件里 $bad 个不同"; bad=$((bad > 0 ? bad : 1)); fi

# ⑥ 开号目录图片段（内部工单 §3）：names-and-bios.txt「图片」段自「图片」起行到空行或文件末，
#    每行第一个词＝子目录/文件名，须在开号目录里真实存在，缺一个即退出码 1；开号目录本身不存在只提示，不算失败（别的机器上没有）。
KIT="${KIT_DIR:-$HOME/Desktop/pg-accounts-kit}"
BIOS="$KIT/names-and-bios.txt"
kbad=0; kn=0
if [ -f "$BIOS" ]; then
  while IFS= read -r rel; do
    kn=$((kn + 1))
    [ -f "$KIT/$rel" ] || { echo "✘ 图片段列了但不存在：$KIT/$rel"; kbad=$((kbad + 1)); }
  done < <(awk '/^图片/ {s=1; next} s && !NF {exit} s {print $1}' "$BIOS")
  if [ "$kn" -eq 0 ]; then echo "✘ 图片段为空：$BIOS"; kbad=1; fi
  [ "$kbad" -eq 0 ] && echo "✔ 图片段 $kn 个文件都在 $KIT"
else
  echo "⚠ 开号目录没有 names-and-bios.txt，图片段未核：$KIT"
fi
[ "$bad" -eq 0 ] && [ "$kbad" -eq 0 ] && exit 0
exit 1
