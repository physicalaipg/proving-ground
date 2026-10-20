"""YB-EET01 固件协议核心的宿主侧自检：同一个驱动层分别接 mock 串口与固件协议核心，逐项比对。不接板。"""
from collections import deque
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zlib

import numpy as np
import pytest

from harness.interface import Action
from real.camera import Camera, CameraConfig
from real.mock_serial import FakeClock, MockSerial
from real.real_env import RealRobotUGV02
from real import smoke, stallcheck
from real.ugv02 import (BadArgsError, BootQuietError, FirmwareError, LowVoltageError, SafetyError, UGV02, UGV02Config,
                        UnknownCommandError, YB_EET01, reset_class)

FIRMWARE = Path(__file__).resolve().parents[2] / "real" / "firmware" / "yb-eet01-json"


@pytest.fixture(scope="session")
def proto_host(tmp_path_factory):
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("宿主机没有 C 编译器")
    out = tmp_path_factory.mktemp("yb") / "proto_host"
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
                    "-I", str(FIRMWARE / "components" / "proto"),
                    str(FIRMWARE / "components" / "proto" / "yb_proto.c"),
                    str(FIRMWARE / "host_test" / "proto_host.c"), "-lm", "-o", str(out)], check=True)
    return out


@pytest.fixture(scope="session")
def wheel_host(tmp_path_factory):
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("宿主机没有 C 编译器")
    out = tmp_path_factory.mktemp("yb") / "wheel_host"
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
                    "-I", str(FIRMWARE / "components" / "proto"), "-I", str(FIRMWARE / "main"),
                    str(FIRMWARE / "components" / "proto" / "yb_wheel.c"),
                    str(FIRMWARE / "host_test" / "wheel_host.c"), "-lm", "-o", str(out)], check=True)
    return out


@pytest.fixture(scope="session")
def boot_host(tmp_path_factory):
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("宿主机没有 C 编译器")
    out = tmp_path_factory.mktemp("yb") / "boot_host"
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
                    "-I", str(FIRMWARE / "components" / "proto"),
                    str(FIRMWARE / "components" / "proto" / "yb_boot.c"),
                    str(FIRMWARE / "host_test" / "boot_host.c"), "-o", str(out)], check=True)
    return out


def test_zero_target_brakes_one_wheel_and_clears_its_pid(wheel_host):
    """审查 X3-02：一只轮堵转 100 拍后目标归零，输出当拍为零，历史输出不带进下一次起步。"""
    want = 0.1 / (math.pi * 0.065 / 1040 / 0.01)     # 0.1 m/s 换成每拍脉冲数
    beats = ["%.6f 0" % want] * 100 + ["0 0"] * 3 + ["%.6f 0" % want]
    reply = subprocess.run([str(wheel_host)], input="\n".join(beats) + "\n", capture_output=True, text=True,
                           check=True).stdout.splitlines()
    rows = [tuple(float(value) for value in line.split()) for line in reply]
    assert len(rows) == 104 and 100 < rows[99][0] <= 200
    assert rows[100:103] == [(0.0, 0.0, 0.0)] * 3
    assert rows[103] == rows[0]


class FirmwareSerial:
    """把固件协议核心包成串口对象；时间取注入的时钟，逐行同步。"""

    def __init__(self, binary, clock, limit_mps=0.5, boot_quiet=False, volts=7.4):
        self.clock = clock
        # 固件在时刻 0 开机。缺省让时钟零点落在开机静默期之后；boot_quiet 为真时两者重合
        self._since_boot_ms = 0 if boot_quiet else 2000
        self.is_open = True
        self.timeout = self.write_timeout = 0.2
        self._buffer = b""
        self._replies = []
        self._proc = subprocess.Popen([str(binary), str(limit_mps), "6.5", str(volts), "7", "1"],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def _ask(self, content):
        self._proc.stdin.write("%d %s\n" % (round(self.clock.monotonic() * 1000) + self._since_boot_ms, content))
        self._proc.stdin.flush()
        lines = []
        while True:
            line = self._proc.stdout.readline()
            if line in ("", ".\n"):
                return lines
            lines.append(line)

    def write(self, data):
        if not self.is_open:
            raise OSError("firmware serial closed")
        self._buffer += data
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            self._replies += [out[2:].encode() for out in self._ask(line.decode()) if out.startswith("O ")]
        return len(data)

    def readline(self):
        if not self.is_open:
            raise OSError("firmware serial closed")
        return self._replies.pop(0) if self._replies else b""

    @property
    def wheels(self):
        _, left, right, _ = self._ask("?")[0].split()
        return float(left), float(right)

    @property
    def stop(self):
        """停车锁存：0 无，1 心跳，2 低压，4 复位。"""
        return int(self._ask("?")[0].split()[3])

    def voltage(self, volts):
        self._ask("V%.3f" % volts)

    def same_beat(self, cmd):
        """送一行指令，之前不走控制环那一拍：与上一行落在同一拍里。"""
        self._replies += [out[2:].encode() for out in self._ask("!" + json.dumps(cmd)) if out.startswith("O ")]

    def withhold(self, cmd):
        """串口任务收完这一行、写了停车序号，停在投指令槽之前：快照压住不投。之前不走控制环那一拍。"""
        self._replies += [out[2:].encode() for out in self._ask("!H" + json.dumps(cmd)) if out.startswith("O ")]

    def post(self):
        """把压住的快照按先后放一张进指令槽。之前不走控制环那一拍。"""
        self._ask("!P")

    def close(self):
        self.is_open = False
        if self._proc.poll() is None:
            self._proc.stdin.close()
            self._proc.wait(timeout=5)


def send(serial, cmd):
    serial.write((json.dumps(cmd) + "\n").encode())


def robot_on(serial, clock):
    camera = Camera(CameraConfig(width=8, height=6),
                    frame_source=lambda: np.zeros((6, 8, 3), dtype=np.uint8))
    return RealRobotUGV02(UGV02(serial, clock=clock), camera)


@pytest.mark.parametrize("action", [Action.FORWARD, Action.LEFT, Action.RIGHT, Action.STOP])
def test_driver_runs_unchanged_and_matches_mock(proto_host, action):
    results = []
    for make in (lambda c: MockSerial(c), lambda c: FirmwareSerial(proto_host, c)):
        clock = FakeClock()
        serial = make(clock)
        robot = robot_on(serial, clock)
        robot.reset(5, "instruction")
        result = robot.act(action)
        results.append((result.duration_s, result.extra["odometry"], serial.wheels))
        robot.close()
    mock, firmware = results
    assert firmware[0] == pytest.approx(mock[0])
    assert firmware[1]["distance_m"] == pytest.approx(mock[1]["distance_m"], abs=1e-4)
    assert firmware[1]["yaw_rad"] == pytest.approx(mock[1]["yaw_rad"], abs=1e-3)
    assert tuple(firmware[2]) == tuple(mock[2]) == (0, 0)


def test_feedback_frame_fields_match_mock(proto_host):
    frames = []
    for make in (lambda c: MockSerial(c), lambda c: FirmwareSerial(proto_host, c)):
        clock = FakeClock()
        serial = make(clock)
        send(serial, {"T": 143, "cmd": 0})
        send(serial, {"T": 1, "L": 0.2, "R": -0.1})
        send(serial, {"T": 130})
        replies = [json.loads(line) for line in iter(serial.readline, b"")]
        frames.append(replies[-1])
        # mock 缺省回显开，关回显那一条自身会被回显；固件缺省回显关
        assert [reply["T"] for reply in replies[:-1]] in ([], [143])
    mock, firmware = frames
    assert list(mock) == ["T", "L", "R", "r", "p", "y", "temp", "v"]
    assert list(firmware) == list(mock) + ["low_voltage", "reset_reason", "boot", "tl", "tr"]   # 原字段名与次序不动，新字段排在最后
    assert (firmware["low_voltage"], firmware["reset_reason"], firmware["boot"]) == (0, 1, 7)
    assert (firmware["tl"], firmware["tr"]) == pytest.approx((0.2, -0.1))   # 控制侧当前目标（审查 X3-08）
    assert firmware["T"] == mock["T"] == 1001
    assert (firmware["L"], firmware["R"]) == pytest.approx((mock["L"], mock["R"]))
    assert all(isinstance(firmware[key], (int, float)) for key in firmware)


def test_watchdog_zeroes_wheels_like_mock(proto_host):
    for make in (lambda c: MockSerial(c), lambda c: FirmwareSerial(proto_host, c)):
        clock = FakeClock()
        serial = make(clock)
        send(serial, {"T": 136, "cmd": 3000})
        send(serial, {"T": 1, "L": 0.2, "R": 0.2})
        clock.sleep(3.0)
        assert serial.wheels == pytest.approx((0.2, 0.2))
        send(serial, {"T": 130})  # 查询不刷新心跳
        clock.sleep(0.001)
        assert serial.wheels == (0, 0)


def test_watchdog_cannot_be_lengthened_or_disabled(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 136, "cmd": 600000})
    send(serial, {"T": 1, "L": 0.2, "R": 0.2})
    clock.sleep(3.001)
    assert serial.wheels == (0, 0) and serial.stop == 1
    send(serial, {"T": 136, "cmd": 0})
    send(serial, {"T": 1, "L": 0.2, "R": 0.2})
    assert serial.stop == 0   # 心跳锁存由有效运动指令清除
    clock.sleep(0.101)
    assert serial.wheels == (0, 0)


