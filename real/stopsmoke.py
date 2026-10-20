"""X3-15 板上冒烟（门一步 5a；内部工单 §4）。冒烟，非证明。

台架四轮离地。「非零—停—非零」交替 ≥20 次：每次以慢速转 run_s 秒，发零速，然后在 watch_s 秒内只问反馈、不再发任何
非零指令，逐帧记轮速与固件目标（tl、tr）。判据：任一次停后、在收到新的非零指令之前，已经停稳的轮子又转起来
（轮速超过停稳阈值或固件目标不是 0）＝「复转」，门一失守；watch_s 内一直没停稳＝「未停」。全部通过只说明这几十次
在这块板上没有复现 X3-15 的时序，不证明固件的停车保证成立；双核调度与串口积压的最坏情形不在这里。
结果记 smoke_runs/<日期>-stopsmoke/stop.csv，沿用 stallcheck 的目录法，不与回合数据混。走驱动层（急停、确认都照常）。
"""
import argparse
import csv
from pathlib import Path
import time

from real import smoke
from real.ugv02 import UGV02, UGV02Config


def cycle_once(driver, speed, run_s, watch_s, clock):
    """一次「非零—停—看」。返回 (判词, 帧列表)；判词 ∈ pass / 复转 / 未停。"""
    driver.move_for(speed, speed, run_s)         # 到时限自己发零速并问一帧
    frames, stopped_seen, verdict = [], False, "未停"
    deadline = clock.monotonic() + watch_s
    period = driver.config.heartbeat_period_s
    while clock.monotonic() < deadline and not driver.estopped:
        reply = driver.feedback()                # 只问，不发任何非零
        frames.append(reply)
        if driver._frame_shows_stopped(reply):
            stopped_seen, verdict = True, "pass"
        elif stopped_seen:
            return "复转", frames                 # 停稳过、没发过非零、又动了
        clock.sleep(period)                      # 按续发周期问，不空转
    if driver.estopped and verdict == "pass":
        verdict = "急停锁存：" + driver.reason    # 看的途中链路或固件出了故障
    return verdict, frames


def run(driver, *, cycles=20, speed=0.1, run_s=0.5, watch_s=0.6, clock=None, writer=None):
    clock = clock or driver.clock
    results = []
    for n in range(1, cycles + 1):
        if driver.estopped:
            results.append((n, "急停锁存"))
            break
        verdict, frames = cycle_once(driver, speed, run_s, watch_s, clock)
        results.append((n, verdict))
        if writer:
            for k, reply in enumerate(frames):
                writer.writerow([n, k, reply.get("L"), reply.get("R"), reply.get("tl"), reply.get("tr"), verdict])
        if verdict != "pass":
            break
    return results


def main(argv=None, *, link=None, clock=None):
    parser = argparse.ArgumentParser(description="X3-15 bench smoke: nonzero-stop-nonzero cycles, wheels off the ground")
    parser.add_argument("--port", help="serial port; omit only when a link is injected")
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--speed", type=float, default=0.1)
    parser.add_argument("--run-s", type=float, default=0.5)
    parser.add_argument("--watch-s", type=float, default=0.6)
    parser.add_argument("--out", help="output directory (default smoke_runs/<date>-stopsmoke)")
    args = parser.parse_args(argv)
    if args.cycles < 1 or not all(x > 0 for x in (args.speed, args.run_s, args.watch_s)):
        parser.error("cycles >= 1 and speed/run-s/watch-s > 0")
    out_dir = Path(args.out or smoke.ROOT / "smoke_runs" / time.strftime("%Y%m%d-stopsmoke")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    driver = UGV02(link, clock=clock, config=UGV02Config()) if link is not None else UGV02.connect(args.port)
    try:
        with open(out_dir / "stop.csv", "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if f.tell() == 0:
                writer.writerow(["cycle", "frame", "L", "R", "tl", "tr", "verdict"])
            results = run(driver, cycles=args.cycles, speed=args.speed, run_s=args.run_s, watch_s=args.watch_s,
                          clock=clock, writer=writer)
    finally:
        driver.close()
    passed = sum(1 for _, v in results if v == "pass")
    last = results[-1][1] if results else "无"
    print("冒烟，非证明：%d/%d 次通过；末次＝%s；记录 %s" % (passed, args.cycles, last, out_dir / "stop.csv"))
    print("判词：%s" % ("pass" if passed == args.cycles else "门一失守（%s）" % last))
    return 0 if passed == args.cycles else 1


if __name__ == "__main__":
    raise SystemExit(main())
