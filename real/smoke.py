"""Smoke entry.

Default (--mock): offline deterministic single episode, no model calls or real devices.
Real mode (--port): one oracle episode per call on the real chassis. The oracle walks known
checkpoint coordinates by wheel odometry and never reads the camera; the camera is sampled every
step for the record. The pose handed to the harness scorer is dead reckoning, not ground truth.
Output goes to a smoke directory outside episodes/; the site builder does not read it.
"""
import argparse
import csv
from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from harness.interface import Action, ActResult, MotionSpec, Pose
from real.camera import Camera, CameraConfig, MF200
from real.mock_serial import FakeClock, MockSerial
from real.real_env import RealRobotUGV02
from real.ugv02 import SELFTEST_SUFFIX, SafetyError, UGV02, UGV02Config, YB_EET01

ROOT = Path(__file__).resolve().parents[1]
RESULT_FIELDS = ("episode", "seed", "arrived", "checkpoints_reached", "n_checkpoints", "steps", "aborted",
                 "void", "void_reason", "void_phase", "void_source", "reason", "final_x_m", "final_y_m", "final_yaw_deg",
                 "start_voltage_v", "measured_error_cm", "wall_s")
PASS_FRACTION = 2 / 3  # at least two of three episodes must be judged arrived


class EpisodeAborted(RuntimeError):
    pass


class OdometryPoseRobot:
    """Smoke-only adapter: adds a dead-reckoned pose and the oracle's view of it to a real robot."""
    name = "yb-eet01-real-smoke"

    def __init__(self, robot, checkpoints, reach_radius_m):
        self.robot, self.motion = robot, robot.motion
        self.checkpoints = [tuple(map(float, point)) for point in checkpoints]
        self.reach_radius_m = reach_radius_m
        self.x = self.y = self.yaw = 0.0
        self._distance = self._yaw = 0.0

    def _with_gt(self, obs):
        obs.extra["gt"] = {"pose": (self.x, self.y, self.yaw), "checkpoints": self.checkpoints, "done": False,
                           "source": "wheel odometry"}
        return obs

    def reset(self, seed, instruction=""):
        obs = self.robot.reset(seed, instruction)
        odometry = self.robot.driver.odometry()
        self.x = self.y = self.yaw = 0.0
        self._distance, self._yaw = odometry["distance_m"], odometry["yaw_rad"]
        return self._with_gt(obs)

    def observe(self):
        return self._with_gt(self.robot.observe())

    def act(self, action):
        result = self.robot.act(action)
        odometry = result.extra["odometry"]
        step, turn = odometry["distance_m"] - self._distance, odometry["yaw_rad"] - self._yaw
        self._distance, self._yaw = odometry["distance_m"], odometry["yaw_rad"]
        self.x += step * math.cos(self.yaw + turn / 2)
        self.y += step * math.sin(self.yaw + turn / 2)
        self.yaw += turn
        if result.extra["void"] or result.extra["estopped"]:
            raise EpisodeAborted(result.extra["void_reason"] or result.extra["reason"] or "emergency stop")
        return ActResult(result.action, result.duration_s, None, Pose(self.x, self.y, self.yaw), result.extra)

    def pose(self):
        return Pose(self.x, self.y, self.yaw)

    def course(self):
        return {"checkpoints": self.checkpoints, "start": (0.0, 0.0), "reach_radius_m": self.reach_radius_m}

    def close(self):
        self.robot.close()


def parse_checkpoints(text):
    points = [tuple(float(value) for value in item.split(",")) for item in text.split(";") if item.strip()]
    if not points or any(len(point) != 2 or not all(math.isfinite(v) for v in point) for point in points):
        raise ValueError("checkpoints must look like '0.8,0;0.8,0.8'")
    return points