def test_speed_limits(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    send(serial, {"T": 1, "L": 2.5, "R": 0.0})    # 超 ±2.0：整条忽略
    assert serial.wheels == pytest.approx((0.1, 0.1))
    send(serial, {"T": 1, "L": 0.9, "R": -0.9})   # 超固件限幅：夹到限幅值
    assert serial.wheels == pytest.approx((0.5, -0.5))
    assert serial.readline() == b""


@pytest.mark.parametrize("line", [b"not json", b"[1,2]", b'{"T":1,"L":0.2,"R":0.2', b'{"T":1,"L":NaN,"R":0}',
                                  b'{"T":1,"L":{"a":1},"R":0}', b"{" + b" " * 300 + b"}", b""])
def test_bad_lines_are_dropped_silently(proto_host, line):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    serial.write(line + b"\n")
    assert serial.readline() == b"" and serial.wheels == (0, 0)


@pytest.mark.parametrize("cmd,err,got", [({"T": 0}, "unknown_cmd", 0), ({"T": 136}, "bad_args", 136),
                                         ({"T": "1"}, "bad_args", -1)])
def test_error_frames_for_other_commands_are_skipped(proto_host, cmd, err, got):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    driver = UGV02(serial, clock=clock)
    send(serial, cmd)
    assert serial.wheels == (0, 0)
    assert driver.feedback()["T"] == 1001     # 非运动指令的错帧排在前面，驱动层跳过
    assert not driver.estopped
    send(serial, cmd)
    assert json.loads(serial.readline()) == {"T": -1, "err": err, "got": got}


@pytest.mark.parametrize("cmd,error,kind", [({"T": 1, "L": 0.1}, BadArgsError, "bad_args"),
                                            ({"T": 13, "X": 0.1, "Z": 0.3}, UnknownCommandError, "unknown"),
                                            ({"T": 11, "L": 100, "R": 100}, UnknownCommandError, "unknown")])
def test_error_frames_for_motion_commands_raise_typed_errors(proto_host, cmd, error, kind):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    driver = UGV02(serial, clock=clock)
    send(serial, cmd)
    with pytest.raises(error) as caught:
        driver.feedback()
    assert isinstance(caught.value, FirmwareError) and isinstance(caught.value, SafetyError)
    assert caught.value.kind == kind
    assert driver.estopped and serial.wheels == (0, 0)


def test_ugv02_frames_without_error_frames_behave_as_before():
    clock = FakeClock()
    serial = MockSerial(clock)
    driver = UGV02(serial, clock=clock)
    serial.replay = deque([{"T": 1001, "L": 0.0, "R": 0.0}, {"T": 1002, "x": 1}])
    assert driver.feedback() == {"T": 1001, "L": 0.0, "R": 0.0}
    assert not driver.estopped
    with pytest.raises(SafetyError, match="feedback timeout"):      # 不认识的帧照旧跳过，读不到 T=1001 照旧超时
        driver.feedback()


def test_echo_switch(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 130})
    assert json.loads(serial.readline())["T"] == 1001 and serial.readline() == b""   # 缺省不回显
    send(serial, {"T": 143, "cmd": 1})
    send(serial, {"T": 130})
    assert [json.loads(line)["T"] for line in iter(serial.readline, b"")] == [130, 1001]


def test_low_voltage_needs_two_seconds_below_threshold(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 136, "cmd": 3000})
    for volts, wait in ((6.4, 1.9), (6.6, 0.2), (6.4, 1.0), (6.4, 0.9)):   # 中途回到阈值以上，计时重来
        send(serial, {"T": 1, "L": 0.1, "R": 0.1})
        serial.voltage(volts)
        clock.sleep(wait)
        send(serial, {"T": 1, "L": 0.1, "R": 0.1})
        assert serial.stop == 0 and serial.wheels == pytest.approx((0.1, 0.1))
    clock.sleep(0.1)
    serial.voltage(6.4)            # 连续低于阈值满 2 秒
    assert serial.stop == 2 and serial.wheels == (0, 0)


