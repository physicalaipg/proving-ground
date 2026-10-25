# 首期尽调（first-issue due diligence）· 10-29 发布门

> 依据：裁定 2026-10-08-04（内部工单 A4／C5）：三项回执齐且 (a) 通过方可 10-29 发；正式批 `c174ad7` 的验收以 (a) 通过为前提。排序与退路：内部工单 §一（10-09）；(c) 口径：附条修订1（10-09）。
> 纪律：脚本只读调用 harness、**不改监视件**（`twin/`、`harness/`、协议规则区、提示模板、种子；`bash tools/prereg_check.sh` 前后各跑一次，须零差异）；花费计入 ≤$150/期 上限，超则停报；密钥只从项目 `.env` 读，不入仓。

## 顺序（内部工单 §一）

| 序 | 项 | 口径 | 交付 | 期限 |
|---|---|---|---|---|
| 1 | (a) 动作解析对照 | 三模型各 N=10，提示**附 oracle 下一步动作文本**；判据＝到达占比 1.000、sim 1.000，超过 greedy（0.900／0.7067），与 astar 持平→解析通路正常、低分系感知决策〔(a) 判通过 10-10，裁定 2026-10-10-04〕；仍≈random（0.010）→判 harness 缺陷 | 表 `a-action-parse.csv`＋命令与输出尾行＋结论一行「通过／harness 缺陷」 | **≤10-15 回执** |
| 2 | (b) 步数敏感性 | 80→160 步，三模型各 N=10；只记观察入 `CHANGELOG.md`，不改冻结常量（改常量＝v1，不在首期） | 表 `b-steps-160.csv`＋命令与输出尾行 | 随 (a) 同批，不阻塞 |
| 3 | (c) 内部参照 | 参照模型＝主理人既有海外多模态模型密钥可调用的最强**正式版**多模态模型一个（不用 preview、不新开账户；行名「模型ID--思考档--端点」）；与 `c174ad7` 同一 Course 01、同一冻结种子的前 10 回合 N=10，同时按 (a) 口径做动作解析对照；只内部对照、不发布不进榜不入 CSV | **不在本目录**：原始 episodes、日志与结论只入 内部治理仓 私有目录（路径不在本仓记，内部工单）；本目录与本仓全历史不得出现 (c) 文件与该密钥（凭证闸加核） | **(a) 先跑，(c) 随后**（内部工单 ⑥）：用已填密钥做 N=10 同种子参照，与 (a) 同交；对照行只写在 内部治理仓 (c) README，本仓不记 (c) 数字（内部工单），≤10-15 |

## (a) 增核三项（内部工单，2026-10-09；时限不变 ≤10-15）

起因：内部工单 中三家 VLM 完成率 0～1/30，F3 与 random 基线同级；(a) 必须能分清「模型能力」与「管线缺陷」。现行清单（上表 (a) 行）只含 oracle 动作文本对照一项，下列三项均未含、全部新增；harness 现无请求体图像元数据与渲染帧 sha256 的落盘（`grep -rn sha256 harness/` 零命中），① 须由 (a) 脚本在调用侧记录。

| 项 | 做法 | 交付 |
|---|---|---|
| ① 图像送达 | 每家抽 3 回合，记录请求体中图像的尺寸、字节数、编码，并核对是否与该步渲染帧的 sha256 一致；**只记元数据**，请求中的密钥与头信息不落盘、不进回执 | 表 `a1-image-delivery.csv`（模型｜seed｜step｜宽×高｜字节数｜编码｜帧 sha256 前 12 位｜一致／不一致） |
| ② 动作映射 | 每家抽 5 个 F3 回合（取自内部工单 csv），逐步对照「模型输出原文 → 解析出的动作 → 实际执行的动作」，列出任何不一致 | 表 `a2-action-mapping.csv`＋不一致清单（无则写 0） |
| ③ 判据与步长 | 报单步位移分布及其与 0.40 m 的比值（`forward_m`＝0.20 m，阈值＝两步；两口径差见内部工单脚注）；glm 的 11 个 F2 回合抽 3 个看原始输出，判定是模型拒动还是被解析成空动作 | 分布表 `a3-step-displacement.csv`＋3 回合判定各一行 |

判为缺陷即按内部工单走 v1 重跑，≤10-24。

## (a) 增核续三项（内部工单，2026-10-09；时限不变 ≤10-15）

| 项 | 做法 | 交付 |
|---|---|---|
| ④ 位移口径偏差 | 查明 `traveled_m` 是否把碰撞当步「指令未兑现」的位移也计入；扩到全部 F3 回合，统计两口径差值的分布（均值、众数、是否集中在 ≈0.20 m）。**结论写进 (a)，口径是否属缺陷由审定方判，回执不自判**。维护者 10-09 预查事实见下，会话二可直接引用并复核 | `a4-displacement-measures.csv`（模型｜seed｜cls｜traveled_m｜disp_log_m｜差值｜第 0 步动作）＋分布一段 |
| ⑤ 记录位置 | ① 的图像元数据与 ④ 所需数据**只在 (a) 脚本的调用侧记录，不改 harness 监视区**；若必须改监视区才能记录，先停工报审定方 | 回执注明记录点（脚本文件与函数） |
| ⑥ 会话二排序 | (a) 先跑；(c) 随后用已填密钥做 N=10 同种子参照，只入 内部治理仓 私有目录（路径不在本仓记），与 (a) 同交；对照行只写在 内部治理仓 (c) README（内部工单） | 顺序表第 3 行已改 |

### ④ 预查事实（维护者 10-09，只读；c174ad7 run 与 random 基线共 120 回合；不判缺陷）

- 读码：`harness/scoring.py` 的 `_last` 在 `__post_init__` 初始化为 `start`；`update()` 每步以动作后实际位姿 `res.pose` 与上一位姿的欧氏距离累加 `traveled_m`（第 74 行）；`res.collided` 只计 `collisions`／事件，不参与位移。即 **`traveled_m`＝动作后实际位姿增量之和（含第 0 步 start→首位姿），不含指令量**。日志 `pose` 为动作后位姿、无 start，故 `disp_log_m` 恰少第 0 步的实际位移。
- 差值＝第 0 步实际位移（120 回合按第 0 步动作分桶）：forward→0.18–0.20 m 54 回合；forward→0～0.18 m 之间 10 回合（第 0 步即碰撞或未完全兑现）〔**10-09 勘误（内部工单预查）**：这 10 回合第 0 步 `collided` 均为 False，位移 0.1706～0.1785 m，落在打滑系数 0.90–1.00×0.20 m 与 3% 噪声范围内；**120 回合中第 0 步碰撞的回合数＝0**；原句保留〕；left 39、right 16、stop 1 回合→≈0。5 个争议回合第 0 步均为 forward（差 0.1745～0.1864）。
- 全部 F3 回合（103）两口径差值：均值 0.1115、中位 0.1805；0.01 m 分箱众数 0.00（41 回合）、次 0.18（32）、0.19（24）；落在 [0.18,0.20] 52 回合、＝0 40 回合、两者之间 11 回合——**双峰（0 与≈0.19），不是单一 ≈0.20**。分家：deepseek 均值 0.1271／中位 0.1824，glm 0.0779／0.0，qwen 0.0995／0.1785，random 0.1309／0.1825。
- 碰撞步实际位移（第 1 步起，按动作×是否碰撞；n／均值／中位／最大，m）：forward 未碰 626／0.1871／0.1864／0.2083；forward 碰撞 1796／0.0375／0.0225／0.1956；left 未碰 1554／0.0000／0.0000／0.0002；left 碰撞 559／0.0178／0.0163／0.0484；right 未碰 685／0.0000／0.0000／0.0004；right 碰撞 306／0.0174／0.0155／0.0424；stop 71／0。即**碰撞步只计兑现位移，指令未兑现部分不计入 `traveled_m`**。
- 顺带（③ 预查）：未碰撞前进步实际位移均值 0.1871 m（名义 `forward_m` 0.20），与 0.40 m 之比 ≈0.47。

## (a) 增核续四项（内部工单，2026-10-09；⑦⑨⑩ 并入 (a) 清单尾部、与 (a) 同交、不挤占 ≤10-15；⑧ 在 (a) 交付后、v1 开跑前独立提交）

| 项 | 做法 | 交付 |
|---|---|---|
| ⑦ 定义引文 | 引 tag `protocol-v0-prereg` 中 traveled_m 及一切位移类指标的定义原文：文件路径＋行号＋tag hash；未定义写「未定义」；**只引不判**。维护者预查引文见下 | 引文表入 (a) 回执 |
| ⑧ 日志补起点（＋registry oracle 改报错同批，内部工单段一） | harness 日志在第 0 步动作前写入起点位姿；**不动 `scoring.py` 计分逻辑**；改后跑 1 回合冒烟：位姿累加与 traveled_m 差 <1e-6，结果入回执；须在 v1（≤10-24）前合入；合入时在本页写一行「日志补起点、计分未变」；既有日志不回填。纪律：`harness/` 属监视件，改动须在 `CHANGELOG.md` 登记为「不改数字的代码改动」并过 `prereg_check.sh`（三基线逐位一致）。**本轮（10-09）未动 harness** | 独立提交＋冒烟结果 |
| ⑨ 步长兑现 | 未碰前进步实际位移的分布（均值、P10/P50/P90、按模型分列）；逐条核 ③ 判据与成功条件，回报是否有阈值按名义 0.20 m 推算，有则列出；只记不改。维护者预查见下 | 表 `a9-step-realization.csv`＋阈值清单 |
| ⑩ 首步碰撞 | 列第 0 步碰撞回合（种子、模型、出生点沿朝向到最近障碍的距离、是否 <0.20 m）；统计全部种子出生间隙 <0.20 m 的个数；只记不判、不换种子。维护者预查见下 | 表 `a10-spawn-gap.csv` |

