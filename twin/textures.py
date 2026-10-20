"""检查点数字牌贴图（PNG，运行时生成到 twin/_assets/，不入仓）。"""
from __future__ import annotations

import os

SIGN_COLORS = {1: (220, 40, 40), 2: (40, 160, 60), 3: (40, 90, 220), 4: (230, 180, 20), 5: (170, 40, 190)}
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_assets")


def ensure_sign_pngs(n: int = 5, size: int = 256) -> str:
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(ASSET_DIR, exist_ok=True)
    for i in range(1, n + 1):
        path = os.path.join(ASSET_DIR, f"sign{i}.png")
        if os.path.exists(path):
            continue
        im = Image.new("RGB", (size, size), (255, 255, 255))
        d = ImageDraw.Draw(im)
        bw = size // 10
        d.rectangle([0, 0, size - 1, size - 1], outline=SIGN_COLORS.get(i, (0, 0, 0)), width=bw)
        try:
            font = ImageFont.load_default(size=int(size * 0.62))
        except TypeError:   # 旧 Pillow
            font = ImageFont.load_default()
        txt = str(i)
        bbox = d.textbbox((0, 0), txt, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), txt, fill=(0, 0, 0), font=font)
        im.save(path)
    return ASSET_DIR