def test_low_voltage_latch_cannot_be_cleared_by_software(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    driver = UGV02(serial, clock=clock)
    serial.voltage(6.0)
    clock.sleep(2.0)
    serial.voltage(6.0)
    assert serial.stop == 2
    serial.voltage(8.0)            # 电压回升不解锁
    clock.sleep(5.0)
    serial.voltage(8.0)
    for cmd in ({"T": 1, "L": 0.0, "R": 0.0}, {"T": 136, "cmd": 3000}, {"T": 143, "cmd": 0}, {"T": 0}):
        send(serial, cmd)
    assert serial.stop == 2
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert serial.wheels == (0, 0)
    with pytest.raises(LowVoltageError):
        driver.feedback()
    with pytest.raises(SafetyError):
        driver.clear_estop()       # 上位机的清除入口对低压无效
    assert driver.estopped and serial.stop == 2 and serial.wheels == (0, 0)


def test_every_zero_speed_command_buys_one_braked_beat(proto_host):
    """不变量①：零速到达后一个控制周期内必生效，同一拍里后面又到了非零指令也先刹一拍。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert serial.wheels == pytest.approx((0.1, 0.1))
    serial.same_beat({"T": 1, "L": 0.0, "R": 0.0})
    serial.same_beat({"T": 1, "L": 0.2, "R": 0.2})
    assert serial.wheels == (0, 0)                      # 这一拍刹停
    assert serial.wheels == pytest.approx((0.2, 0.2))   # 后到的非零指令下一拍生效
    serial.same_beat({"T": 1, "L": 0.2, "R": 0.2})
    serial.same_beat({"T": 1, "L": 0.0, "R": 0.0})
    assert serial.wheels == (0, 0) and serial.wheels == (0, 0) and serial.stop == 0


def test_stop_seq_without_its_snapshot_keeps_wheels_at_zero(proto_host):
    """审查 X3-15：串口任务停在写停车序号与投指令槽之间，控制环走多少拍都不再出旧目标。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert serial.wheels == pytest.approx((0.1, 0.1))
    serial.withhold({"T": 1, "L": 0.0, "R": 0.0})
    assert [serial.wheels for _ in range(5)] == [(0, 0)] * 5
    serial.post()                                       # 零速的快照这才到
    assert serial.wheels == (0, 0) and serial.wheels == (0, 0) and serial.stop == 0


def test_snapshot_older_than_the_stop_is_not_taken(proto_host):
    """审查 X3-15：停车序号先被取走，早于它的非零快照后到也不取；恢复只认明确更晚的指令。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert serial.wheels == pytest.approx((0.1, 0.1))
    serial.withhold({"T": 1, "L": 0.2, "R": 0.2})       # 序号 N-1，控制侧还没收下
    serial.withhold({"T": 1, "L": 0.0, "R": 0.0})       # 序号 N 的零速：停车序号先到
    assert serial.wheels == (0, 0)
    serial.post()                                       # N-1 的快照这才到
    assert serial.wheels == (0, 0) and serial.wheels == (0, 0)
    serial.post()                                       # 零速 N 的快照到
    assert serial.wheels == (0, 0) and serial.stop == 0
    send(serial, {"T": 1, "L": 0.2, "R": 0.2})          # N+1
    assert serial.wheels == pytest.approx((0.2, 0.2)) and serial.stop == 0


def test_later_command_in_the_beat_of_a_stop_still_takes_effect(proto_host):
    """不变量②不回归：槽里已是零速之后的非零指令、停车序号是那条零速的，刹一拍后非零指令生效。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert serial.wheels == pytest.approx((0.1, 0.1))
    serial.withhold({"T": 1, "L": 0.0, "R": 0.0})       # 序号 N，停车序号已写
    serial.same_beat({"T": 1, "L": 0.2, "R": 0.2})      # 序号 N+1 盖进指令槽
    assert serial.wheels == (0, 0)
    assert serial.wheels == pytest.approx((0.2, 0.2)) and serial.stop == 0
    serial.withhold({"T": 1, "L": 0.0, "R": 0.0})       # 停车序号先被取走，随后槽里直接到了更晚的非零指令
    assert serial.wheels == (0, 0)
    serial.same_beat({"T": 1, "L": 0.3, "R": 0.3})
    assert serial.wheels == pytest.approx((0.3, 0.3)) and serial.stop == 0


# ── 审查 X3-08：端到端停车确认 ──

def frame(left, right, **extra):
    return {"T": 1001, "L": left, "R": right, "r": 0, "p": 0, "y": 0, "temp": 25, "v": 7.4, **extra}


def test_feedback_reports_the_control_target(proto_host):
    """反馈帧的 tl、tr 是控制侧当前目标：零速收下后为 0，停车序号先到、快照压住时也为 0。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 1, "L": 0.1, "R": -0.1})
    send(serial, {"T": 130})
    reply = json.loads(serial.readline())
    assert (reply["tl"], reply["tr"]) == pytest.approx((0.1, -0.1))
    send(serial, {"T": 1, "L": 0.2, "R": 0.2})
    serial.withhold({"T": 1, "L": 0.0, "R": 0.0})        # 停车序号写了，零速快照压住
    send(serial, {"T": 130})                             # 这一拍控制侧凭序号清目标
    reply = json.loads(serial.readline())
    assert (reply["L"], reply["R"], reply["tl"], reply["tr"]) == (0, 0, 0, 0)
    serial.post()
    send(serial, {"T": 130})
    reply = json.loads(serial.readline())
    assert (reply["tl"], reply["tr"]) == (0, 0) and serial.stop == 0


def test_emergency_stop_is_confirmed_against_firmware_feedback(proto_host):
    """上位机急停后读反馈确认：固件目标 0 且轮速停稳才算确认；固件协议核心上一帧即确认。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    robot = robot_on(serial, clock)
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert serial.wheels == pytest.approx((0.1, 0.1))
    robot.emergency_stop()
    assert robot.driver.stop_confirmed is True and robot.driver.stop_confirm_reads == 1
    assert serial.wheels == (0, 0)


def test_emergency_stop_resends_zero_speed_until_feedback_shows_stopped():
    """确认不了就再发一次零速再问，直到一帧显示停稳；每次读都附带一条零速。"""
    clock = FakeClock()
    serial = MockSerial(clock, replay=[frame(0.1, 0.1, tl=0.1, tr=0.1), frame(0, 0, tl=0.1, tr=0.1), frame(0, 0, tl=0, tr=0)])
    driver = UGV02(serial, clock=clock)
    serial.commands.clear()
    driver.emergency_stop("test")
    kinds = [command["T"] for _, command in serial.commands]
    assert kinds == [1, 130, 1, 130, 1, 130]              # 零速、问；不确认→零速、问；再不确认→零速、问
    assert all(command == {"T": 1, "L": 0.0, "R": 0.0} for _, command in serial.commands if command["T"] == 1)
    assert driver.stop_confirmed is True and driver.stop_confirm_reads == 3 and driver.estopped


@pytest.mark.parametrize("replay", [
    [frame(0.1, 0.1)] * 5,                                 # 轮子一直在转
    [frame(0, 0, tl=0.1, tr=0.1)] * 5,                     # 轮速 0 但固件目标不是 0（堵转也算没停）
    [],                                                    # 链路不回
])
def test_emergency_stop_reports_unconfirmed_when_no_frame_shows_stopped(replay):
    """三次读都确认不了：stop_confirmed=False、读次数封顶在 stop_confirm_tries，锁存与原因不变、不抛错。"""
    clock = FakeClock()
    serial = MockSerial(clock, replay=replay)
    driver = UGV02(serial, clock=clock, config=UGV02Config(stop_confirm_tries=3))
    serial.commands.clear()
    driver.emergency_stop("first reason")
    assert driver.stop_confirmed is False and driver.stop_confirm_reads == 3
    assert driver.estopped and driver.reason == "first reason"
    assert [command["T"] for _, command in serial.commands] == [1, 130, 1, 130, 1, 130]


def test_fault_seen_while_confirming_keeps_the_first_reason():
    """确认期间读到 boot 变了：记故障，不再递归急停，原因仍是第一条。"""
    clock = FakeClock()
    serial = MockSerial(clock, replay=[frame(0, 0, boot=7), frame(0, 0, boot=8)])
    driver = UGV02(serial, clock=clock)
    driver.feedback()
    driver.episode_mark = (driver.lock_faults, driver.boot)
    driver.emergency_stop("first reason")
    assert driver.stop_confirmed is True and driver.episode_fault == "reset" and driver.reason == "first reason"


@pytest.mark.parametrize("reply,stopped", [
    (frame(0, 0), True),                                   # UGV02 固件没有 tl/tr：只看轮速
    (frame(0.02, 0), False),
    (frame(0, 0, tl=0, tr=0), True),
    (frame(0, 0, tl=0.1, tr=0), False),
    (frame(0, 0, tl=0), False),                            # 两个字段缺一不算
    (frame(0, 0, tl=True, tr=True), False),                # 布尔不算数
    (frame(0, 0, tl="0", tr="0"), False),
])
def test_frame_shows_stopped_rule(reply, stopped):
    driver = UGV02(MockSerial(FakeClock()), clock=FakeClock())
    assert driver._frame_shows_stopped(reply) is stopped


def test_verify_stopped_after_motion_also_requires_target_zero():
    """回合动作结束的停稳核验：轮速 0 但固件目标不是 0 也判「停后仍在动」，回合作废。"""
    clock = FakeClock()
    # STOP 动作：到时限的零速后问一帧（目标 0），静置后停稳核验再问一帧（轮速 0、目标 0.1）
    serial = MockSerial(clock, replay=deque([frame(0, 0, tl=0, tr=0), frame(0, 0, tl=0.1, tr=0.1)] + [frame(0, 0, tl=0, tr=0)] * 5))
    robot = robot_on(serial, clock)
    moving = robot.act(Action.STOP)
    assert moving.extra["estopped"] and moving.extra["reason"] == "wheels still moving after stop"
    assert moving.extra["stop_confirmed"] is True   # 急停后的确认读到目标 0 的帧


def test_commands_inside_one_beat_all_take_effect(proto_host):
    """不变量②：同一拍之内连到的设置与运动指令都生效，后到的运动指令为准，设置不被覆盖掉。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    assert serial.stop == 4                             # 先走一拍，遥测槽里有了静默期后的快照
    serial.same_beat({"T": 136, "cmd": 500})
    serial.same_beat({"T": 1, "L": 0.1, "R": 0.1})
    serial.same_beat({"T": 143, "cmd": 1})
    serial.same_beat({"T": 1, "L": 0.2, "R": 0.1})
    serial.same_beat({"T": 130})                        # 查询不等控制环：回的是上一拍的快照
    replies = [json.loads(line) for line in iter(serial.readline, b"")]
    assert [reply["T"] for reply in replies] == [1, 130, 1001] and replies[-1]["L"] == 0
    assert serial.wheels == pytest.approx((0.2, 0.1))
    clock.sleep(0.5)
    assert serial.wheels == pytest.approx((0.2, 0.1)) and serial.stop == 0
    clock.sleep(0.001)
    assert serial.wheels == (0, 0) and serial.stop == 1   # 心跳设置 500 ms 生效


def test_no_task_waits_for_another():
    """不变量③：串口任务永不等待控制任务，反之亦然。main.c 里没有锁，队列收发一律零等待。"""
    source = (FIRMWARE / "main" / "main.c").read_text(encoding="utf-8")
    code = "\n".join(line.split("//")[0] for line in source.splitlines())
    for banned in ("xSemaphore", "portMAX_DELAY", "xQueueSend", "proto_lock"):
        assert banned not in code
    waits = re.findall(r"xQueue(?:Receive|Peek)\([^;]*?,\s*([^,()]+)\)", code)
    assert len(waits) == 3 and set(waits) == {"0"}
    assert code.count("xQueueOverwrite(") == 3 and code.count("esp_task_wdt_reset()") == 1


def test_boot_quiet_refuses_motion_for_two_seconds(proto_host):
    """修订5 R2：任何复位后 2 s 内不出力；静默期过后复位锁存由下一条有效 T:1 清除。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock, boot_quiet=True)
    driver = UGV02(serial, clock=clock)                 # 开头的零速与设置照收
    assert serial.stop == 4 and not driver.estopped
    clock.sleep(1.999)
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert json.loads(serial.readline()) == {"T": -1, "err": "boot_quiet", "got": 1}
    assert serial.stop == 4 and serial.wheels == (0, 0)
    clock.sleep(0.001)
    assert serial.stop == 4 and serial.wheels == (0, 0)   # 静默期过了不会自己动
    for cmd in ({"T": 130}, {"T": 136, "cmd": 3000}, {"T": 143, "cmd": 0}, {"T": 0}):
        send(serial, cmd)
    assert serial.stop == 4
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert serial.stop == 0 and serial.wheels == pytest.approx((0.1, 0.1))