### ⑦ 预查引文（tag `protocol-v0-prereg`＝tag 对象 `cb3efd364cb74ae2186fdd56f8dd08a1a09ca119`→提交 `cd63010d55ca150a8c67667d45c1a9cf96f5a063`，2026-09-25；行号为该提交内行号；只引不判）

- `protocol/v0.md` L25：「动作步长（孪生与真机固件同一组数）：forward **0.20 m**；left／right **30°**；线速上限 0.20 m/s；角速上限 60°/s；动作后静置 0.30 s。」
- `protocol/v0.md` L32：「| 到达半径 | **0.40 m** | 中心入圈即到达；真机俯拍同值。下限＝步长 0.20＋车身半长 0.126＋柱半径 0.03 ≈ 0.36，0.30 时直行接近必撞柱 |」
- `protocol/v0.md` L37：「| **路程比** | 实际轨迹长 ÷ 理想路径长 | 理想路径＝折线 start→c1→…→c5 各段长之和，**每段扣除一个到达半径**（入圈即算到达，不必走到柱心）；只对成功回合汇总；**不进仿真分** |」；L81：「路程比不进仿真分：分母＝理想路径长（折线扣到达半径），样本＝成功回合，另列。」
- `protocol/v0.md` L107：「**可解性判定**：每个种子在标称条件（无打滑、无噪声）下由 A* 顺序规划 5 段；任一段无解、或总步数 > 80，即判**不可解并剔除**。」
- **traveled_m 本身：协议正文未定义**（仅 L37「实际轨迹长」一词，未写计算法）。代码定义：`harness/scoring.py` L13（docstring「path_ratio = 实际轨迹长 ÷ 理想路径长」）、L37（字段 `traveled_m: float = 0.0`）、L45–46（`_last` 初值＝start）、L69（`self.traveled_m += math.hypot(p[0] - self._last[0], p[1] - self._last[1])`，p＝动作后实际位姿）、L110–112（`ideal_path_m`＝折线各段长−到达半径之和）、L115–116（`path_ratio = traveled_m / max(ideal_path_m, 1e-6)`）、L127–129（summary 四位小数输出）；`harness/run_batch.py` L39（results.csv 列 `traveled_m`、`ideal_path_m`、`path_ratio`）；`harness/interface.py` L48–49（`forward_m: float = 0.20`、`turn_deg: float = 30.0`）；`twin/configs/course01.yaml` L9（`reach_radius_m: 0.40` 及「必须 > 步长＋车身半长＋柱半径（0.20＋0.126＋0.03≈0.36）」）、L36（`forward_m: 0.20`）、L50（`slip: [0.90, 1.00]`「实际位移＝指令位移×slip」）、L51（`motion_noise_pct: 3`）、L53（`max_steps: 80`「无障碍理想路径≈26 步直行＋≈15 步转向」）。
- tag 之外：F2 阈值 `DISP_MIN_M`＝0.40 出自 内部工单 预登记（pg `0fb6e5e`，2026-10-09），文件头写「= 到达半径常量 0.40 m」。

### ⑨ 预查（10-09；未碰前进步实际位移，第 1 步起按日志相邻位姿；单位 m）

| 模型 | n | 均值 | P10 | P50 | P90 | min | max | 均值/0.40 |
|---|---|---|---|---|---|---|---|---|
| deepseek-flash | 251 | 0.1870 | 0.1765 | 0.1864 | 0.1983 | 0.1686 | 0.2063 | 0.467 |
| glm-5v-turbo | 57 | 0.1877 | 0.1785 | 0.1864 | 0.1983 | 0.1726 | 0.2083 | 0.469 |
| qwen3-vl-plus | 197 | 0.1866 | 0.1765 | 0.1864 | 0.1983 | 0.1686 | 0.2063 | 0.466 |
| random | 121 | 0.1877 | 0.1785 | 0.1864 | 0.1964 | 0.1706 | 0.2083 | 0.469 |
| 合计 | 626 | 0.1871 | 0.1765 | 0.1864 | 0.1983 | 0.1686 | 0.2083 | 0.468 |

第 0 步（起点由种子重算）未碰前进 64 回合：均值 0.1855、P10 0.1785、P50 0.1845、P90 0.1937。与配置 slip [0.90, 1.00]×0.20＝0.18–0.20、噪声 3%（1σ）一致。

阈值与成功条件逐条（是否按名义 0.20 m 推算；只记不改）：
1. 到达半径 0.40 m（配置 L9、协议 L32）——**是**：下限「步长 0.20＋车身半长 0.126＋柱半径 0.03≈0.36」按名义步长推算。
2. 成功＝5 个检查点按序全到达（协议 L11）——间接：依赖到达半径。
3. 回合上限 80 步（配置 L53、协议 L33）——**是**：注释「无障碍理想路径≈26 步直行」按 0.20 m/步折算。
4. 可解性剔除（协议 L107；`twin/planner.py` L116–133 标称运动学 `self.d = forward_m`、前进扫掠半长含 forward_m）——**是**：A* 以名义 0.20 m 步、无打滑无噪声搜索，总步数 >80 剔除（seed 1019 因此剔除）。
5. 规划安全余量 `MARGIN_M` 0.02（`twin/planner.py` L27 注「0.2 m×3% 噪声≈6 mm/步」）——**是**（名义步长×噪声）。
6. F2 阈值 `DISP_MIN_M` 0.40（内部工单，非 tag）——写法＝到达半径常量；数值上＝2×名义步长。
7. 路程比（协议 L37）——否：分母几何折线长，不含步长；分子 traveled_m 为实际位移。
8. 仿真分 v2＝到达占比−min(0.1×接触事件数, 0.5)（协议 L92）——否：不含位移阈值。
备注：`scoring.py` L32 默认 `reach_radius_m = 0.30` 未被使用，运行时由配置 0.40 传入（`run_batch.py` L264 `load_task(cfg["motion"], cfg["checkpoints"]["reach_radius_m"], …)`）。

### ⑩ 预查（10-09；只记不判，不换种子）

- **第 0 步碰撞回合数＝0**（120 回合逐条核首记录 `collided`）。内部工单所称「第 0 步碰撞的 10 回合」所据为 ④ 预查原句误写（见 ④ 勘误）：这 10 回合第 0 步前进、无碰撞、位移 0.1706–0.1785 m——种子 1015（deepseek、glm）、1025（deepseek）、1027（deepseek、glm、qwen、random）、1028（deepseek、qwen、random）。
- 起点可由种子重算：`twin.arena.sample_layout(cfg, seed).start`（布局流 `random.Random(seed)` 只依赖种子，L30）；120 回合 |起点→首位姿距离 − (traveled_m − disp_log_m)| 最大 0.0001（＝CSV 四位小数舍入），差值即第 0 步实际位移，逐回合吻合。
- 出生间隙（两种定义：A＝车身矩形沿朝向直行至首次接触墙／障碍／立柱的距离，`World.rect_free` 余量 0、步进 1 mm；B＝中心点沿朝向射线到最近物体表面的距离，`World.point_clearance` r＝0）：`seeds.csv` 32 个种子（含剔除 1005、1019）A 最小 0.246（seed 1008；次 0.284 seed 1000）、中位 0.7255、最大 2.07；B 最小 0.447（seed 1031）。**<0.20 m：A 0 个、B 0 个**。5 个争议回合种子：1006 A 0.473／B 1.903，1013 0.700／0.878，1015 0.405／1.949，1016 1.449／2.238。
- 配置使然：障碍距起点 ≥ clearance_m 0.40＋0.10、检查点距起点 ≥0.60、起点抖动后外接圆离墙 ≥0.03（`twin/arena.py` L38–43、L54、L72）。

### ⑧ 既有日志的公开计划（事实，候审定方定；本轮未动 harness）

- runs/ 下逐步日志由 `.gitignore` L7–9（`episodes/runs/*/logs/`、`*.jsonl`）排除，现仓内未跟踪、不随仓公开；`.gitignore` L10–11 例外 `!episodes/editions/**/*.jsonl`，runbook §1 T+12～+20h「复制逐步日志到 `editions/<期>/logs/`」与 §6「完整逐步日志已复制到 `editions/<期>/logs/`（jsonl 入仓）」、兜底段「完整日志与未剪辑视频随发」——即首期计划把 `runs.csv` 所引 sim_run 的逐步日志复制入 `episodes/editions/2026-10-21-pilot01/logs/` 入仓公开。现 `runs.csv` sim_run 列空（待填 c174ad7 run `2026-09-25-pilot01`，三模型各 30 回合＝90 份 jsonl）；baselines（astar／greedy／random）不在 `runs.csv`，是否随发未写明；该目录现仅 `.gitkeep`。这些既有日志均无起点行，起点可由种子＋配置重算（见 ⑩）。

## (a) 增核续两项（内部工单，2026-10-09；⑫ 规则先提交、⑪ 后跑，二者并入 (a) 同交 ≤10-15；⑬ 随 ⑧ 在 (a) 交付后、v1 前提交）

### ⑫ 阈值处置规则（先定规则后跑；本节提交须早于 ⑪ 的结果提交，回执报两个 commit hash 及先后顺序；规则原文照录）

