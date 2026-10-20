# 发布日 runbook（内部工单）· 48h 目标 / 72h 硬线

> 依据：内部工单 卡 D 与第五节「窗口内任一次模型发布→发布日演练：≤48h 目标，72h 硬线；两次超 72h→待命失效，修好前不发新一期」；裁定 2026-09-25-06（人手小时 KPI：第三期起 ≤3 h，>6 h 判工具链失败重做）；裁定 2026-09-25-12（双语同发）；裁定 2026-09-25-16（主理人亲手只许四类：物理操作、付费、账号开通、拍板）。
> 触发：任一前沿多模态模型 **API 公开可用**（不是发布会时刻）。T0＝可用时刻，按 UTC+8 记进 `episodes/editions.csv` 的 `trigger_released_at`。
> **首期数据路径（内部工单 P3 改判，裁定 2026-09-25-19）**：首期（2026-10-21-pilot01）正式仿真数据＝内部工单 Q4 在 tag `protocol-v0-prereg` 之后、冻结种子集上跑出的 **3×N=30**，**T0 直接发 N=30**，不经 N=10 快评、不重跑；真机侧 N=10 pilot（内部工单）。首期 T0＝主理人拍板的发布开工时刻（无模型发布触发，`trigger_model` 填 `edition01`）。
> 【兜底路径——仅当 Q4 延误、T0 前无正式仿真数据时启用；原文保留】「三条不动：**发布日 N=10 快评**（仿真＋真机各 10 回合）→ **7 日内 N=30 正式**（真机 N=30；仿真 N 按协议 §9 正式 N 规则）→ **完整日志与未剪辑视频随发**」。两条路径共同不动的是：完整日志与未剪辑视频随发、72h 硬线。
> 分＝协议 §5 仿真分（harness 单一真源）。72h 硬线内发不出完整包，就是一次超线，不发残包；砍 N、砍随发项都不是选项，能砍的只有剪辑精度。

## 0 待命态（每周核一次，≤15 min；任一项红即修，不等模型发布）

| 项 | 核法 | 谁 |
|---|---|---|
| 车与场地 | 电池满电＋备用电池；场地 2×2 m 铺好、5 立柱与障碍在箱；俯拍机位固定；急停三层可用（rig-safety 硬门，`内部治理仓/35_papers/p5-realbot/protocol/safety-protocol.md`） | 主理人（物理） |
| 密钥与预算 | 项目 `.env` 首季三家（阿里云百炼／智谱／DeepSeek，`docs/pilot-run-01.md` §1）密钥有效（`run_batch --preflight-only` 探活 ≈¥0.02）；本期预算余额记在 `notes.md`；`--budget-usd` 上限由主理人授权 | 密钥／授权＝主理人；探活＝CC |
| 代码 | `python -m twin.selftest` 8 项 PASS；`python3 tools/build_site.py --check` ✔；`python3 tools/selftest_site.py` ✔；ffmpeg 可用且含 `subtitles`／`drawtext` 滤镜：`bash tools/setup_ffmpeg.sh --check`（换机重建去掉 `--check`，源码精简编到 `~/.local/ffmpeg-libass`，≈5 分钟；`compose_video.py` 自动查找；瘦身版 brew `ffmpeg` 缺这两滤镜，`ffmpeg-full` 在本机 ~/.brew 前缀无 bottle） | CC |
| 账号 | 四平台登录态与两步验证正常（`docs/accounts-checklist.md`） | 主理人 |
| 冻结物 | `bash tools/prereg_check.sh` ✔（监视表 twin/／harness/／协议规则区／种子与 tag `protocol-v0-prereg` 零差异或勘误已登记 `CHANGELOG.md`，且三基线重跑逐位一致，协议 §9.3）；改过任一规则即 v1 新一季并整批重跑，不在发布日改 | CC |
| 峰谷时段 | DeepSeek 行按峰谷计价（高峰＝北京时间工作日 9–12、14–18）：仿真批排闲时段，`summary.csv` `price_tier` 记实际时段；发布日撞上高峰不等，照跑并注明 | CC |

## 1 时间线（T0 起算；括号内为人手小时记录项，写 `episodes/editions/<期>/human-hours.csv`）