def test_motion_refused_for_boot_quiet_voids_the_episode(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock, boot_quiet=True)
    robot = robot_on(serial, clock)
    robot.reset(5, "instruction")
    result = robot.act(Action.FORWARD)
    assert result.extra["void"] and result.extra["void_reason"] == "reset" and result.extra["estopped"]
    assert serial.wheels == (0, 0)
    robot.close()


def test_low_voltage_relatches_inside_boot_quiet(proto_host):
    """修订5 R2：复位清掉低压锁存，电压仍低则静默期内重新锁上；采样晚到时静默顺延到去抖段落定。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock, boot_quiet=True, volts=6.0)
    for wait in (1.0, 1.05):
        clock.sleep(wait)
        send(serial, {"T": 1, "L": 0.1, "R": 0.1})
        assert json.loads(serial.readline()) == {"T": -1, "err": "boot_quiet", "got": 1}
        assert serial.stop == 4 and serial.wheels == (0, 0)
    serial.voltage(6.0)                                 # 开机后 2.05 s 才到的采样
    assert serial.stop == 2
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    assert json.loads(serial.readline()) == {"T": -1, "err": "low_voltage", "got": 1}
    assert serial.wheels == (0, 0)


BOOT_MAGIC = 0x59424254


def rtc(count, magic=BOOT_MAGIC, crc=None):
    """RTC 区三个字的十进制写法；CRC 缺省按标准 CRC-32 算，与固件同一算法。"""
    crc = zlib.crc32(struct.pack("<II", magic, count)) if crc is None else crc
    return "%d %d %d" % (magic, count, crc)


def boots(boot_host, lines):
    out = subprocess.run([str(boot_host)], input="\n".join(lines) + "\n", capture_output=True, text=True,
                         check=True).stdout
    return [tuple(map(int, row.split())) for row in out.splitlines()]


def test_boot_count_steps_by_one_along_a_watchdog_reset_chain(boot_host):
    """内部工单-2：RTC 区乱码（上电、首刷）时用种子起；此后 RTC 区保留的每次复位加一，种子不再用。"""
    rows = boots(boot_host, ["W 1000 305419896 7 7"] + ["K %d" % seed for seed in (1, 2, 3, 4)])
    assert rows == [(1000, 0), (1001, 1), (1002, 1), (1003, 1), (1004, 1)]


@pytest.mark.parametrize("wiped", ["0 0 0", "4294967295 4294967295 4294967295"])
def test_reset_key_reseeds_only_when_rtc_record_is_wiped(boot_host, wiped):
    """R3③ 两种分支：RESET 键不清 RTC 区则照常加一；清了（全 0 或全 1）则换新种子。
    本例只证两条分支各自的结果（种子是人为选的），**不证「永不撞号」**——换种子后与旧值相撞的概率约 2^-30
    （固件 README；X3 五轮报告指出原名「never repeats」言过其实，内部工单 F 如实改名）。"""
    assert boots(boot_host, ["W 500 " + wiped, "K 9", "K 77"]) == [(500, 0), (501, 1), (502, 1)]
    assert boots(boot_host, ["W 500 " + wiped, "K 9", "W 77 " + wiped]) == [(500, 0), (501, 1), (77, 0)]


def test_boot_record_is_checked_by_magic_and_crc(boot_host):
    """魔数、CRC、计数范围任一不对都当校验不过，重播种子；计数不为 0，只用低 30 位。"""
    rows = boots(boot_host, [
        "W 9 " + rtc(41),                                                       # 有效记录：加一
        "W 9 " + rtc(41, crc=zlib.crc32(struct.pack("<II", BOOT_MAGIC, 41)) ^ 1),   # CRC 错一位
        "W 9 " + rtc(41, magic=BOOT_MAGIC + 1),                                 # 魔数不对（CRC 按它自洽）
        "W 9 " + rtc(0),                                                        # 计数为 0
        "W 9 " + rtc(0x40000000),                                               # 计数超出 30 位
        "W 9 " + rtc(0x3FFFFFFF),                                               # 加一绕回 0，改记 1
        "W 0 0 0 0",                                                            # 种子为 0，改记 1
        "W %d 0 0 0" % (0xC0000005),                                            # 种子只取低 30 位
    ])
    assert rows == [(42, 1), (9, 0), (9, 0), (9, 0), (9, 0), (1, 1), (1, 0), (5, 0)]


def test_boot_does_not_look_at_the_reset_reason():
    """R0-2：重播种子只看 RTC 区校验，不看复位原因（原先上电原因一律重播）；种子在内部熵源开着时取，关熵源在开 ADC 之前。"""
    source = (FIRMWARE / "main" / "main.c").read_text(encoding="utf-8")
    code = "\n".join(line.split("//")[0] for line in source.splitlines())
    assert "ESP_RST_POWERON" not in code and "yb_boot_next(&boot_rtc, seed)" in code
    order = [code.index(mark) for mark in ("bootloader_random_enable();", "seed = esp_random();",
                                            "bootloader_random_disable();", "sensors_init()")]
    assert order == sorted(order) and code.count("esp_random()") == 1
    # 内部工单：开与关在 app_main 里成对、各一次，中间只有取种一句、没有早退；关熵源之前没有任何 ADC 读
    main = code[code.index("void app_main(void)"):]
    assert code.count("bootloader_random_enable()") == main.count("bootloader_random_enable()") == 1
    assert code.count("bootloader_random_disable()") == main.count("bootloader_random_disable()") == 1
    between = main[main.index("bootloader_random_enable();"):main.index("bootloader_random_disable();")]
    assert between.split() == ["bootloader_random_enable();", "seed", "=", "esp_random();"]
    head = main[:main.index("bootloader_random_disable();")]
    assert "return" not in head and not re.search(r"sensors_|adc_", head)
    drive = (FIRMWARE / "main" / "drive.c").read_text(encoding="utf-8")
    assert not re.search(r"adc|sensors_", drive, re.I)      # 取种之前只跑过 drive_init()


@pytest.mark.parametrize("base,bad,reason", [(dict(lock_faults=0), dict(lock_faults=1), "lock_fault"),
                                             ({}, dict(boot=8, reset_reason=6), "reset"),
                                             ({}, dict(boot=None), "reset")])
def test_no_motion_command_after_the_frame_that_shows_a_fault(base, bad, reason):
    """审查 X3-12：读到故障次数增长或 boot 计数变化（含回合中途 boot 缺了），同一拍发零速，此后非零指令数＝0，回合作废。"""
    clock = FakeClock()
    good = {"T": 1001, "L": 0, "R": 0, "v": 7.4, "boot": 7, "reset_reason": 1, **base}
    serial = MockSerial(clock, replay=[good] * 3 + [{**good, **bad}] * 100)
    robot = robot_on(serial, clock)
    robot.reset(1)                                        # 第一帧定基线
    begun = len(serial.commands)
    result = robot.act(Action.FORWARD)                    # 动作内前两帧正常，第三帧起带故障
    sent = [cmd for _, cmd in serial.commands[begun:]]
    shown = [i for i, cmd in enumerate(sent) if cmd == {"T": 130}][2]
    moving = [i for i, cmd in enumerate(sent) if cmd.get("T") == 1 and (cmd["L"] or cmd["R"])]
    assert len(moving) == 3 and max(moving) < shown
    assert sent[shown + 1] == {"T": 1, "L": 0.0, "R": 0.0}
    assert serial.commands[begun + shown][0] == serial.commands[begun + shown + 1][0]   # 同一拍
    assert result.extra["void"] and result.extra["void_reason"] == reason and result.extra["estopped"]
    assert result.extra["boot"] == {**good, **bad}["boot"] and robot.act(Action.FORWARD).extra["rejected"]
    robot.close()


def test_ugv02_frames_without_the_count_never_void():
    clock = FakeClock()
    robot = robot_on(MockSerial(clock), clock)
    robot.reset(5, "instruction")
    result = robot.act(Action.FORWARD)
    # 内部工单-1：缺字段记 NA（None），不记 0
    assert (robot.driver.lock_faults, robot.driver.boot, robot.driver.reset_reason) == (None, None, None)
    assert (result.extra["lock_faults"], result.extra["boot"], result.extra["reset_reason"]) == (None, None, None)
    assert not result.extra["void"]
    robot.close()


def test_low_voltage_flag_in_feedback_raises_even_without_motion(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    driver = UGV02(serial, clock=clock)
    serial.voltage(6.0)
    clock.sleep(2.0)
    serial.voltage(6.0)
    with pytest.raises(LowVoltageError):
        driver.feedback()


def test_low_voltage_voids_the_episode(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    robot = robot_on(serial, clock)
    robot.reset(5, "instruction")
    serial.voltage(6.0)
    clock.sleep(2.0)
    serial.voltage(6.0)
    result = robot.act(Action.FORWARD)
    assert result.extra["void"] and result.extra["void_reason"] == "low_voltage"
    assert result.extra["estopped"] and result.extra["odometry"]["distance_m"] == 0
    again = robot.act(Action.FORWARD)
    assert again.extra["rejected"] and again.extra["void"]
    robot.close()


def test_start_voltage_gate():
    for volts, opens in ((7.4, True), (6.9, False)):
        clock = FakeClock()
        serial = MockSerial(clock, replay=[{"T": 1001, "L": 0, "R": 0, "v": volts}] * 3)
        camera = Camera(CameraConfig(width=8, height=6), frame_source=lambda: np.zeros((6, 8, 3), dtype=np.uint8))
        robot = RealRobotUGV02(UGV02(serial, config=UGV02Config(**YB_EET01), clock=clock), camera)
        if opens:
            assert robot.reset(1).step == 0 and robot.start_voltage_v == volts and not robot.void_reason
        else:
            with pytest.raises(LowVoltageError):
                robot.reset(1)
            assert robot.void_reason == "low_voltage"
    # UGV02 缺省配置不设门槛，行为不变
    clock = FakeClock()
    robot = robot_on(MockSerial(clock, replay=[{"T": 1001, "L": 0, "R": 0}] * 2), clock)
    assert robot.reset(1).step == 0 and robot.start_voltage_v is None


@pytest.fixture
def smoke_root(tmp_path, monkeypatch):
    """把 smoke 与清单工具的仓根都指到临时目录，测试不往仓里写。"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    import manifest
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr(manifest, "ROOT", tmp_path)
    return tmp_path, manifest


