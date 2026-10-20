from collections import deque

import numpy as np
import pytest

from harness.interface import Action, MotionSpec
from real.camera import Camera, CameraConfig
from real.mock_serial import FakeClock, MockSerial
from real.real_env import RealRobotUGV02
from real.ugv02 import UGV02, UGV02Config


def make_robot(latency_s, *, duration_s=1.0, config=None):
    clock = FakeClock()
    serial = MockSerial(clock, latency_s=latency_s)
    driver = UGV02(serial, clock=clock, config=config or UGV02Config(),
                   motion=MotionSpec(forward_m=duration_s * .2))
    camera = Camera(CameraConfig(width=2, height=2),
                    frame_source=lambda: np.zeros((2, 2, 3), dtype=np.uint8))
    serial.commands.clear()
    serial._replies.clear()
    return RealRobotUGV02(driver, camera), serial, clock


def motion_commands(serial):
    return [(stamp, command) for stamp, command in serial.commands if command["T"] == 1]


@pytest.mark.parametrize("latency_s", [0, .02, .05])
def test_heartbeat_latency_regression(latency_s):
    robot, serial, _ = make_robot(latency_s)
    robot.act(Action.FORWARD)
    moving = [stamp for stamp, command in motion_commands(serial) if command["L"]]
    assert max(later - earlier for earlier, later in zip(moving, moving[1:])) <= .140001


@pytest.mark.parametrize("latency_s", [0, .02, .05])
def test_deadline_stop_latency_regression(latency_s):
    robot, serial, _ = make_robot(latency_s, duration_s=.12)
    robot.act(Action.FORWARD)
    commands = motion_commands(serial)
    stopped = next(stamp for stamp, command in commands if command["L"] == command["R"] == 0)
    assert stopped - commands[0][0] <= .160001


@pytest.mark.parametrize("latency_s", [0, .02, .05])
def test_precise_heartbeat_and_stop_order(latency_s):
    robot, serial, _ = make_robot(latency_s)
    result = robot.act(Action.FORWARD)
    moving = [stamp for stamp, command in motion_commands(serial) if command["L"]]
    assert [later - earlier for earlier, later in zip(moving, moving[1:])] == pytest.approx(
        [robot.driver.config.heartbeat_period_s] * (len(moving) - 1))
    stop_index = next(index for index, (_, command) in enumerate(serial.commands)
                      if command["T"] == 1 and command["L"] == command["R"] == 0)
    assert serial.commands[stop_index][0] == pytest.approx(moving[0] + 1)
    assert serial.commands[stop_index + 1][1]["T"] == 130
    assert not result.extra["estopped"]


@pytest.mark.parametrize("latency_s", [0, .02, .05])
@pytest.mark.parametrize("duration_s", [.83, 1.0, 1.17])
def test_duration_overrun_latches_with_write_pause(latency_s, duration_s):
    robot, serial, _ = make_robot(latency_s, duration_s=duration_s)
    serial.pause_at_s = duration_s - .15
    serial.pause_duration_s = .3
    result = robot.act(Action.FORWARD)
    commands = motion_commands(serial)
    stopped = next(stamp for stamp, cmd in commands if cmd["L"] == cmd["R"] == 0)
    elapsed = stopped - commands[0][0]
    assert result.extra["motion_duration_s"] == pytest.approx(elapsed)
    assert elapsed > duration_s + robot.driver.config.duration_tolerance_s
    assert result.extra["duration_exceeded"] and result.extra["estopped"]
    assert commands[-1][1] == {"T": 1, "L": 0, "R": 0}
    assert serial.wheels == (0, 0)
    assert robot.act(Action.LEFT).extra["rejected"]
    robot.clear_estop()
    assert not robot.driver.estopped
    assert not robot.act(Action.STOP).extra["rejected"]


def test_constant_150ms_latency_is_self_consistent():
    robot, serial, _ = make_robot(.15)
    result = robot.act(Action.FORWARD)
    assert motion_commands(serial)[-1][1] == {"T": 1, "L": 0, "R": 0}
    assert result.extra["duration_exceeded"] is result.extra["estopped"]
    assert serial.wheels == (0, 0)


@pytest.mark.parametrize("latency_s", [0, .02, .05])
def test_negative_remaining_is_normal(latency_s):
    robot, serial, clock = make_robot(latency_s, duration_s=.02)
    original_feedback = robot.driver.feedback

    def late_feedback():
        reply = original_feedback()
        clock.now += .03
        return reply

    robot.driver.feedback = late_feedback
    result = robot.act(Action.FORWARD)
    assert not result.extra["estopped"]
    assert serial.wheels == (0, 0)


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("stage", ["feedback", "settle", "verify", "serial_read", "serial_write"])
def test_unexpected_exception_stops_before_reraise(stage, error_type):
    robot, serial, clock = make_robot(.05)
    original = error_type("injected fault")

    def fail(*args):
        raise original

    if stage == "feedback":
        robot.driver.feedback = fail
    elif stage == "serial_read":
        serial.readline = fail
    elif stage == "serial_write":
        original_write = serial.write

        def write(data):
            serial.write = original_write
            fail()

        serial.write = write
    elif stage == "settle":
        original_sleep = clock.sleep

        def sleep(seconds):
            if seconds == robot.motion.settle_s:
                fail()
            original_sleep(seconds)

        clock.sleep = sleep
    else:
        robot._verify_stopped = fail
    with pytest.raises(error_type) as caught:
        robot.act(Action.FORWARD)
    assert caught.value is original
    assert motion_commands(serial)[-1][1] == {"T": 1, "L": 0, "R": 0}
    assert serial.wheels == (0, 0)
    assert robot.driver.estopped
    assert robot.act(Action.LEFT).extra["rejected"]


@pytest.mark.parametrize("speed,threshold,stopped", [(.009, .01, True), (-.01, .01, True),
                                                   (.011, .01, False), (.015, .02, True)])
def test_stopped_threshold(speed, threshold, stopped):
    robot, serial, _ = make_robot(0, config=UGV02Config(stopped_speed_threshold_mps=threshold))
    serial.replay = deque([{"T": 1001, "L": speed, "R": -speed}] * 2)
    result = robot.act(Action.STOP)
    assert result.extra["estopped"] is not stopped


@pytest.mark.parametrize("command", [(("T", 1), ("L", .1), ("R", 0)),
                                     (("T", 11),), (("T", 13),), (), (("T", "1"),),
                                     (("T", 999), ("value", float("nan"))), (1,)])
def test_invalid_emergency_command_rejected_at_construction(command):
    with pytest.raises(ValueError, match="emergency command"):
        UGV02Config(emergency_command=command)


@pytest.mark.parametrize("field", ["stopped_speed_threshold_mps", "duration_tolerance_s"])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_safety_thresholds(field, value):
    with pytest.raises(ValueError):
        UGV02Config(**{field: value})


def test_additional_emergency_command_follows_zero_speed():
    robot, serial, _ = make_robot(0, config=UGV02Config(emergency_command=(("T", 999),)))
    robot.emergency_stop()
    # 零速、附加急停命令，然后是停车确认的查询（审查 X3-08）；mock 一帧即确认
    assert [command for _, command in serial.commands] == [
        {"T": 1, "L": 0, "R": 0}, {"T": 999}, {"T": 130}]
    assert robot.driver.stop_confirmed is True and robot.driver.stop_confirm_reads == 1