- oracle 30/30 → 四处阈值全不动；README 记一句「名义步长 0.20、实兑均值 0.187，阈值经 oracle 验证可解」。
- oracle ＜30/30 → 半径 0.40、余量 0.02 不动；步上限统一改为 91（＝ceil(80×0.20/0.1765)，按实兑 P10 折算原设计射程），在 v1 生效，所有模型与基线同跑；改后 oracle 复跑须 30/30，仍不足报审定方，不得再调参、不换种子（N=30 预注册）。
- 任何改动记为偏差，写入 (a) README 偏差记录。

（四处阈值＝⑨ 清单第 1、3、4、5 项：到达半径 0.40、回合上限 80 步、A* 可解性剔除、规划余量 0.02。）

### ⑪ astar 基线（令文称 oracle；内部工单段一 5 起列名只用 `astar`，oracle 作废为列名；规则提交后执行，结果另节追加）

- 口径：对首期 N=30 种子逐一执行，A* 规划，每步按实际位姿重规划；动作空间、slip＋噪声、80 步上限、到达半径 0.40、规划余量 0.02 全部与模型同；噪声种子与对应模型回合一致。回报：完成数/30、未完成种子清单及失败原因（超步／碰撞）、A* 路径长、实际用步数。astar 与 greedy、random 同为三条脚本基线，与附真值提示行（(a) 批）同在站点『基线与天花板（读真值·非视觉）』单列，不进模型榜（裁定 2026-10-10-06：「三条脚本基线＋附真值提示行」，只落本页与站点列，协议冻结物不动）（协议 §6「三者成本 0、不进榜单」句，现行 L108；内部工单 第 2 条措辞），日志入 editions。
- 三列注（内部工单段一 2；措辞按 harness 实际能力，`harness/agents/scripted.py`）：**astar＝上限参照**——已知地图 A*，读真值布局、位姿与该回合打滑系数，全知规划（协议「天花板基准」行）；**greedy＝启发式基线**——真值贪心导航，读位姿与下一检查点，朝目标转向、对准即前进、不避障（协议「基线」行，内部工单原 oracle 内部工单降为基线）；**random＝下限**——不看图不读真值，forward:left:right＝2:1:1、每步 1% stop（协议「基线（下界）」行）。三者成本 0；协议 tag 版 L105／现行 L108「三者成本 0、不进榜单，站点单列「基线与天花板（读真值·非视觉）」；榜单只列模型」。

### ⑪ 结果（维护者 2026-10-09 21:11:19–21:11:24 −0700，在规则提交 `41c9680`（21:10:35 −0700）之后；run `episodes/runs/2026-10-09-oracle-patch5/`）

- 命令：`.venv/bin/python -m harness.run_batch --agents astar --n 30 --seed0 1000 --out episodes/runs/2026-10-09-oracle-patch5 --frames 0` → 尾行「astar n= 30 sim_score=1.000±0.000 success=1.00 cp=5.00 coll_steps=0.0 coll_events=0.0 total(old)=5.00 path_ratio=1.2725 usd/episode=0.0」；wall 4.7 s；usd 0；rejection_rate 0.0625（筛 32 取 30，剔 1005、1019，与 09-25 同）。
- 代理＝现有 `astar`（`harness/agents/scripted.py` L71–144）：每步读实际位姿，以 VALIDATE_MARGIN 0.01 校核余下计划，失效即按 MARGIN 0.02 重规划（兜底余量 0）；动作空间、slip（按布局种子）、噪声（`twin/robot_twin.py` L59 `random.Random(seed*104729+7)`，按回合种子初始化、与模型回合一致）、80 步上限、到达半径 0.40 全同模型；配置 sha256 `7fcf28e7…` 同正式批。实际机制＝每步校核、失效重规划（审定方 10-09 认可，裁定 2026-10-09-11 ①：oracle 只须证可解，与 09-25 预注册基线 0 差异优先于令文措辞；不复跑、不记偏差）。
- **完成数 30/30；未完成种子：无；碰撞步 0**。实际用步 19–74（均 36.87；最大 seed 1012 用 74/80）；名义 A* 计划步（`seeds.csv` astar_steps）18–56（均 34.6）；重规划合计 191 次；理想路径长均 2.64 m、实际轨迹长均 3.29 m（path_ratio 1.2725）。与 09-25 基线 run `2026-09-25-pilot01-baselines` 的 astar 30 行逐字段（success／checkpoints_reached／collisions／traveled_m／ideal_path_m／steps／path_ratio／sim_score）0 处差异；`bash tools/prereg_check.sh` → 「✔ …三基线逐位一致」rc 0。
- 逐种子：

| seed | 名义 A* 计划步（legs） | 理想路径 m | 实际用步 | 实际轨迹 m | 碰撞步 | 重规划 |
|---|---|---|---|---|---|---|
| 1000 | 33（4/7/6/12/4） | 2.4269 | 33 | 3.3164 | 0 | 5 |
| 1001 | 27（6/5/5/3/8） | 2.2168 | 21 | 2.1798 | 0 | 7 |
| 1002 | 32（4/3/8/9/8） | 2.2351 | 27 | 2.3901 | 0 | 5 |
| 1003 | 34（4/2/8/10/10） | 2.6959 | 33 | 3.2945 | 0 | 5 |
| 1004 | 35（6/7/7/7/8） | 2.862 | 39 | 3.6575 | 0 | 6 |
| 1006 | 50（9/5/13/14/9） | 3.2692 | 49 | 3.9174 | 0 | 5 |
| 1007 | 34（11/6/8/4/5） | 2.6509 | 35 | 3.3679 | 0 | 5 |
| 1008 | 37（11/7/14/0/5） | 2.5394 | 33 | 3.3402 | 0 | 4 |
| 1009 | 23（7/4/7/5/0） | 2.4852 | 21 | 2.039 | 0 | 4 |
| 1010 | 20（3/4/9/0/4） | 1.922 | 19 | 1.8268 | 0 | 4 |
| 1011 | 28（7/5/5/8/3） | 2.532 | 25 | 2.164 | 0 | 5 |
| 1012 | 56（36/0/3/7/10） | 3.2861 | 74 | 4.1078 | 0 | 18 |
| 1013 | 44（9/12/8/10/5） | 2.4014 | 49 | 5.2562 | 0 | 8 |
| 1014 | 45（9/4/7/16/9） | 3.5928 | 47 | 4.078 | 0 | 7 |
| 1015 | 33（11/0/8/7/7） | 2.3236 | 26 | 2.3385 | 0 | 4 |
| 1016 | 18（5/1/4/8/0） | 1.8349 | 20 | 2.0112 | 0 | 4 |
| 1017 | 34（7/10/6/8/3） | 2.8875 | 48 | 4.2902 | 0 | 6 |
| 1018 | 50（10/5/12/13/10） | 3.5682 | 61 | 4.7841 | 0 | 8 |
| 1020 | 31（6/6/5/14/0） | 2.657 | 29 | 2.6698 | 0 | 5 |
| 1021 | 35（4/6/5/16/4） | 1.6346 | 31 | 3.8063 | 0 | 7 |
| 1022 | 35（6/7/8/4/10） | 3.0312 | 31 | 2.7947 | 0 | 7 |
| 1023 | 20（4/4/7/0/5） | 1.8881 | 19 | 1.9874 | 0 | 5 |
| 1024 | 50（13/9/7/12/9） | 3.7156 | 51 | 4.7127 | 0 | 6 |
| 1025 | 18（6/0/6/5/1） | 1.7193 | 24 | 2.5111 | 0 | 4 |
| 1026 | 32（8/4/5/3/12） | 2.7755 | 27 | 2.5745 | 0 | 5 |
| 1027 | 40（9/10/7/8/6） | 3.6916 | 43 | 4.0086 | 0 | 6 |
| 1028 | 38（7/0/12/10/9） | 3.0862 | 46 | 3.7289 | 0 | 8 |
| 1029 | 39（7/7/6/14/5） | 2.8228 | 38 | 3.4988 | 0 | 8 |
| 1030 | 32（4/17/0/10/1） | 1.8381 | 65 | 4.6552 | 0 | 13 |
| 1031 | 35（11/11/0/8/5） | 2.6181 | 42 | 3.4334 | 0 | 7 |

- **⑫ 适用第一支（astar〔原记 oracle〕30/30）：四处阈值全不动。名义步长 0.20、实兑均值 0.187，阈值经 oracle 验证可解。** 偏差记录：无新增。

### ⑭ v1 回归门（内部工单，2026-10-09；**已随 ⑧ 结 10-10**：astar 对 d4af9ae／greedy 对 tag 基线 0 差异〔pg `760ab56`〕，门句已写进 runbook §6「v1 正式批与回归门」项）

- 规则原文（内部工单）：「v1 的 astar 与 oracle 两列须与 pg d4af9ae 逐字段 0 差异（日志新增起点行除外）；任一字段不符即停跑报审定方，视为 ⑧ 越界。回执附 diff 命令与输出尾行。」**内部工单段一 5 改为：「v1 的 astar 列与 d4af9ae 的 astar 结果（原记 oracle）逐字段 0 差异」**，其余不变。
- 比对对象：d4af9ae 的 `episodes/runs/2026-10-09-oracle-patch5/results.csv` astar 30 行（与 09-25 基线 astar 行逐字段相同）。命名注意：⑪ 的 oracle 列＝`astar` 代理所跑；`harness/agents/registry.py` L12 里字串 `oracle` 是 greedy 的旧别名（内部工单 回执用语），v1 跑批与榜单列名用 `astar`、不用 `oracle`，免歧义。
- 命令（10-09 对 d4af9ae 自比自测：results 0 差异 rc 0；日志 30 份 0 不符）：
  - results（字段 1–15＝agent…steps，排除成本／延迟／wall 列）：`diff <(git show d4af9ae:episodes/runs/2026-10-09-oracle-patch5/results.csv | cut -d, -f1-15) <(grep -E '^(agent|astar)' episodes/runs/<v1-run>/results.csv | cut -d, -f1-15)`，输出为空且 rc 0 ＝过门。
  - 日志（起点行除外，比 step／action／decision_valid／collided／pose／reached／next_checkpoint）：对每个 seed，`python3 -c` 读两份 jsonl、跳过无 action 的起点行、逐键比较；不符数须为 0。
