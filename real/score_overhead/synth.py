"""Synthetic overhead video for the scorer's self-test (internal work order D). Not evidence about the real camera."""
from __future__ import annotations

import math
from pathlib import Path

from real.score_overhead.markers import CAR_ID, CORNER_IDS, dictionary


def world_to_pixel_matrix(size_px=(1920, 1080), size_m: float = 2.0, oblique: float = 0.12):
    """A mildly oblique camera: the 2 m square maps to a trapezoid in the frame."""
    import cv2
    import numpy as np
    w, h = size_px
    half = size_m / 2
    s = 0.42 * h
    src = np.array([(-half, -half), (half, -half), (half, half), (-half, half)], dtype=np.float32)
    dst = np.array([(w / 2 - s * (1 + oblique), h / 2 + s), (w / 2 + s * (1 + oblique), h / 2 + s),
                    (w / 2 + s * (1 - oblique), h / 2 - s), (w / 2 - s * (1 - oblique), h / 2 - s)], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def _marker_img(mid: int, px: int = 200):
    import cv2
    return cv2.aruco.generateImageMarker(dictionary(), mid, px, borderBits=1)


def _paste_marker(canvas, Hw2p, mid: int, x: float, y: float, yaw_rad: float, size_m: float):
    """Marker square centred at (x, y), its top edge toward yaw (the arrow); white quiet zone around it."""
    import cv2
    import numpy as np
    img = _marker_img(mid)
    px = img.shape[0]
    q = size_m / 2 * 1.5          # quiet zone
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    def w(dx, dy):  # marker-local (forward dx, left dy) → world
        return (x + c * dx - s * dy, y + s * dx + c * dy)
    def proj(pts):
        pts = np.array(pts, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, Hw2p).reshape(-1, 2)
    hs = size_m / 2
    # image corners TL, TR, BR, BL ↔ world: top edge at +forward; TL is the left end of the top edge
    world_quad = [w(hs, hs), w(hs, -hs), w(-hs, -hs), w(-hs, hs)]
    quiet = [w(q, q), w(q, -q), w(-q, -q), w(-q, q)]
    cv2.fillConvexPoly(canvas, proj(quiet).astype(np.int32), (255, 255, 255))
    M = cv2.getPerspectiveTransform(np.array([(0, 0), (px - 1, 0), (px - 1, px - 1), (0, px - 1)], dtype=np.float32), proj(world_quad).astype(np.float32))
    warped = cv2.warpPerspective(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), M, (canvas.shape[1], canvas.shape[0]), flags=cv2.INTER_NEAREST, borderValue=(0, 255, 0))
    mask = cv2.warpPerspective(np.full(img.shape, 255, np.uint8), M, (canvas.shape[1], canvas.shape[0]), flags=cv2.INTER_NEAREST)
    canvas[mask > 0] = warped[mask > 0]


def path_poses(points: list[tuple[float, float]], step_m: float = 0.02) -> list[tuple[float, float, float]]:
    """Poses along a polyline at a fixed spacing; yaw = direction of travel."""
    out = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        d = math.hypot(x2 - x1, y2 - y1); yaw = math.atan2(y2 - y1, x2 - x1)
        n = max(1, int(d / step_m))
        out += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n, yaw) for k in range(n)]
    out.append((points[-1][0], points[-1][1], out[-1][2] if out else 0.0))
    return out


def write_video(path: Path, poses, course: dict, marker_size_m: float = 0.08, fps: float = 30.0, size_px=(1920, 1080)) -> None:
    import cv2
    import numpy as np
    Hw2p = world_to_pixel_matrix(size_px, course["arena_size_m"])
    half = course["arena_size_m"] / 2
    corner_world = {1: (-half, -half), 2: (half, -half), 3: (half, half), 4: (-half, half)}
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size_px)
    assert writer.isOpened()
    for x, y, yaw in poses:
        canvas = np.full((size_px[1], size_px[0], 3), (90, 110, 120), np.uint8)
        # boundary tape and obstacle footprints, for the eye only
        quad = cv2.perspectiveTransform(np.array([corner_world[i] for i in (1, 2, 3, 4)], dtype=np.float32).reshape(-1, 1, 2), Hw2p).reshape(-1, 2)
        cv2.polylines(canvas, [quad.astype(np.int32)], True, (40, 40, 200), 3)
        for o in course["obstacles"]:
            c = cv2.perspectiveTransform(np.array([(o["x"], o["y"])], dtype=np.float32).reshape(-1, 1, 2), Hw2p).reshape(2)
            cv2.circle(canvas, (int(c[0]), int(c[1])), 12, (60, 80, 140), -1)
        for i, (wx, wy) in corner_world.items():
            _paste_marker(canvas, Hw2p, i, wx, wy, 0.0, marker_size_m)
        _paste_marker(canvas, Hw2p, CAR_ID, x, y, yaw, marker_size_m)
        writer.write(canvas)
    writer.release()
