import json
import math
import threading

import numpy as np
import pytest

from harness.interface import Action, MotionSpec, Robot
from real.camera import Camera, CameraConfig
from real.mock_serial import FakeClock, MockSerial
from real.real_env import RealRobotUGV02
from real.ugv02 import SafetyError, UGV02, UGV02Config


def setup_robot(clock=None):
    clock = clock or FakeClock()
    serial = MockSerial(clock)
    driver = UGV02(serial, clock=clock)
    camera = Camera(CameraConfig(width=8, height=6), frame_source=lambda: np.zeros((6, 8, 3), dtype=np.uint8))
    return RealRobotUGV02(driver, camera), serial, clock


def send(serial, cmd):
    serial.write((json.dumps(cmd) + "\n").encode())


@pytest.mark.parametrize("action,seconds,distance,yaw", [
    (Action.FORWARD, 1.3, .2, 0), (Action.LEFT, .8, 0, math.pi / 6),
    (Action.RIGHT, .8, 0, -math.pi / 6), (Action.STOP, .3, 0, 0)])
def test_robot_contract(action, seconds, distance, yaw):
    robot, serial, clock = setup_robot()
    assert isinstance(robot, Robot)
    first = robot.reset(5, "instruction")
    assert first.step == 0 and first.instruction == "instruction"
    result = robot.act(action)
    assert result.duration_s == pytest.approx(seconds)
    assert result.extra["odometry"]["distance_m"] == pytest.approx(distance)
    assert result.extra["odometry"]["yaw_rad"] == pytest.approx(yaw)
    assert result.pose is result.collided is None
    assert serial.wheels == (0, 0)
    obs = robot.observe()
    assert obs.step == 1 and obs.extra == obs.for_model().extra == {}
    assert obs.image.shape == (6, 8, 3) and obs.image.dtype == np.uint8
    assert robot.pose() is None
    with pytest.raises(RuntimeError, match="calibration"):
        robot.course()
    robot.close()
    assert not serial.is_open


def test_mock_line_protocol_echo_limits_and_watchdog():
    clock = FakeClock()
    serial = MockSerial(clock)
    serial.write(b'bad json\n{"T":1,"L":0.2,')
    assert serial.wheels == (0, 0)
    serial.write(b'"R":0.2}\n')
    assert json.loads(serial.readline())["T"] == 1
    assert serial.wheels == (.2, .2)
    send(serial, {"T": 1, "L": 3, "R": 0})
    assert serial.wheels == (.2, .2)
    send(serial, {"T": 143, "cmd": 0})
    while serial.readline():
        pass
    send(serial, {"T": 13, "X": .1, "Z": 1})
    assert serial.wheels == pytest.approx((.014, .186))
    clock.sleep(2.9)
    send(serial, {"T": 130})
    assert json.loads(serial.readline())["L"] == pytest.approx(.014)
    clock.sleep(.2)
    assert serial.wheels == (0, 0)  # Queries do not refresh heartbeat.


def test_heartbeat_renewal_and_loss():
    clock = FakeClock()
    serial = MockSerial(clock)
    driver = UGV02(serial, clock=clock, config=UGV02Config(heartbeat_timeout_s=.5))
    driver.move_for(.2, .2, 1.2)
    moving = [t for t, cmd in serial.commands if cmd.get("L") == .2]
    assert len(moving) >= 10
    assert max(b - a for a, b in zip(moving, moving[1:])) <= .100001
    driver.set_wheels(.2, .2)
    clock.sleep(.51)  # Host stopped servicing the driver.
    assert serial.wheels == (0, 0)


@pytest.mark.parametrize("failure", ["fail_write", "fail_read", "drop_feedback", "disconnect"])
def test_faults_latch_and_reject(failure):
    robot, serial, clock = setup_robot()
    if failure == "disconnect":
        serial.close()
    else:
        setattr(serial, failure, True)
    result = robot.act(Action.FORWARD)
    assert result.extra["estopped"]
    mark = len(serial.commands)
    assert robot.act(Action.LEFT).extra["rejected"]
    assert len(serial.commands) == mark
    clock.sleep(3.1)
    assert serial.wheels == (0, 0)