def run_real_episode(driver, camera, out_dir, episode, *, checkpoints, reach_radius_m=0.30, max_steps=40,
                     seed=None, meta=None):
    """Run one oracle episode and replace its row in <out_dir>/results.csv. Returns the row."""
    from harness.agents.scripted import GreedyAgent
    from harness.episode import run_episode
    from harness.task import load_task

    out_dir = Path(out_dir)
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    seed = episode if seed is None else seed
    inner = RealRobotUGV02(driver, camera)
    robot = OdometryPoseRobot(inner, checkpoints, reach_radius_m)
    motion = robot.motion
    task = load_task({"forward_m": motion.forward_m, "turn_deg": motion.turn_deg}, reach_radius_m, len(checkpoints))
    row = dict.fromkeys(RESULT_FIELDS, "")
    row.update(episode=episode, seed=seed, n_checkpoints=len(checkpoints), arrived=0, aborted=0, void=0)
    started = time.time()
    try:
        try:
            summary = run_episode(robot, GreedyAgent(motion.turn_deg), seed, max_steps, task,
                                  log_path=str(out_dir / "logs" / ("ep%02d.jsonl" % episode)),
                                  frames_dir=str(out_dir / "frames" / ("ep%02d" % episode)))
            row.update(arrived=int(summary["success"]), checkpoints_reached=summary["checkpoints_reached"],
                       steps=summary["steps"])
        except (EpisodeAborted, SafetyError) as exc:
            row.update(aborted=1, reason=str(exc))
        row.update(void=int(bool(inner.void_reason)), void_reason=inner.void_reason,
                   void_phase=inner.void_detail.get("phase", ""), void_source=inner.void_detail.get("source", ""),
                   final_x_m=round(robot.x, 4), final_y_m=round(robot.y, 4),
                   final_yaw_deg=round(math.degrees(robot.yaw), 2), wall_s=round(time.time() - started, 2),
                   start_voltage_v="" if inner.start_voltage_v is None else inner.start_voltage_v)
        # A self-test build on the chassis never yields episode data (internal work order patch 4 R3), whatever --firmware-ver said.
        if str((driver.firmware or {}).get("ver", "")).endswith(SELFTEST_SUFFIX):
            row.update(arrived=0, void=1, void_reason="selftest_firmware")
    finally:
        robot.close()
    rows = [r for r in read_results(out_dir) if int(r["episode"]) != episode] + [row]
    write_results(out_dir, sorted(rows, key=lambda r: int(r["episode"])))
    info = {"kind": "real-smoke", "pose_source": "wheel odometry (dead reckoning), not ground truth",
            "agent": "scripted/greedy on odometry pose", "checkpoints": checkpoints,
            "reach_radius_m": reach_radius_m, "max_steps": max_steps, "prompt_sha256": task.prompt_sha256,
            "motion": {"forward_m": motion.forward_m, "turn_deg": motion.turn_deg,
                       "linear_mps": motion.linear_mps, "angular_dps": motion.angular_dps}}
    info.update(meta or {})
    previous = read_meta(out_dir)
    # Firmware lock faults seen inside each episode; any above zero voided that episode (void_reason lock_fault).
    # null (NA) when the frames carry no count, as firmware 0.2.0 frames do not.
    info["lock_faults"] = {**previous.get("lock_faults", {}), str(episode): inner.lock_faults}
    # The banner line the firmware prints at boot, when the driver happened to read one; null otherwise.
    info["firmware_banner"] = {**previous.get("firmware_banner", {}), str(episode): driver.firmware}
    (out_dir / "meta.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return row


def read_meta(out_dir):
    try:
        return json.loads((Path(out_dir) / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def check_firmware(out_dir, firmware):
    """Episodes on different firmware are never scored together (internal work order patch 3 R0-1).

    Review X3-16: a run directory whose meta.json cannot be read or carries no firmware_ver is never appended to."""
    path = Path(out_dir) / "meta.json"
    if not path.exists():
        return
    previous = read_meta(out_dir)
    if not previous or "firmware_ver" not in previous:
        raise SystemExit("%s is unreadable or has no firmware_ver; use a new --out" % path)
    if previous["firmware_ver"] != firmware:
        raise SystemExit("firmware %s differs from %s already in %s; use a new --out"
                         % (firmware, previous.get("firmware_ver"), out_dir))


def read_results(out_dir):
    path = Path(out_dir) / "results.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_results(out_dir, rows):
    with open(Path(out_dir) / "results.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def finalize(out_dir, planned=3, measured=None):
    """Write the verdict and the sha256 manifest, then verify the manifest. Returns the verdict dict."""
    sys.path.insert(0, str(ROOT / "tools"))
    import manifest

    out_dir = Path(out_dir).resolve()
    rows = read_results(out_dir)
    for row in rows:
        if int(row["episode"]) in (measured or {}):
            row["measured_error_cm"] = measured[int(row["episode"])]
    write_results(out_dir, rows)
    valid = [row for row in rows if not int(row["void"])]
    arrived = sum(int(row["arrived"]) for row in valid)
    required = math.ceil(planned * PASS_FRACTION)
    verdict = {"planned": planned, "run": len(rows), "void": len(rows) - len(valid), "arrived": arrived,
               "required": required, "passed": len(valid) >= planned and arrived >= required}
    target = out_dir / "verdict.json"
    target.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums = out_dir / manifest.SUMS
    sums.write_text("".join("%s  %s\n" % (manifest.sha256(path), path.resolve().relative_to(ROOT).as_posix())
                            for path in manifest.files_under(out_dir)), encoding="utf-8")
    verdict["manifest_ok"] = manifest.verify(sums) == 0
    verdict["passed"] = bool(verdict["passed"] and verdict["manifest_ok"])
    return verdict


def connect(args, motion):
    """Returns driver, camera and a meta dict. --port mock exercises the real-mode path without devices."""
    config = UGV02Config(**{**YB_EET01, "track_width_m": args.turn_width})
    camera_config = CameraConfig(**MF200)
    if args.port == "mock":
        clock = FakeClock()
        serial = MockSerial(clock, track_width_m=args.turn_width)
        blank = np.zeros((camera_config.height, camera_config.width, 3), dtype=np.uint8)
        return (UGV02(serial, motion=motion, config=config, clock=clock),
                Camera(camera_config, frame_source=lambda: blank), {"port": "mock", "camera": "blank frames"})
    if not args.camera:
        raise SystemExit("--camera needs a USB product string or VID:PID")
    picked = {"index": int(args.camera)} if args.camera.isdigit() else {"device": args.camera}
    driver = UGV02.connect(args.port, config=config, motion=motion)
    try:
        camera = Camera(camera_config, **picked)
    except Exception:
        driver.close()
        raise
    return driver, camera, {"port": args.port, "camera": args.camera, "camera_config": asdict(camera_config),
                            "exposure_mode": "locked" if camera_config.exposure is not None else "auto",
                            "white_balance_mode": "locked" if camera_config.wb_temperature is not None else "auto",
                            "uvc_lock": ["%s=%d" % setting for setting in camera.lock]}


def git_head():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def real_main(args):
    out_dir = Path(args.out or ROOT / "smoke_runs" / time.strftime("%Y%m%d-real")).resolve()
    if ROOT not in out_dir.parents or out_dir == ROOT / "episodes" or (ROOT / "episodes") in out_dir.parents:
        raise SystemExit("smoke output must live inside the repository and outside episodes/")
    if args.finalize:
        measured = {}
        for item in args.measured or []:
            key, value = item.split("=")
            measured[int(key)] = float(value)
        verdict = finalize(out_dir, args.episodes, measured)
        print(json.dumps(verdict, ensure_ascii=False))
        return 0 if verdict["passed"] else 1
    if not 1 <= args.episode <= args.episodes:
        raise SystemExit("--episode must be within 1..--episodes")
    firmware = "mock" if args.port == "mock" else args.firmware_ver
    if not firmware:
        raise SystemExit("--firmware-ver is required on a real port (the ver in the firmware's banner, e.g. 0.2.0)")
    if firmware.endswith(SELFTEST_SUFFIX):
        raise SystemExit("self-test firmware never produces episode data; flash the production build first")
    check_firmware(out_dir, firmware)
    motion = MotionSpec(linear_mps=args.linear_mps, angular_dps=args.angular_dps)
    driver, camera, meta = connect(args, motion)
    meta.update(git_head=git_head(), turn_width_m=args.turn_width, firmware_ver=firmware)
    row = run_real_episode(driver, camera, out_dir, args.episode, checkpoints=parse_checkpoints(args.checkpoints),
                           reach_radius_m=args.reach_radius, max_steps=args.max_steps, meta=meta)
    print(json.dumps(row, ensure_ascii=False))
    return 0 if row["arrived"] and not row["void"] else 1


def mock_main(args):
    clock = FakeClock()
    config = CameraConfig(width=64, height=48)
    camera = Camera(config, frame_source=lambda: np.zeros((48, 64, 3), dtype=np.uint8))
    robot = RealRobotUGV02(UGV02(MockSerial(clock, latency_s=args.latency / 1000), clock=clock), camera)
    try:
        obs = robot.reset(0, "向前走，左转，右转，然后停车。")
        for action in (Action.FORWARD, Action.LEFT, Action.RIGHT, Action.STOP):
            print(json.dumps({"observation": {"step": obs.step, "shape": obs.image.shape,
                "instruction": obs.instruction, "extra": obs.extra}}, ensure_ascii=False))
            result = robot.act(action)
            print(json.dumps({"action": action.value, "duration_s": result.duration_s, **result.extra}))
            if result.extra["estopped"]:
                raise RuntimeError(result.extra["reason"])
            obs = robot.observe()
        print("episode complete: 4 steps, stopped")
    finally:
        robot.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="mock smoke by default; --port runs the real chassis")
    parser.add_argument("--mock", action="store_true", help="offline four-step episode (default when --port is absent)")
    parser.add_argument("--latency", type=float, default=0, help="mock read latency in milliseconds")
    parser.add_argument("--port", help="serial port of the chassis; 'mock' runs the real-mode path without devices")
    parser.add_argument("--camera",
                        help="USB product string or VID:PID of the onboard UVC camera; a bare index is for the bench only")
    parser.add_argument("--firmware-ver",
                        help="firmware version on the chassis, recorded in meta.json; required with a real --port")
    parser.add_argument("--out", help="smoke output directory, inside the repository and outside episodes/")
    parser.add_argument("--episode", type=int, default=1, help="which episode this call runs")
    parser.add_argument("--episodes", type=int, default=3, help="planned number of episodes")
    parser.add_argument("--checkpoints", default="0.8,0;0.8,0.8", help="x,y pairs in metres from the start pose")
    parser.add_argument("--reach-radius", type=float, default=0.30)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--turn-width", type=float, default=YB_EET01["track_width_m"],
                        help="turning width in metres (wheelbase plus track for mecanum wheels)")
    parser.add_argument("--linear-mps", type=float, default=0.10, help="smoke runs slower than the protocol speed")
    parser.add_argument("--angular-dps", type=float, default=30.0)
    parser.add_argument("--finalize", action="store_true", help="write verdict.json and SHA256SUMS for --out")
    parser.add_argument("--measured", action="append", metavar="EPISODE=CM",
                        help="tape-measured end-point error for an episode; recorded, never scored")
    args = parser.parse_args(argv)
    if args.port or args.finalize:
        if args.mock:
            parser.error("--mock and --port/--finalize are separate modes")
        return real_main(args)
    return mock_main(args)


if __name__ == "__main__":
    sys.exit(main())
