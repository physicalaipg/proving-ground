"""Stop-look-think-act adapter; odometry is confined to action diagnostics."""
import copy
import math
import threading

from harness.interface import Action, ActResult, Observation
from real.ugv02 import BootQuietError, LowVoltageError, SafetyError, reset_class


class RealRobotUGV02:
    name = "ugv02-real"

    def __init__(self, driver, camera, *, course=None):
        self.driver, self.camera = driver, camera
        self.motion, self.clock = driver.motion, driver.clock
        self.instruction, self.step = "", 0
        self._course = copy.deepcopy(course) if course is not None else None
        self._operations = threading.RLock()
        self.void_reason = ""  # Set once per episode; a voided episode stays void until clear_estop() ends it and reset() opens a new one.
        self.void_detail = {}  # {"phase": start_gate|reset|observe|act, "source": feedback_flag|motion_refused|...} (ruling 2026-10-02-19)
        self._ended = False  # Review X3-17 (ruling 2026-10-02-06): clear_estop() on a voided episode only ends it; motion needs reset().
        self._void_boot = None  # Boot key at the voided episode's mark; the next episode must see a different one (NA → no check).
        self.start_voltage_v = None
        self.lock_faults_start = None  # Firmware's count at the episode's first feedback frame; None when NA.
        self._marked = False  # Whether this episode's first feedback frame has been noted.

    def reset(self, seed, instruction=""):
        with self._operations:
            # Review X3-16: an identified self-test build never opens an episode (the driver has latched the stop).
            if self.driver.firmware_rejected:
                raise SafetyError("self-test firmware on the chassis; flash the production build")
            # Review X3-17: a voided episode has to be ended explicitly (clear_estop) before a new one may open.
            if self.void_reason and not self._ended:
                raise SafetyError("voided episode (%s) not ended: call clear_estop() first" % self.void_reason)
            self.driver.episode_mark = None  # The previous episode's mark does not judge this one's frames.
            self.void_reason, self.void_detail, self._ended = "", {}, False
            try:
                self.driver.set_wheels(0.0, 0.0)
                self.clock.sleep(self.motion.settle_s)
                self._check_start_voltage()
            except BaseException as exc:
                self._note_void(exc, "reset")
                raise
            self.instruction, self.step = instruction, 0
            self.lock_faults_start, self._marked = None, False
            # Reset does not clear a safety latch or silently invent calibration.
            obs = self.observe()
            # Review X3-17: continuing after a void needs a new reset key — the boot counter must have moved on.
            if self._void_boot is not None and self.driver.boot == self._void_boot:
                self.driver.emergency_stop("stale reset key after a voided episode")
                raise SafetyError("new episode needs a fresh reset key: boot %s unchanged since the voided episode (press RESET or power-cycle)"
                                  % self._void_boot)
            self._void_boot = None
            return obs

    def observe(self):
        with self._operations:
            try:
                self.driver.set_wheels(0.0, 0.0)
                self._verify_stopped()
            except BaseException as exc:
                self._note_void(exc, "observe")  # Same exit as act(): a low-voltage or reset read here voids too (X3-06 ①).
                raise
            self._note_lock_faults()
            return Observation(self.camera.read(), self.instruction, self.step, self.clock.time())

    def act(self, action):
        try:
            return self._act(action)
        except BaseException as exc:
            self.driver.emergency_stop(str(exc))
            raise

    def _act(self, action):
        if not isinstance(action, Action):
            self.driver.emergency_stop("act requires a discrete Action")
            raise ValueError("act requires a discrete Action")
        with self._operations:
            start = self.clock.monotonic()
            rejected = self.driver.estopped or self._ended
            timing = {}
            if not rejected:
                speed = self.motion.linear_mps
                turn_speed = math.radians(self.motion.angular_dps) * self.driver.config.track_width_m / 2
                left, right, duration = {
                    Action.FORWARD: (speed, speed, self.motion.forward_m / speed),
                    Action.LEFT: (-turn_speed, turn_speed, self.motion.turn_deg / self.motion.angular_dps),
                    Action.RIGHT: (turn_speed, -turn_speed, self.motion.turn_deg / self.motion.angular_dps),
                    Action.STOP: (0.0, 0.0, 0.0),
                }[action]
                try:
                    try:
                        timing = self.driver.move_for(left, right, duration)
                    except SafetyError as exc:
                        self._note_void(exc, "act")
                        timing = self.driver.motion_timing
                    self.clock.sleep(self.motion.settle_s)
                    if not self.driver.estopped:
                        self._verify_stopped()
                except SafetyError as exc:
                    self._note_void(exc, "act")  # Return latched fault to the episode loop, never hide it.
                except Exception as exc:
                    self.driver.emergency_stop(str(exc))
                    raise
            self._note_lock_faults()
            self.step += 1
            return ActResult(action, self.clock.monotonic() - start, None, None,
                {"odometry": self.driver.odometry(), "estopped": self.driver.estopped,
                 "rejected": rejected, "reason": self.driver.reason,
                 "stop_confirmed": self.driver.stop_confirmed,
                 "void": bool(self.void_reason), "void_reason": self.void_reason, "void_detail": dict(self.void_detail),
                 "episode_ended": self._ended, "firmware_ver": (self.driver.firmware or {}).get("ver"),
                 "lock_faults": self.lock_faults, "boot": self.driver.boot,
                 "reset_reason": self.driver.reset_reason,
                 "reset_class": reset_class(self.driver.reset_reason), **timing})

    def _note_void(self, exc, phase="act"):
        if self.void_reason:
            return  # Only the first cause of a void is recorded.
        if isinstance(exc, LowVoltageError):
            self.void_reason = "low_voltage"
        # Motion refused for the quiet period: the board has reset under the episode.
        elif isinstance(exc, BootQuietError):
            self.void_reason = "reset"
        else:
            return
        self.void_detail = {"phase": phase, "source": getattr(exc, "source", "unknown")}
        self._void_boot = self.driver.episode_mark[1] if self.driver.episode_mark else self.driver.boot

    @property
    def lock_faults(self):
        """Firmware lock faults since the episode's first feedback frame; None (NA) when a frame lacks the count."""
        if not self._marked:
            return 0
        if None in (self.lock_faults_start, self.driver.lock_faults):
            return None
        return self.driver.lock_faults - self.lock_faults_start

    def _note_lock_faults(self):
        # The fault count growing or the boot counter changing inside an episode voids the episode. The driver
        # compares every frame against the mark and latches the stop itself (review X3-12); here it is recorded.
        if not self._marked:
            self._marked = True
            self.lock_faults_start = self.driver.lock_faults
            self.driver.episode_fault = ""
            self.driver.episode_mark = (self.driver.lock_faults, self.driver.boot)
        elif self.driver.episode_fault and not self.void_reason:
            self.void_reason = self.driver.episode_fault
            self.void_detail = {"phase": "act" if self.step or self._marked else "reset", "source": "feedback_frame"}
            self._void_boot = self.driver.episode_mark[1] if self.driver.episode_mark else None

    def _check_start_voltage(self):
        minimum = self.driver.config.min_start_voltage_v
        if not minimum:
            return
        voltage = self.driver.feedback().get("v")  # A latch frame here raises LowVoltageError; reset() records it as phase "reset".
        self.start_voltage_v = voltage
        if not isinstance(voltage, (int, float)) or not math.isfinite(voltage) or voltage < minimum:
            exc = LowVoltageError("battery %s V below start threshold %s V" % (voltage, minimum))
            exc.source = "start_gate"
            self._note_void(exc, "start_gate")
            raise exc

    def _verify_stopped(self):
        # Review X3-08: wheels below the stopped threshold and, when the firmware reports its target, that target at zero.
        feedback = self.driver.feedback()
        if not self.driver._frame_shows_stopped(feedback):
            self.driver.emergency_stop("wheels still moving after stop")
            raise SafetyError(self.driver.reason)

    def emergency_stop(self):
        self.driver.emergency_stop()

    def clear_estop(self):
        """Clear the host-side latch. On a voided episode this only ends the episode (review X3-17, ruling 2026-10-02-06):
        motion stays refused until reset() opens a new episode under a fresh reset key."""
        with self._operations:
            if self.void_reason:
                self._ended = True
            self.driver.clear_estop()

    def pose(self):
        return None

    def course(self):
        if self._course is None:
            raise RuntimeError("real course calibration not supplied")
        return copy.deepcopy(self._course)

    def close(self):
        self.driver.emergency_stop("closed")
        with self._operations:
            try:
                self.driver.close()
            finally:
                self.camera.close()
