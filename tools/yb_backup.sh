#!/usr/bin/env bash
# yb_backup.sh —— 板卡厂商 YB-EET01 整片备份、判版本、回退（内部工单 P3）。规程见 real/firmware/yb-eet01-json/docs/backup-restore.md
# 用法：
#   tools/yb_backup.sh backup   <串口>              # 识别芯片与容量 → 整片读两次 → 哈希一致才算成立 → 判板上固件版本
#   tools/yb_backup.sh restore  <串口> <备份镜像>     # 回退：把备份镜像从 0x0 整片写回
#   tools/yb_backup.sh identify <镜像>              # 只对已有镜像判版本，不接板
#   tools/yb_backup.sh bootlog  <串口>              # 复位一次并读 5 秒启动文字（读开机版本行用）
#   tools/yb_backup.sh --self-test                  # 不接板自测（用箱内厂商镜像造样本）
# 环境变量：
#   ESPTOOL        esptool 可执行文件，缺省在 ~/esp/esptool-venv/bin/ 下找
#   YB_VENDOR_DIR  厂商镜像目录（仓外；未设则判版本与自测无从比对）
#   YB_BACKUP_DIR  备份落盘目录，缺省 ~/esp/backups/yb-eet01/。备份不进任何仓库：镜像里可能带 WiFi 参数
#   YB_MANUAL=1    跳过自动复位，直接按手动下载模式连（板子须已按住 BOOT 点过复位）
#   YB_CONFIRM=RESTORE  回退时免交互确认
#   YB_BAUD        esptool 速率，缺省 115200；460800 只许在这里显式给。10-02 实机：460800 切速后首条命令三次 Invalid head of packet（含手动下载模式、换线换口），115200 两次整片读出哈希一致（内部工单 A2，裁定 2026-10-02-21）
# 退出码：0 成立；2 用法或环境错误；3 连不上板；4 两次读出不一致、长度不足或落盘失败（备份不成立）；5 镜像头异常；6 回退被拒或失败
# 写法约定：变量后面紧跟中文或全角标点时一律写成 ${名字}。bash 3.2 在 UTF-8 环境下会把后面的字节并进变量名（审查 X3-05）
set -uo pipefail

VENDOR_DIR="${YB_VENDOR_DIR:-}"   # 厂商镜像目录（仓外、不入库）；未设则判版本与自测跳过比对
BACKUP_DIR="${YB_BACKUP_DIR:-$HOME/esp/backups/yb-eet01}"
BAUD="${YB_BAUD:-115200}"

find_esptool() {
  local c
  for c in "${ESPTOOL:-}" "$HOME/esp/esptool-venv/bin/esptool" "$HOME/esp/esptool-venv/bin/esptool.py"; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  echo "✘ 找不到 esptool：设 ESPTOOL，或按规程装到 ~/esp/esptool-venv" >&2
  return 2
}

sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
bytes() { wc -c < "$1" | tr -d ' '; }

# 从 flash_id 的输出里取板身份，一行一项：chip＝芯片型号、mac、size＝Flash 字节数。缺任何一项即失败
board_id() {
  local log="$1" chip mac size_mb
  chip="$(sed -n -E 's/^Chip (is|type):? *([^ ]+).*/\2/p' "$log" | head -1)"
  mac="$(sed -n -E 's/^MAC: *([0-9A-Fa-f:]+).*/\1/p' "$log" | head -1 | tr 'A-F' 'a-f')"
  size_mb="$(sed -n 's/.*Detected flash size: *\([0-9]*\)MB.*/\1/p' "$log" | head -1)"
  [ -n "$chip" ] && [ -n "$mac" ] && [ -n "$size_mb" ] || return 1
  printf 'chip=%s\nmac=%s\nsize=%s\n' "$chip" "$mac" "$((size_mb * 1024 * 1024))"
}

