"""Deterministic line-oriented firmware mock and replayable feedback source."""
from collections import deque
import json
import math


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        if seconds < 0:
            raise ValueError("negative time")
        self.now += seconds


class MockSerial:
    def __init__(self, clock, *, track_width_m=0.172, replay=None, latency_s=0.0,
                 pause_at_s=None, pause_duration_s=0.0):
        if not math.isfinite(latency_s) or latency_s < 0:
            raise ValueError("latency must be finite and nonnegative")
        if (not math.isfinite(pause_duration_s) or pause_duration_s < 0 or
            (pause_at_s is not None and (not math.isfinite(pause_at_s) or pause_at_s < 0))):
            raise ValueError("write pause timing must be finite and nonnegative")
        self.pause_at_s, self.pause_duration_s = pause_at_s, pause_duration_s
        self.latency_s = latency_s
        self.clock, self.track_width_m = clock, track_width_m
        self.is_open = True
        self.echo = True
        self.timeout = self.write_timeout = 0.2
        self.watchdog_s = 3.0
        self._last_motion = clock.monotonic()
        self._wheels = (0.0, 0.0)
        self._buffer = b""
        self._replies = deque()
        self.replay = None if replay is None else deque(replay)
        self.commands = []
        self.fail_write = self.fail_read = False
        self.drop_feedback = False

    @property
    def wheels(self):
        if self.clock.monotonic() - self._last_motion > self.watchdog_s:
            self._wheels = (0.0, 0.0)
        return self._wheels

    def write(self, data):
        if not self.is_open or self.fail_write:
            raise OSError("mock serial write failed")
        self._buffer += data
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                cmd = json.loads(line)
                if not isinstance(cmd, dict):
                    continue
                self.commands.append((self.clock.monotonic(), cmd))
                if self.echo:
                    self._replies.append(line + b"\n")
                self._dispatch(cmd)
            except (ValueError, TypeError, KeyError):
                pass
        # One-shot blocking write: the command is issued before the host resumes.
        if self.pause_at_s is not None and self.clock.monotonic() >= self.pause_at_s:
            self.pause_at_s = None
            self.clock.sleep(self.pause_duration_s)
        return len(data)

    def _dispatch(self, cmd):
        kind = cmd.get("T")
        if kind in (1, 13):
            if kind == 1:
                left, right = float(cmd["L"]), float(cmd["R"])
            else:
                left = float(cmd["X"]) - float(cmd["Z"]) * self.track_width_m / 2
                right = float(cmd["X"]) + float(cmd["Z"]) * self.track_width_m / 2
            if all(math.isfinite(v) and abs(v) <= 2 for v in (left, right)):
                self._wheels = (left, right)
                self._last_motion = self.clock.monotonic()
        elif kind == 143:
            self.echo = bool(cmd["cmd"])
        elif kind == 136:
            self.watchdog_s = float(cmd["cmd"]) / 1000
        elif kind == 130 and not self.drop_feedback:
            if self.replay is not None:
                if self.replay:
                    value = self.replay.popleft()
                    self._replies.append(value if isinstance(value, bytes) else (json.dumps(value) + "\n").encode())
            else:
                left, right = self.wheels
                self._replies.append((json.dumps({"T": 1001, "L": left, "R": right,
                    "r": 0, "p": 0, "y": 0, "temp": 25, "v": 12}) + "\n").encode())

    def readline(self):
        if not self.is_open or self.fail_read:
            raise OSError("mock serial read failed")
        self.clock.sleep(self.latency_s)
        return self._replies.popleft() if self._replies else b""

    def close(self):
        self.is_open = False