def test_real_mode_pipeline_on_mock(smoke_root):
    tmp_path, manifest = smoke_root
    out = tmp_path / "smoke_runs" / "t"
    for episode in (1, 2, 3):
        code = smoke.main(["--port", "mock", "--out", str(out), "--episode", str(episode)])
        assert code == 0
    assert smoke.main(["--finalize", "--out", str(out), "--measured", "2=7.5"]) == 0
    rows = smoke.read_results(out)
    assert [row["arrived"] for row in rows] == ["1", "1", "1"] and rows[1]["measured_error_cm"] == "7.5"
    assert all(row["checkpoints_reached"] == "2" and row["void"] == "0" for row in rows)
    assert len(list((out / "frames" / "ep01").glob("*.png"))) == int(rows[0]["steps"])
    verdict = json.loads((out / "verdict.json").read_text())
    assert verdict["passed"] and verdict["arrived"] == 3 and verdict["required"] == 2
    assert manifest.verify(out / "SHA256SUMS") == 0
    with pytest.raises(SystemExit):
        smoke.main(["--port", "mock", "--out", str(tmp_path / "episodes" / "x")])
    meta = json.loads((out / "meta.json").read_text())
    assert meta["firmware_ver"] == "mock" and meta["lock_faults"] == {"1": None, "2": None, "3": None}
    assert meta["firmware_banner"] == {"1": None, "2": None, "3": None}


def test_real_mode_records_the_firmware_version_and_never_mixes_versions(smoke_root):
    """内部工单-1：真串口必填 --firmware-ver；同一输出目录里版本不同（或没记版本）就拒跑。"""
    tmp_path, _ = smoke_root
    out = tmp_path / "smoke_runs" / "f"
    with pytest.raises(SystemExit, match="--firmware-ver"):
        smoke.main(["--port", "/dev/null-chassis", "--camera", "0", "--out", str(out)])
    out.mkdir(parents=True)
    (out / "meta.json").write_text(json.dumps({"firmware_ver": "0.1.0"}))
    with pytest.raises(SystemExit, match="0.2.0 differs from 0.1.0"):
        smoke.main(["--port", "/dev/null-chassis", "--camera", "0", "--firmware-ver", "0.2.0", "--out", str(out)])
    (out / "meta.json").write_text(json.dumps({"kind": "real-smoke"}))
    with pytest.raises(SystemExit, match="has no firmware_ver"):   # X3-16：元数据缺版本不放行
        smoke.check_firmware(out, "0.2.0")
    smoke.check_firmware(tmp_path / "smoke_runs" / "empty", "0.2.0")


def test_driver_keeps_the_firmware_banner():
    clock = FakeClock()
    banner = {"fw": "yb-eet01-json", "ver": "0.2.0", "proto": "ugv02-subset-1", "board": "YB-EET01", "imu": 1}
    serial = MockSerial(clock, replay=[{"T": 1001, "L": 0, "R": 0, "v": 7.4, "boot": 7}] * 3)
    robot = robot_on(serial, clock)
    serial._replies.append((json.dumps(banner) + "\n").encode())   # 标识行不回应任何指令，开机时自己冒出来
    robot.reset(1)
    assert robot.driver.firmware == banner and robot.driver.boot == 7 and robot.driver.lock_faults is None
    robot.close()


def test_real_mode_records_aborted_episode(smoke_root):
    tmp_path, _ = smoke_root
    clock = FakeClock()
    serial = MockSerial(clock, track_width_m=0.261)
    driver = UGV02(serial, config=UGV02Config(**YB_EET01), clock=clock)
    serial.replay = deque(
        [{"T": 1001, "L": 0, "R": 0, "v": 7.4}] * 3 + [{"T": -1, "err": "low_voltage", "got": 1}])
    camera = Camera(CameraConfig(width=8, height=6), frame_source=lambda: np.zeros((6, 8, 3), dtype=np.uint8))
    row = smoke.run_real_episode(driver, camera, tmp_path / "smoke_runs" / "v", 1, checkpoints=[(0.8, 0.0)])
    assert row["aborted"] == 1 and row["void"] == 1 and row["void_reason"] == "low_voltage" and row["arrived"] == 0
    assert not smoke.finalize(tmp_path / "smoke_runs" / "v", planned=1)["passed"]


