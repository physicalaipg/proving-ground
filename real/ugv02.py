"""UGV02 line protocol. All movement goes through a bounded, serviced action."""
from dataclasses import dataclass
import json
import math
import threading
import time as _time

from harness.interface import MotionSpec


class SystemClock:
    monotonic = staticmethod(_time.monotonic)
    time = staticmethod(_time.time)
    sleep = staticmethod(_time.sleep)


@dataclass(frozen=True)
class UGV02Config:
    wheel_diameter_m: float = 0.0800
    pulses_per_revolution: int = 1650
    track_width_m: float = 0.172
    model_main: int = 2
    model_module: int = 0
    speed_closed_loop: bool = False  # Source model 2 is open-loop; verify on arrival.
    emergency_command: tuple = (("T", 1), ("L", 0.0), ("R", 0.0))
    baudrate: int = 115200
    heartbeat_timeout_s: float = 3.0
    heartbeat_period_s: float = 0.1
    read_timeout_s: float = 0.2
    stopped_speed_threshold_mps: float = 0.01
    stop_confirm_tries: int = 3  # Feedback reads (each resending zero speed) an emergency stop may spend confirming the stop (review X3-08).
    duration_tolerance_s: float = 0.1
    min_start_voltage_v: float = 0.0  # 0 disables the pre-episode battery gate.

    def __post_init__(self):
        values = (self.wheel_diameter_m, self.track_width_m,
                  self.heartbeat_timeout_s, self.heartbeat_period_s, self.read_timeout_s)
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError("geometry and timing must be finite and positive")
        if not self.heartbeat_period_s + self.read_timeout_s < self.heartbeat_timeout_s <= 3:
            raise ValueError("heartbeat/read budget must be shorter than watchdog <= 3 s")
        if not all(math.isfinite(value) and value >= 0 for value in
                   (self.stopped_speed_threshold_mps, self.duration_tolerance_s, self.min_start_voltage_v)):
            raise ValueError("stop threshold, duration tolerance and start voltage must be finite and nonnegative")
        if type(self.stop_confirm_tries) is not int or self.stop_confirm_tries < 1:
            raise ValueError("stop_confirm_tries must be a positive integer")
        try:
            command = dict(self.emergency_command)
            json.dumps(command, allow_nan=False)
            if (type(command.get("T")) is not int or
                (command["T"] in (1, 11, 13) and command != {"T": 1, "L": 0.0, "R": 0.0})):
                raise ValueError("additional emergency command cannot command motion")
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid emergency command") from exc


class SafetyError(RuntimeError):
    pass


class FirmwareError(SafetyError):
    """The firmware answered a motion command with an error frame."""
    kind = "unknown"
    source = "unknown"  # "motion_refused" (error frame to T:1) or "feedback_flag" (flag inside a T:1001 frame)


class BadArgsError(FirmwareError):
    kind = "bad_args"


class LowVoltageError(FirmwareError):
    kind = "low_voltage"


class BootQuietError(FirmwareError):
    """The firmware is inside its post-reset quiet period and refuses motion."""
    kind = "boot_quiet"


class UnknownCommandError(FirmwareError):
    kind = "unknown"


MOTION_COMMANDS = (1, 11, 13)
FIRMWARE_ERRORS = {"bad_args": BadArgsError, "low_voltage": LowVoltageError, "boot_quiet": BootQuietError}
# esp_reset_reason() values grouped by class (internal work order patch 4 R3): every judgment uses the class, the single
# value only goes to logs. "fault" covers the watchdogs and panic.
RESET_CLASSES = {1: "power_or_external", 2: "power_or_external", 3: "software",
                 4: "fault", 5: "fault", 6: "fault", 7: "fault", 9: "brownout"}
# Version suffix of a firmware built with the self-test stall hooks; such a build never produces episode data.
SELFTEST_SUFFIX = "-selftest"
# YB-EET01 preset: mecanum wheels driven as a differential pair; track_width_m is the turning width.
YB_EET01 = dict(wheel_diameter_m=0.065, pulses_per_revolution=1040, track_width_m=0.2676,
                speed_closed_loop=True, min_start_voltage_v=7.0)