- 任一不符：停跑、报审定方、记为 ⑧ 越界（偏差记录一行）。
- greedy 列（内部工单第 1 条，取代内部工单段一 3 所加「greedy 无 d4af9ae 锚、v1 结果即首锚」句；含内部工单段一步 3）：v1 greedy 列对 tag 内 `2026-09-25-pilot01-baselines` 的 greedy 回放结果（30 行，种子 1000–1031 去 1005、1019）逐字段 0 差异；astar 门对 d4af9ae 不变。

### ⑬ runbook §6 补一行（**已落 10-10**：runbook §6 加「v1 正式批与回归门」一项含跑前自检与 ⑭；站点文案＝`editions/2026-10-21-pilot01/notes.md` 首期讲法五句／真机列待锚（第二期）／征集文案／基线与天花板列＋附真值提示行／判据脚注、`site/i18n/ui.json` pending／board.sub／board.empty／baseline.sub、`editions.csv` 文案字段、`runs.csv` note；零数字零代码，`build_site.py` 重生成 site/data）

- v1 定义（内部工单段一 1，取代 裁定 2026-10-09-11 ②「三模型各 30＋baselines」的泛称）：**三模型各 30＋random／greedy／astar 三条脚本基线＋附真值提示行（(a) 批，不新跑；裁定 2026-10-10-06）（同在站点『基线与天花板（读真值·非视觉）』单列，不进模型榜；协议 §6 该句现行 L108；措辞依内部工单第 2 条）**；greedy 零成本、确定性，不占 150 美元上限。步 0 核：协议 greedy 行（tag 版 L101＝现行 L104，逐字同）「| greedy | 基线 | **是（非视觉）** | 贪心真值导航：朝下一检查点转向、对准即前进，不避障（内部工单原 oracle，内部工单降为基线）；成本 0 |」，「性质」列＝基线，prereg 一致。注意协议同节「三者成本 0、不进榜单，站点单列『基线与天花板（读真值·非视觉）』；榜单只列模型」——「榜单列」读作站点该单列，候审定方认。
- 入 runbook 时并加一行跑前自检（内部工单段一 3）：「跑批前核 `--agents` 列表，含 `oracle` 即中止；基线写 astar,greedy,random」。
- 「editions/<期>/logs/ 收 v1 全部模型与 baselines（random、greedy、astar）逐步日志」（原文 random、oracle，内部工单段一 5 改 astar，内部工单段一 1 加 greedy；裁定 2026-10-09-09 ③：首期公开日志一律取 v1，v1 前日志不入 editions、不回填）。

### 段二 · greedy 预注册基线数据（内部工单第 3 条，2026-10-10：内部工单段二「greedy 参考跑」**作废、不跑**；改为从 tag 内 pilot01-baselines 的 greedy 30 行读出完成数／到达占比／sim 分，与内部工单三模型＋random 并排一表，标「预注册基线数据，非新跑」）

| 行 | N | 完成数 | 到达占比 | sim 分均值 | 接触事件/回合 | 来源 |
|---|---|---|---|---|---|---|
| astar | 30 | 30 | 1.0000 | 1.0000 | 0.00 | tag `protocol-v0-prereg`（cd63010）内 `2026-09-25-pilot01-baselines/results.csv`——**预注册基线数据，非新跑** |
| greedy | 30 | 26 | 0.9000 | 0.7067 | 2.07 | tag `protocol-v0-prereg`（cd63010）内 `2026-09-25-pilot01-baselines/results.csv`——**预注册基线数据，非新跑** |
| random | 30 | 0 | 0.0867 | 0.0100 | 5.03 | tag `protocol-v0-prereg`（cd63010）内 `2026-09-25-pilot01-baselines/results.csv`——**预注册基线数据，非新跑** |
| qwen3-vl-plus | 30 | 0 | 0.2267 | 0.0767 | 2.90 | c174ad7 正式批 `2026-09-25-pilot01/results.csv`（内部工单 同批） |
| glm-5v-turbo | 30 | 0 | 0.0067 | 0.0067 | 0.40 | c174ad7 正式批 `2026-09-25-pilot01/results.csv`（内部工单 同批） |
| deepseek-flash | 30 | 1 | 0.2733 | 0.0667 | 5.73 | c174ad7 正式批 `2026-09-25-pilot01/results.csv`（内部工单 同批） |

- 读法：到达占比＝到达检查点数÷5 的均值；greedy 完成 26/30、到达占比 0.900、sim 0.7067（(a) 判据「greedy 0.707 量级」指此 sim 分；到达占比口径为 0.900）；三模型行与 random 行同为 N=30、同冻结种子集。命令：`git show protocol-v0-prereg:episodes/runs/2026-09-25-pilot01-baselines/results.csv`（greedy 30 行、1005／1019 不在）＋ `episodes/runs/2026-09-25-pilot01/results.csv`，按 agent 汇总（会话二 10-10，脚本内联 python，尾行同本表）。
- 〔作废（内部工单第 3 条），留此备查〕原做法：`run_batch --agents greedy --n 30 --seed0 1000 --frames 0 --out episodes/runs/<日期>-greedy-ref`（目录名含 greedy、不含 oracle），只作 10-15／16 定首期讲法的参考；不改任何代码。既有事实：09-25 基线批 `2026-09-25-pilot01-baselines` 已有 greedy 30 行（sim_score 0.7067、到达占比 0.900、接触事件/回合 2.1），greedy 确定性，复跑应逐字段同。

### 段一 · oracle 命名普查（内部工单，2026-10-09；只报不改）

- **步 0 核：`harness/agents/registry.py` 在 prereg 监视表内**（`tools/prereg_check.sh` L8／L48–49：监视表＝twin/ 与 harness/ 全部跟踪文件 ∪ 新文件 ∪ 规则文本）→ 按令文**停、不改、报审定方**；步 1（oracle 改报错＋测试）与步 4（改后回归）未做。**已裁（内部工单段一，10-09）：不单独提交，并入 ⑧ 批次——(a) 之后、v1 之前，与 ⑧ 起点行同批走「不改数字的代码改动」：`CHANGELOG.md` 一条合并登记（⑧＋registry）＋`prereg_check.sh` 三基线逐位一致＋⑭ 命令对 d4af9ae 比对 0 差异，一次回归覆盖两项。过渡（即日起至 ⑧ 落地）：(a) 与 ⑬ runbook 的跑批命令显式写 `--agents astar`，禁用 `oracle` 字串；⑬ 入 runbook 时加一行跑前自检「agents 列表含 oracle 即中止」。** 改法（**已执行 10-10，见下节「⑧ 批次 D1／D2」**；原拟）：`is_scripted` 去掉 `or name == "oracle"`；`make_agent` 对 `"oracle"` 抛 `SystemExit("oracle 已作废为列名：天花板用 astar，贪心真值用 greedy")`；`run_batch` L220 未知名提示同句；测试 `tests/test_registry_oracle.py`：`run_batch --agents oracle` 非零退出。
- 步 2 别名普查（`registry.py` 全文 45 行）：显式名＝`astar`／`greedy`／`random`（`SCRIPTED`，L12）＋ `models.yaml` 行名（配置即身份，L19–23）；别名**仅一个**＝`oracle`→`GreedyAgent`（L16、L33，注释称「greedy 的旧名别名（内部工单回执用语）」）。名不副实者：`oracle` 本身（天花板应为 astar）。另两处同词异义（只报）：pg `real/oracle.py`＝内部工单黄金用例的真机开环 A* 回放脚本（「oracle 小样」）；协议 L104 greedy 行注「内部工单原 oracle，内部工单降为基线」。
- 步 3 历史普查（pg 全仓＋内部治理仓，含 `git log --all -S`）：
  | 位置 | 记名 | 实为 | 判定 |
  |---|---|---|---|
  | pg `episodes/runs/2026-09-25-pipeline/`（meta／results／summary 三件入库，`e157caa` 2026-09-24，oracle＋random×100，oracle success 0.76） | `oracle`（model_id `scripted/oracle`） | 内部工单 v0 贪心真值导航＝今 `greedy`（内部工单 `7c6ba49` 改名） | **实为 greedy、记为 oracle**——结果文件不删不改，站点不引用（build_site 只引 pilot01） |
  | pg `episodes/runs/2026-10-09-oracle-patch5/`（本页 ⑪） | 目录名 `oracle`；results 行 `agent=astar` | astar | 目录名沿令文用语、数据列名正确，不改 |
  | 内部治理仓 `00_portfolio/orders/内部工单-receipt.md` L10「流水线验证批 oracle＋random×N=100」 | oracle | greedy（同上批） | 回执原文不改，本条注记 |
  | 内部治理仓 `内部工单-order.md` L53／L56「规划器 oracle」「两 oracle 基线」、`内部工单-order.md` L14 | oracle | astar（规划器）／astar＋greedy | 令文原件不改 |
  | 内部治理仓 `内部工单-order.md` L24、`内部工单-receipt.md` §E、`内部工单-*`、`内部工单-patch1-receipt.md`、`35_papers/p5-realbot/cards/sprint-h0b-h2.md` L409「oracle 小样」 | oracle | 真机黄金用例脚本 `real/oracle.py`（非 greedy） | 同词异义，只报 |
  `--agents oracle` 字串：pg 工作树与全历史（`git log --all -S"--agents oracle"`）0 命中；内部治理仓 0 命中。