| 时段 | 动作 | 产物 | 谁 |
|---|---|---|---|
| T+0 ~ +1h | 登记：`editions.csv` 新行（`edition_id=<YYYY-MM-DD>-<slug>`，`status=planned`，`trigger_model`，`trigger_released_at`）；建 `episodes/editions/<期>/`（`runs.csv`／`video.csv`／`human-hours.csv`／`notes.md` 从 pilot01 目录复制表头） | 期目录 | CC |
| T+0 ~ +2h | 接入：`harness/models.yaml` 加一行——行名＝模型 ID＋思考档＋端点（配置即身份，协议 §7）、**官网单价 curl 落盘核对**后 `price_verified: true`、图像 token 规则、峰谷时段（如有）；`--preflight-only` 探活 1 次；投稿行按协议 §8 在 `runs.csv` 标 `verified`（rerun／self-reported） | models.yaml diff | CC；付费授权＝主理人 |
| T+2 ~ +6h | 仿真侧：**首期公开数据＝v1 跑批**（≤10-24 落地后 `runs.csv` `sim_run` 指向 `episodes/runs/<v1 run 目录，落地后填实际路径>`，N=30；c174ad7＝验收批、只作对照、不再作数据源，裁定 2026-10-09-09 ③／-11 ②；内部工单 A-3）｜【兜底】仿真快评：`run_batch --agents <新模型>,<在榜模型…> --n 10 --budget-usd <授权> --preflight --out episodes/runs/<日期>-<期>-sim10`（同一组种子；在榜模型可复用已有 run，不重跑） | run 目录 | CC |
| T+2 ~ +12h | 真机快评 N=10：按 内部工单 操作清单（≤10 步）；每回合布局按种子的布局卡摆放；俯拍＋机载录像；`recorded_at` 记 epoch；**开工前过 rig-safety「每次开工前」清单，三层急停实测** | `episodes/real/<日期>-<期>-real10/`＋原片 | 主理人（物理）；计分／回位／记时＝工具链（内部工单） |
| T+12 ~ +20h（原片归档，先于色彩门与入包） | 相机原片**原样**拷入本机 `~/Movies/pg-media/originals/`（原片即母版，裁定 2026-10-02-01；不转码、不改名、不进 git），逐文件 `shasum -a 256` 记入同目录 `SHA256SUMS` 与私有器材台账，**记完再走管线**；`compose_video.py` 的输入取自该目录。D-Log M 对照条（`ref-compare`）同样归档、不过门、不计入基准 | `originals/SHA256SUMS`＋台账行 | CC（相机接 Mac＝主理人） |
| T+12 ~ +20h（色彩门，入包前） | 原片（Normal 8-bit 直出，`docs/shooting-card.md`）逐条过 `python3 tools/color_gate.py --video <原片…> --t <样帧秒> --gray-rect "<灰卡区 x,y,w,h>" --anchor-rect "<固定锚点区>" --out-dir <报告目录>`：预检（直方图呈 log 形态→FAIL「profile 误用」）＋五项：①中性度（灰区 \|a*\|、\|b*\|）②曝光（灰区 L*）③跨场次一致性（锚点区对基准片段 ΔE2000）④高光裁切 ⑤码率＋原片 sha256 在账本；阈值全在 `tools/color_gate.yaml`（v0 空位 10-04 定稿，空位时退出码 3 只报数）。**任一项不过不得发布**；改过工具先跑 `color_gate.py --selftest` | `color_gate.json`（多片另有 `summary.json`）＋两张示波 PNG | CC |
| T+12 ~ +20h | 入包：`runs.csv` 填 sim_run／real_run；复制逐步日志到 `editions/<期>/logs/`；字幕＋双画框成片（`docs/video-template.md` §4）；原片上传取外链＋sha256 → `video.csv`；`manifest.py gen`＋`verify` | 发布包 | CC（上传账号操作＝主理人） |
| T+12 ~ +20h（实拍素材） | 实拍素材（H.265／10-bit，4K）经 `tools/compose_video.py` 转 1080p 后入双画框：直接作 `--overhead`／`--onboard` 输入，工具内解码、缩放裁切，成片 1920×1080 H.264 yuv420p，不必先另行转码；`bash tools/setup_ffmpeg.sh --check` 通过的精简版 ffmpeg 已含 hevc 解码与 yuv420p10le（内部工单，10-01 实测：4K Main 10 测试片 → 1080p 成片）；展示拍摄素材不作评测数据、不入 `episodes/` | 双画框成片 | CC |
| T+20 ~ +30h | 渲染：`notes.md`（中文真源：读法、异常、选法）→ `render_en.py status/import/build` 出 `notes.en.md`（**快评允许带 MT-UNREVIEWED 标记发布**，正式版前校对去标）；`build_site.py`＋`--check`；本地预览核对三列、保真度、$／成功、每步延迟 | 站点数据＋双语说明 | CC |
| T+30 ~ +48h（目标） | 发布：站点（push → Pages；首次公开先按 §7 演练结论开 Pages）；YouTube＋X（英文渲染）；B 站＋公众号（中文渲染）——**同一小时内出**；`editions.csv` 填 `published_at`、`status=quick`、`human_hours`；`build_site.py` 重建；提交 | 四平台链接写回 `notes.md` | 发帖＝主理人账号；文案与素材＝CC |
| T+48 ~ +72h（硬线） | 只允许用于修复上面任一环节的故障；72h 未发＝记一次超线（`notes.md` 与 内部治理仓 STATE 记「发布日超线 1/2」） | — | 主理人拍板 |
| T+7d 内 | 【兜底路径才有此步；首期仿真 T0 已是 N=30，真机补跑与否由主理人拍板】正式：真机 N=30＋仿真正式 N；`status=formal`；英文校对去标；站点重建；四平台补发「正式版」并更新链接 | 正式包 | 同上 |
| T+8d | 复盘：人手小时合计对照 KPI（第三期起 ≤3 h；>6 h 判工具链失败，内部工单 重做）；发布用时（站点 KPI 自动算）；异常入 `notes.md` | 复盘 3 行 | CC 起草，主理人拍板 |