# 判版本：分三段与厂商镜像比对，跳开 0x9000–0x10000 的 nvs 与 phy_init（用过的板子这两区必然不同）
identify() {
  python3 - "$1" "$VENDOR_DIR" <<'PY'
import glob, os, re, sys
image, vendor_dir = sys.argv[1], sys.argv[2]
b = open(image, "rb").read()
print("镜像 %s｜%d 字节｜偏移 0 魔数 %#04x｜偏移 0x8000 %s" % (os.path.basename(image), len(b), b[0], b[0x8000:0x8002].hex()))
if b[0] != 0xE9 or b[0x8000:0x8002] != b"\xaa\x50":
    print("✘ 镜像头异常：不是未加密的乐鑫镜像（空片、已加密或读错）。停下贴回")
    sys.exit(5)
vendors = sorted(glob.glob(os.path.join(vendor_dir, "*.bin")))
if not vendors:
    print("⚠ 厂商镜像目录为空，无从比对：%s" % vendor_dir)
hit = None
for path in vendors:
    v = open(path, "rb").read()
    parts = [("引导区", 0x0, 0x8000), ("分区表", 0x8000, 0x9000), ("应用区", 0x10000, len(v))]
    same = [b[lo:hi] == v[lo:hi] for _, lo, hi in parts]
    print("  对 %s：%s" % (os.path.basename(path), "｜".join(
        "%s %s" % (name, "同" if ok else "异") for (name, _, _), ok in zip(parts, same))))
    if all(same):
        hit = os.path.basename(path)
found = sorted({m.decode() for m in re.findall(rb"[vV]\d+\.\d+\.\d+", b[0x10000:])})
print("应用区内的版本字样：%s" % (" ".join(found) or "无"))
print("判定：%s" % ("板上固件＝" + hit if hit else "与箱内各版都不全同，版本未判定"))
PY
}

connect_args() {
  if [ "${YB_MANUAL:-0}" = "1" ]; then echo "--before no_reset"; else echo "--before default_reset"; fi
}

# 先试自动复位；连不上再提示手动下载模式
probe() {
  local tool="$1" port="$2" log="$3"
  # shellcheck disable=SC2046
  if "$tool" --port "$port" --baud "$BAUD" $(connect_args) --after no_reset flash_id > "$log" 2>&1; then return 0; fi
  if [ "${YB_MANUAL:-0}" = "1" ]; then return 3; fi
  echo "⚠ 自动复位没连上。改走手动下载模式："
  echo "   1 按住板上 BOOT 键不放；2 点一下 RESET 键；3 松开 BOOT 键。"
  if [ ! -t 0 ]; then
    echo "   做完后加 YB_MANUAL=1 重跑本命令。"
    return 3
  fi
  printf "   做完按回车继续："; read -r _
  YB_MANUAL=1
  # shellcheck disable=SC2046
  "$tool" --port "$port" --baud "$BAUD" --before no_reset --after no_reset flash_id > "$log" 2>&1 || return 3
}

backup() {
  local port="$1" tool out id size size_hex h1 h2 got n
  tool="$(find_esptool)" || return 2
  [ -e "$port" ] || { echo "✘ 串口不存在：${port}"; return 2; }
  out="$BACKUP_DIR/$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$out" || return 2
  echo "== 1 识别芯片与 Flash 容量"
  probe "$tool" "$port" "$out/flash_id.log" || { tail -5 "$out/flash_id.log"; echo "✘ 连不上板，未读出任何数据"; return 3; }
  grep -E "Chip is|Chip type|Detected flash size|MAC" "$out/flash_id.log"
  id="$(board_id "$out/flash_id.log")" || { echo "✘ 没读全芯片型号、MAC 与 Flash 容量，停下贴回"; return 3; }
  size="$(echo "$id" | sed -n 's/^size=//p')"
  size_hex="$(printf '0x%x' "$size")"
  for n in 1 2; do
    echo "== 2.${n} 整片读出第 ${n} 次（0 至 ${size_hex}）"
    # shellcheck disable=SC2046
    "$tool" --port "$port" --baud "$BAUD" $(connect_args) --after no_reset \
      read_flash 0 "$size_hex" "$out/read$n.bin" > "$out/read$n.log" 2>&1 || { tail -5 "$out/read$n.log"; echo "✘ 第 ${n} 次读出失败"; return 3; }
    tail -1 "$out/read$n.log"
    # 两次读出同样截短时哈希也一致，所以长度单独核（审查 X3-04）
    got="$(bytes "$out/read$n.bin")" || got=""
    if [ "$got" != "$size" ]; then
      echo "✘ 第 ${n} 次读出长度不符：应为 ${size} 字节，实得 ${got:-未知} 字节。备份不成立，不烧录，停下贴回"
      return 4
    fi
  done
  h1="$(sha "$out/read1.bin")"; h2="$(sha "$out/read2.bin")"
  echo "== 3 两次读出的 sha256"
  echo "   read1 ${h1}"
  echo "   read2 ${h2}"
  if [ "${#h1}" -ne 64 ] || [ "${#h2}" -ne 64 ]; then
    echo "✘ 哈希没算出来，备份不成立。停下贴回"
    return 4
  fi
  if [ "$h1" != "$h2" ]; then
    echo "✘ 两次读出不一致，备份不成立。不烧录，停下贴回"
    return 4
  fi
  mv "$out/read1.bin" "$out/backup.bin" && rm "$out/read2.bin" \
    && echo "$h1  backup.bin" > "$out/backup.bin.sha256" && printf '%s\nsha256=%s\n' "$id" "$h1" > "$out/backup.bin.id" \
    && [ "$(sha "$out/backup.bin")" = "$h1" ] && [ -s "$out/backup.bin.sha256" ] && [ -s "$out/backup.bin.id" ] \
    || { echo "✘ 备份落盘失败（镜像、哈希或板身份文件没写成），备份不成立。停下贴回"; return 4; }
  echo "== 4 判板上固件版本"
  identify "$out/backup.bin" | tee "$out/identify.log"
  [ "${PIPESTATUS[0]}" -eq 0 ] || return 5
  echo "✔ 备份成立：${out}/backup.bin（${size} 字节，sha256 前 16 位 ${h1:0:16}）"
  echo "  回退命令：tools/yb_backup.sh restore ${port} ${out}/backup.bin"
}