@pytest.mark.parametrize("speeds", [(float("nan"), 0), (.21, .21), (-.2, .2), (3, 3)])
def test_limits_rejected_without_clipping(speeds):
    robot, serial, _ = setup_robot()
    mark = len(serial.commands)
    with pytest.raises(SafetyError):
        robot.driver.set_wheels(*speeds)
    assert robot.driver.estopped
    assert all(cmd.get("L", 0) == cmd.get("R", 0) == 0 for _, cmd in serial.commands[mark:])


def test_estop_interrupts_action_and_requires_explicit_clear():
    robot, serial, clock = setup_robot()
    original_sleep = clock.sleep
    def stop_during_sleep(seconds):
        original_sleep(seconds)
        robot.emergency_stop()
    clock.sleep = stop_during_sleep
    result = robot.act(Action.FORWARD)
    assert result.extra["estopped"] and serial.wheels == (0, 0)
    mark = len(serial.commands)
    robot.reset(1)
    assert robot.act(Action.RIGHT).extra["rejected"]
    assert all(cmd.get("L", 0) == cmd.get("R", 0) == 0 for _, cmd in serial.commands[mark:])
    clock.sleep = original_sleep
    robot.clear_estop()
    assert not robot.act(Action.FORWARD).extra["estopped"]


def test_queued_action_cannot_bypass_estop():
    robot, serial, _ = setup_robot()
    ready = threading.Event()
    results = []
    def queued():
        ready.set()
        results.append(robot.act(Action.FORWARD))
    with robot._operations:
        thread = threading.Thread(target=queued)
        thread.start()
        ready.wait()
        robot.emergency_stop()
    thread.join()
    assert results[0].extra["rejected"]
    assert all(cmd.get("L", 0) == cmd.get("R", 0) == 0 for _, cmd in serial.commands)


def test_feedback_replay_and_echo_skip():
    clock = FakeClock()
    serial = MockSerial(clock, replay=[{"T": 1001, "L": .1, "R": .2},
                                       {"T": 1001, "L": 0, "R": 0}])
    driver = UGV02(serial, clock=clock)
    driver.feedback()  # Skips initial echo.
    clock.sleep(.5)
    driver.feedback()
    assert driver.left_m == pytest.approx(.05)
    assert driver.right_m == pytest.approx(.1)
    with pytest.raises(SafetyError, match="timeout"):
        driver.feedback()
    assert driver.estopped


def test_short_write_and_bad_feedback():
    robot, serial, _ = setup_robot()
    serial.write = lambda data: len(data) - 1
    with pytest.raises(SafetyError, match="short"):
        robot.driver.set_wheels(.1, .1)
    assert robot.driver.estopped
    clock = FakeClock()
    driver = UGV02(MockSerial(clock, replay=[{"T": 1001, "L": "NaN", "R": 0}]), clock=clock)
    with pytest.raises(SafetyError, match="invalid"):
        driver.feedback()


def test_fake_camera_validation_and_course_copy():
    camera = Camera(CameraConfig(width=2, height=2), frame_source=lambda: np.zeros((2, 2), dtype=np.uint8))
    with pytest.raises(ValueError, match="RGB"):
        camera.read()
    robot, _, _ = setup_robot()
    robot._course = {"checkpoints": [(1, 2)], "start": (0, 0), "reach_radius_m": .2}
    robot.course()["checkpoints"].clear()
    assert robot.course()["checkpoints"] == [(1, 2)]
    with pytest.raises(ValueError, match="discrete"):
        robot.act((.2, .2))


def test_observation_refuses_moving_feedback():
    robot, serial, _ = setup_robot()
    from collections import deque
    serial.replay = deque([{"T": 1001, "L": .1, "R": .1}])
    with pytest.raises(SafetyError, match="still moving"):
        robot.observe()
    assert robot.driver.estopped