## 2 人手小时记录（裁定 2026-09-25-06；`human-hours.csv`）

`date,phase,start,end,minutes,who,note` —— phase 取：`arena`（铺场／摆布局）｜`robot`（真机回合含回位）｜`video`（录像／剪辑／上传）｜`publish`（发帖／文案核对）｜`other`。工具自动记录的（内部工单 会话脚本）与人工补记的都进同一表；合计填 `editions.csv` `human_hours`，站点 KPI 直接读。

## 3 分工（四类原则）

- **主理人只做**：物理操作（铺场、摆布局、上电、急停、录像机位）、付费（API 预算授权、平台订阅）、账号（四平台发帖与上传）、拍板（超线判定、正式版放行、异常处置）。
- **CC 做其余**：登记、接入与核价、跑批、入包、字幕成片命令、双语渲染、站点构建、提交与推送（推送前主理人示下）、复盘草稿。
- 真机侧任何一步先过 rig-safety 硬门；发布日不新增硬件改动。

## 4 触发后的第一条命令清单（复制即用）

```bash
cd <仓根>
python3 -m twin.selftest && python3 tools/build_site.py --check && python3 tools/selftest_site.py   # 待命态自检
bash tools/prereg_check.sh                                                                          # 监视表与 tag protocol-v0-prereg 零差异／勘误已登记，三基线逐位一致
.venv/bin/python -m harness.run_batch --agents <新行名> --n 1 --preflight-only --budget-usd 1        # 探活（行名＝模型 ID--思考档--端点，见 models.yaml）
.venv/bin/python -m harness.run_batch --agents <新模型>,<在榜模型> --n 10 --budget-usd <授权> --preflight --out episodes/runs/<日期>-<期>-sim10   # 【兜底路径】首期直接引用 Q4 的 N=30 run，不跑此行
python3 tools/manifest.py gen episodes/editions/<期> && python3 tools/manifest.py verify episodes/editions/<期>/SHA256SUMS
python3 tools/render_en.py status episodes/editions/<期>/notes.md && python3 tools/render_en.py build episodes/editions/<期>/notes.md
python3 tools/build_site.py && python3 -m http.server -d site 8000     # 本地预览 http://localhost:8000/
```

## 5 止损与升级

- 探活失败／端点不可达 → 不开跑，记 `notes.md`，主理人决定换端点或延后；不改协议。
- 预算护栏触发（`meta.json` `budget_stop`）→ 已完成回合照发，`notes.md` 写明 N 实际值；不补跑越预算。
- 真机故障（车／相机／场地）→ 72h 内修不好即超线；**真机列必须在场，可为「待锚」态并附公开征集入口；仿真结果不得表述为真机能力**（内部工单 §三对齐 裁定 2026-10-08-02；原句「不发『仅仿真』的期（榜单三列缺一列不成期）」自此作废）。

### 5.1 首期视频（内部工单 §二；首期＝纯仿真渲染，主理人无拍摄项）