restore() {
  local port="$1" image="$2" tool want have size answer log target
  tool="$(find_esptool)" || return 2
  [ -e "$port" ] || { echo "✘ 串口不存在：${port}"; return 2; }
  [ -f "$image" ] && [ -f "$image.sha256" ] || { echo "✘ 镜像或同名 .sha256 不在：${image}"; return 6; }
  want="$(cut -d' ' -f1 "$image.sha256")"; have="$(sha "$image")"
  [ "$want" = "$have" ] || { echo "✘ 镜像哈希与备份时所记不符，拒绝写入"; return 6; }
  identify "$image" || return 5
  # 备份身份：只回退本脚本备份出来的整片镜像，长度须等于备份时所记的 Flash 容量（审查 X3-04）
  [ -s "$image.id" ] || { echo "✘ 同名 .id 不在，不是本脚本备份出来的镜像，拒绝写入：${image}"; return 6; }
  size="$(bytes "$image")"
  [ "$size" = "$(sed -n 's/^size=//p' "$image.id")" ] || { echo "✘ 镜像长度 ${size} 字节与备份时所记的 Flash 容量不符，拒绝写入"; return 6; }
  # 板身份文件里绑着镜像哈希：镜像、.sha256、.id 三件须出自同一次备份，混配即拒（审查 X3-10）
  [ "$have" = "$(sed -n 's/^sha256=//p' "$image.id")" ] || { echo "✘ 板身份文件所记的镜像哈希与这份镜像不符，三件不是同一次备份的，拒绝写入"; return 6; }
  echo "将把 ${image}（${size} 字节）从 0x0 整片写回 ${port}。"
  answer="${YB_CONFIRM:-}"
  if [ -z "$answer" ] && [ -t 0 ]; then printf "确认请输入 RESTORE："; read -r answer; fi
  [ "$answer" = "RESTORE" ] || { echo "✘ 未确认，未写入"; return 6; }
  log="$(mktemp)" || return 2
  probe "$tool" "$port" "$log" || { rm -f "$log"; echo "✘ 连不上板，未写入"; return 3; }
  target="$(board_id "$log")" || target=""
  rm -f "$log"
  # 目标板的芯片型号、MAC、Flash 容量须与备份时所记逐项相同，换了板子不写
  if [ -z "$target" ] || [ "$target" != "$(grep -v '^sha256=' "$image.id")" ]; then
    echo "✘ 目标板与备份时所记不是同一块板，拒绝写入"
    echo "  备份时：$(grep -v '^sha256=' "$image.id" | tr '\n' ' ')"
    echo "  目标板：$(echo "${target:-没读全}" | tr '\n' ' ')"
    return 6
  fi
  # 闪存参数一律保持镜像头原值，不让工具改写
  # shellcheck disable=SC2046
  "$tool" --port "$port" --baud "$BAUD" $(connect_args) --after hard_reset \
    write_flash --flash_mode keep --flash_freq keep --flash_size keep 0x0 "$image" || { echo "✘ 写入失败"; return 6; }
  echo "✔ 已整片写回并复位。开串口 115200 看启动文字核对版本行"
}

