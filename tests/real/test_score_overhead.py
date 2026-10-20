"""Overhead offline scorer v0 (internal work order D): synthetic video → track → score; geometry of the contact judge."""
import math

import pytest

yaml = pytest.importorskip("yaml")
np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("cv2.aruco")

from real.course.register import load_course
from real.course.layout import ROOT
from real.score_overhead import score as score_mod, synth, track as track_mod

L1 = ROOT / "real" / "course" / "L1.yaml"


@pytest.fixture(scope="module")
def course():
    return load_course(L1)


@pytest.fixture(scope="module")
def footprint():
    rb = yaml.safe_load(open(L1, encoding="utf-8"))["physical"]["robot"]
    return float(rb["footprint_length_m"]), float(rb["footprint_width_m"])


def test_contact_judge_geometry(course, footprint):
    j = score_mod.ContactJudge(course, *footprint, 0.02)
    o4 = next(o for o in course["obstacles"] if o["n"] == 4)              # cylinder ⌀0.121 at (-0.07, -0.103)
    assert j.contact(o4["x"] + 0.30, o4["y"], 0.0) == ""
    assert j.contact(o4["x"] + 0.16, o4["y"], 0.0) == "O4"                 # nose 0.10 + radius 0.0605 + margin 0.02 > 0.16
    assert j.contact(0.0, 0.0, 0.0) == "O4" if math.hypot(0.07, 0.103) < 0.1 + 0.0605 + 0.02 else True
    assert j.contact(0.95, 0.0, 0.0) == "wall" and j.contact(0.85, 0.0, 0.0) == ""
    o1 = next(o for o in course["obstacles"] if o["n"] == 1)              # box 0.242 at (-0.67, 0.276), yaw 78.3°
    assert j.contact(o1["x"] + 0.40, o1["y"], 90.0) == "" and j.contact(o1["x"] + 0.19, o1["y"], 90.0) == "O1"


def _run(tmp_path, course, footprint, detour):
    cps = list(course["checkpoints"])
    o4 = next(o for o in course["obstacles"] if o["n"] == 4)              # cylinder on the straight line 1→2
    pts = [course["start"], cps[0], (0.30, 0.20), cps[1], cps[2]]           # waypoint keeps leg 1→2 clear of O4
    if detour:  # brush obstacle O4 between checkpoint 3 and 4
        pts.append((o4["x"] + 0.14, o4["y"] + 0.02))
    pts += cps[3:]
    poses = synth.path_poses(pts, step_m=0.03)
    video = tmp_path / ("detour.mp4" if detour else "clean.mp4")
    synth.write_video(video, poses, course)
    rows = track_mod.track_video(str(video), size_m=course["arena_size_m"], every=1)
    return poses, rows, score_mod.score_track(rows, course, length_m=footprint[0], width_m=footprint[1], margin_m=0.02)


def test_track_recovers_pose_from_synthetic_video(tmp_path, course, footprint):
    poses, rows, res = _run(tmp_path, course, footprint, detour=False)
    seen = [r for r in rows if r["detected"]]
    assert len(seen) >= 0.95 * len(poses)
    err = [math.hypot(r["x"] - p[0], r["y"] - p[1]) for r, p in zip(rows, poses) if r["detected"]]
    assert max(err) < 0.02
    dyaw = [abs((r["yaw_deg"] - math.degrees(p[2]) + 180) % 360 - 180) for r, p in zip(rows, poses) if r["detected"]]
    assert max(dyaw) < 6.0
    assert res["checkpoints_reached"] == 5 and res["success"] == 1 and res["collision_events"] == 0 and res["sim_score"] == 1.0
    assert res["source"] == "overhead" and not res["step_aligned"] and 1.0 <= res["path_ratio"] < 2.0   # 走到柱心＋绕行点，理想路径每段扣到达半径


def test_detour_into_an_obstacle_counts_one_contact_event(tmp_path, course, footprint):
    _, rows, res = _run(tmp_path, course, footprint, detour=True)
    assert res["checkpoints_reached"] == 5 and res["collision_events"] == 1 and res["contacts"][0]["with"] == "O4"
    assert res["sim_score"] == pytest.approx(0.9)


def test_step_alignment_groups_frames_by_log_time(course, footprint):
    # 3 steps of one second each; frames at 10 Hz; contact only inside step 2
    track = []
    for k in range(30):
        x = -0.75 + 0.01 * k
        track.append({"frame": k, "t_s": k / 10, "detected": 1, "x": x, "y": -0.75, "yaw_deg": 0.0})
    log = [{"step": 0, "t": 1000.0}, {"step": 1, "t": 1001.0}, {"step": 2, "t": 1002.0}]
    j = score_mod.ContactJudge(course, *footprint, 0.02)
    res = score_mod.score_track(track, course, length_m=footprint[0], width_m=footprint[1], margin_m=0.02, log_rows=log, t0=1000.0)
    assert res["steps"] == 3 and res["step_aligned"]
    groups = score_mod.group_by_steps(track, log, 1000.0)
    assert [len(g) for g in groups] == [10, 10, 10]


def test_track_csv_roundtrip(tmp_path):
    rows = [{"frame": 0, "t_s": 0.0, "detected": 1, "x": 0.1, "y": -0.2, "yaw_deg": 30.0, "px": 1.0, "py": 2.0},
            {"frame": 1, "t_s": 0.0333, "detected": 0, "x": "", "y": "", "yaw_deg": "", "px": "", "py": ""}]
    p = tmp_path / "t.csv"
    track_mod.write_track(rows, p, {"video": "x"})
    back = track_mod.read_track(p)
    assert back[0]["x"] == 0.1 and back[1]["x"] is None and back[1]["detected"] == 0 and p.with_suffix(".meta.json").exists()
