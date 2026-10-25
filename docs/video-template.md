# 首期视频模板（内部工单）· 无旁白 · 双语字幕 · 俯拍＋机载双画框

> 依据：内部工单 卡 D「首期视频模板（无旁白、双语字幕）」、裁定 2026-09-25-12（一个真源、两个渲染，发布日同时出）。
> 工具：`tools/make_subtitles.py`（日志→双语字幕）、`tools/compose_video.py`（双画框合成，ffmpeg）。本机 ffmpeg 须含 libass／freetype（瘦身版 `ffmpeg` 公式缺 `subtitles`／`drawtext` 滤镜，09-25 实测；`brew install ffmpeg-full` 在本机 ~/.brew 前缀无 bottle、源码编依赖失败）→ 用官方源码编精简版到 `~/.local/ffmpeg-libass`（脚本化：`bash tools/setup_ffmpeg.sh`，`--check` 只核对；内部工单），`compose_video.py` 自动查找。
> 示例产物（内部工单 P4，基线批 greedy seed 1000 真实日志、非 dry-run）：`docs/examples/pilot01-baselines_greedy_seed1000_dual.mp4`＋同名 `.srt`／`.zh.srt`／`.en.srt`＋首帧 `.png`；俯拍用色块占位（孪生无俯拍）。
> 原则：**视频只是日志的可视化**——画面来自录像，字幕来自 `logs/*.jsonl`，数字来自 `summary.csv`；不配音、不加评论、不剪掉失败。

## 0 首期配置（内部工单 §二，2026-10-09；覆盖本模板中与之冲突的首期条款）

| 项 | 首期值 |
|---|---|
| 素材 | **纯仿真渲染**（孪生第一人称回放＋俯视渲染），不用真机或实拍；主理人无拍摄项；俯拍／机载双画框与实拍色彩门首期不适用 |
| 时长与版本 | 横版 2～3 分钟；同一剪辑出中英两版（YouTube 英文、B 站中文）；无人声，只用字幕卡 |
| 结构 | 头条结论 → 三家第一人称回放与 A*、random 并排 → 内部工单三分类表 → 真机列「待锚」＋按协议投稿复跑入口 → 片尾站点链接 |
| 选段 | 每家取中位仿真分回合一个、最高分回合一个，同分取种子号小者（取代 §1「总分最接近中位数」的首期用法）；规则先提交、后渲染；种子号写 `notes.md` |
| 衍生件 | X：30～45 秒剪辑＋链接；公众号：中文图文（榜单图、三分类表、GIF、链接） |
| 数字 | 画面内一切数字只来自 build 流水线，不手打 |
| 节奏 | 粗剪即开；定剪候尽调 (a) 结论；素材冻结 10-25 |
| 禁入 | (c) 内部参照与 Gemini 的任何内容 |

## 1 两类视频，都随发

| 类 | 内容 | 时长 | 去向 |
|---|---|---|---|
| **未剪辑原片**（每模型每回合一支或整场一支） | 俯拍原片＋机载原片，不剪、不加字幕，只在文件名与索引里标期／模型／种子 | 原长 | 上传到可外链的位置（YouTube 不公开列表／B 站／GitHub Release 附件），sha256、字节数、时长写入 `episodes/editions/<期>/video.csv`；随发 |
| **双画框剪辑**（首期：每模型 1 支代表回合 ＋ 1 支汇总） | 本模板产物：左俯拍、右机载，顶部信息条，底部双语字幕，片尾榜单卡 | 单回合 ≤ 80 步 × 2.5 s ≈ 3.5 min；汇总 ≤ 8 min | B 站＋YouTube 同一支文件；X 发 ≤ 2 min 片段；公众号发图文＋帧图 |

代表回合怎么选：**不挑最好看的**。取该模型 `results.csv` 里总分最接近其中位数的种子；三模型用同一种子优先（同一布局横向可比）。选法写进 `notes.md`。

## 2 画面规范（1920×1080，30 fps）

```
┌──────────────────────────────┬──────────────────────────────────┐
│                              │  <期> · <模型> · seed <N> · v0   │  ← 信息条 36px 白
│                              │  stop · look · think · act | …   │  ← 副标 22px 灰
│        俯拍 1080×1080        │  ┌────────────────────────┐      │
│   （场地 2×2 m 方，等比      │  │   机载 800×600 (4:3)   │      │  ← 机载画面 y=240
│     放大后居中裁方）         │  │   模型看到的那一帧     │      │
│                              │  └────────────────────────┘      │
│                              │        第 12 步 · 目标 2 号 · 前进 │  ← 字幕中文行
│                              │  Step 12 · target #2 · forward · "…" │  ← 字幕英文行（含模型 note）
└──────────────────────────────┴──────────────────────────────────┘
```

