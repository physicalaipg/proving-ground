#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yb_jog_log.py —— 带时间戳的逐帧点动记录（内部工单 gate2 A1 补证工具；审定方 10-10「停车时刻以日志为准」）。

与 ~/esp/yb_jog.py 同一口径（10 Hz 发 T:1、每拍跟一条 T:130 查询、限 0.2 m/s／10 s），差别只在**每一帧都带时间戳打印**，
且 watch 窗（段末停发心跳后、不发零速）同样逐帧记录直到轮速 <0.01 或 6 s 超时；末尾给四个时刻：首帧、段末（停发）、自停、自停用时。
不改固件、不碰监视区；只读反馈，运动指令与 yb_jog.py 相同。

用法：
  python3 real/tools/yb_jog_log.py <串口> <左> <右> <秒≤10> [watch] [--csv 文件]
  python3 real/tools/yb_jog_log.py --self-test      # mock 串口自测，不碰硬件
每帧一行：`<自首发起秒> <段内|watch> L=<..> R=<..> tl=<..> tr=<..> boot=<..>`；--csv 另存同列 CSV。
退出码：0 正常；2 用法或串口错误；3 自测失败。
"""
import json, sys, time

LIMIT_MPS, LIMIT_S = 0.2, 10.0


def ask(link, tries=8):
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


def run(link, left, right, seconds, watch, clock=time, out=print, csv_rows=None):
    """段内 10 Hz 发 T:1＋查询；watch 时段末停发、只查询并逐帧记录到自停。返回 (自停用时 或 None, 帧数)。"""
    def emit(phase, t, r):
        row = (round(t, 3), phase, r.get("L"), r.get("R"), r.get("tl"), r.get("tr"), r.get("boot"))
        out("%7.3f  %-5s L=%.4f R=%.4f tl=%.2f tr=%.2f boot=%s" % (t, phase, r.get("L", 0), r.get("R", 0), r.get("tl", 0), r.get("tr", 0), r.get("boot")))
        if csv_rows is not None:
            csv_rows.append(row)
    t0 = clock.monotonic()
    n = 0
    end = t0 + seconds
    while clock.monotonic() < end:
        link.write((json.dumps({"T": 1, "L": left, "R": right}) + "\n").encode())
        r = ask(link)
        if r:
            n += 1
            emit("段内", clock.monotonic() - t0, r)
        clock.sleep(0.08)
    last = clock.monotonic()
    out("段末（停发心跳）t=%.3f s" % (last - t0))
    stop_s = None
    if watch:
        while clock.monotonic() - last < 6:
            r = ask(link)
            if r:
                n += 1
                emit("watch", clock.monotonic() - t0, r)
                if abs(r.get("L", 1)) < 0.01 and abs(r.get("R", 1)) < 0.01:
                    stop_s = clock.monotonic() - last
                    out("自停 t=%.3f s；自停用时 %.2f 秒（自段末起）" % (clock.monotonic() - t0, stop_s))
                    break
            clock.sleep(0.05)
        else:
            out("6 秒内未自停")
    link.write(b'{"T":1,"L":0.0,"R":0.0}\n')
    return stop_s, n


# ---------- mock 自测 ----------
class _FakeClock:
    def __init__(self): self.now = 0.0
    def monotonic(self): return self.now
    def sleep(self, s): self.now += s


class _FakeLink:
    """模拟固件：有心跳时速度趋向目标；停发心跳后保持目标，超过 heartbeat_s 后速度归零。空读推进假时钟。"""
    def __init__(self, clock, heartbeat_s=3.1):
        self.clock, self.hb = clock, heartbeat_s
        self.target = (0.0, 0.0); self.last_motion = None; self.speed = (0.0, 0.0)
        self.pending = []; self.written = []
    def write(self, data):
        self.written.append(data)
        msg = json.loads(data)
        if msg.get("T") == 1:
            self.target = (msg["L"], msg["R"]); self.last_motion = self.clock.monotonic()
        elif msg.get("T") == 130:
            now = self.clock.monotonic()
            tgt = self.target if (self.last_motion is not None and now - self.last_motion <= self.hb) else (0.0, 0.0)
            # 一阶趋近
            self.speed = tuple(s + 0.5 * (t - s) for s, t in zip(self.speed, tgt))
            self.pending.append(json.dumps({"T": 1001, "L": round(self.speed[0], 4), "R": round(self.speed[1], 4),
                                            "tl": tgt[0], "tr": tgt[1], "boot": 7}).encode() + b"\n")
    def readline(self):
        if self.pending:
            return self.pending.pop(0)
        self.clock.sleep(0.2)
        return b""


def self_test():
    ok = []
    clk = _FakeClock(); link = _FakeLink(clk); outl = []; rows = []
    stop_s, n = run(link, 0.05, 0.0, 2.0, True, clock=clk, out=outl.append, csv_rows=rows)
    seg = [r for r in rows if r[1] == "段内"]; wt = [r for r in rows if r[1] == "watch"]
    ok.append(("段内有帧且带递增时间戳", len(seg) >= 5 and all(a[0] < b[0] for a, b in zip(seg, seg[1:]))))
    ok.append(("watch 窗逐帧记录、速度先非零后归零", len(wt) >= 3 and wt[0][2] > 0.01 and wt[-1][2] < 0.01))
    ok.append(("自停用时≈心跳超时（3.1±0.5 s）", stop_s is not None and abs(stop_s - 3.1) < 0.5))
    ok.append(("末尾发零速", link.written[-1] == b'{"T":1,"L":0.0,"R":0.0}\n'))
    ok.append(("只发 T:1 与 T:130", all(json.loads(w).get("T") in (1, 130) for w in link.written)))
    for name, good in ok:
        print("  %s %s" % ("✅" if good else "❌", name))
    return 0 if all(g for _, g in ok) else 3


def main(argv):
    if argv[:1] == ["--self-test"]:
        return self_test()
    csv_path = None
    if "--csv" in argv:
        i = argv.index("--csv"); csv_path = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    if len(argv) < 4:
        print(__doc__); return 2
    port, left, right, seconds = argv[0], float(argv[1]), float(argv[2]), float(argv[3])
    watch = len(argv) > 4 and argv[4] == "watch"
    if not (abs(left) <= LIMIT_MPS and abs(right) <= LIMIT_MPS and 0 < seconds <= LIMIT_S):
        print("✘ 点动限 %.1f m/s、%.0f 秒" % (LIMIT_MPS, LIMIT_S)); return 2
    import serial
    try:
        link = serial.Serial(port, 115200, timeout=0.2)
    except Exception as e:
        print("✘ 开口失败：%s" % e); return 2
    time.sleep(3)                      # 开口即复位板子，等它起来并过完 2 秒静默
    link.reset_input_buffer()
    rows = [] if csv_path else None
    print("首发 wall=%s" % time.strftime("%H:%M:%S"))
    try:
        run(link, left, right, seconds, watch, csv_rows=rows)
    finally:
        link.close()
    if csv_path:
        import csv
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["t_s", "phase", "L", "R", "tl", "tr", "boot"]); w.writerows(rows)
        print("CSV → %s（%d 帧）" % (csv_path, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