def test_driver_estop_latch_is_host_side(proto_host):
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    driver = UGV02(serial, clock=clock)
    driver.set_wheels(0.1, 0.1)
    driver.emergency_stop("test")
    assert serial.wheels == (0, 0)
    with pytest.raises(SafetyError):
        driver.set_wheels(0.1, 0.1)
    assert serial.wheels == (0, 0)
    driver.clear_estop()
    driver.set_wheels(0.1, 0.1)
    assert serial.wheels == pytest.approx((0.1, 0.1))
    assert math.isfinite(driver.odometry()["distance_m"])


# ── 内部工单：自检钩子（编译门控）与按复位类判 ──

HOOK_NAMES = ("yb_stall_block", "yb_stall_spin", "yb_stall_spin_noirq", "yb_stall_abort")
# 两份镜像所在的固件目录；缺省是本检出，审查用的 worktree 里没有镜像时用环境变量指到主检出
IMAGES = Path(os.environ.get("YB_FW_IMAGES", FIRMWARE))


def image_strings(path):
    """镜像里的可打印串：有 strings 就用它，另对原字节再搜一遍。"""
    data = path.read_bytes()
    tool = shutil.which("strings")
    text = subprocess.run([tool, "-a", str(path)], capture_output=True, check=True).stdout if tool else b""
    return [name for name in HOOK_NAMES + ("selftest",) if name.encode() in data or name.encode() in text]


def test_production_image_carries_no_hook_command_name():
    """R3①：生产构建的 .bin 不含钩子命令名；自检构建的 .bin 含全部四个（对照，证明这条查得出来）。"""
    production = IMAGES / "build" / "yb-eet01-json.bin"
    selftest = IMAGES / "build-selftest" / "yb-eet01-json.bin"
    if not production.exists():
        pytest.skip("没有生产镜像：先 idf.py build，或用 YB_FW_IMAGES 指到有镜像的固件目录")
    assert image_strings(production) == []
    if selftest.exists():
        assert image_strings(selftest) == list(HOOK_NAMES) + ["selftest"]


