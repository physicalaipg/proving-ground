#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yb_volt_watch.py —— 只读电压观察（内部工单 §3；仅标准库＋pyserial）。

用法：
  python3 real/tools/yb_volt_watch.py <串口> [秒数=30] [间隔秒=1.0]
  python3 real/tools/yb_volt_watch.py --self-test        # mock 串口自测，不碰硬件
做什么：
  - 开口不拉 DTR/RTS（先置低再 open），尽量不复位板子；开口后头 1 s 盯着有没有开机行／版本行出现，
    有即打印「开口复位：是」——复位与否由板子实际回话判定，不靠假设。
  - 之后每隔 <间隔秒> 发一条 {"T":130}（只读查询，固件回一帧 T=1001），打印 时刻、v、low_voltage、boot、reset_reason。
  - **不发任何 T:1（运动）指令**；结束不发零速、不改任何状态。
  - 末尾汇总：v 最小／最大、low_voltage 是否出现过 1、boot 在观察期内有没有变。
退出码：0 正常结束；2 用法或串口错误；3 自测失败。
"""
import json, sys, time

BANNER_KEYS = (b'"fw":', b"esp_image:", b"boot: ", b"rst:", b"ESP-ROM")


def open_quiet(port):
    """先把 DTR/RTS 置低再打开，避免自动复位电路被拉；能否真正不复位以 watch_reset 的观察为准。"""
    import serial
    link = serial.Serial()
    link.port, link.baudrate, link.timeout = port, 115200, 0.2
    link.dtr = False
    link.rts = False
    link.open()
    return link


def watch_reset(link, clock, seconds=1.0):
    """开口后静听 seconds 秒：见到开机行或版本行＝板子刚复位。返回 (是否复位, 证据行)。"""
    end = clock.monotonic() + seconds
    evidence = None
    while clock.monotonic() < end:
        line = link.readline()
        if not line:
            continue
        if any(k in line for k in BANNER_KEYS):
            evidence = line.decode("utf-8", "replace").strip()
            break
    return evidence is not None, evidence


def query_once(link, tries=8):
    """只读查询：发 T:130，取回第一帧 T=1001。"""
    link.write(b'{"T":130}\n')
    for _ in range(tries):
        line = link.readline()
        try:
            reply = json.loads(line)
        except ValueError:
            continue
        if isinstance(reply, dict) and reply.get("T") == 1001:
            return reply
    return None


def run(link, seconds, interval, clock=time, out=print):
    reset, evidence = watch_reset(link, clock)
    out("开口复位：%s%s" % ("是" if reset else "否（1 s 内无开机行／版本行）", "｜" + evidence if evidence else ""))
    t0 = clock.monotonic()
    volts, lows, boots, n = [], 0, set(), 0
    while clock.monotonic() - t0 < seconds:
        reply = query_once(link)
        t = clock.monotonic() - t0
        if reply is None:
            out("%6.1f s  无帧" % t)
        else:
            n += 1
            v = float(reply.get("v", float("nan")))
            lv = int(reply.get("low_voltage", -1))
            volts.append(v); lows += (lv == 1); boots.add(reply.get("boot"))
            out("%6.1f s  v=%.2f  low_voltage=%d  boot=%s  reset_reason=%s" % (t, v, lv, reply.get("boot"), reply.get("reset_reason")))
        clock.sleep(interval)
    if volts:
        out("汇总：帧 %d；v 最小 %.2f 最大 %.2f；low_voltage 出现 1 共 %d 帧；boot %s" % (
            n, min(volts), max(volts), lows, "未变" if len(boots) == 1 else "变过（%d 个值）" % len(boots)))
    else:
        out("汇总：%d 帧，无有效帧" % n)
    return 0


class _FakeLink:
    """mock 串口：记录写入，按脚本回行；空读模拟真串口的 0.2 s 超时（推进假时钟，否则静听循环不会结束）。"""
    def __init__(self, lines, clock, banner=False):
        self.written, self._lines, self._clock = [], list(lines), clock
        if banner:
            self._lines.insert(0, b'{"fw":"yb-eet01-json","ver":"0.2.0"}\n')
        self._armed = banner   # 无 banner 时开口静默，readline 回空
    def readline(self):
        if self._lines and (self._armed or self.written):
            return self._lines.pop(0)
        self._clock.sleep(0.2)
        return b""
    def write(self, data):
        self.written.append(data)
        self._armed = True


class _FakeClock:
    def __init__(self): self.now = 0.0
    def monotonic(self): return self.now
    def sleep(self, s): self.now += s


def self_test():
    frame = lambda v, lv, boot: json.dumps({"T": 1001, "L": 0, "R": 0, "v": v, "low_voltage": lv, "boot": boot, "reset_reason": 1}).encode() + b"\n"
    ok = []
    # ① 不复位、两帧、只写了 T:130
    clk = _FakeClock(); link = _FakeLink([frame(7.81, 0, 11), frame(7.79, 0, 11)], clk)
    outl = []
    run(link, seconds=2, interval=1.0, clock=clk, out=outl.append)
    ok.append(("只发 T:130、不发 T:1", all(w == b'{"T":130}\n' for w in link.written) and len(link.written) == 2))
    ok.append(("不复位判「否」", outl[0].startswith("开口复位：否")))
    ok.append(("汇总 v 范围与 boot 未变", "v 最小 7.79 最大 7.81" in outl[-1] and "boot 未变" in outl[-1]))
    # ② 开口见版本行→判「是」；low_voltage 1 计数；boot 变
    clk = _FakeClock(); link = _FakeLink([frame(5.01, 1, 5), frame(5.0, 1, 6)], clk, banner=True)
    outl = []
    run(link, seconds=2, interval=1.0, clock=clk, out=outl.append)
    ok.append(("开口见版本行判「是」", outl[0].startswith("开口复位：是")))
    ok.append(("low_voltage 1 计 2 帧、boot 变过", "共 2 帧" in outl[-1] and "变过" in outl[-1]))
    for name, good in ok:
        print("  %s %s" % ("✅" if good else "❌", name))
    return 0 if all(g for _, g in ok) else 3


def main(argv):
    if argv[:1] == ["--self-test"]:
        return self_test()
    if not argv or argv[0].startswith("-"):
        print(__doc__); return 2
    port = argv[0]
    seconds = float(argv[1]) if len(argv) > 1 else 30.0
    interval = float(argv[2]) if len(argv) > 2 else 1.0
    try:
        link = open_quiet(port)
    except Exception as e:   # 串口不存在／被占用
        print("✘ 开口失败：%s" % e); return 2
    try:
        return run(link, seconds, interval)
    finally:
        link.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