- 形态：横版 2～3 分钟，同一剪辑出中英两版（YouTube 英文、B 站中文）；不配人声，只用字幕卡；不用真机或实拍素材。
- 结构：头条结论 → 三家第一人称回放与 A*、random 并排 → 补丁13 三分类表 → 真机列「待锚（第二期）」＋征集入口（仿真按协议复跑 protocol-v0-prereg ＋ 真机复跑意向登记；真机协议 v0 第二期前发布，内部工单 ④）→ 片尾站点链接。
- 选段规则（先提交、后渲染）：每家取中位仿真分回合一个、最高分回合一个，同分取种子号小者；选法与种子号写进 `notes.md`。
- 衍生件：X 发 30～45 秒剪辑＋链接；公众号发中文图文（榜单图、三分类表、GIF、链接）。
- 所有画面数字只来自 build 流水线（`summary.csv`／`build_site.py` 产物），不手打；粗剪即开，定剪候 (a) 结论；素材冻结 10-21（§6）。
- **(c) 内部参照与 Gemini 的任何内容不得出现**（裁定 2026-10-09-02）。
- 两次超 72h → 待命失效：修好工具链前不发新一期（实验表止损，主理人拍板）。

## 6 随发清单（发布前逐项打勾，缺一不发）

- [ ] `runs.csv` 所引仿真与真机 run 的 `summary.csv`／`results.csv`／`seeds.csv`／`meta.json` 在仓
- [ ] 完整逐步日志已复制到 `editions/<期>/logs/`（jsonl 入仓）
- [ ] 未剪辑原片已上传，`video.csv` 每行有 `url`／`sha256`／`bytes`／`duration_s`／`recorded_at`
- [ ] `SHA256SUMS` 重生成且 verify ✔
- [ ] `models.yaml` 新模型 `price_verified: true` 且 `price_source` 可访问
- [ ] `notes.md`（中文）＋ `notes.en.md`（流水线生成，标记状态写在文首）
- [ ] `build_site.py --check` ✔；站点三列、保真度、$／成功、每步延迟与 `summary.csv` 抽查一致
- [ ] **v1 正式批与回归门**（内部工单 ⑬，10-10）：v1＝三模型各 30＋random／greedy／astar 三条脚本基线＋附真值提示行（(a) 批，不新跑；均在站点「基线与天花板（读真值·非视觉）」单列，不进模型榜，裁定 2026-10-10-06）；跑前自检 `.venv/bin/python -m pytest tests/test_registry.py -q`（registry 对 `oracle`／未登记名报错退出）＋ `bash tools/prereg_check.sh` rc 0；跑后 ⑭ 回归门＝v1 astar 列对 `d4af9ae` `results.csv` 字段 1–15 `diff` 空、greedy 列对 tag 内 `2026-09-25-pilot01-baselines` greedy 30 行 `diff` 空（命令见 `audits/first-issue-due-diligence/README.md` ⑭），任一不符即停报 CSO
- [ ] `editions.csv`：`trigger_released_at`、`published_at`、`n_sim`、`n_real`、`human_hours`、`status`
- [ ] 四平台同时段发布，链接回填 `notes.md`
- [ ] **站点页脚放公众号搜一搜二维码**（内部工单 §4）：绿底为主、白底备，文件在 `site/assets/brand/accounts/wechat/`；不上人牌页 crescens.one
- [ ] **10-22 前资料刷新**（内部工单 §4）：主理人重传 X／YouTube 带 `-v3.3` 的横幅（09-29 已重传一次；用平台预览核手机层第三行，被裁则另出两行版）并回填站点链接；公众号ID 设好后 `docs/accounts-checklist.md` 补一行，crescens-one `site_links.json` 的公众号仍是文本列
- [ ] **公开前凭证闸（10-22 公开硬门；内部工单 §4）**：`bash tools/push_gate.sh --check` rc 0（凭证审计＋gitleaks 全史）。仓一公开，全部历史提交随之可见，所以扫全史，不只扫最新提交。基线 2026-09-27：gitleaks 全史 22 个提交（含分支 `codex/内部工单`）零命中；登记在册 1 处误报（`.gitleaksignore`，翻译记忆块 id，非密钥）；凭证审计零剩余命中，allowlist 在册 29 行（均词表词，密钥形态 0）。公开当日在当时的 HEAD 重跑，有新命中就逐条登记或改文件，未清零不公开。**加核一项（内部工单 附条修订1）**：首期尽调 (c) 的文件与 Google 密钥不得出现在本仓全历史——`git log --all --name-only --format= | /usr/bin/grep -i -E "internal-reference|due-diligence/c-"` 与 `git grep -I -l -e "AIza" $(git rev-list --all)` 两条均须空输出
- [ ] **素材冻结 10-21**（内部工单 §三；原 10-25，随发布日 10-22 改）：中英渲染素材（`notes.md`／`notes.en.md`、双画框成片或首期替代片、封面图）＋四平台文案定稿入仓 `episodes/editions/<期>/posts/`（`youtube.md`／`x.md`／`bilibili.md`／`wechat.md`，中文真源、英文经 `render_en.py`）；冻结后只许勘误级改动，改了就在 `notes.md` 记一行
- [ ] **定时预置 10-21**（内部工单 §三；原 10-27）：按发布日卡「四平台定时发布逐步卡」（主理人操作卡，内部件、不在本仓）预置定时；发布小时＝**UTC 2026-10-22 13:00**（裁定 2026-10-20-01 改日，反转裁定则 10-23；北京 21:00／美东 09:00 EDT／美西 06:00 PDT；一律以 UTC 标注）；平台当时无定时选项的在卡上标「当场手发」；发布日主理人动作只剩核预览、开关、手发项
- [ ] **外部时间戳齐备**（内部工单 验收入卷，10-10；裁定 2026-10-10-02）：`protocol/timestamps/` 全部 `.ots` 已 `ots upgrade` 至比特币 attestation，并逐件 `ots verify` 通过（本机无比特币节点时用客户端的无节点校验模式 `ots --no-bitcoin verify <file>.ots`，核至区块高度）；命令与尾行入发布日回执；upgrade 产生的 `.bak` 不入库