def reset_class(reason):
    """Class of a reset cause; None when the frame carried no cause (NA)."""
    return None if reason is None else RESET_CLASSES.get(reason, "unknown")


class UGV02:
    def __init__(self, serial, *, motion=MotionSpec(), config=UGV02Config(), clock=None):
        self.serial, self.motion, self.config = serial, motion, config
        self.clock = clock or SystemClock()
        self._lock = threading.RLock()
        self._estop = threading.Event()
        self.reason = ""
        self.left_m = self.right_m = 0.0
        # Fault count (firmware 0.1.x only), boot counter and reset cause from the latest frame.
        # None (NA) when the frame lacks the field, never 0 (internal work order patch 3 R0-1).
        self.lock_faults = self.boot = self.reset_reason = None
        self._firmware = None  # The firmware's banner line, if one was read (it is printed once per boot).
        # Review X3-16: a banner with the self-test suffix latches the stop at once and for good (clear_estop refuses).
        self.firmware_rejected = False
        self.episode_mark = None  # (lock_faults, boot) at the episode's first frame, set by real_env; None: no check.
        self.episode_fault = ""  # "lock_fault" or "reset" once a frame departs from the mark.
        self._sample = None
        self._closed = False
        self._confirming = False
        # Outcome of the latest emergency stop's confirmation (review X3-08): None before any, True once a frame
        # showed the firmware target at zero (tl/tr, when the firmware reports them) and the wheels below the
        # stopped threshold, False when no such frame arrived within stop_confirm_tries reads.
        self.stop_confirmed = None
        self.stop_confirm_reads = 0
        self.motion_timing = {}
        vals = (motion.forward_m, motion.turn_deg, motion.linear_mps, motion.angular_dps)
        if not all(math.isfinite(v) and v > 0 for v in vals):
            raise ValueError("motion values must be finite and positive")
        if not math.isfinite(motion.settle_s) or motion.settle_s < 0:
            raise ValueError("invalid settle time")
        try:
            serial.timeout = config.read_timeout_s
            serial.write_timeout = config.read_timeout_s
            self._send({"T": 143, "cmd": 0})
            self._send({"T": 136, "cmd": int(config.heartbeat_timeout_s * 1000)})
            self.set_wheels(0.0, 0.0)
        except Exception as exc:
            self.emergency_stop(str(exc))
            raise SafetyError(str(exc)) from exc

    @classmethod
    def connect(cls, port, *, config=UGV02Config(), **kwargs):
        import serial  # Optional dependency, never imported by the mock path.
        link = serial.Serial(port, config.baudrate, timeout=config.read_timeout_s,
                             write_timeout=config.read_timeout_s)
        try:
            return cls(link, config=config, **kwargs)
        except Exception:
            link.close()
            raise

    @property
    def estopped(self):
        return self._estop.is_set()

    @property
    def firmware(self):
        return self._firmware

    @firmware.setter
    def firmware(self, banner):
        # Review X3-16: judged the moment the identity is known, wherever it came from (banner line or operator).
        self._firmware = banner
        if str((banner or {}).get("ver", "")).endswith(SELFTEST_SUFFIX):
            self.firmware_rejected = True
            self.emergency_stop("self-test firmware on the chassis; flash the production build")

    def _send(self, command):
        if self._closed or not self.serial.is_open:
            raise OSError("serial disconnected")
        data = (json.dumps(command, allow_nan=False) + "\n").encode()
        issued = self.clock.monotonic()
        if self.serial.write(data) != len(data):
            raise OSError("short serial write")
        if command.get("T") == 1:
            self._last_motion_sent_s = issued

    def set_wheels(self, left, right):
        with self._lock:
            if self.estopped and (left or right):
                raise SafetyError("emergency stop latched")
            v = (left + right) / 2
            omega = (right - left) / self.config.track_width_m
            wheel_limit = self.motion.linear_mps + math.radians(self.motion.angular_dps) * self.config.track_width_m / 2
            if (not all(math.isfinite(x) for x in (left, right)) or
                max(abs(left), abs(right)) > min(2.0, wheel_limit) + 1e-12 or
                abs(v) > self.motion.linear_mps + 1e-12 or
                abs(omega) > math.radians(self.motion.angular_dps) + 1e-12):
                self.emergency_stop("speed limit exceeded")
                raise SafetyError(self.reason)
            try:
                self._send({"T": 1, "L": float(left), "R": float(right)})
            except Exception as exc:
                self.emergency_stop(str(exc))
                if isinstance(exc, OSError):
                    raise SafetyError(str(exc)) from exc
                raise

    def emergency_stop(self, reason="manual emergency stop"):
        # Publish before acquiring the wire lock: waiting movement cannot resume.
        self._estop.set()
        with self._lock:
            if self._confirming:
                return  # A fault seen while confirming a stop: the latch is already set, keep the first reason.
            self.reason = reason
            self.stop_confirmed = False
            self.stop_confirm_reads = 0
            try:
                self._send({"T": 1, "L": 0.0, "R": 0.0})
                command = dict(self.config.emergency_command)
                if command != {"T": 1, "L": 0.0, "R": 0.0}:
                    self._send(command)
                self._confirm_stop()
            except BaseException:
                pass  # Preserve the original fault even if the stop write is interrupted.
                # Physical disconnect: firmware watchdog is the remaining fallback.

    def _confirm_stop(self):
        # Review X3-08: a sent zero-speed line is not a stopped robot. Read feedback until one frame shows the
        # firmware's own target at zero (tl/tr; absent on UGV02 firmware, then wheel speed alone decides) and the
        # wheels below the stopped threshold; every read that does not confirm resends zero speed first. Bounded by
        # stop_confirm_tries reads of read_timeout_s each, so it ends under a dead link as well. Faults seen here do
        # not recurse into emergency_stop; the latch is already set.
        self._confirming = True
        try:
            for attempt in range(self.config.stop_confirm_tries):
                if attempt:
                    self._send({"T": 1, "L": 0.0, "R": 0.0})
                self.stop_confirm_reads = attempt + 1
                try:
                    reply = self._read_frame(raise_low_voltage=False)
                except (OSError, ValueError, TypeError, KeyError, TimeoutError, FirmwareError):
                    continue
                if self._frame_shows_stopped(reply):
                    self.stop_confirmed = True
                    return True
            return False
        finally:
            self._confirming = False

    def _frame_shows_stopped(self, reply):
        threshold = self.config.stopped_speed_threshold_mps
        if max(abs(float(reply["L"])), abs(float(reply["R"]))) > threshold:
            return False
        targets = [reply.get(key) for key in ("tl", "tr")]
        if any(value is not None for value in targets):
            # Firmware that reports its target: both must be present, numeric and exactly zero.
            return all(isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0
                       for value in targets)
        return True

    def clear_estop(self):
        with self._lock:
            if self.firmware_rejected:
                raise SafetyError("self-test firmware on the chassis: the stop cannot be cleared; flash the production build")
            self.set_wheels(0.0, 0.0)
            self.feedback()  # Require a healthy link before explicitly unlocking.
            self.reason = ""
            self._estop.clear()

    def feedback(self):
        with self._lock:
            try:
                return self._read_frame()
            except Exception as exc:
                self.emergency_stop(str(exc))
                if isinstance(exc, (OSError, ValueError, TypeError, KeyError)):
                    raise SafetyError(str(exc)) from exc
                raise

    def _read_frame(self, raise_low_voltage=True):
        # One T:130 query and its reply; raises on a bad link but never latches the stop itself.
        with self._lock:
            self._send({"T": 130})
            deadline = self.clock.monotonic() + self.config.read_timeout_s
            for _ in range(256):  # Also bound a noisy, nonblocking injected source.
                if self.clock.monotonic() >= deadline:
                    break
                line = self.serial.readline()
                if not line:
                    break
                try:
                    reply = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if isinstance(reply, dict) and reply.get("T") == -1 and "err" in reply:
                    if reply.get("got") in MOTION_COMMANDS:
                        error = FIRMWARE_ERRORS.get(reply["err"], UnknownCommandError)
                        exc = error("firmware rejected motion command: %s" % reply["err"])
                        exc.source = "motion_refused"
                        raise exc
                    continue
                if isinstance(reply, dict) and "fw" in reply and "T" not in reply:
                    self.firmware = reply
                    continue
                if not isinstance(reply, dict) or reply.get("T") != 1001:
                    continue
                if reply.get("low_voltage") and raise_low_voltage:
                    exc = LowVoltageError("firmware reports low voltage latch")
                    exc.source = "feedback_flag"
                    raise exc
                left, right = float(reply["L"]), float(reply["R"])
                if not all(math.isfinite(v) and abs(v) <= 2 for v in (left, right)):
                    raise ValueError("invalid wheel feedback")
                now = self.clock.monotonic()
                if self._sample is not None:
                    then, prev_l, prev_r = self._sample
                    self.left_m += prev_l * (now - then)
                    self.right_m += prev_r * (now - then)
                self._sample = (now, left, right)
                for key in ("lock_faults", "boot", "reset_reason"):
                    value = reply.get(key)
                    setattr(self, key, value if type(value) is int and value >= 0 else None)
                self._check_episode_mark()
                return reply
            raise TimeoutError("wheel feedback timeout")

    def _check_episode_mark(self):
        # Latch on the frame that shows it, before the next motion command goes out (review X3-12).
        if self.episode_mark is None or self.episode_fault:
            return
        faults, boot = self.episode_mark
        # A field that is NA at the mark judges nothing; one that goes missing after the mark counts as a departure.
        if boot is not None and self.boot != boot:
            kind = "reset"
        elif faults is not None and (self.lock_faults is None or self.lock_faults > faults):
            kind = "lock_fault"
        else:
            kind = ""
        if kind:
            self.episode_fault = kind
            self.emergency_stop("firmware %s during the episode" % kind.replace("_", " "))

    def move_for(self, left, right, duration_s):
        self.motion_timing = {}
        if not math.isfinite(duration_s) or duration_s < 0:
            self.emergency_stop("invalid movement duration")
            raise SafetyError(self.reason)
        started = self.clock.monotonic()
        deadline = started + duration_s
        cycle = 0
        try:
            while not self.estopped:
                issued = self.clock.monotonic()
                if issued >= deadline:
                    break
                self.set_wheels(left, right)
                if cycle == 0:
                    started = self._last_motion_sent_s
                    deadline = started + duration_s
                self.feedback()
                cycle += 1
                remaining = min(started + cycle * self.config.heartbeat_period_s, deadline) - self.clock.monotonic()
                self.clock.sleep(max(0.0, remaining))
        except BaseException as exc:
            self.emergency_stop(str(exc))
            raise
        else:
            self.set_wheels(0.0, 0.0)
            elapsed = self._last_motion_sent_s - started if cycle and (left or right) else 0.0
            exceeded = elapsed > duration_s + self.config.duration_tolerance_s
            self.motion_timing = {"motion_duration_s": elapsed, "duration_limit_s": duration_s,
                                  "duration_tolerance_s": self.config.duration_tolerance_s,
                                  "duration_exceeded": exceeded}
            if exceeded:
                self.emergency_stop("movement duration exceeded")
            self.feedback()
            return self.motion_timing

    def odometry(self):
        return {"left_m": self.left_m, "right_m": self.right_m,
                "distance_m": (self.left_m + self.right_m) / 2,
                "yaw_rad": (self.right_m - self.left_m) / self.config.track_width_m}

    def close(self):
        self.emergency_stop("closed")
        self._closed = True
        self.serial.close()
