# 出处与哈希对照（公开快照仓 ↔ 原仓私有存档）

> 本仓（`physicalaipg/proving-ground`）是 2026-10-20 自原开发仓**单提交快照**而来；原仓改名 `proving-ground-archive`、保持私有、完整历史留档不删。快照树与原仓清场提交的树逐字节相同（两边 `git rev-parse HEAD^{tree}` 一致，见下）。

## 1 预注册锚点怎么核

- 规则冻结于原仓提交 **`cd63010d55ca150a8c67667d45c1a9cf96f5a063`**（tag `protocol-v0-prereg`，tag 对象 `cb3efd364cb74ae2186fdd56f8dd08a1a09ca119`，git 自报日期 2026-09-25）。
- 第三方时间证据：`protocol/timestamps/protocol-v0-prereg.txt.ots`（OpenTimestamps，比特币区块 970739／970754／970794，最早区块时间 **2026-10-10 07:25:40Z**）。凭证只证明「`protocol-v0-prereg.txt` 的内容不晚于该区块已存在」；该文件 [b] 段列出 25 件监视文件在 tag 内的 sha256。
- 公开可复核的办法：本仓 `twin/`、`harness/` 全部文件与 `protocol/v0.md`（规则区）、`protocol/prompt_v0.md`、`episodes/runs/2026-09-25-pilot01-baselines/{seeds.csv,meta.json}` **原样保留、未随清场改动**；逐文件 `shasum -a 256` 对照 `protocol-v0-prereg.txt` [b] 段即可（差异只应是 `CHANGELOG.md` 登记过的勘误与「不改数字」的代码改动）。`tools/prereg_check.sh` 依赖 tag，在本仓无 tag 可比，请改用上述逐文件对照。
- 因此这些文件里仍保留内部编号与本机路径字样（声明残留，清单 `tools/public_scan_exclude.txt`）：改一字即破上述哈希。`protocol/v0.en.md` 与 `protocol/i18n/` 为其便利译本与回译记录，随之不动。

## 2 原仓哈希 → 本仓

本仓文件（README、CHANGELOG、审计记录、`.gitleaksignore` 等）引用的原仓提交短号（如 `c174ad7`、`d4af9ae`、`41c9680`、`cd63010`）**都是原仓私有历史里的提交**，本仓不含这些对象。对照：

| 原仓对象 | 含义 | 本仓对应 |
|---|---|---|
| `cd63010`（tag `protocol-v0-prereg`） | 规则冻结点 | 无对应提交；监视件内容原样在本仓初始提交内，核法见 §1 |
| `c174ad7` | 验收批（三模型 N=30，只作对照） | 数据在 `episodes/runs/2026-09-25-pilot01/` |
| `d4af9ae`、`41c9680` | 回归门 ⑭ 所引的 astar 对照批 | 对照用的 results 在原仓；本仓以 `episodes/editions/2026-10-21-pilot01/logs/` 内副本与 `episodes/runs/2026-10-15-v1/` 为准 |
| 其余 45 个提交短号＋1 tag（完整清单在原仓审计产物） | 历史记录引用 | 全部映射到本仓**初始提交**（单提交快照）；本仓初始提交 hash 与树 hash 记于下表 |

| 项 | 值 |
|---|---|
| 原仓清场提交（archive HEAD） | 见本仓初始提交说明 |
| 本仓初始提交 | 见 `git log --reverse` 首条 |
| 树 hash（两边一致） | 见本仓初始提交说明 |

## 3 快照时做了什么（清场批，10-20）

- 去除：内部治理仓名、本机绝对路径、内部工单号与裁定号（改写为「内部工单」「裁定 日期-序号」通用称谓）、厂商名（改写为「板卡厂商」）；厂商原件不入快照；内部派卡与操作卡 5 件移出。
- 加入：`LICENSE`（Apache-2.0，代码）、`LICENSE-DATA`（CC BY 4.0，数据与文档）、本文件、`episodes/runs/2026-09-25-pipeline/NOTE.md`、提交侧闸 `tools/githooks/pre-commit`＋`tools/public_scan.py`。
- `episodes/editions/2026-10-21-pilot01/SHA256SUMS` 改为只列 git 跟踪文件（`tools/manifest.py`）。
- 数字、计分、协议规则、监视件一字未动。