# 读启动文字：经 RTS 复位一次，读 5 秒。板子没有自动复位电路时，由人在这 5 秒内点一下 RESET
bootlog() {
  local port="$1" tool py
  tool="$(find_esptool)" || return 2
  py="$(dirname "$tool")/python"
  [ -x "$py" ] || { echo "✘ esptool 所在环境里找不到 python：$py"; return 2; }
  [ -e "$port" ] || { echo "✘ 串口不存在：$port"; return 2; }
  "$py" - "$port" <<'PY'
import sys, time
import serial
link = serial.Serial(sys.argv[1], 115200, timeout=0.2)
link.dtr = False
link.rts = True
time.sleep(0.1)
link.rts = False
end = time.monotonic() + 5
while time.monotonic() < end:
    line = link.readline()
    if line:
        print(line.decode("utf-8", "replace").rstrip())
link.close()
PY
}

self_test() {
  local d v ok=0 fail=0 out img rc
  v="$VENDOR_DIR/microROS_Robot_V2.0.0.bin"
  [ -f "$v" ] || { echo "✘ 自测要用的厂商镜像不在：$v"; return 2; }
  d="$(mktemp -d)"
  python3 - "$v" "$d" <<'PY'
import sys
v = open(sys.argv[1], "rb").read()
full = bytearray(v + b"\xff" * (4 * 1024 * 1024 - len(v)))
full[0x9000:0x9010] = b"used-nvs-content"          # 用过的板子：nvs 区与厂商镜像不同
open(sys.argv[2] + "/same.bin", "wb").write(full)
full[0x20000] ^= 0xFF                                # 应用区改一个字节
open(sys.argv[2] + "/other.bin", "wb").write(full)
open(sys.argv[2] + "/blank.bin", "wb").write(b"\xff" * (4 * 1024 * 1024))
PY
  out="$(identify "$d/same.bin")";  if [ $? -eq 0 ] && echo "$out" | grep -q "板上固件＝microROS_Robot_V2.0.0.bin"; then ok=$((ok+1)); echo "  ✅ 同版镜像判出 V2.0.0"; else fail=$((fail+1)); echo "  ❌ 同版镜像未判出"; fi
  out="$(identify "$d/other.bin")"; if [ $? -eq 0 ] && echo "$out" | grep -q "版本未判定"; then ok=$((ok+1)); echo "  ✅ 改过应用区的镜像判为未判定"; else fail=$((fail+1)); echo "  ❌ 改过的镜像判错"; fi
  out="$(identify "$d/blank.bin")"; if [ $? -eq 5 ]; then ok=$((ok+1)); echo "  ✅ 空片镜像报镜像头异常"; else fail=$((fail+1)); echo "  ❌ 空片镜像未报异常"; fi
  echo "x  backup.bin" > "$d/same.bin.sha256"
  out="$(YB_CONFIRM=RESTORE ESPTOOL=/usr/bin/true restore /dev/null "$d/same.bin")"; if [ $? -eq 6 ] && echo "$out" | grep -q "哈希"; then ok=$((ok+1)); echo "  ✅ 哈希不符的镜像拒绝回退"; else fail=$((fail+1)); echo "  ❌ 哈希不符未被拒"; fi
  # 以下五条走备份与回退的整条通路，用假 esptool 顶替，不碰任何设备；另起子进程并指定 UTF-8 环境（审查 X3-04、X3-05）
  cat > "$d/esptool" <<'SH'
#!/usr/bin/env bash
# 假 esptool：只认 flash_id、read_flash、write_flash 三个动作
case " $* " in
  *" flash_id "*)   echo "Chip is ESP32-S3 (QFN56)"; echo "MAC: ${FAKE_MAC:-aa:bb:cc:dd:ee:01}"; echo "Detected flash size: ${FAKE_SIZE_MB:-4}MB" ;;
  *" read_flash "*) for last; do :; done; head -c "${FAKE_READ_BYTES:-4194304}" "$FAKE_IMAGE" > "$last"; echo "Read done" ;;
  *" write_flash "*) echo "MOCK WRITE REACHED" ;;
