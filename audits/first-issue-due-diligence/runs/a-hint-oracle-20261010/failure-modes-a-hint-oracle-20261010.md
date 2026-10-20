# 失败模式三分类表 · a-hint-oracle-20261010（内部工单）

> 判据见 `tools/failure_modes.py` 文件头（预登记提交先于本表）；阈值 DISP_MIN_M=0.4、F1 占比≥0.5。逐回合明细 `failure-modes-a-hint-oracle-20261010.csv`。

| run | agent | N | 完成 | F1 解析或格式失败 | F2 未动 | F3 行进后碰撞或超步 | 位移不可得回合 | 位移交叉核对不一致 |
|---|---|---|---|---|---|---|---|---|
| a-hint-oracle-20261010 | deepseek-flash--nothink--official | 10 | 10 | 0 | 0 | 0 | 0 | 0 |
| a-hint-oracle-20261010 | glm-5v-turbo--nothink--official | 10 | 10 | 0 | 0 | 0 | 0 | 0 |
| a-hint-oracle-20261010 | qwen3-vl-plus--nothink--official | 10 | 10 | 0 | 0 | 0 | 0 | 0 |

表注：位移取 results.csv `traveled_m`（含第 0 步）；`disp_log_m` 由日志相邻位姿累加（无起点、少第 0 步），只作交叉核对；「不一致」＝两种位移对 0.40 m 阈值判断相反的回合数（有则逐回合在 csv 的 `disp_cross_check` 列可查）。位移不可得时按有效前进动作数 == 0 判 F2。