- 步 5 口径落字：本页 ⑪ 标题、⑫ 适用句、⑬、⑭ 已改列名为 astar（原记 oracle 以括注保留）；裁定 2026-10-09-09 加注「文中 oracle＝astar 代理；四阈值依据不变」在 内部治理仓内部记录。

### ⑧ 批次 D1 调用点普查＋D2 registry 失败关闭（会话一 2026-10-10；内部工单 验收块 D；起点 pg `18599d2`／内部治理仓 `752fe3f`；本节只记事实）

- **D1 普查**（`git grep -n -i -e hint -e oracle -e AStarAgent`，全仓跟踪文件；清单按 ⑧ 节注记①）：
  | 词 | 命中处 | 性质 | 处置 |
  |---|---|---|---|
  | hint | 仅 `audits/first-issue-due-diligence/a_action_parse.py`（`HintedAgent`、`--hint`、`HINT_TPL`） | 调用侧诊断脚本，监视区外 | `--hint` 由「默认 oracle」改 **required**（无默认，必须显式 `oracle`／`none`）；`harness/`、`twin/`、`tools/`、`docs/` 零 hint 代码与参数 |
  | oracle（代理名） | `harness/agents/registry.py` L12／L16／L33（greedy 旧别名） | 监视区内、回落点 | **关死**：`is_scripted("oracle")`→False；`make_agent`／`run_batch` 传 `oracle` → `SystemExit("oracle 已作废为列名：天花板用 astar，贪心真值用 greedy")` |
  | oracle（显示映射） | `site/app.js` L118 `oracle: 1`、`site/i18n/ui.json` `kind.oracle`「基线（旧名 oracle＝贪心）」 | 旧数据标签；`site/data/` 现无 oracle 行 | 非调用点，不改；旧批 `episodes/runs/2026-09-25-pipeline/` 处置归 内部工单（NOTE.md） |
  | oracle（注释／文档） | `harness/agents/scripted.py` L4／L6／L108、`harness/interface.py` L9、`twin/planner.py` L4–5、`protocol/v0.md` 基线表 greedy 行、`protocol/i18n/*`、`protocol/v0.en.md` | 历史措辞，非代理名调用 | 不改（协议冻结物；注释非行为） |
  | oracle（真机黄金用例） | `real/oracle.py`、`tests/real/test_pg002_b_e.py`、`tools/real_prereg_check.sh`、`protocol/real-v0.md` | 同词异义（开环回放脚本） | 不改 |
  | AStarAgent | `harness/agents/{__init__,registry,scripted}.py`、`twin/selftest.py`、`a_action_parse.py` L38／L119／L129（算提示） | 天花板代理本体与自检 | 不改 |
  | 环境变量／配置开关 | `harness/` 内 `os.environ` 仅 `.env` 载入与 `key_env` 读密钥（`run_batch.py` L61–62／L239、`llm.py` L36）；`twin/configs/course01.yaml` 无 hint／oracle 键 | 无可打开提示的开关 | 无需关 |
- **v1 跑批路径**：`python -m harness.run_batch --agents <三行>,astar,greedy,random …` 无 `--hint` 参数、不导入 `a_action_parse.py`，`HintedAgent` 只存在于该诊断脚本；`--agents` 含 `oracle` 即在种子筛选前退出（rc≠0）。
- **D2 registry**（改法＝段一「原拟」，执行同句）：`harness/agents/registry.py` 新增 `reject_unknown`（未登记名／`oracle` → `SystemExit`，原未知名为 `KeyError`）与 `validate_model_row`（行缺必备键 provider／model／thinking／endpoint／key_env／price_in／price_out／price_verified、provider 未登记、`price_tiers` 不含 peak／offpeak 两档或各档缺 price_in／price_out、有峰谷表无 `peak_hours_beijing` → 报错退出，**不回落默认价**）；`run_batch.py` 入口两行改调用上述两函数；`__init__.py` 只加导出。`models.yaml` 本身零改动（现有各行全部通过完整性核，含 (c) 所用海外候选行——该行自 tag `cd63010` 已在表内，(c) 零痕迹维持）。
- **自测** `tests/test_registry.py` 10 条：别名作废、未登记名、必备键逐一缺省、provider 未登记、tier 三种缺省（缺 offpeak／档缺 price_out／无 peak_hours_beijing）、仓内 models.yaml 各行通过、CLI `--agents oracle`／`no-such-row`／`astar,oracle` → rc≠0 且不产生 seeds.csv。`.venv/bin/python -m pytest tests -q` → `201 passed`。
- **回归**（裁定 2026-10-09-14「一次回归覆盖两项」）：`bash tools/prereg_check.sh` 尾行「✔ 监视表差异均已登记 CHANGELOG.md（勘误／不改数字的代码改动），三基线逐位一致，可按协议 v0 开跑」rc 0（`CHANGELOG.md` 第 20 行一条合并登记三文件哈希）；⑭ 命令：`run_batch --agents astar,greedy --n 30 --frames 0 --out <仓外临时目录>` → astar 对 `d4af9ae` results 字段 1–15 `diff` 空 rc 0、greedy 对 tag 内 `2026-09-25-pilot01-baselines` greedy 30 行 `diff` 空 rc 0（临时目录不入库）。
- **日志补起点（10-10 验收块修订1 B，裁定 2026-10-10-08 三条件全过、已落）**：`run_episode` 在 reset 后取 `robot.pose()`，只作第 0 步日志行行尾附加字段 `start_pose`；(1) 新日志第 0 步行键序＝原序＋尾 `start_pose`、其余行无此键；(2) 旧读法三表对 c174ad7 与 (a) 批既有日志重算，csv／md 产物与 HEAD 逐字节一致（`failure_modes.py` 121 行 csv 全同、`a_tables_c174ad7.py` 三表与 `a_action_parse.py tables` 三表 `git status` 干净）；(3) prereg_check rc 0 三基线逐位一致。冒烟：astar／greedy seed 1000，`start_pose`→各步 pose 累加与计分器口径（起点＝course.start 全精度）差 3.4e-7／3.2e-7 <1e-6；summary `traveled_m` 为 4 位舍入值，与累加值舍入后同。既有日志不回填；首期公开日志取 v1（自带起点字段）。CHANGELOG 第 21 行另记一行。⑧ 节注记②「对两 tag 生效」已作废（内部工单），本批只对 `protocol-v0-prereg`。⑬⑭ 候审定方另发。

## (a) 回执 · 会话二 2026-10-10（内部工单 (a)＋内部工单 ①②③＋内部工单 ⑤＋内部工单送达探针；只列事实，是否缺陷由审定方判）

> 脚本（本目录，调用侧）：`a_action_parse.py`（跑批 run／探针 probe／①② 表 tables）、`a_tables_c174ad7.py`（c174ad7 批的 ②③）。监视件零改动：`bash tools/prereg_check.sh` 开跑前尾行「✔ 监视表差异均已登记 CHANGELOG.md（勘误／不改数字的代码改动），三基线逐位一致，可按协议 v0 开跑」rc 0（10-10 04:08）；收场再跑一次见本节末。
> ⑤ 记录点（内部工单）：① 图像元数据＝`a_action_parse.py` `attach_request_hook()`（openai SDK httpx 客户端 `event_hooks["request"]`，读请求体 JSON 的 `image_url` data URL；不读请求头）；oracle 提示与原文日志＝`HintedAgent.decide()`（`calls/<agent>/seed<N>.jsonl`，本地、`*.jsonl` 被 .gitignore 排除不入仓）；无一处改 `harness/`、`twin/`。密钥与请求头不落盘、不进本页。

### 置顶

- ① 图像送达：**干净**——(a) 批 3 行 × 310 步＝930 次 HTTP 请求，请求体图像与该步渲染帧（640×480 RGB）按 harness 同参数（`encode_jpeg(img, 512)`，JPEG q85）重编码逐字节一致 930/930；指令文本亦 930/930 一致。
- ② 动作映射：**干净**——c174ad7 批每家 5 个 F3 回合（共 15 回合 685 步）与 (a) 批 930 步，「输出原文→解析动作→执行动作」0 不一致；(a) 批执行动作＝oracle 提示 930/930，`invalid_outputs` 0、`api_errors` 0。
- ③ 判据与步长：未碰前进步单步位移中位 0.1864 m＝0.40 m 的 0.466（全部步中位 0.0012，原地转向步占多）；glm 11 个 F2 回合＝9 个模型自行输出 `stop`、2 个 80 步仅原地转向、0 个空解析（抽检 3＝seed 1000／1002／1003）。**不判缺陷**。
- (a) 本体：三行各 **10/10 完成、到达占比 1.000、sim 1.000、碰撞事件 0、步数逐种子同为 31/21/31/33/37/43/36/33/26/19**（＝每步从真实位姿重规划的 A* 路径）；按本页顺序表 (a) 行预设判据（到达占比达 greedy 量级→解析通路正常、低分系感知决策；仍≈random→harness 缺陷），事实落在「解析通路正常」一侧；**通过／缺陷由审定方判**。
- 送达探针（内部工单，一次性、不进榜）：三家对 seed 1000 首帧均答「3 个：红、紫、黄」，与分割渲染真值（1 红／4 黄／5 紫可见，2 绿／3 蓝不可见）**一致 ×3**。
- (c)：见 内部治理仓 (c) README（本仓不记 (c) 数字）。

