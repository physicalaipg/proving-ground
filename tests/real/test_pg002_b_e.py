"""internal work order B (camera config helper) and E (open-loop oracle over L1)."""
import shutil

import pytest

yaml = pytest.importorskip("yaml")
pytest.importorskip("numpy")

from harness.interface import Action, Observation
from real import camera_measure, oracle
from real.course.layout import ROOT


def test_hfov_formula():
    assert camera_measure.hfov_deg(1.0, 1.4) == pytest.approx(69.98, abs=0.05)
    assert camera_measure.vid_pid_hex("UVC Camera VendorID_1452 ProductID_34068") == "05ac:8514"
    assert camera_measure.vid_pid_hex("no ids") is None
    with pytest.raises(ValueError):
        camera_measure.hfov_deg(0, 1)


def test_camera_config_write_keeps_comments(tmp_path, monkeypatch, capsys):
    target = tmp_path / "camera.yaml"
    shutil.copy(ROOT / "real" / "config" / "camera.yaml", target)
    monkeypatch.setattr(camera_measure, "CONFIG", target)
    assert camera_measure.main(["fov", "--distance", "1.0", "--width", "1.5", "--height", "1.1", "--write"]) == 0
    assert camera_measure.main(["mount", "--height-m", "0.16", "--forward-m", "0.09", "--write"]) == 0
    assert camera_measure.main(["select", "--vid-pid", "1BCF:2C99", "--write"]) == 0
    cfg = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert cfg["camera"]["fov"]["hfov_deg"] == pytest.approx(73.7, abs=0.1) and cfg["camera"]["fov"]["vfov_deg"] == pytest.approx(57.6, abs=0.1)
    assert cfg["camera"]["mount"]["height_m"] == 0.16 and cfg["camera"]["mount"]["forward_offset_m"] == 0.09   # pitch 未给＝保留原值
    assert cfg["camera"]["selector"]["vid_pid"] == "1bcf:2c99"
    assert cfg["delta"]["height_m"] == pytest.approx(0.01) and cfg["delta"]["hfov_deg"] == pytest.approx(3.7, abs=0.1)
    text = target.read_text(encoding="utf-8")
    assert "采集口径" in text and "twin_assumed:" in text   # comments and the untouched block survive the rewrite
    with pytest.raises(SystemExit):
        camera_measure.main(["select", "--vid-pid", "nope"])


def test_oracle_plan_matches_twin_legs_and_replays_open_loop():
    plan = oracle.plan_actions()
    assert plan["solvable"] and plan["source"] in ("twin", "measured")
    if plan["source"] == "twin":
        assert plan["legs"] == [7, 10, 6, 8, 3] and len(plan["actions"]) == 34   # seeds.csv row 1017
    agent = oracle.OpenLoopOracle(plan["actions"])
    assert not agent.needs_gt
    agent.start_episode("i", 1017)
    import numpy as np
    obs = Observation(np.zeros((480, 640, 3), np.uint8), "i", 0, 0.0)
    out = [agent.decide(obs).action for _ in range(len(plan["actions"]) + 2)]
    assert out[:len(plan["actions"])] == plan["actions"] and out[-2:] == [Action.STOP, Action.STOP]
    assert all(a in (Action.FORWARD, Action.LEFT, Action.RIGHT) for a in plan["actions"])
