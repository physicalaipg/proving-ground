# Course 01「看图走路」（Look-and-Go）协议 v0 · 真机段（内部工单 C；候 tag `real-v0-prereg`，≤2026-10-15）

> 本文件是真机段的冻结物（裁定 2026-10-05-06）。`protocol/v0.md` 的任务、动作、计分、提示词与仿真分规则（tag `protocol-v0-prereg`）全部沿用、一字不改；本段只定真机侧常量与程序。勘误 ⑥（CHANGELOG 2026-09-25）预留的 tag 名 `protocol-v0-real-prereg` 由令文改为 `real-v0-prereg`，同一件事。tag 后、真机跑测前不得改本段与下列冻结件；改＝v1 另期。核对：`bash tools/real_prereg_check.sh`。

## 1 冻结件（tag 时逐文件 sha256）

| 件 | 文件 | 状态（10-06） |
|---|---|---|
| L1 布局常量 | `real/course/L1.yaml`（twin 块＝种子 1017）＋ `real/course/L1-measured.yaml`（登记实测值即常量） | twin 块已定；实测件候 A3 登记照 |
| 相机实测值 | `real/config/camera.yaml` | 候 B 实测（VID:PID、高度、前移、水平视场、锁定回读） |
| 动作与回合常量 | 前进 **0.20 m**、转向 30°、线速 ≤0.20 m/s、角速 ≤60°/s、动作后静置 0.30 s、到达半径 **0.40 m**、回合上限 **80 步**（`harness/interface.py` MotionSpec、`twin/configs/course01.yaml`，与 `protocol/v0.md` §4 同一组数） | 已冻结于 `protocol-v0-prereg`；令文 C 段「步长 0.30」与之不符，CC 按协议 0.20 m 记、0.30 为静置秒数，候 CSO 认 |
| 碰撞口径（真机） | 接触＝车体外廓矩形（`L1.yaml` physical.robot.footprint）与障碍脚印膨胀 `collision_margin_m`（0.02）相交，或任一角出 2×2 边界（＝孪生的墙）；计**接触起始事件**，仿真分公式同 `protocol/v0.md` §5.1（0.1/事件、封顶 0.5、不低于 0）；判定来源＝俯拍离线计分（`real/score_overhead`），按回合日志时间对齐到步 | 代码已入，人工推车视频验证候素材 |
| 黄金用例定义 | oracle＝`real/oracle.py`：按 L1 已知坐标（登记后取实测）用孪生 A* 规划一次、开环回放、不看图不看位姿；N=10、只做一次、不进榜；用途＝校准路程比分母与可达性 | 已入 |
| 被测模型与 API 版本 | `harness/models.yaml` 首季三行：`qwen3-vl-plus--nothink--official`（model qwen3-vl-plus，dashscope compatible-mode v1）、`glm-5v-turbo--nothink--official`（model glm-5v-turbo，open.bigmodel.cn paas/v4）、`deepseek-flash--nothink--official`（model deepseek-flash，DeepSeek 官方端点）；配置即身份，改任一项＝新行 | 已冻结于 `protocol-v0-prereg` |
| N | 真机每模型 **N=10**（标 pilot；裁定 2026-09-25-04 首期 N=10） | — |
| 平台 | 旧车 **YB-EET01 V2.0，标「非参考平台」**（参考平台仍为 §2 同类差速底盘 UGV02 类；固件 `yb-eet01-json` 0.2.0，JSON 串口子集） | — |
| 提示词 | `protocol/prompt_v0.md`，sha256 同 `protocol-v0-prereg`；真机的 `{next_checkpoint}`／`{next_color}` 由离线计分事后给不出——**真机回合内进度提示由上位机按 L1 已知坐标＋车载里程计估算给出**（候 CSO 认；与仿真同一模板） | 候定 |

## 2 真机分、迁移差、保真度

- 真机分＝同一公式（§5.1）作用于俯拍离线判定的到达与接触事件；回合作废（低压／复位／自检固件，`void_reason`）不计入 N，充电或换 reset key 后补跑同回合号。
- 迁移差＝真机分 − 仿真分（同模型；仿真分取 Twin-01 种子 1017 同布局 N=10 的均值，不是首期 N=30 冻结集均值）；保真度＝各模型 |迁移差| 均值（`harness/scoring.py` `transfer_gap`／`fidelity`）。
- 榜单三列：仿真分（N=30 冻结集）｜真机分（L1，N=10，pilot）｜迁移差（L1 同布局）；真机未在 10-22 前完成则真机列标「待锚」照发（裁定 2026-10-05-04）。

## 3 门三与跑测程序（令文 E）

1. 10-16 门三＝一模型一回合全链路（停-看-想-动，固件限速、三层急停，台架通过后落地）＋俯拍离线计分 PASS（该回合的 track.csv／score.json 出得来且与人眼判定一致）。
2. 10-17～10-22 同场次：黄金用例 N=10（一次）→ 3 模型 × N=10；每回合俯拍（测量链）＋ Pocket 3（展示）。
3. 每回合前人工回位到十字标记（首季不做自动回位，裁定 2026-10-05-05）；人手小时计入 KPI。
4. 安全：固件限速、离散有界动作、三层急停（内部治理仓 `35_papers/p5-realbot/protocol/safety-protocol.md`）；低压确认读→回合作废（裁定 2026-10-02-19）。

## 4 tag 程序

A3 登记件与 B 实测件填齐 → `tests/real` 全过 → `bash tools/real_prereg_check.sh --freeze` 打印各冻结件 sha256 写入本节表下 → `git tag -a real-v0-prereg -m "真机段预注册（内部工单 C，裁定 2026-10-05-06）"` → 推私有 origin（push_gate）。此后 `bash tools/real_prereg_check.sh` 任一冻结件与 tag 不同即 rc 1。