### (a) 本体 · 附 oracle 提示跑批

- 口径：三行＝榜单三行（nothink、official）；种子＝冻结种子集（从 1000 起筛 32 得 30 可解、剔 1005／1019，与 c174ad7 同法）前 10 个＝1000–1004、1006–1010（本页顺序表未定取法，按令文「取冻结种子集前 10 个」）；提示＝每步用 harness `AStarAgent` 从孪生真值算下一步动作（每步从当前真实位姿重规划、不复用余下计划），以固定模板附在指令文本末尾（模板全文在 `runs/a-hint-oracle-20261010/meta.json` `hint_template`：「Navigation aid for this diagnostic run: a map-aware planner has computed that the correct next action from the robot's current position is "<action>". Use exactly this action for this step (still answer in the required one-line JSON).」）；其余（system 提示、图像、80 步、到达半径、slip／噪声、计分）与 c174ad7 全同，`config_sha256 7fcf28e7…`、`prompt_sha256 b9006b83…` 与 c174ad7 meta 同。
- 命令：`.venv/bin/python audits/first-issue-due-diligence/a_action_parse.py run --agents qwen3-vl-plus--nothink--official,glm-5v-turbo--nothink--official,deepseek-flash--nothink--official --n 10 --hint oracle --budget-usd 5 --out audits/first-issue-due-diligence/runs/a-hint-oracle-20261010`（04:12:40–04:30:44 −0700）→ 尾行：`== done … wall=1083.1s usd_total=0.2528 hint=oracle`；
  `qwen3-vl-plus… n= 10 sim_score=1.000±0.000 success=1.00 reached_frac=1.000 coll_events=0.0 steps=31.0 hint_follow=1.0 usd=0.0426 tier=flat invalid=0 api_err=0`／`glm-5v-turbo… … usd=0.178 tier=flat …`／`deepseek-flash… … usd=0.0323 tier=offpeak …`（三行其余字段同）。
- 表 `runs/a-hint-oracle-20261010/results.csv`（30 行，sha256 前 12 位 `93ad3872feda`）、`summary.csv`（`64b0cf9a52a8`）；三分类（同口径脚本）：`python3 tools/failure_modes.py --run audits/first-issue-due-diligence/runs/a-hint-oracle-20261010 --out-dir audits/first-issue-due-diligence/runs/a-hint-oracle-20261010` → 三行各「完成 10｜F1 0｜F2 0｜F3 0｜交叉核对不一致 0」。

| 行 | N | 完成 | 到达占比 | sim | 碰撞事件/回合 | 步均 | 提示遵从（执行==提示） | tokens in/out | 美元 | 人民币（×7.1） | price_tier | 时延均/P95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3-vl-plus | 10 | 10 | 1.000 | 1.000 | 0.0 | 31.0 | 310/310 | 197 844／10 408 | 0.0426 | 0.3021 | flat | 1.292／2.915 |
| glm-5v-turbo | 10 | 10 | 1.000 | 1.000 | 0.0 | 31.0 | 310/310 | 208 683／10 029 | 0.1780 | 1.2638 | flat | 1.179／2.354 |
| deepseek-flash | 10 | 10 | 1.000 | 1.000 | 0.0 | 31.0 | 310/310 | 192 330／9 191 | 0.0323 | 0.2293 | offpeak（周六全天闲时） | 0.957／1.409 |

- 对照（同 10 个种子，c174ad7 无提示）：qwen 0/10 完成、glm 0/10、deepseek 0/10（`episodes/runs/2026-09-25-pilot01/results.csv` seeds 1000–1010 行，仅 deepseek seed 1016 成功、不在前 10）。若判缺陷：本体无缺陷项可指；若审定方认为「附提示即 10/10」本身需另核，改动面在监视区外（本目录脚本）。

### ① 图像送达（内部工单 ①；每家抽 3 回合＝种子集前 3 个 1000／1001／1002，逐步落 `runs/a-hint-oracle-20261010/a1-image-delivery.csv` 249 行，`3fbde903a3f7`；全 30 回合汇总 `a1-image-delivery-summary.csv`）

- 命令：`.venv/bin/python audits/first-issue-due-diligence/a_action_parse.py tables --run audits/first-issue-due-diligence/runs/a-hint-oracle-20261010` → 尾行三行 `① <行>: episodes=10 calls=310 http=310 image_match=310 mismatch=0`（qwen／glm／deepseek 各一）。
- 「一致」定义：请求体 `image_url` 的 base64 ＝ 该步 `Observation.image`（640×480 RGB）经 `harness.agents.llm.encode_jpeg(img, 512)` 重编码的 base64，逐字节相等；同时记渲染帧原始 RGB 的 sha256 与请求体 JPEG 的 sha256。

| 模型 | 回合 | 步 | 尺寸 | 字节 | 编码 | 帧 sha256 前 12（RGB）→ 请求体 JPEG sha256 前 12 | 一致否 |
|---|---|---|---|---|---|---|---|
| qwen3-vl-plus | 1000／1001／1002 | 83（31＋21＋31） | 512×384（全部） | 9 749–23 452 | `data:image/jpeg;base64`，PIL 识别 JPEG | 例 seed 1000 步 0：`71896da8fbe3`→`19118632cc33`（＝期望）；步 1：`a6fa3a4d8900`→`9e5518d27a3d` | 83/83 一致 |
| glm-5v-turbo | 1000／1001／1002 | 83 | 512×384 | 同上范围 | 同上 | 同帧同哈希（三家同一渲染流） | 83/83 一致 |
| deepseek-flash | 1000／1001／1002 | 83 | 512×384 | 同上范围 | 同上 | 同上 | 83/83 一致 |

- 全 30 回合：930/930 一致，指令文本 930/930 一致（`text_match` True）。若判缺陷（如认为 512×384 q85 降采样本身是缺陷）：改动面在**监视区内**（`harness/agents/llm.py` `encode_jpeg`、`protocol/v0.md` §4 常量「512×384 JPEG q85」）。

### ② 动作映射（内部工单 ②）

- c174ad7 批（内部工单分类的 F3 回合，逐步原文已留存于 `episodes/runs/2026-09-25-pilot01/logs/`，`raw_text` 全批最长 233 字＜日志 300 字截断，未截断）：每家取 F3 回合按种子升序前 5——deepseek 1000／1001／1002／1003／1004（356 步）、glm 1001／1004／1006／1007／1009（42 步）、qwen 1000／1001／1002／1003／1004（287 步）；逐步「原文→`Action.parse`→日志 `action`」，表 `a2-action-mapping-c174ad7.csv`（685 行，`d7d70423a1c9`）。命令：`.venv/bin/python audits/first-issue-due-diligence/a_tables_c174ad7.py` → 尾行 `== 写出 a2-action-mapping-c174ad7.csv（685 行，不一致 0）、a3-step-displacement.csv（40 行）、a3-glm-f2-review.csv（11 行）`。顺带全批：4 303 步解析==执行 4 303/4 303，`decision_valid=false` 0 步。
- (a) 批：930 步全表 `runs/a-hint-oracle-20261010/a2-action-mapping.csv`（`0eba470686de`）；尾行 `② <行>: steps=310 parse→exec 不一致=0 executed==hint=310/310` ×3。

| 回合 | 步 | 输出原文（≤80 字） | 解析动作 | 执行动作 | 一致否 |
|---|---|---|---|---|---|
| deepseek seed 1000（c174ad7，F3） | 0 | `{"action": "forward", "note": "Checkpoint 1 ahead-left; checkpoint 4 sign visible right; purple obstacle on right. Next target: 1."}` | forward | forward | 一致 |
| deepseek seed 1000（c174ad7，F3） | 1 | `{"action": "left", "note": "See checkpoint 5 ahead; purple obstacle right. Need checkpoint 1, so turn left to search."}` | left | left | 一致 |
| qwen seed 1000（(a) 批，提示 forward） | 0 | `{"action": "forward", "note": "Checkpoint 1 (red) is directly ahead; moving towa…` | forward | forward | 一致（＝提示） |
| qwen seed 1000（(a) 批，提示 left） | 1 | `{"action": "left", "note": "Turned left; checkpoint 1 (red) now in view ahead, o…` | left | left | 一致（＝提示） |
| 其余 1 611 步 | — | 见两张 csv | — | — | 全部一致 |

- 不一致清单：**0**。若判缺陷：改动面在**监视区内**（`harness/interface.py` `Action.parse`、`harness/episode.py` 重试与 stop 兜底）。

### ③ 判据与步长（内部工单 ③；表 `a3-step-displacement.csv` 40 行 `83e0a7e0feb3`、`a3-glm-f2-review.csv` 11 行 `670b1ab07bb3`）

- 单步位移＝c174ad7 批（三模型 90 回合）＋基线批 random 30 回合日志相邻位姿欧氏距离（第 1 步起；第 0 步无起点行不计，与 ④ 预查同）；比值＝中位数／0.40。

