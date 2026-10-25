# proving-ground · 物理AI实验场（PG 线）

> 定位句：**一个把每一代 AI 都放进真实世界跑一遍、并把跑不过的地方亲手造出来的人。**
> 本仓＝公开快照仓（单提交）；规则冻结出处、原仓对照与许可见文末「出处与许可」。

## 一条命令跑一批（Twin-01 v0，内部工单）

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m twin.selftest                                    # 接口契约自测（8 项，含 A* 零碰撞）
.venv/bin/python -m harness.run_batch --agents astar,greedy,random --n 30   # 成本 0：A* 天花板／贪心／随机基线，验证流水线
# 模型在环（密钥只放项目根目录 .env，已 gitignore，runner 自动载入；跑前打印 provider+model；预算护栏逼近即停）：
bash tools/prereg_check.sh                                           # 监视表（twin/ harness/ 协议规则区 种子）与 tag protocol-v0-prereg 零差异或勘误已登记 CHANGELOG.md，且三基线重跑逐位一致，才开跑真模型
bash tools/setup_ffmpeg.sh --check                                   # 发布日视频合成用 ffmpeg（含 libass/freetype）；缺则去掉 --check 从源码重建到 ~/.local/ffmpeg-libass
.venv/bin/python -m harness.run_batch --agents qwen3-vl-plus--nothink--official,glm-5v-turbo--nothink--official,deepseek-flash--nothink--official --n 30 --budget-usd 60 --preflight
```

协议与常量见 `protocol/v0.md`（英文 `protocol/v0.en.md`；行名＝模型 ID--思考档--端点，配置即身份）；试跑记录见 `docs/pilot-run-01.md`；发布流程见 `docs/release-day-runbook.md`；站点本地预览 `python3 tools/build_site.py && python3 -m http.server -d site 8000`。输出在 `episodes/runs/<时间戳>/`：`seeds.csv`（种子可解性筛选：剔除理由、A* 标称步数）、`results.csv`（逐回合：仿真分、到达数、碰撞步数与事件数、路程比、成本、计价时段…）、`summary.csv`（每行：仿真分 ±95% CI、成功率、碰撞事件、路程比、美元与人民币成本并列、每步时延均值/P95）、`meta.json`（配置与提示词 sha256、种子、剔除率、行身份、预算护栏触发记录）、`logs/<行>/seed*.jsonl`（逐步日志：动作、原始输出、时延、成本、位姿、碰撞）、`frames/`（前几回合相机帧）。

## 目录

| 目录 | 内容 |
|---|---|
| `harness/` | 停-看-想-动**接口**（`interface.py`，孪生与真机共用）、任务层（`task.py`，指令渲染）、计分（`scoring.py`，**仿真分单一真源**）、回合循环（`episode.py`）、Agent（`agents/`：astar／greedy／random 读真值基线、anthropic／openai_compat 模型）、批量跑测（`run_batch.py`）、模型表（`models.yaml`，行名＝配置即身份）、真机端占位（`robot_real.py`，内部工单） |
| `twin/` | Twin-01 数字孪生（MuJoCo）：配置（`configs/course01.yaml`，套件到货后改值不改码）、布局采样与域随机化（`arena.py`）、MJCF 生成（`mjcf.py`）、机器人实现（`robot_twin.py`）、契约自测（`selftest.py`） |
| `protocol/` | 协议 v0 中文真源 `v0.md` ＋ 英文渲染 `v0.en.md`（`tools/render_en.py` 生成，带校对标记）、术语表、提示词 v0（冻结物）、套件候选清单 |
| `real/` | 真机侧（内部工单）：驱动与停-看-想-动适配（`ugv02.py`、`real_env.py`、`camera.py`）、旧车固件 `firmware/yb-eet01-json/`、真机 smoke（`smoke.py`）、固定布局 L1 与布局卡／场地登记（`course/`）、车载相机实测常量（`config/camera.yaml`、`camera_measure.py`）、俯拍离线计分 v0（`score_overhead/`：ArUco 码、视频→车位、与孪生同格式分数）、黄金用例 oracle（`oracle.py`）；真机段协议 `protocol/real-v0.md`，冻结核对 `tools/real_prereg_check.sh` |
| `docs/` | 引擎选型记录、试跑 01、发布日 runbook（48h/72h）、首期视频模板、账号开通清单 |
| `episodes/` | 跑测输出（`runs/` 仿真、`real/` 真机）、每期发布包 `editions/<期>/`（完整日志、未剪辑视频索引、sha256 清单，规范见 `episodes/README.md`）、相机帧样例 |
| `site/` | 双语静态榜单站（GitHub Pages；数据只来自 `episodes/`，`tools/build_site.py` 生成） |
| `tools/` | `build_site.py`（站点数据）、`manifest.py`（sha256 清单）、`render_en.py`（中→英渲染流水线）、`make_subtitles.py`／`compose_video.py`（双语字幕与双画框成片） |

## 工程约束

干净起建；接口先于实现；不改变发布数字的仿真工作不算进展；真机侧安全＝固件限速、离散有界动作、三层急停。

## 环境

macOS 用 `MUJOCO_GL=cgl`（代码已默认设置），Linux 用 `egl`；CPU 即可，M2 Pro 上 640×480 约 2 ms/帧。Python ≥3.11（本机 3.13.12 实测）。

## 出处与许可

- **出处**：本仓是 2026-10-20 自原开发仓的单提交快照；原仓改名存档、保持私有、历史不删。规则冻结于原仓提交 `cd63010`（tag `protocol-v0-prereg`），外部时间证据＝`protocol/timestamps/protocol-v0-prereg.txt.ots`（比特币区块 970739，2026-10-10 07:25Z）。原仓哈希对照、监视件逐文件核法与清场说明见 `docs/provenance.md`；监视件与其译本原样保留（含内部编号字样），清单 `tools/public_scan_exclude.txt`。
- **许可（双许可分界）**：代码目录（`harness/`、`twin/`、`real/`、`tools/`、`site/` 的脚本与样式、`tests/`、`audits/` 下脚本）按 `LICENSE`（Apache-2.0）；`episodes/`、`editions/`（含日志、CSV、说明与帖文）与 `docs/`、`protocol/` 的文档按 `LICENSE-DATA`（CC BY 4.0）。
- 提交侧闸：`git config core.hooksPath tools/githooks`（gitleaks＋`tools/public_scan.py`）；推送侧 `tools/push_gate.sh`。
