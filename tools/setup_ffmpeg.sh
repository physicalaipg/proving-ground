#!/usr/bin/env bash
# setup_ffmpeg.sh —— 重建带 libass／freetype 的精简 ffmpeg（内部工单 P8；把补丁 2 P4 的手工编译步骤脚本化，换机能重建）。
# 为什么不用 brew ffmpeg：瘦身公式缺 subtitles／drawtext 两滤镜；ffmpeg-full 在非默认 brew 前缀（如 ~/.brew，Tier 3）无 bottle、
# 源码编 47 个依赖且 09-25 实测下载 libthai 失败。改用 ffmpeg 官方源码只编精简版，依赖用 brew 已装件。
# 用法（任意目录）：bash tools/setup_ffmpeg.sh [--prefix DIR] [--version 9.0.2] [--jobs N] [--check] [--keep-src]
#   --check     只核对 PREFIX/bin/ffmpeg 是否存在且含 subtitles／drawtext 滤镜，不编译（发布日清单用）
#   --prefix    安装前缀，默认 ~/.local/ffmpeg-libass（compose_video.py 自动查找此处）
#   --version   ffmpeg 版本，默认 9.0.2（09-25 实编版本；换版须重跑 compose_video 示例核对）
#   --keep-src  保留源码目录（默认编完删除；源码放 $TMPDIR/ffmpeg-build）
# 退出码：0 成功（或 --check 通过）；1 --check 未通过；2 依赖缺失／下载失败；3 configure／make 失败。
# 核对：装完打印 `ffmpeg -version` 首行、两滤镜存在、以及 compose_video.py 的查找说明。
set -euo pipefail
PREFIX="$HOME/.local/ffmpeg-libass"; VERSION="9.0.2"; JOBS=""; CHECK=0; KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2;;
    --version) VERSION="$2"; shift 2;;
    --jobs) JOBS="$2"; shift 2;;
    --check) CHECK=1; shift;;
    --keep-src) KEEP=1; shift;;
    *) echo "未知参数 $1"; exit 2;;
  esac
done
FF="$PREFIX/bin/ffmpeg"

check_filters() {  # $1=ffmpeg 路径；两滤镜齐全返回 0
  local f="$1" missing=""
  [ -x "$f" ] || { echo "✘ $f 不存在或不可执行"; return 1; }
  for flt in subtitles drawtext; do "$f" -hide_banner -filters 2>/dev/null | awk '{print $2}' | grep -qx "$flt" || missing="$missing $flt"; done
  if [ -n "$missing" ]; then echo "✘ $f 缺滤镜:${missing}（需 libass／freetype）"; return 1; fi
  echo "✔ $("$f" -version 2>/dev/null | head -1)"; echo "✔ 滤镜 subtitles／drawtext 均在：$f"; return 0
}

if [ "$CHECK" -eq 1 ]; then check_filters "$FF" && exit 0 || exit 1; fi
if check_filters "$FF" 2>/dev/null; then echo "== 已装好，跳过编译（要重编先删 ${PREFIX}）"; exit 0; fi

# 1 依赖：brew 已装件（libass 带 fontconfig／freetype／harfbuzz／fribidi；x264 供 --enable-libx264；pkgconf 给 configure 找库）
command -v brew >/dev/null || { echo "✘ 需要 Homebrew（brew.sh）"; exit 2; }
BREW_PREFIX="$(brew --prefix)"
NEED="libass freetype fontconfig harfbuzz fribidi x264 pkgconf"
[ "$(uname -m)" = x86_64 ] && NEED="$NEED nasm"   # x86 汇编才需要 nasm；arm64 不装
MISSING=""
for pkg in $NEED; do brew list --formula "$pkg" >/dev/null 2>&1 || MISSING="$MISSING $pkg"; done
if [ -n "$MISSING" ]; then echo "== brew install$MISSING"; brew install $MISSING || { echo "✘ brew 依赖安装失败"; exit 2; }; fi
export PKG_CONFIG_PATH="$BREW_PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export PATH="$BREW_PREFIX/bin:$PATH"

# 2 源码：ffmpeg 官方 tarball（xz）
SRC_ROOT="${TMPDIR:-/tmp}/ffmpeg-build"; mkdir -p "$SRC_ROOT"; cd "$SRC_ROOT"
TARBALL="ffmpeg-$VERSION.tar.xz"
if [ ! -f "$TARBALL" ]; then
  echo "== 下载 https://ffmpeg.org/releases/$TARBALL"
  curl -fL --retry 3 -o "$TARBALL" "https://ffmpeg.org/releases/$TARBALL" || { echo "✘ 下载失败"; exit 2; }
fi
rm -rf "ffmpeg-$VERSION"; tar -xJf "$TARBALL"; cd "ffmpeg-$VERSION"

# 3 configure（与 09-25 实编一致；--extra-cflags/ldflags 指向 brew 前缀，非默认前缀 ~/.brew 时必需）
JOBS="${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)}"
echo "== configure → ${PREFIX}（brew 前缀 ${BREW_PREFIX}，-j${JOBS}）"
./configure --prefix="$PREFIX" --enable-gpl --enable-libx264 --enable-libass --enable-libfreetype --enable-libfontconfig \
  --enable-libharfbuzz --enable-libfribidi --disable-doc --disable-ffplay --disable-debug \
  --extra-cflags="-I$BREW_PREFIX/include" --extra-ldflags="-L$BREW_PREFIX/lib" >configure.log 2>&1 \
  || { echo "✘ configure 失败，见 $SRC_ROOT/ffmpeg-$VERSION/configure.log（末 20 行）："; tail -20 configure.log; exit 3; }
echo "== make -j${JOBS}（09-25 本机 M 系列约 3–6 分钟）"
make -j"$JOBS" >make.log 2>&1 || { echo "✘ make 失败，见 $SRC_ROOT/ffmpeg-$VERSION/make.log（末 20 行）："; tail -20 make.log; exit 3; }
make install >install.log 2>&1 || { echo "✘ make install 失败"; tail -20 install.log; exit 3; }
cd "$SRC_ROOT"; [ "$KEEP" -eq 1 ] || rm -rf "ffmpeg-$VERSION"

# 4 核对
check_filters "$FF" || exit 3
echo "== 完成。compose_video.py 按 --ffmpeg → \$FFMPEG → PATH → ~/.local/ffmpeg-libass/bin/ffmpeg 查找；非默认前缀请传 --ffmpeg $FF 或 export FFMPEG=$FF"