| 分组 | n | 均值 m | P10 | 中位 | P90 | min | max | 中位/0.40 |
|---|---|---|---|---|---|---|---|---|
| 全部步（三模型＋random） | 5 597 | 0.0357 | 0.0000 | 0.0012 | 0.1785 | 0.0000 | 0.2083 | 0.003 |
| forward 未碰 | 626 | 0.1871 | 0.1765 | 0.1864 | 0.1983 | 0.1686 | 0.2083 | **0.466** |
| forward 碰撞 | 1 796 | 0.0375 | 0.0000 | 0.0225 | 0.1155 | 0.0000 | 0.1956 | 0.056 |
| left 未碰／碰撞 | 1 554／559 | 0.0000／0.0178 | — | 0.0000／0.0163 | — | — | 0.0002／0.0484 | 0.000／0.041 |
| right 未碰／碰撞 | 685／306 | 0.0000／0.0174 | — | 0.0000／0.0155 | — | — | 0.0004／0.0424 | 0.000／0.039 |
| stop | 71 | 0 | — | 0 | — | — | 0 | 0 |
| 按模型（全部步）：deepseek／glm／qwen／random | 2 139／389／1 685／1 384 | 0.0395／0.0336／0.0290／0.0386 | — | 0.0088／0.0000／0.0000／0.0170 | — | — | — | 0.022／0.000／0.000／0.042 |

- 即 0.40 m 判据≈2.15 个实兑前进步（名义 2 步）；与 ⑨ 预查（未碰前进步均值 0.1871）同源同值。
- glm 11 个 F2 回合原始输出判读（机械规则：有不可解析步→空解析；末步 `action=stop` 且 JSON 有效→模型自行 stop；否则→仅原地转向）：

| seed | 抽检 | 步 | traveled_m | invalid 步 | f/l/r/s | 末步原文（节录） | 判读 |
|---|---|---|---|---|---|---|---|
| 1000 | 抽检 | 80 | 0.3749 | 0 | 2/62/16/0 | `{"action": "left", "note": "Facing purple wall. Turning left to find path to checkpoint 1 (red)."}` | 仅原地转向（80 步内前进 2 步） |
| 1002 | 抽检 | 3 | 0.1745 | 0 | 1/1/0/1 | `{"action": "stop", "note": "At checkpoint 1 (red). Checkpoint 2 (green) visible to the right…` | 模型自行 stop（自称到达 1 号） |
| 1003 | 抽检 | 3 | 0.3907 | 0 | 2/0/0/1 | `{"action": "stop", "note": "Reached checkpoint 1 (red). It is very close. Stopping here."}` | 模型自行 stop |
| 1008 |  | 80 | 0.0000 | 0 | 0/70/10/0 | `…"left"… Continue turning left to find checkpoint 1…` | 仅原地转向 |
| 1020／1021／1023／1025／1026／1028／1030 |  | 4／3／11／4／29／4／3 | 0.39／0.19／0.00／0.18／0.38／0.37／0.18 | 0 | 末步均 stop | 均自称已到达 1 号（1021 自称「visited all checkpoints」） | 模型自行 stop ×7 |

- 合计：模型自行 stop 9、仅原地转向 2、空解析 0（全 11 回合 `decision_valid=false` 步＝0，与内部工单 F1=0 一致；stop 时 `reached` 均为 0）。若判缺陷：模型自行 stop／原地转向属模型行为，无 harness 改动面；若认为提示词应抑制早停，改动面在**监视区内**（`protocol/prompt_v0.md`＝冻结物，改即换版本）；F2 阈值 `DISP_MIN_M`＝0.40 在 `tools/failure_modes.py`（**监视区外**，预登记件、改即 v2 表）。

### 送达探针（内部工单；一次性、不进榜；`probe-20261010/probe.json` `cfa74341afaa`，图 `probe-seed1000-t000.jpg`＝请求体原 JPEG 16 761 B `19118632cc33`）

- 命令：`.venv/bin/python audits/first-issue-due-diligence/a_action_parse.py probe --agents qwen3-vl-plus--nothink--official,glm-5v-turbo--nothink--official,deepseek-flash--nothink--official --out audits/first-issue-due-diligence/probe-20261010` → 尾行 `== probe done → …/probe.json`。帧＝(a) 第一回合（seed 1000）首帧，经 harness 同参数编码；提示只问（英文，无 system）「How many checkpoint signs with a colored border are visible in this photo, and what is the border color of each visible sign? Answer in one short line.」；三次请求的图像均与期望逐字节一致（钩子记录同 ①）。
- 渲染真值（MuJoCo 分割渲染，按 geom 计牌面像素，可见阈 ≥100 px）：1 红 11 076 px、4 黄 3 184 px、5 紫 1 492 px 可见；2 绿、3 蓝 0 px 不可见。

| 模型 | 原文回答 | 对照 | tokens in/out | 美元 | 时延 s |
|---|---|---|---|---|---|
| qwen3-vl-plus | `Three checkpoint signs are visible: sign 1 with a red border, sign 5 with a purple border, and sign 4 with a yellow border.` | 一致（数、色、编号全对） | 245／32 | 0.00008 | 1.27 |
| glm-5v-turbo | `3 checkpoints: 1 (red), 5 (purple), 4 (yellow)` | 一致 | 290／19 | 0.00026 | 1.06 |
| deepseek-flash | `3 checkpoint signs are visible: one with a red border, one with a purple border, and one with a yellow border.` | 一致（未报编号，提示未问编号） | 242／25 | 0.00005 | 1.25 |

### 与内部工单三分类、内部工单敏感性脚注的矛盾核对

- 内部工单：**无矛盾**——分类表 F1 全 0 与 ② 的 `decision_valid=false` 0 步、解析==执行 4 303/4 303 相符；F2 11 回合经 ③ 原文判读为模型自行 stop／原地转向（非解析为空），F3 为行进后碰撞或超步——与分类定义相符；(a) 附提示 10/10 表明 c174ad7 的 0～1/30 不来自图像送达、解析或执行通路（①② 干净），与内部工单「分清模型能力与管线缺陷」的起因一致。
- 内部工单：**无矛盾**——脚注「0.40 m＝两步、两口径差≈一步（中位 0.1785）」与 ③ 未碰前进步中位 0.1864（0.466×0.40）、④ 预查差值 0.18–0.20 同源；5 个争议回合的判定不受 (a) 结果影响（(a) 批 30 回合交叉核对不一致 0，不新增争议回合）。
- 另记一处措辞差异（非矛盾，候审定方定）：本页顺序表 (a) 行判据写「到达占比达 greedy 0.707 量级」，0.707 是 greedy 的 sim 分，其到达占比为 0.900（段二表）；(a) 批两者均 1.000，不影响判读。

### (b) 步数敏感性（内部工单 (b)；**观察，不进榜、不改判据**；令块「(b) 输出落 (a) 目录」与本页顺序表「观察入 `CHANGELOG.md`」相左处以令块为准，CHANGELOG 在租约外未动，差异记回执）

- 口径：回合上限 80→160（只改本次跑批参数 `--max-steps 160`；冻结常量 `twin/configs/course01.yaml` `max_steps: 80` 不动，`config_sha256 7fcf28e7…` 同 c174ad7）；三行各 N=10、同冻结种子前 10、无提示；种子可解性筛选仍按 80 步（与冻结集同法）。run `runs/b-steps-160-20261010/`（05:22:51–05:59:15 −0700，wall 2182.9 s）；逐回合表 `b-steps-160.csv`（30 行，`024f1b755f62`）＝该 run `results.csv`（`8666cc07ed22`）加 `max_steps` 列。
- 命令：`.venv/bin/python audits/first-issue-due-diligence/a_action_parse.py run --agents qwen3-vl-plus--nothink--official,glm-5v-turbo--nothink--official,deepseek-flash--nothink--official --n 10 --hint none --max-steps 160 --budget-usd 5 --out audits/first-issue-due-diligence/runs/b-steps-160-20261010` → 尾行 `== done … wall=2182.9s usd_total=0.3568 hint=none`；`qwen… sim_score=0.120±0.130 success=0.00 reached_frac=0.240 coll_events=2.7 steps=74.8 … usd=0.0964`／`glm… 0.010±0.020 success=0.00 reached_frac=0.040 coll_events=1.0 steps=26.0 … usd=0.1445`／`deepseek… 0.100±0.105 success=0.10 reached_frac=0.380 coll_events=7.2 steps=118.9 … usd=0.116 tier=offpeak`；三行 `invalid=0 api_err=0`。三分类：`python3 tools/failure_modes.py --run audits/first-issue-due-diligence/runs/b-steps-160-20261010 --out-dir audits/first-issue-due-diligence/runs/b-steps-160-20261010` → deepseek 完成 1／F3 9；glm F2 4／F3 6（交叉核对不一致 1）；qwen F2 2／F3 8（`116f4f54956f`）。

| 行 | 上限 | 完成 | 到达占比 | sim | 碰撞事件/回合 | 步均 | 用到 >80 步的回合 | 第 80 步后新增到达 | 第 80 步到达数合计→终局 | 自行 stop 回合 |
|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-flash | 160（本批） | 1 | 0.380 | 0.100 | 7.2 | 118.9 | 7/10 | +8 | 11→19 | 4 |
| deepseek-flash | 80（c174ad7 同 10 种子） | 0 | 0.340 | 0.080 | 5.8 | 75.6 | — | — | — | 1 |
| qwen3-vl-plus | 160（本批） | 0 | 0.240 | 0.120 | 2.7 | 74.8 | 3/10 | 0 | 12→12 | 7 |
| qwen3-vl-plus | 80（c174ad7 同 10 种子） | 0 | 0.220 | 0.070 | 2.2 | 61.2 | — | — | — | 4 |
| glm-5v-turbo | 160（本批） | 0 | 0.040 | 0.010 | 1.0 | 26.0 | 1/10 | 0 | 2→2 | 10 |
| glm-5v-turbo | 80（c174ad7 同 10 种子） | 0 | 0.020 | 0.020 | 0.3 | 21.7 | — | — | — | 7 |

