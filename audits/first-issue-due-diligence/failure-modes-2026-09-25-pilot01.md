# 失败模式三分类表 · 2026-09-25-pilot01（内部工单）

> 判据见 `tools/failure_modes.py` 文件头（预登记提交先于本表）；阈值 DISP_MIN_M=0.4、F1 占比≥0.5。逐回合明细 `failure-modes-2026-09-25-pilot01.csv`。

| run | agent | N | 完成 | F1 解析或格式失败 | F2 未动 | F3 行进后碰撞或超步 | 位移不可得回合 | 位移交叉核对不一致 |
|---|---|---|---|---|---|---|---|---|
| 2026-09-25-pilot01 | deepseek-flash--nothink--official | 30 | 1 | 0 | 0 | 29 | 0 | 0 |
| 2026-09-25-pilot01 | glm-5v-turbo--nothink--official | 30 | 0 | 0 | 11 | 19 | 0 | 4 |
| 2026-09-25-pilot01 | qwen3-vl-plus--nothink--official | 30 | 0 | 0 | 2 | 28 | 0 | 1 |
| 2026-09-25-pilot01-baselines | random | 30 | 0 | 0 | 3 | 27 | 0 | 0 |

表注：位移取 results.csv `traveled_m`（含第 0 步）；`disp_log_m` 由日志相邻位姿累加（无起点、少第 0 步），只作交叉核对；「不一致」＝两种位移对 0.40 m 阈值判断相反的回合数（有则逐回合在 csv 的 `disp_cross_check` 列可查）。位移不可得时按有效前进动作数 == 0 判 F2。

## 脚注 · 位移判据敏感性（内部工单，2026-10-09；手工追加于脚本产物之后，重跑 `tools/failure_modes.py` 后须重新追加本节）

0.40 m 判据与单步位移同量级：协议 v0 单步前进 `forward_m`＝0.20 m（`harness/interface.py`），阈值恰为两步。两种位移口径（`traveled_m` 含第 0 步；日志位姿累加 `disp_log_m` 无起点、少第 0 步）之差在 120 回合里为 0～0.1964 m（中位 0.1785 m），即约一步。有 5 回合在两种口径下对 0.40 m 的判断相反，按预登记（`traveled_m`）计入 F3，分类结果与上表不改：

| 模型 | seed | traveled_m | 位姿累加值 disp_log_m | 预登记判定 | 位姿累加口径下 |
|---|---|---|---|---|---|
| glm-5v-turbo | 1006 | 0.4904 | 0.3060 | F3（collisions=1 steps=4） | F2 |
| glm-5v-turbo | 1013 | 0.5534 | 0.3689 | F3（collisions=0 steps=6） | F2 |
| glm-5v-turbo | 1015 | 0.5169 | 0.3424 | F3（collisions=4 steps=7） | F2 |
| glm-5v-turbo | 1016 | 0.5474 | 0.3610 | F3（collisions=2 steps=9） | F2 |
| qwen3-vl-plus | 1013 | 0.5474 | 0.3630 | F3（collisions=0 steps=4） | F2 |

按模型计数：glm-5v-turbo 4、qwen3-vl-plus 1、deepseek-flash 0、random 0。若改用位姿累加口径（只改 F2／F3 之间，完成与 F1 不变），各家计数为：deepseek-flash F2 0／F3 29（不变）；glm-5v-turbo F2 15／F3 15（原 11／19）；qwen3-vl-plus F2 3／F3 27（原 2／28）；random F2 3／F3 27（不变）。与 (a) 动作解析对照的矛盾核对在 (a) 跑完后做（随 (a) 回执 ≤10-15 同交）。