## 7 T0 段：GitHub Pages 发布演练结论（内部工单 P5；2026-09-25 实测）

- 演练：一次性公开仓 `pages-drill-20260925`（**补丁 3 P4 改判：保留、保持私有、更名 `pg-pages-rehearsal`，登记 内部治理仓 `IGNORED.md` 免检，不删**；只含占位 `index.html`＋精简 `pages.yml`，不含协议与数据），`gh repo create --public` → `gh api -X POST repos/<owner>/<repo>/pages -f build_type=workflow`（先开 Pages、源＝Actions）→ `git push` → 工作流 build＋deploy → `curl` 200。不改「proving-ground 10-29 前私有」裁定。
- 用时（UTC）：建仓 12:59:39 → 开 Pages 12:59:45 → 推送 12:59:48 → 工作流开始 12:59:55 → 部署成功 13:00:19 → 站点 200 于 13:00:22；**建仓到可访问 43 s，工作流本体 24 s**。发布日按 **≤5 min** 预留即可，含首次开 Pages。
- 坑：①Pages 必须在第一次 push 之前用 API 开（`build_type=workflow`），否则首个工作流的 `configure-pages` 会因站点未启用而失败；也可在 `actions/configure-pages@v5` 加 `enablement: true`，但需要 admin token。②站点地址固定为 `https://<owner>.github.io/<repo>/`，`site/` 内相对路径（`i18n/`、`data/`）可直接用；自定义域名本次未测（暂无域名）。③`gh` 的 OAuth token 默认没有 `delete_repo` 权限，`gh repo delete` 报 403；删仓前须主理人跑一次 `gh auth refresh -h github.com -s delete_repo`（浏览器授权）。演练仓已改私有（`gh repo edit --visibility private`），改私有后 Pages 站点仍返回 200（缓存／未即时下线），删仓才彻底——**补丁 3 P4：不删，保留为私有演练仓 `pg-pages-rehearsal`（10-29 前可再演练一次）；删除授权取消**。④`ubuntu-latest` 将于 2026-10-19 迁 Ubuntu 26（工作流提示），10-29 发布日前跑一次 `workflow_dispatch` 复核。
- 正式发布 2026-10-22 13:00Z 的顺序（10-20 改：公开的是**新建的单提交快照仓** `physicalaipg/proving-ground`，原仓改名 `proving-ground-archive` 留档私有）：a 主理人当场放行（拍板，不预置）→ **b 新仓改公开** `gh repo edit physicalaipg/proving-ground --visibility public` → c `gh api -X POST repos/physicalaipg/proving-ground/pages -f build_type=workflow` → d `gh workflow run pages.yml`（或 `git push`）（触发 `pages.yml`：`build_site --check`＋`selftest_site`＋`manifest verify` 过了才 deploy）→ `curl` 站点 200 → 地址写入 内部治理仓 护照 PG 锚点节。
