"""任务层（协议 v0 的代码落点）：提示词文件 → system 段、指令模板；每步按「下一检查点」渲染指令。任务语义只在这里，孪生与真机都不知道任务。"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

PROMPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "protocol", "prompt_v0.md")
# harness 常量（协议 v0「harness 常量」节；改动即换协议版本）：
MEMORY_NOTES = 3                     # 回传给模型的最近 note 条数，对所有模型固定，models.yaml 不可覆盖
SIGN_COLOR_NAMES = {1: "red", 2: "green", 3: "blue", 4: "yellow", 5: "purple"}   # 数字牌边框色（与 twin/textures.py SIGN_COLORS 同序；真机牌照此印）


@dataclass(frozen=True)
class Task:
    system: str            # 已填入步长的 system 文本（英文主文）
    instruction_tpl: str   # 含 {reach_radius_m} {next_checkpoint} {next_color} 的模板
    reach_radius_m: float
    n_checkpoints: int
    prompt_sha256: str
    memory_notes: int = MEMORY_NOTES  # 回传给模型的最近 note 条数（0＝无记忆）；协议常量，不随模型变

    def render(self, next_checkpoint: int) -> str:
        """下一检查点提示只含身份（编号）与外观（牌边框色），不含方位／距离／朝向（补丁 3 Q2 提示边界）。"""
        k = min(next_checkpoint, self.n_checkpoints)
        # 用 replace 不用 str.format：提示词里有 JSON 花括号
        return (self.instruction_tpl.replace("{reach_radius_m}", str(self.reach_radius_m))
                .replace("{next_checkpoint}", str(k)).replace("{next_color}", SIGN_COLOR_NAMES.get(k, "")))


def load_task(motion: dict, reach_radius_m: float, n_checkpoints: int = 5, path: str = PROMPT_PATH) -> Task:
    text = open(path, encoding="utf-8").read()
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    sys_m = re.search(r"## system.*?\n\n(.*?)\n\n（对照", text, re.S)
    ins_m = re.search(r"## instruction.*?\n\n(.*?)\n\n（对照", text, re.S)
    if not (sys_m and ins_m):
        raise ValueError(f"提示词文件格式不符：{path}")
    system = sys_m.group(1).strip().replace("{forward_m}", str(motion["forward_m"])).replace("{turn_deg}", f"{motion['turn_deg']:g}")
    return Task(system, ins_m.group(1).strip(), reach_radius_m, n_checkpoints, sha)
