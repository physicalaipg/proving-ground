"""Bench check of the control-task stall hooks (internal work order patch 4 R3). Wheels off the ground, one stall per call.

Needs a firmware built with YB_SELFTEST; its version carries the -selftest suffix. The tool spins the wheels at
jog speed, sends one hook command and times from that write to the banner the firmware prints after the reset
that follows. Then it reads the reset cause back and watches the wheel speeds until the limit has passed.
Whether the motors stopped is judged by eye and on video; this is the serial side of the same event.
It talks to the port directly, not through the driver layer, and what it writes is never episode data.
"""
import argparse
import csv
import json
from pathlib import Path
import sys
import time

from real import smoke
from real.ugv02 import SELFTEST_SUFFIX, SystemClock, reset_class

HOOKS = {"block": b'{"T":9101,"hook":"yb_stall_block"}\n',              # blocks forever
         "spin": b'{"T":9102,"hook":"yb_stall_spin"}\n',                # busy loop, interrupts on
         "spin_noirq": b'{"T":9103,"hook":"yb_stall_spin_noirq"}\n',    # busy loop, interrupts off
         "abort": b'{"T":9104,"hook":"yb_stall_abort"}\n'}
# What the ESP-IDF 5.1 documentation leads one to expect, not a measurement. The verdict uses the class only.
EXPECTED = {"block": (6,), "spin": (6,), "spin_noirq": (5, 6), "abort": (4,)}
ZERO, QUERY = b'{"T":1,"L":0.0,"R":0.0}\n', b'{"T":130}\n'
LIMIT_S = 2.0           # wheels still turning this long after the hook went out: bench red card
WAIT_S = 5.0            # how long to wait for the banner before giving up
STOPPED_MPS = 0.01
FIELDS = ("run", "kind", "verdict", "expected_reason", "reset_reason", "reset_class", "boot_before", "boot_after",
          "rtc_kept", "banner_ver", "hook_to_banner_s", "hook_to_stopped_frame_s", "turning_at_limit",
          "speed_before_mps", "note")


def read_reply(link):
    """One line off the port: a dict, {} for a line that is not a JSON object, None when nothing came."""
    line = link.readline()
    if not line:
        return None
    try:
        reply = json.loads(line)
    except (ValueError, UnicodeError):
        return {}
    return reply if isinstance(reply, dict) else {}


def is_banner(reply):
    return bool(reply) and "fw" in reply and "T" not in reply


def ask(link, tries=8):
    """Query once. Returns (feedback frame or None, error frame or None)."""
    link.write(QUERY)
    for _ in range(tries):
        reply = read_reply(link)
        if reply is None:
            break
        if reply.get("T") == 1001:
            return reply, None
        if reply.get("T") == -1:
            return None, reply
    return None, None


