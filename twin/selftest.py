"""接口契约自测（python -m twin.selftest）：图像规格／停不动／前进步长／转角／碰撞判定／greedy 一回合／布局复现／A* 一回合。"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from harness.agents import AStarAgent, GreedyAgent
from harness.episode import run_episode
from harness.interface import Action, Robot
from harness.task import load_task
from twin.config import load_config
from twin.robot_twin import TwinRobot


def main() -> int:
    cfg = load_config()
    cfg["randomization"]["enabled"] = False         # 契约测试用标称值
    r = TwinRobot(cfg=cfg)
    assert isinstance(r, Robot), "TwinRobot 不满足 harness.interface.Robot 协议"
    obs = r.reset(0)
    p = r.pose(); sx, sy, syaw = r.layout.start
    assert abs(p.x - sx) < 1e-4 and abs(p.y - sy) < 1e-4 and abs(p.yaw_rad - syaw) < 1e-4, "起点位姿与布局不一致"
    H, W = cfg["camera"]["height"], cfg["camera"]["width"]
    assert obs.image.shape == (H, W, 3) and obs.image.dtype == np.uint8, obs.image.shape
    assert obs.image.std() > 5, "图像近乎单色，渲染可能失败"
    print(f"[1] 图像 {obs.image.shape} uint8，std={obs.image.std():.1f}  OK")

    p0 = r.pose(); res = r.act(Action.STOP); p1 = r.pose()
    assert math.hypot(p1.x - p0.x, p1.y - p0.y) < 1e-3 and res.collided is False
    print("[2] STOP 不移动  OK")

    p0 = r.pose(); r.act(Action.FORWARD); p1 = r.pose()
    d = math.hypot(p1.x - p0.x, p1.y - p0.y)
    assert abs(d - cfg["motion"]["forward_m"]) < 0.03, f"前进 {d:.3f} m ≠ {cfg['motion']['forward_m']}"
    print(f"[3] FORWARD 位移 {d:.3f} m（目标 {cfg['motion']['forward_m']}）  OK")

    y0 = r.pose().yaw_rad; r.act(Action.LEFT); y1 = r.pose().yaw_rad
    da = math.degrees((y1 - y0 + math.pi) % (2 * math.pi) - math.pi)
    assert abs(da - cfg["motion"]["turn_deg"]) < 4, f"左转 {da:.1f}° ≠ {cfg['motion']['turn_deg']}"
    y0 = y1; r.act(Action.RIGHT); y1 = r.pose().yaw_rad
    db = math.degrees((y1 - y0 + math.pi) % (2 * math.pi) - math.pi)
    assert abs(db + cfg["motion"]["turn_deg"]) < 4, f"右转 {db:.1f}°"
    print(f"[4] LEFT {da:.1f}° / RIGHT {db:.1f}°  OK")

    # 朝墙直行直到碰撞
    import copy
    cfg_nobs = copy.deepcopy(cfg); cfg_nobs["obstacles"]["count_min"] = cfg_nobs["obstacles"]["count_max"] = 0
    r2 = TwinRobot(cfg=cfg_nobs); r2.reset(1); r2.set_pose(0.6, 0.0, 0.0)   # 无障碍场，朝 +x 墙直行
    hit = False
    for _ in range(6):
        if r2.act(Action.FORWARD).collided:
            hit = True; break
    x_wall = 1.0 - cfg["robot"]["length_m"] / 2
    assert hit, "撞墙未判定碰撞"
    assert abs(r2.pose().x - x_wall) < 0.03, f"撞墙后 x={r2.pose().x:.3f}，应≈{x_wall:.3f}（穿墙或提前误判）"
    print(f"[5] 撞墙判定碰撞且不穿模（x={r2.pose().x:.3f}≈{x_wall:.3f}）  OK")
    r2.close()

    task = load_task(cfg["motion"], cfg["checkpoints"]["reach_radius_m"], cfg["checkpoints"]["count"])
    print(f"    reach_radius={cfg['checkpoints']['reach_radius_m']} max_steps={cfg['episode']['max_steps']}")
    # 无障碍场：贪心 greedy 必须 5 个全到达（检验计分器、任务层与循环）
    r3 = TwinRobot(cfg=cfg_nobs)
    s = run_episode(r3, GreedyAgent(cfg["motion"]["turn_deg"]), seed=3, max_steps=cfg["episode"]["max_steps"], task=task)
    print(f"[6] greedy 无障碍场：reached={s['checkpoints_reached']} success={s['success']} stopped={s['stopped_by_agent']} "
          f"coll={s['collisions']} steps={s['steps']} path_ratio={s['path_ratio']} wall={s['wall_s']}s")
    assert s["success"] == 1 and 0.85 <= s["path_ratio"] <= 1.3, s   # 全到达即结束，agent 不必再答 stop；贪心不避障（转身可能擦到已访问立柱），碰撞数不作断言，零碰撞契约由 [8] A* 承担
    r3.close()
    # 有障碍场（同种子布局一致性）：两次采样必须完全相同
    from twin.arena import sample_layout
    a, b = sample_layout(cfg, 3), sample_layout(cfg, 3)
    assert a.checkpoints == b.checkpoints and a.start == b.start and [o["x"] for o in a.obstacles] == [o["x"] for o in b.obstacles]
    cfg_on = copy.deepcopy(cfg); cfg_on["randomization"]["enabled"] = True
    c = sample_layout(cfg_on, 3)
    assert c.checkpoints == a.checkpoints and [o["x"] for o in c.obstacles] == [o["x"] for o in a.obstacles], "随机化开关改变了布局"
    print("[7] 同种子布局可复现，且与随机化开关无关  OK")
    # A*（补丁 3 Q1）：有障碍标称场，取首个可解种子，A* 必须全到达且零碰撞（规划器碰撞模型与孪生几何一致）
    from twin.planner import course_plan
    seed_ok = next(sd for sd in range(3, 60) if course_plan(cfg, sample_layout(cfg, sd), cfg["episode"]["max_steps"])["solvable"])
    r4 = TwinRobot(cfg=cfg)
    s = run_episode(r4, AStarAgent(), seed=seed_ok, max_steps=cfg["episode"]["max_steps"], task=task)
    print(f"[8] A* 有障碍标称场（seed {seed_ok}，{r4.course()['obstacles']} 障碍）：reached={s['checkpoints_reached']} success={s['success']} "
          f"coll={s['collisions']} steps={s['steps']} path_ratio={s['path_ratio']} wall={s['wall_s']}s")
    assert s["success"] == 1 and s["collisions"] == 0, s
    r4.close()
    r.close()
    print("selftest PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
