"""Real course L1 (internal work order A): the stored constants equal the twin's seed, and registration maps clicks back to metres."""
import json
import math

import pytest

yaml = pytest.importorskip("yaml")
np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from real.course import layout as layout_mod, register
from real.course.layout import ROOT

L1 = ROOT / "real" / "course" / "L1.yaml"


def load():
    return yaml.safe_load(open(L1, encoding="utf-8"))


def test_l1_twin_block_pins_seed_1017():
    lay = load()
    assert lay["twin"]["seed"] == 1017
    assert lay["twin"] == layout_mod.export_layout(1017)


def test_l1_sign_words_match_prompt():
    prompt = (ROOT / "protocol" / "prompt_v0.md").read_text(encoding="utf-8")
    for p in load()["twin"]["checkpoints"]:
        assert f"{p['n']} {p['color']}" in prompt


def test_l1_geometry_respects_protocol_constants():
    tw = load()["twin"]
    c = tw["constants"]
    half = tw["arena_size_m"] / 2
    pts = [(p["x"], p["y"]) for p in tw["checkpoints"]]
    for i, a in enumerate(pts):
        assert half - max(abs(a[0]), abs(a[1])) >= c["wall_margin_m"] - 1e-3
        for b in pts[i + 1:]:
            assert math.hypot(a[0] - b[0], a[1] - b[1]) >= c["min_gap_m"] - 1e-3
    for o in tw["obstacles"]:
        for a in pts + [(tw["start"]["x"], tw["start"]["y"])]:
            assert math.hypot(a[0] - o["x"], a[1] - o["y"]) >= c["obstacle_clearance_m"] - 1e-3
    assert 3 <= len(tw["obstacles"]) <= 5


def _project(Hw2p, x, y):
    u, v, w = Hw2p @ (x, y, 1.0)
    return [float(u / w), float(v / w)]


def _synthetic_points(lay, offsets=None, yaw_delta=0.0):
    """Clicks of a photo taken by an oblique camera: world → pixel via a chosen projective transform."""
    tw = lay["twin"]
    world_corners = np.array([(-1, -1), (1, -1), (1, 1), (-1, 1)], dtype=np.float32)
    pixel_corners = np.array([(212, 880), (1720, 905), (1500, 140), (390, 120)], dtype=np.float32)
    Hw2p = cv2.getPerspectiveTransform(world_corners, pixel_corners).astype(np.float64)
    offsets = offsets or {}
    st = tw["start"]
    yaw = math.radians(st["yaw_deg"] + yaw_delta)
    pts = [(-1, -1), (1, -1), (1, 1), (-1, 1), (st["x"], st["y"]), (st["x"] + 0.15 * math.cos(yaw), st["y"] + 0.15 * math.sin(yaw))]
    for p in tw["checkpoints"]:
        dx, dy = offsets.get(("checkpoint", p["n"]), (0, 0))
        pts.append((p["x"] + dx, p["y"] + dy))
    for o in tw["obstacles"]:
        dx, dy = offsets.get(("obstacle", o["n"]), (0, 0))
        pts.append((o["x"] + dx, o["y"] + dy))
    return {"photo": "synthetic", "clicks": [_project(Hw2p, x, y) for x, y in pts]}


def test_register_recovers_world_coordinates_from_oblique_photo():
    lay = load()
    rep = register.solve(_synthetic_points(lay, {("checkpoint", 3): (0.03, -0.02)}), lay)
    assert rep["all_ok"] and rep["yaw_ok"]
    by = {(i["kind"], i["n"]): i for i in rep["items"]}
    assert by[("checkpoint", 3)]["dev_m"] == pytest.approx(math.hypot(0.03, 0.02), abs=2e-3)
    assert by[("checkpoint", 1)]["dev_m"] < 1e-3
    assert abs(by[("start", "S")]["dyaw_deg"]) < 0.5
    assert rep["max_dev_m"] <= rep["tolerance_m"]


def test_register_rejects_items_beyond_tolerance_and_yaw():
    lay = load()
    rep = register.solve(_synthetic_points(lay, {("obstacle", 2): (0.0, 0.08)}, yaw_delta=25.0), lay)
    assert not rep["all_ok"] and not rep["yaw_ok"]
    bad = [i for i in rep["items"] if not i["ok"]]
    assert [(i["kind"], i["n"]) for i in bad] == [("obstacle", 2)]


def test_register_requires_full_click_list():
    lay = load()
    pts = _synthetic_points(lay)
    pts["clicks"] = pts["clicks"][:-1]
    with pytest.raises(ValueError):
        register.solve(pts, lay)


def test_load_course_prefers_measured_file(tmp_path):
    lay = load()
    layout = tmp_path / "L1.yaml"
    layout.write_text(yaml.safe_dump(lay, allow_unicode=True, sort_keys=False), encoding="utf-8")
    course = register.load_course(layout)
    assert course["source"] == "twin" and len(course["checkpoints"]) == 5 and course["reach_radius_m"] == 0.4
    rep = register.solve(_synthetic_points(lay, {("checkpoint", 2): (0.04, 0.0)}), lay)
    register.measured_path(layout).write_text(yaml.safe_dump(register.measured_block(rep), allow_unicode=True, sort_keys=False), encoding="utf-8")
    course = register.load_course(layout)
    assert course["source"] == "measured"
    assert course["checkpoints"][1][0] == pytest.approx(lay["twin"]["checkpoints"][1]["x"] + 0.04, abs=2e-3)
    wrong = yaml.safe_load(register.measured_path(layout).read_text(encoding="utf-8")); wrong["layout_seed"] = 1
    register.measured_path(layout).write_text(yaml.safe_dump(wrong), encoding="utf-8")
    with pytest.raises(ValueError):
        register.load_course(layout)


def test_card_renders_one_html_with_every_item():
    from real.course import make_card
    lay = load()
    html = make_card.render_html(lay)
    for p in lay["twin"]["checkpoints"]:
        assert f"{p['n']} {p['color']}" in html
    assert html.count("<svg") == 2 and "A(-1,-1)" in html