def run_stall(link, kind, *, clock, speed=0.05, spin_s=2.0, settle_s=3.0):
    row = dict.fromkeys(FIELDS, "")
    row.update(kind=kind, expected_reason="|".join(map(str, EXPECTED[kind])), note="")

    def done(verdict, note=""):
        link.write(ZERO)
        row.update(verdict=verdict, note=note)
        return row

    # Opening the port may reset the board: let it boot and sit out its quiet period, and keep its banner.
    end = clock.monotonic() + settle_s
    while clock.monotonic() < end:
        reply = read_reply(link)
        if is_banner(reply):
            row["banner_ver"] = str(reply.get("ver", ""))
    if row["banner_ver"] and not row["banner_ver"].endswith(SELFTEST_SUFFIX):
        return done("not_selftest", "banner says %s" % row["banner_ver"])

    before, error = ask(link)
    if before is None:
        return done("no_frame", json.dumps(error) if error else "no feedback frame before the hook")
    row["boot_before"] = before.get("boot", "")

    end = clock.monotonic() + spin_s
    while clock.monotonic() < end:
        link.write((json.dumps({"T": 1, "L": speed, "R": speed}) + "\n").encode())
        frame, error = ask(link)
        if error is not None:
            return done("refused", json.dumps(error))
        before = frame or before
        clock.sleep(0.08)
    row["speed_before_mps"] = round(min(abs(before["L"]), abs(before["R"])), 4)
    if row["speed_before_mps"] <= STOPPED_MPS:
        return done("not_turning", "wheels were not turning when the hook was due")

    link.write(HOOKS[kind])
    if hasattr(link, "flush"):
        link.flush()
    sent = clock.monotonic()
    banner = None
    while banner is None and clock.monotonic() - sent < WAIT_S:
        reply = read_reply(link)
        if reply and reply.get("T") == -1 and reply.get("err") == "unknown_cmd":
            return done("not_selftest", "the firmware does not know the hook command")
        if is_banner(reply):
            banner = clock.monotonic() - sent
            row.update(banner_ver=str(reply.get("ver", "")), hook_to_banner_s=round(banner, 3))
    if banner is None:
        return done("red_card", "no reset seen within %.0f s of the hook" % WAIT_S)

    # The board is back and inside its quiet period: only zero speed and queries from here on.
    link.write(ZERO)
    after, turning = None, False
    while after is None or clock.monotonic() - sent < LIMIT_S + 0.3:
        frame, _ = ask(link)
        took = clock.monotonic() - sent
        if frame is not None:
            after = after or frame
            moving = max(abs(frame["L"]), abs(frame["R"])) > STOPPED_MPS
            if not moving and row["hook_to_stopped_frame_s"] == "":
                row["hook_to_stopped_frame_s"] = round(took, 3)
            turning = turning or (moving and took >= LIMIT_S)
        if after is None and took > WAIT_S:
            return done("red_card", "no feedback frame after the reset")
        clock.sleep(0.05)
    reason, boot = after.get("reset_reason"), after.get("boot")
    kept = type(boot) is int and type(row["boot_before"]) is int and boot == row["boot_before"] + 1
    row.update(reset_reason="" if reason is None else reason, reset_class=reset_class(reason) or "",
               boot_after="" if boot is None else boot, rtc_kept=int(kept), turning_at_limit=int(turning))
    if banner > LIMIT_S or turning or row["hook_to_stopped_frame_s"] == "":
        return done("red_card", "not stopped within %.0f s of the hook" % LIMIT_S)
    if not row["banner_ver"].endswith(SELFTEST_SUFFIX):
        return done("not_selftest", "banner says %s" % row["banner_ver"])
    if boot == row["boot_before"]:
        return done("boot_unchanged", "the reset did not change the boot count")
    if row["reset_class"] != "fault":
        return done("unexpected_class", "a stalled control task should reset as a fault")
    return done("pass")


def record(out_dir, row, meta):
    """Append the row to <out_dir>/stall.csv; every attempt is kept."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "stall.csv"
    rows = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    row["run"] = len(rows) + 1
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows + [row])
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None, *, link=None, clock=None):
    parser = argparse.ArgumentParser(description="one control-task stall on the bench, wheels off the ground")
    parser.add_argument("--port", required=True, help="serial port of the chassis")
    parser.add_argument("--firmware-ver", required=True,
                        help="version in the firmware's banner; must end with %s" % SELFTEST_SUFFIX)
    parser.add_argument("--kind", required=True, choices=sorted(HOOKS))
    parser.add_argument("--out", help="output directory, inside the repository and outside episodes/")
    parser.add_argument("--speed", type=float, default=0.05, help="wheel speed before the hook, m/s")
    parser.add_argument("--spin-s", type=float, default=2.0, help="how long the wheels turn before the hook")
    args = parser.parse_args(argv)
    if not args.firmware_ver.endswith(SELFTEST_SUFFIX):
        raise SystemExit("the stall hooks only exist in a self-test build (version ending in %s)" % SELFTEST_SUFFIX)
    if not 0 < args.speed <= 0.2 or not 0 < args.spin_s <= 10:
        raise SystemExit("jog limits: 0.2 m/s, 10 s")
    out_dir = Path(args.out or smoke.ROOT / "smoke_runs" / time.strftime("%Y%m%d-selftest")).resolve()
    if smoke.ROOT not in out_dir.parents or (smoke.ROOT / "episodes") in (out_dir, *out_dir.parents):
        raise SystemExit("output must live inside the repository and outside episodes/")
    smoke.check_firmware(out_dir, args.firmware_ver)
    if link is None:
        import serial  # Optional dependency, as in the driver layer.
        link = serial.Serial(args.port, 115200, timeout=0.2)
    try:
        row = run_stall(link, args.kind, clock=clock or SystemClock(), speed=args.speed, spin_s=args.spin_s)
    finally:
        try:
            link.write(ZERO)
        finally:
            link.close()
    record(out_dir, row, {"kind": "selftest-stall", "firmware_ver": args.firmware_ver, "port": args.port,
                          "git_head": smoke.git_head(), "limit_s": LIMIT_S,
                          "note": "bench self-test; never episode data"})
    print(json.dumps(row, ensure_ascii=False))
    if row["verdict"] == "red_card":
        print("RED CARD 台架红牌：立即物理断电，门一不开")
    return 0 if row["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
