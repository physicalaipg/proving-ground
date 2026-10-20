"""从配置＋布局生成 MJCF（不手写 XML）。"""
from __future__ import annotations

import math
from typing import Any

from .arena import Layout


def _f(v: float) -> str:
    return f"{v:.6f}"


def build_xml(cfg: dict[str, Any], lay: Layout, asset_dir: str) -> str:
    a = cfg["arena"]; cp = cfg["checkpoints"]; rb = cfg["robot"]; cam = cfg["camera"]; ph = cfg["physics"]
    half = a["size_m"] / 2; wt = a["wall_thickness_m"]; wh = a["wall_height_m"]
    L, W, H = rb["length_m"], rb["width_m"], rb["height_m"]
    zc = H / 2 + 0.002                                   # 底盘悬空 2 mm，不与地面接触（平面三自由度模型）
    cf = f'friction="{_f(rb.get("contact_friction", 0.3))} 0.005 0.0001"'   # 静物与车身共用的接触摩擦
    fovy = math.degrees(2 * math.atan(math.tan(math.radians(cam["hfov_deg"]) / 2) * cam["height"] / cam["width"]))
    f1, f2 = lay.floor_rgb
    lx, ly, lz = lay.light["pos"]; ld = lay.light["diffuse"]; la = lay.light["ambient"]
    x = [f'<mujoco model="twin01-seed{lay.seed}">',
         f'<compiler angle="radian" texturedir="{asset_dir}"/>',
         f'<option timestep="{ph["timestep"]}" integrator="implicitfast" gravity="0 0 -9.81"/>',
         f'<visual><global offwidth="{cam["width"]}" offheight="{cam["height"]}"/>'
         f'<headlight ambient="{_f(la)} {_f(la)} {_f(la)}" diffuse="0.2 0.2 0.2" specular="0 0 0"/><map znear="0.01" zfar="20"/></visual>',
         '<asset>',
         f'<texture name="floor" type="2d" builtin="checker" rgb1="{_f(f1[0])} {_f(f1[1])} {_f(f1[2])}" rgb2="{_f(f2[0])} {_f(f2[1])} {_f(f2[2])}" width="512" height="512"/>',
         '<material name="floor" texture="floor" texrepeat="8 8" reflectance="0"/>']
    for i in range(1, cp["count"] + 1):
        x.append(f'<texture name="sign{i}" type="2d" file="sign{i}.png"/><material name="sign{i}" texture="sign{i}" texrepeat="1 1" texuniform="false" reflectance="0"/>')
    x += ['</asset>', '<worldbody>',
          f'<light name="lamp" pos="{_f(lx)} {_f(ly)} {_f(lz)}" dir="{_f(-lx)} {_f(-ly)} {_f(-lz)}" diffuse="{_f(ld)} {_f(ld)} {_f(ld)}" specular="0.1 0.1 0.1" castshadow="true"/>',
          f'<geom name="floor" type="plane" size="{_f(half + 0.3)} {_f(half + 0.3)} 0.05" material="floor" friction="{_f(lay.friction)} 0.005 0.0001"/>']
    wr = " ".join(_f(v) for v in lay.wall_rgba)
    for name, (px, py, sx, sy) in {"wall_n": (0, half + wt / 2, half + wt, wt / 2), "wall_s": (0, -half - wt / 2, half + wt, wt / 2),
                                    "wall_e": (half + wt / 2, 0, wt / 2, half + wt), "wall_w": (-half - wt / 2, 0, wt / 2, half + wt)}.items():
        x.append(f'<geom name="{name}" type="box" pos="{_f(px)} {_f(py)} {_f(wh / 2)}" size="{_f(sx)} {_f(sy)} {_f(wh / 2)}" rgba="{wr}" {cf}/>')
    sx0, sy0, syaw = lay.start
    x += [f'<body name="robot" pos="{_f(sx0)} {_f(sy0)} {_f(zc)}">',
          '<joint name="jx" type="slide" axis="1 0 0" damping="0.5"/><joint name="jy" type="slide" axis="0 1 0" damping="0.5"/>',
          f'<joint name="jyaw" type="hinge" axis="0 0 1" damping="0.05"/>',
          f'<geom name="chassis" type="box" size="{_f(L / 2)} {_f(W / 2)} {_f(H / 2)}" rgba="0.15 0.15 0.18 1" mass="{rb["mass_kg"]}" {cf}/>',
          f'<geom name="nose" type="box" pos="{_f(L / 2 - 0.02)} 0 {_f(H / 2 + 0.01)}" size="0.02 0.03 0.01" rgba="0.9 0.5 0.1 1" contype="0" conaffinity="0"/>',
          f'<camera name="eye" pos="{_f(cam["forward_offset_m"])} 0 {_f(cam["height_m"] - zc)}" xyaxes="0 -1 0 0 0 1" fovy="{_f(fovy)}"/>',
          '</body>']
    ph_, pr, ss = cp["post_height_m"], cp["post_radius_m"], cp["sign_size_m"]
    for i, ((px, py), yaw) in enumerate(zip(lay.checkpoints, lay.sign_yaws), start=1):
        x.append(f'<geom name="post_{i}" type="cylinder" pos="{_f(px)} {_f(py)} {_f(ph_ / 2)}" size="{_f(pr)} {_f(ph_ / 2)}" rgba="0.35 0.35 0.38 1" {cf}/>')
        # 数字牌＝两片背靠背的有限平面（2D 贴图正反都正立；平面碰撞为无限大，故必须关闭碰撞）
        cy_, sy_ = math.cos(yaw), math.sin(yaw); zs = ph_ + ss / 2
        for side, (nx, ny) in (("f", (cy_, sy_)), ("b", (-cy_, -sy_))):
            x.append(f'<geom name="sign_{i}{side}" type="plane" pos="{_f(px + nx * 0.004)} {_f(py + ny * 0.004)} {_f(zs)}" size="{_f(ss / 2)} {_f(ss / 2)} 0.01" '
                     f'xyaxes="{_f(-ny)} {_f(nx)} 0 0 0 1" material="sign{i}" contype="0" conaffinity="0"/>')
        x.append(f'<geom name="signbody_{i}" type="box" pos="{_f(px)} {_f(py)} {_f(zs)}" size="0.003 {_f(ss / 2)} {_f(ss / 2)}" euler="0 0 {_f(yaw)}" rgba="0.2 0.2 0.2 1" contype="0" conaffinity="0"/>')
    for i, o in enumerate(lay.obstacles, start=1):
        rgba = " ".join(_f(v) for v in o["rgba"]); hz = o["height"] / 2
        if o["kind"] == "box":
            x.append(f'<geom name="obs_{i}" type="box" pos="{_f(o["x"])} {_f(o["y"])} {_f(hz)}" size="{_f(o["size"] / 2)} {_f(o["size"] / 2)} {_f(hz)}" euler="0 0 {_f(o["yaw"])}" rgba="{rgba}" {cf}/>')
        else:
            x.append(f'<geom name="obs_{i}" type="cylinder" pos="{_f(o["x"])} {_f(o["y"])} {_f(hz)}" size="{_f(o["size"] / 2)} {_f(hz)}" rgba="{rgba}" {cf}/>')
    x += ['</worldbody>', '<actuator>',
          '<velocity name="vx" joint="jx" kv="60" forcerange="-25 25"/>',
          '<velocity name="vy" joint="jy" kv="60" forcerange="-25 25"/>',
          '<velocity name="vyaw" joint="jyaw" kv="3" forcerange="-3 3"/>',
          '</actuator>', '</mujoco>']
    return "\n".join(x)