- 俯拍：固定机位、场地满幅、检查点编号朝上可读；不加轨迹叠加（真机侧 内部工单 若产出自动计分叠加层，作为可选第二版本，原片仍随发）。
- 机载：**就是送模的那张图**（512×384 等比放大到 800×600），与日志一一对应；孪生演示用 `frames/` PNG 序列。
- 信息条：期号、模型 ID（与 `models.yaml` 键一致）、种子、协议版本；副标固定一句 `stop · look · think · act | no narration · bilingual subtitles | raw logs & unedited video published`。
- 片头卡（3 s）：由字幕第 1 条承担（期 · 模型 · 种子 · 协议），不另做片头动画。
- 片尾卡（4 s）：字幕最后一条＝该回合结果（到达 x/5 · 碰撞 · 步数 · 美元）；汇总视频片尾另加一张静态三列榜单图（由站点截图，`site/` 本地预览 → 浏览器截图，不手画）。
- 无旁白；音轨只保留俯拍机位环境音（机器人电机声即「真机证据」），或 `--mute`。不加配乐。

## 3 字幕规范

- 来源：`tools/make_subtitles.py <jsonl> --model … --edition … [--t0 录像起始 epoch | --step-seconds 2.5]`，生成 `.srt`（双语两行，烧录）、`.zh.srt`、`.en.srt`（平台分轨）。
- 内容只有五种事实：步号／目标检查点／动作、碰撞、重问（不可解析或 API 错）、模型 note 原文（英文行，≤70 字符）、回合结果。**不写形容词**。
- 中文行在上、英文行在下；烧录样式：白字黑边约 30 px，右列底部（`force_style` 见 `compose_video.py`；注意 libass 把 SRT 按 PlayRes 384×288 处理，边距与字号须按比例换算，直接写 1080p 像素会把字幕推出画面——09-25 实测坑）。
- 真机对齐：录像起始 epoch（`recorded_at`）写进 `video.csv`；日志每步 `t` 减去它即字幕时间。误差 >0.5 s 时先校 `--t0`，不手挪单条字幕。
- 平台：B 站上传 `.srt`（中文为主，英文可作第二轨）；YouTube 上传 `.zh.srt` 与 `.en.srt` 两轨（Studio → 字幕）；X 用烧录版短片。

## 4 制作步骤（每期，目标人手 ≤ 30 min，计入 human-hours.csv）

1. 选代表回合（§1 规则），记进 `notes.md`。
2. `python3 tools/make_subtitles.py episodes/real/<run>/logs/<模型>/seed<N>.jsonl --model <模型> --edition <期> --t0 <epoch> --out episodes/editions/<期>/subtitles/<模型>_seed<N>`
3. `python3 tools/compose_video.py --overhead <俯拍.mp4> --onboard <机载.mp4> --srt episodes/editions/<期>/subtitles/<模型>_seed<N>.srt --title "<期> · <模型> · seed <N> · v0" --out episodes/editions/<期>/video/<期>_<模型>_seed<N>_dual.mp4`
4. 未剪辑原片与双画框成片一起 `python3 tools/manifest.py hash <文件>` → 填 `video.csv`（`view` ∈ overhead｜onboard｜dual｜summary）；成片本体不入仓（`.gitignore` 排除 `episodes/editions/*/video/`），只入索引。
5. 上传四平台（`docs/accounts-checklist.md`），把外链填回 `video.csv` 的 `url` 列；`python3 tools/manifest.py gen episodes/editions/<期>`；`python3 tools/build_site.py`。

## 5 命名

- 原片：`<期>_<模型>_seed<N>_overhead.mp4`／`_onboard.mp4`；整场原片：`<期>_<模型>_session<K>_overhead.mp4`
- 成片：`<期>_<模型>_seed<N>_dual.mp4`；汇总：`<期>_summary_dual.mp4`
- 字幕：`<期>/subtitles/<模型>_seed<N>.srt|.zh.srt|.en.srt`

## 6 发布前自检（全部为「是」才发）

- [ ] 成片字幕的步数、碰撞数与 `results.csv` 该行一致
- [ ] 信息条模型 ID 与 `models.yaml` 键一致，协议版本与 `editions.csv` 一致
- [ ] 原片 sha256 已入 `video.csv`，`SHA256SUMS` 已重生成并 verify 通过
- [ ] 无旁白、无配乐、无评论性文字；失败回合未被剪掉（汇总视频若只放代表回合，`notes.md` 写明选法）
- [ ] 中英字幕轨都已上传（B 站／YouTube），X 片段 ≤ 平台时长上限（以官方页面为准）