- 观察（不判）：① 只有 deepseek 用到多出的步数（7 回合跑过 80 步，其中 seed 1007 于第 136 步 5/5 完成，第 80 步后合计新增到达 8 个检查点），同时碰撞事件随步数上升（7.2 vs 5.8/回合）；② qwen 3 回合跑满 160 步但第 80 步后新增到达 0，其余 7 回合在 9–63 步内自行 stop；③ glm 9 回合在 2–42 步内自行 stop、1 回合跑到 152 步新增 0——F2「模型自行 stop」型回合不因上限放宽而改变；④ 同种子两批 80 步内结果本就不同（API 非确定性，如 deepseek seed 1006：c174ad7 到达 4、本批 0；qwen seed 1009：3 vs 0），故跨批差异含采样噪声，只记观察。若改常量＝v1、不在首期（本页顺序表）。

### 花费（本会话 pg 侧；汇率 7.1；deepseek 全程 offpeak＝北京时间周六全天闲时）

| 批 | qwen3-vl-plus | glm-5v-turbo | deepseek-flash（offpeak） | 小计 |
|---|---|---|---|---|
| (a) 附提示 N=10 ×3 | $0.0426／¥0.3021 | $0.1780／¥1.2638 | $0.0323／¥0.2293 | $0.2528／¥1.795 |
| 送达探针 ×3 | $0.00008 | $0.00026 | $0.00005 | $0.00039／¥0.0028 |
| (b) 160 步 N=10 ×3 | $0.0964／¥0.6842 | $0.1445／¥1.0258 | $0.1160／¥0.8234 | $0.3568／¥2.533 |
| 本会话 pg 侧合计 | $0.1391 | $0.3228 | $0.1484 | **$0.6100／¥4.331** |

- 期内累计（pg 侧，≤$150/期，裁定 2026-10-08-04）：c174ad7 正式批 $0.6653（含 09-25 探活）＋ ⑪ astar $0 ＋ 本会话 $0.6100 ＝ **$1.2753 ≈ 0.85%**；(c) 花费与含 (c) 的总累计只记 内部治理仓 (c) README。
- 来源：各 run `summary.csv` `usd_total`／`cny_total`／`price_tier` 列；探针 `probe-20261010/probe.json` `usd` 字段。

### 收场核（会话二，10-10）

- `bash tools/prereg_check.sh`（跑批后）尾行「✔ 监视表差异均已登记 CHANGELOG.md（勘误／不改数字的代码改动），三基线逐位一致，可按协议 v0 开跑」rc 0；`git diff --stat -- harness/models.yaml` 空；`git status --porcelain -- harness twin protocol` 0 行。
- porcelain 开场（04:00）：`?? episodes/runs/20260925-231109/`、`?? episodes/runs/20260925-231257/`（租约外两旧目录，不碰）；04:10 曾出现 `?? real/tools/`（他会话 RIG 线新建，租约外，不碰，后由该会话处置、收场已不在）；收场：上述两旧目录＋本目录租约内文件（README、脚本 2、表 5、`probe-20261010/`、`runs/` 两 run 的 csv／md／json；`logs/`、`calls/` 的 `*.jsonl` 被 `.gitignore` 第 9 行排除，留本地）。本仓 `audits/` 下 `grep -ril -e gemini -e internal-reference` 零命中。
- (c) 内部参照：全部产物只在 内部治理仓 (c) 目录；本仓零 (c) 痕迹；对照行见 内部治理仓 (c) README。

### 自检记录 · ② 动作映射在公开批 v1 上重跑（10-20，公开清场批）

- 命令：`A_RUN=2026-10-15-v1 A_FM=failure-modes-2026-10-15-v1.csv A_SUFFIX=2026-10-15-v1 .venv/bin/python audits/first-issue-due-diligence/a_tables_c174ad7.py`（脚本改为环境变量换批，缺省仍为 c174ad7；缺省批三表重跑逐字节不变）。
- 结果：每家 F3 回合按种子升序前 5（deepseek 1000／1002／1003／1004／1006，376 步；glm 1000／1002／1004／1006／1007，160 步；qwen 1000／1001／1003／1004／1006，241 步），合计 777 步，「原文→`Action.parse`→执行」**不一致 0**；原文最长 169 字。表 `a2-action-mapping-2026-10-15-v1.csv`（777 行）；同批顺手产出 `a3-step-displacement-2026-10-15-v1.csv`（40 行）、`a3-glm-f2-review-2026-10-15-v1.csv`（8 行，v1 的 glm F2 为 8 回合），只作记录不改五句。
- 五句 ① 的「0 不一致」自此与「4134 步」同源于 v1（来源表已改）。

## 偏差记录（⑫ 规则：任何改动记为偏差；⑧ 合入时记「日志补起点、计分未变」）

| 日期 | 改动 | 依据 | 提交 |
|---|---|---|---|
| 2026-10-10 | registry 失败关闭：`oracle` 别名作废改报错、未登记名／行缺省报错不回落（`registry.py`、`__init__.py`、`run_batch.py` 入口两行）；计分未变、三基线逐位一致、⑭ 0 差异 | 内部工单 验收块 D（裁定 2026-10-09-14 并批） | 见 CHANGELOG 第 20 行；提交号入 内部治理仓 回执 |
| 2026-10-10 | 日志补起点、计分未变：第 0 步行尾加附加字段 `start_pose`（`harness/episode.py`），既有字段顺序数值零改动；旧读法三表对既有日志产物逐字节不变；三基线逐位一致 | 裁定 2026-10-10-08 三条件（验收块修订1 B）全过 | CHANGELOG 第 21 行；提交号入 内部治理仓 回执 |

## (a) 判 harness 缺陷时的退路（内部工单 §一）

当日起走协议 §9.3：改语义＝v1 重打 tag、正式批重跑，**≤10-24 完成**；10-25～10-28 留给随发清单（runbook §6）与公开前凭证闸；**死线 10-29 不动**，榜标 v1。

## 回执格式

三表（a／b／c）＋每表命令与输出尾行；(a) 结论一行。回执落 内部治理仓 `00_portfolio/orders/`（内部工单 随附），本目录只放数据表与脚本。

## 状态

- 10-10（会话一，验收块修订1＋⑬）：裁定 05 号 五句到齐、裁定 07 号 改「4 行 9 个路径字串」、registry 改动与 tier 读法采信（760ab56 不 revert）；日志补起点三条件全过已落（裁定 2026-10-10-08）；⑬ 站点文案＋runbook §6 落字；⑭ 标结；prereg_check 跑前跑后 rc 0。
- 10-10（会话一）：审定方验收块＝(a) 判**通过**（裁定 2026-10-10-04；0～1/30 归模型决策能力、监视件零改动）、首期讲法 v1 五句（裁定 05 号）、⑪⑬「三条脚本基线＋附真值提示行」（裁定 06 号）、本页 6 处 内部治理仓 路径入内部工单清洗批（裁定 07 号）；顺序表 (a) 行判据句按验收块 B1 改；会话二租约收回、会话一唯一写；⑧ 批次 D1／D2 落地（新节），日志补起点候裁；⑬⑭ 候另发。
- 10-10：会话二交 (a)（附 oracle 提示三行 10/10；①②③ 干净、不判）＋内部工单送达探针（三家一致）＋(b) 观察＋(c)（只在 内部治理仓）；内部工单三条落字（⑭ greedy 回放锚句、⑪⑬「三条脚本基线…单列」、段二改读 tag 内 greedy 30 行并表）；内部工单：(c) 路径与厂商名自本页移走；脚本 `a_action_parse.py`／`a_tables_c174ad7.py` 与表入本目录；prereg_check 前后 rc 0；候审定方验收（通过／缺陷由审定方判）。
- 10-09：内部工单：greedy 入 v1 三条脚本列（⑪ 三列注、⑬ v1 定义、⑭ greedy 首锚句）；段二 greedy 参考跑登记（(a) 验收后、⑧ 前）。
- 10-09：内部工单 段一：registry 改报错已裁并入 ⑧ 批次（一次回归覆盖两项）；过渡期跑批命令显式 `--agents astar`、禁 oracle 字串（本页命令已合规）。
- 10-09：内部工单段一：registry.py 在监视表内、未改报审定方；别名与历史普查入页；⑪⑫⑬⑭ 列名改 astar。
- 10-09：内部工单 ⑭ v1 回归门登记（写入 runbook 验收节候 ⑧⑬ 后）、比对命令自测 0 差异；⑪ 机制句按 裁定 10 号 ① 定稿。
- 10-09：内部工单 ⑫ 规则先提交（`41c9680`）→ ⑪ oracle 30/30（run `2026-10-09-oracle-patch5`），阈值全不动；⑬ 随 ⑧。
- 10-09：内部工单 ⑦⑨⑩ 入表尾、预查入页（⑦ 引文、⑨ 分布与阈值清单、⑩ 首步碰撞 0 回合与出生间隙），⑧ 排期（(a) 交付后、v1 前）；④ 预查勘误一处（10 回合无碰撞）。
- 10-09：内部工单 ④⑤⑥ 入表、④ 预查事实入本页、顺序表 (c) 行改「(a) 先、(c) 随后同交」。
- 10-09：内部工单 (a) 增核三项入表（见上）；内部工单脚注已加在三分类表下。
- 10-09：目录建立（内部工单）；本目录只放 (a)(b)，(c) 不进公开仓、不进站点、不进 `build_site` 输入（附条修订1）；(a)(b) 脚本与跑批候会话二（cwd＝proving-ground）。