esac
SH
  chmod +x "$d/esptool"
  fake() { LC_ALL=en_US.UTF-8 ESPTOOL="$d/esptool" FAKE_IMAGE="$d/same.bin" YB_CONFIRM=RESTORE bash "$0" "$@" 2>&1; }
  out="$(YB_BACKUP_DIR="$d/good" fake backup /dev/null)"; rc=$?; img="$(ls "$d"/good/*/backup.bin 2>/dev/null | head -1)"
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q "备份成立" && [ -n "$img" ] && [ -s "$img.id" ]; then ok=$((ok+1)); echo "  ✅ UTF-8 环境下备份走完并记下板身份"; else fail=$((fail+1)); echo "  ❌ 备份成功通路没走完"; fi
  out="$(YB_BACKUP_DIR="$d/short" FAKE_READ_BYTES=32770 fake backup /dev/null)"
  if [ $? -eq 4 ] && echo "$out" | grep -q "长度不符"; then ok=$((ok+1)); echo "  ✅ 两次同样截短的读出判备份不成立"; else fail=$((fail+1)); echo "  ❌ 截短的读出未被拒"; fi
  out="$(fake restore /dev/null "$img")"
  if [ $? -eq 0 ] && echo "$out" | grep -q "MOCK WRITE REACHED"; then ok=$((ok+1)); echo "  ✅ 同一块板的备份可回退"; else fail=$((fail+1)); echo "  ❌ 同板回退没走到写入"; fi
  out="$(FAKE_MAC=aa:bb:cc:dd:ee:02 fake restore /dev/null "$img")"
  if [ $? -eq 6 ] && ! echo "$out" | grep -q "MOCK WRITE REACHED"; then ok=$((ok+1)); echo "  ✅ 换了板子拒绝回退"; else fail=$((fail+1)); echo "  ❌ 换了板子未被拒"; fi
  head -c 32770 "$d/same.bin" > "$d/cut.bin"; echo "$(sha "$d/cut.bin")  backup.bin" > "$d/cut.bin.sha256"; cp "$img.id" "$d/cut.bin.id"
  out="$(fake restore /dev/null "$d/cut.bin")"
  if [ $? -eq 6 ] && ! echo "$out" | grep -q "MOCK WRITE REACHED"; then ok=$((ok+1)); echo "  ✅ 长度不足的镜像拒绝回退"; else fail=$((fail+1)); echo "  ❌ 长度不足的镜像未被拒"; fi
  # 旁文件混配：另一份同容量、镜像头合法的镜像，配它自己的真哈希，再配上本板的 .id（审查 X3-10）
  echo "$(sha "$d/other.bin")  backup.bin" > "$d/other.bin.sha256"; cp "$img.id" "$d/other.bin.id"
  out="$(fake restore /dev/null "$d/other.bin")"
  if [ $? -eq 6 ] && echo "$out" | grep -q "不是同一次备份" && ! echo "$out" | grep -q "MOCK WRITE REACHED"; then ok=$((ok+1)); echo "  ✅ 旁文件混配的镜像拒绝回退"; else fail=$((fail+1)); echo "  ❌ 旁文件混配未被拒"; fi
  rm -rf "$d"
  echo "结果：${ok} 过 / ${fail} 失败"
  [ "$fail" -eq 0 ] || return 2
}

case "${1:-}" in
  backup)   [ $# -eq 2 ] || { sed -n '2,8p' "$0"; exit 2; }; backup "$2" ;;
  restore)  [ $# -eq 3 ] || { sed -n '2,8p' "$0"; exit 2; }; restore "$2" "$3" ;;
  bootlog)  [ $# -eq 2 ] || { sed -n '2,9p' "$0"; exit 2; }; bootlog "$2" ;;
  identify) [ $# -eq 2 ] && [ -f "$2" ] || { sed -n '2,8p' "$0"; exit 2; }; identify "$2" ;;
  --self-test) self_test ;;
  *) sed -n '2,16p' "$0"; exit 2 ;;
esac