def test_hooks_are_compiled_only_under_the_build_switch():
    """R3①②：钩子只在 selftest.c 里，该文件只在构建开关打开时编进来；开关缺省关；钩子只有四条、只做停摆。"""
    sources = [path for folder in ("main", "components") for path in (FIRMWARE / folder).rglob("*")
               if path.suffix in (".c", ".h", ".txt", ".yml")]
    named = sorted(path.name for path in sources
                   if any(name in path.read_text(encoding="utf-8") for name in HOOK_NAMES))
    assert named == ["selftest.c"]
    cmake = (FIRMWARE / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert re.search(r'set\(srcs "main.c" "drive.c" "sensors.c"\)', cmake)
    gated = cmake[cmake.index("if(YB_SELFTEST)"):cmake.index("endif()", cmake.index('"selftest.c"'))]
    assert '"selftest.c"' in gated and cmake.count("selftest.c") == 1 and "build-selftest$" in gated
    config = (FIRMWARE / "main" / "yb_config.h").read_text(encoding="utf-8")
    assert "#ifndef YB_SELFTEST\n#define YB_SELFTEST     0\n#endif" in config
    assert re.search(r'#if YB_SELFTEST\n#define YB_FW_VERSION   "0\.2\.0-selftest"\n#else\n'
                     r'#define YB_FW_VERSION   "0\.2\.0"\n#endif', config)
    header = (FIRMWARE / "main" / "selftest.h").read_text(encoding="utf-8")
    off = header[header.index("#else"):]
    assert "return false;" in off and off.count("{") == 2       # 开关关着时两个入口都是空函数
    hook = (FIRMWARE / "main" / "selftest.c").read_text(encoding="utf-8")
    code = "\n".join(line.split("//")[0] for line in hook.splitlines())
    assert re.findall(r'\{\\"T\\":(\d+),\\"hook\\":\\"(\w+)\\"\}', code) == [
        (str(9101 + i), name) for i, name in enumerate(HOOK_NAMES)]
    for banned in ("uart_", "gpio_", "drive_", "printf", "esp_restart", "nvs_", "yb_ctrl", "yb_link"):
        assert banned not in code
    assert [stallcheck.HOOKS[kind] for kind in ("block", "spin", "spin_noirq", "abort")] == [
        ('{"T":%d,"hook":"%s"}\n' % (9101 + i, name)).encode() for i, name in enumerate(HOOK_NAMES)]


def test_production_protocol_core_does_not_know_the_hook_commands(proto_host):
    """R3②：钩子的号在 UGV02 指令子集之外；生产固件的协议核心收到只回 unknown_cmd，轮子照转。"""
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    send(serial, {"T": 1, "L": 0.1, "R": 0.1})
    for number, hook in enumerate(stallcheck.HOOKS.values(), 9101):
        serial.write(hook)
        assert json.loads(serial.readline()) == {"T": -1, "err": "unknown_cmd", "got": number}
        assert serial.wheels == pytest.approx((0.1, 0.1)) and serial.stop == 0
    assert not set(range(9101, 9105)) & {1, 11, 13, 130, 131, 136, 142, 143, 900}


def test_reset_causes_are_judged_by_class():
    """R3④：上位机按复位类判，不按单值；固件不按复位原因分支，boot 计数走 RTC 校验腿。"""
    assert [reset_class(value) for value in (1, 2)] == ["power_or_external"] * 2
    assert reset_class(3) == "software" and reset_class(9) == "brownout"
    assert [reset_class(value) for value in (4, 5, 6, 7)] == ["fault"] * 4
    assert [reset_class(value) for value in (0, 8, 10, 99)] == ["unknown"] * 4 and reset_class(None) is None
    for name in ("main.c", "selftest.c", "drive.c", "sensors.c"):
        assert "ESP_RST_" not in (FIRMWARE / "main" / name).read_text(encoding="utf-8")
    clock = FakeClock()
    serial = MockSerial(clock, replay=[{"T": 1001, "L": 0, "R": 0, "v": 7.4, "boot": 7, "reset_reason": 6}] * 8)
    robot = robot_on(serial, clock)
    robot.reset(1)
    result = robot.act(Action.STOP)
    assert (result.extra["reset_reason"], result.extra["reset_class"]) == (6, "fault")
    robot.close()


class StallSerial:
    """自检固件的串口桩：认钩子命令，停摆 0.3 秒后复位，再过 0.4 秒打印标识行；时间取注入的时钟。"""

    def __init__(self, clock, *, production=False, resets=True, reason=6, keep_rtc=True, coast_s=0.0,
                 ver="0.2.0-selftest"):
        self.clock, self.timeout, self.is_open = clock, 0.2, True
        self.production, self.resets, self.reason_next = production, resets, reason
        self.keep_rtc, self.coast_s, self.ver = keep_rtc, coast_s, ver
        self.boot, self.reason, self.wheels = 41, 1, (0.0, 0.0)
        self.deaf_until = self.coast_until = 0.0
        self.due, self.written = [], []

    def write(self, data):
        now = self.clock.monotonic()
        self.written.append((now, data))
        if now < self.deaf_until:
            return len(data)                            # 复位当中，收不到
        cmd = json.loads(data)
        if cmd["T"] == 1:
            self.wheels = (cmd["L"], cmd["R"])
        elif cmd["T"] == 130:
            wheels = (0.05, 0.05) if now < self.coast_until else self.wheels
            self.due.append((now, {"T": 1001, "L": wheels[0], "R": wheels[1], "v": 7.4, "low_voltage": 0,
                                   "reset_reason": self.reason, "boot": self.boot}))
        elif data in stallcheck.HOOKS.values():
            if self.production:
                self.due.append((now, {"T": -1, "err": "unknown_cmd", "got": cmd["T"]}))
            elif self.resets:
                self.deaf_until, self.coast_until = now + 0.7, now + self.coast_s
                self.boot, self.reason = (self.boot + 1 if self.keep_rtc else 900), self.reason_next
                self.wheels = (0.0, 0.0)
                self.due.append((now + 0.7, {"fw": "yb-eet01-json", "ver": self.ver, "imu": 1}))
        return len(data)

    def readline(self):
        now = self.clock.monotonic()
        if self.due and self.due[0][0] <= now + self.timeout:
            ready, reply = self.due.pop(0)
            self.clock.sleep(max(0.0, ready - now))
            return (json.dumps(reply) + "\n").encode()
        self.clock.sleep(self.timeout)
        return b""

    def close(self):
        self.is_open = False


def stall(kind="block", **kwargs):
    clock = FakeClock()
    serial = StallSerial(clock, **kwargs)
    return serial, stallcheck.run_stall(serial, kind, clock=clock)


@pytest.mark.parametrize("kind,reason", [("block", 6), ("spin", 6), ("spin_noirq", 5), ("spin_noirq", 6), ("abort", 4)])
def test_stall_check_times_the_reset_and_judges_by_class(kind, reason):
    """R3③④：时长从钩子命令发出算到标识行到达；判据看复位类，单值只记录；RTC 保留与否照 boot 是否加一记。"""
    serial, row = stall(kind, reason=reason)
    assert row["verdict"] == "pass" and (row["reset_reason"], row["reset_class"]) == (reason, "fault")
    assert row["hook_to_banner_s"] == pytest.approx(0.7) and row["hook_to_stopped_frame_s"] < 2.0
    assert (row["boot_before"], row["boot_after"], row["rtc_kept"], row["turning_at_limit"]) == (41, 42, 1, 0)
    assert row["speed_before_mps"] == 0.05 and row["banner_ver"] == "0.2.0-selftest"
    sent = [data for _, data in serial.written]
    hook = sent.index(stallcheck.HOOKS[kind])
    assert all(data in (stallcheck.ZERO, stallcheck.QUERY) for data in sent[hook + 1:])    # 钩子之后不再发非零
    _, row = stall(kind, reason=reason, keep_rtc=False)
    assert row["verdict"] == "pass" and (row["boot_after"], row["rtc_kept"]) == (900, 0)


@pytest.mark.parametrize("kwargs,verdict", [(dict(resets=False), "red_card"), (dict(coast_s=3.0), "red_card"),
                                            (dict(production=True), "not_selftest"),
                                            (dict(ver="0.2.0"), "not_selftest"), (dict(reason=1), "unexpected_class")])
def test_stall_check_verdicts_other_than_pass(kwargs, verdict):
    """R3③：触发后 2 秒仍在转或不见复位＝台架红牌；板上不是自检固件、复位类不是异常，都不算过。末条一律零速。"""
    serial, row = stall(**kwargs)
    assert row["verdict"] == verdict and serial.written[-1][1] == stallcheck.ZERO


def test_selftest_build_never_mixes_with_production_data(smoke_root):
    """R3①：selftest 构建的版本带后缀，runs 目录不与生产版混；它进不了 real.smoke 的回合数据。"""
    tmp_path, _ = smoke_root
    runs = tmp_path / "smoke_runs"
    with pytest.raises(SystemExit, match="self-test build"):
        stallcheck.main(["--port", "x", "--firmware-ver", "0.2.0", "--kind", "block", "--out", str(runs / "s")])
    with pytest.raises(SystemExit, match="outside episodes"):
        stallcheck.main(["--port", "x", "--firmware-ver", "0.2.0-selftest", "--kind", "block",
                         "--out", str(tmp_path / "episodes" / "s")])
    (runs / "gate").mkdir(parents=True)
    (runs / "gate" / "meta.json").write_text(json.dumps({"kind": "real-smoke", "firmware_ver": "0.2.0"}))
    with pytest.raises(SystemExit, match="0.2.0-selftest differs from 0.2.0"):
        stallcheck.main(["--port", "x", "--firmware-ver", "0.2.0-selftest", "--kind", "block",
                         "--out", str(runs / "gate")])
    for kind in ("block", "abort"):
        clock = FakeClock()
        assert stallcheck.main(["--port", "x", "--firmware-ver", "0.2.0-selftest", "--kind", kind,
                                "--out", str(runs / "s")], link=StallSerial(clock, reason=4), clock=clock) == 0
    rows = list(csv.DictReader(open(runs / "s" / "stall.csv", encoding="utf-8")))
    assert [(row["run"], row["kind"], row["verdict"], row["reset_class"]) for row in rows] == [
        ("1", "block", "pass", "fault"), ("2", "abort", "pass", "fault")]
    assert json.loads((runs / "s" / "meta.json").read_text())["firmware_ver"] == "0.2.0-selftest"
    with pytest.raises(SystemExit, match="0.2.0 differs from 0.2.0-selftest"):
        smoke.main(["--port", "/dev/null-chassis", "--camera", "0", "--firmware-ver", "0.2.0", "--out", str(runs / "s")])
    with pytest.raises(SystemExit, match="never produces episode data"):
        smoke.main(["--port", "/dev/null-chassis", "--camera", "0", "--firmware-ver", "0.2.0-selftest",
                    "--out", str(runs / "new")])


def test_episode_on_a_selftest_banner_is_void(smoke_root):
    """R3①：--firmware-ver 填的是生产版、板上却是自检固件（驱动层读到了它的标识行），该回合作废。"""
    tmp_path, _ = smoke_root
    clock = FakeClock()
    serial = MockSerial(clock, track_width_m=0.261)
    driver = UGV02(serial, config=UGV02Config(**YB_EET01), clock=clock)
    driver.firmware = {"fw": "yb-eet01-json", "ver": "0.2.0-selftest"}
    camera = Camera(CameraConfig(width=8, height=6), frame_source=lambda: np.zeros((6, 8, 3), dtype=np.uint8))
    row = smoke.run_real_episode(driver, camera, tmp_path / "smoke_runs" / "b", 1, checkpoints=[(0.2, 0.0)])
    assert (row["void"], row["void_reason"], row["arrived"]) == (1, "selftest_firmware", 0)


# ── X3-15 板上冒烟脚本（real.stopsmoke；冒烟，非证明）──

def test_stopsmoke_passes_when_wheels_stay_stopped(tmp_path):
    from real import stopsmoke
    clock = FakeClock()
    serial = MockSerial(clock)
    rc = stopsmoke.main(["--cycles", "3", "--out", str(tmp_path)], link=serial, clock=clock)
    rows = list(csv.DictReader(open(tmp_path / "stop.csv", encoding="utf-8")))
    assert rc == 0 and {row["verdict"] for row in rows} == {"pass"} and {row["cycle"] for row in rows} == {"1", "2", "3"}
    kinds = [command["T"] for _, command in serial.commands]
    assert 1 in kinds and 130 in kinds and not any(command.get("T") == 1 and (command["L"] or command["R"])
                                                   for _, command in serial.commands[-3:])


def test_stopsmoke_fails_on_rewinding_wheels(tmp_path):
    """停稳过的帧之后又出现轮速非零＝复转，判门一失守，rc 1。"""
    from real import stopsmoke
    clock = FakeClock()
    # 转 0.5 s 期间问 5 帧、到时限零速后问 1 帧，都停稳；看的第 1 帧停稳、第 2 帧又动了
    serial = MockSerial(clock, replay=deque([frame(0, 0, tl=0, tr=0)] * 7 + [frame(0.1, 0.1, tl=0.1, tr=0.1)] + [frame(0, 0, tl=0, tr=0)] * 50))
    rc = stopsmoke.main(["--cycles", "2", "--out", str(tmp_path)], link=serial, clock=clock)
    rows = list(csv.DictReader(open(tmp_path / "stop.csv", encoding="utf-8")))
    assert rc == 1 and rows[-1]["verdict"] == "复转" and rows[-1]["cycle"] == "1"


# ── X3-16／X3-17 与低压分类（内部工单 F，裁定 2026-10-02-06／-19）──

def test_selftest_banner_latches_the_stop_at_once_and_cannot_be_cleared():
    """X3-16：驱动层读到带 -selftest 后缀的标识行，当拍锁存、此后非零指令数＝0，clear_estop 清不掉，reset 不开回合。"""
    clock = FakeClock()
    good = {"T": 1001, "L": 0, "R": 0, "v": 7.4, "boot": 3}
    serial = MockSerial(clock, replay=[good] * 40)
    robot = robot_on(serial, clock)
    robot.reset(1)
    serial._replies.appendleft((json.dumps({"fw": "yb-eet01-json", "ver": "0.2.0-selftest"}) + "\n").encode())
    begun = len(serial.commands)
    result = robot.act(Action.FORWARD)
    assert robot.driver.firmware_rejected and robot.driver.estopped and "self-test" in robot.driver.reason
    sent = [cmd for _, cmd in serial.commands[begun:]]
    shown = next(i for i, cmd in enumerate(sent) if cmd == {"T": 130})   # 标识行随第一次反馈读到
    assert not any(cmd.get("T") == 1 and (cmd["L"] or cmd["R"]) for cmd in sent[shown:])
    assert result.extra["estopped"] and result.extra["firmware_ver"] == "0.2.0-selftest"
    with pytest.raises(SafetyError, match="cannot be cleared"):
        robot.clear_estop()
    with pytest.raises(SafetyError, match="self-test firmware"):
        robot.reset(2)
    assert robot.act(Action.FORWARD).extra["rejected"]
    robot.close()


def test_production_banner_does_not_latch():
    clock = FakeClock()
    serial = MockSerial(clock, replay=[{"T": 1001, "L": 0, "R": 0, "v": 7.4, "boot": 3}] * 20)
    robot = robot_on(serial, clock)
    serial._replies.append((json.dumps({"fw": "yb-eet01-json", "ver": "0.2.0"}) + "\n").encode())
    robot.reset(1)
    result = robot.act(Action.FORWARD)
    assert not robot.driver.firmware_rejected and not result.extra["estopped"] and result.extra["firmware_ver"] == "0.2.0"
    robot.close()


def test_check_firmware_refuses_unreadable_metadata(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "meta.json").write_text("{not json")
    with pytest.raises(SystemExit, match="unreadable or has no firmware_ver"):
        smoke.check_firmware(out, "0.2.0")
    (out / "meta.json").write_text(json.dumps({"firmware_ver": "0.2.0"}))
    smoke.check_firmware(out, "0.2.0")


def _voided_robot(clock, boot_after=8):
    """A robot whose first act() sees the boot counter move 7 → boot_after (void_reason reset), then frames stay at boot_after."""
    good = {"T": 1001, "L": 0, "R": 0, "v": 7.4, "boot": 7}
    serial = MockSerial(clock, replay=[good] * 3 + [{**good, "boot": boot_after}] * 200)
    robot = robot_on(serial, clock)
    robot.reset(1)
    result = robot.act(Action.FORWARD)
    assert result.extra["void"] and result.extra["void_reason"] == "reset" and result.extra["estopped"]
    return robot, serial


def test_clear_estop_on_a_voided_episode_only_ends_it():
    """X3-17（裁定 2026-10-02-06）：故障回合 clear_estop 后不再发非零；续动须 reset 新回合。"""
    clock = FakeClock()
    robot, serial = _voided_robot(clock)
    robot.clear_estop()
    assert not robot.driver.estopped
    begun = len(serial.commands)
    again = robot.act(Action.FORWARD)
    assert again.extra["rejected"] and again.extra["episode_ended"] and again.extra["void"]
    assert not any(cmd.get("T") == 1 and (cmd["L"] or cmd["R"]) for _, cmd in serial.commands[begun:])
    robot.close()


def test_reset_after_a_void_needs_clear_estop_first_and_a_new_reset_key():
    clock = FakeClock()
    robot, serial = _voided_robot(clock)
    with pytest.raises(SafetyError, match="not ended"):
        robot.reset(2)
    robot.clear_estop()
    # 新回合：首帧 boot 8 ≠ 作废回合基线 7 → 新 reset key 成立，回合打开、可动
    robot.reset(2)
    result = robot.act(Action.FORWARD)
    assert not result.extra["void"] and not result.extra["rejected"] and not result.extra["episode_ended"]
    assert result.extra["boot"] == 8 and result.extra["void_detail"] == {}
    robot.close()


def test_reset_after_a_lock_fault_void_refuses_a_stale_reset_key():
    """lock_fault 作废时板子没重启：boot 未变就不开新回合，直到 RESET／断电换了 key。"""
    clock = FakeClock()
    base = {"T": 1001, "L": 0, "R": 0, "v": 7.4, "boot": 7, "lock_faults": 0}
    serial = MockSerial(clock, replay=[base] * 3 + [{**base, "lock_faults": 1}] * 40 + [{**base, "lock_faults": 1, "boot": 8}] * 40)
    robot = robot_on(serial, clock)
    robot.reset(1)
    result = robot.act(Action.FORWARD)
    assert result.extra["void_reason"] == "lock_fault" and result.extra["void_detail"]["source"] == "feedback_frame"
    robot.clear_estop()
    with pytest.raises(SafetyError, match="fresh reset key"):
        robot.reset(2)
    assert robot.driver.estopped and robot.act(Action.FORWARD).extra["rejected"]
    serial.replay = deque([{**base, "lock_faults": 1, "boot": 8}] * 40)
    robot.clear_estop()
    robot.reset(3)
    assert not robot.act(Action.FORWARD).extra["rejected"]
    robot.close()


def test_low_voltage_is_classified_by_phase_and_source(proto_host):
    """裁定 2026-10-02-19：低压作废带相位（start_gate／reset／observe／act）与来源（feedback_flag／motion_refused）。"""
    # act 中、非零指令被固件错帧拒绝
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    robot = robot_on(serial, clock)
    robot.reset(5, "i")
    serial.voltage(6.0); clock.sleep(2.0); serial.voltage(6.0)
    result = robot.act(Action.FORWARD)
    assert result.extra["void_reason"] == "low_voltage"
    assert result.extra["void_detail"]["phase"] == "act" and result.extra["void_detail"]["source"] in ("motion_refused", "feedback_flag")
    robot.close()
    # observe 中读到锁存帧：同样作废（X3-06 ①），相位 observe
    clock = FakeClock()
    serial = FirmwareSerial(proto_host, clock)
    robot = robot_on(serial, clock)
    robot.reset(5, "i")
    serial.voltage(6.0); clock.sleep(2.0); serial.voltage(6.0)
    with pytest.raises(LowVoltageError):
        robot.observe()
    assert robot.void_reason == "low_voltage" and robot.void_detail == {"phase": "observe", "source": "feedback_flag"}
    robot.close()
    # 开回合门槛：电压低于 7.0 V，回合未打开，相位 start_gate
    clock = FakeClock()
    serial = MockSerial(clock, replay=[{"T": 1001, "L": 0, "R": 0, "v": 6.9}] * 5)
    camera = Camera(CameraConfig(width=8, height=6), frame_source=lambda: np.zeros((6, 8, 3), dtype=np.uint8))
    robot = RealRobotUGV02(UGV02(serial, config=UGV02Config(**YB_EET01), clock=clock), camera)
    with pytest.raises(LowVoltageError):
        robot.reset(1)
    assert robot.void_detail == {"phase": "start_gate", "source": "start_gate"} and robot.start_voltage_v == 6.9
    robot.close()


def test_smoke_rows_carry_the_void_classification(smoke_root):
    tmp_path, _ = smoke_root
    clock = FakeClock()
    serial = MockSerial(clock, track_width_m=0.261)
    driver = UGV02(serial, config=UGV02Config(**YB_EET01), clock=clock)
    serial.replay = deque([{"T": 1001, "L": 0, "R": 0, "v": 7.4}] * 3 + [{"T": -1, "err": "low_voltage", "got": 1}])
    camera = Camera(CameraConfig(width=8, height=6), frame_source=lambda: np.zeros((6, 8, 3), dtype=np.uint8))
    row = smoke.run_real_episode(driver, camera, tmp_path / "smoke_runs" / "c", 1, checkpoints=[(0.8, 0.0)])
    assert (row["void"], row["void_reason"], row["void_phase"], row["void_source"]) == (1, "low_voltage", "act", "motion_refused")
