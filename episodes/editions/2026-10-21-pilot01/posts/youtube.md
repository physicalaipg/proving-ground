> 平台：YouTube｜语言：英主中副（说明栏英文在前、中文在后，同一说明栏）｜上限：标题 ≤100 字符、说明 ≤5000 字符（以上传页提示为准）｜链接位：站点链接（已填）、视频成片＝本条本身、X／B 站／公众号链接发布后回填 `notes.md`。
> 视频链接位：`<VIDEO_URL>`，视频入仓后回填。数字只取 `notes.md` 首期讲法 v1 五句与「结果」节；无旁白、双语字幕、纯仿真渲染。
> 真源＝本文件中文段；英文段按同一内容写成，发布前再对一遍。

## Title

Physical AI Proving Ground · Edition 01 — three vision-language models in a frozen Look-and-Go sim batch: 0–2/30 completed, and it is not the pipeline

## Description (EN)

Edition 01 of the Physical AI Proving Ground: open, reproducible physical-AI evaluation. Simulation first, anchored by real-robot runs.

What you see: Course 01 "Look-and-Go" under protocol v0 (pre-registered, git tag `protocol-v0-prereg`). Three models under test, one from each of three Chinese vendors — qwen3-vl-plus, glm-5v-turbo, deepseek-flash — all with thinking off, official endpoints, N=30 episodes each, same frozen seed set. Pure twin rendering (first-person replay + overhead view), no narration, bilingual subtitles, no edited-out failures.

Five things to read (Edition 01 narrative v1):
1. In the frozen protocol v0 batch the three models completed 0–2/30, and that number does not come from the pipeline: images delivered byte-for-byte (930/930), action "raw text → parsed → executed" 0 mismatches (4134 steps), and with a planning hint computed from ground truth attached at every step it is 10/10 (all three, 0 collisions).
2. Single-frame probe (qualitative, 1 seed × 3 models): all three correctly answered the number and colours of the checkpoint signs visible in the first frame — they can see the signs, they cannot read the route; the failure lies in multi-step spatial reasoning and path decisions, not in the perception front end and not in the harness.
3. Criteria footnote: the 0.40 m displacement gate ≈ two steps (median single forward step without contact 0.186 m); F2 = the model stops on its own or turns in place, F3 = collision or step cap exceeded.
4. The 80-step budget is not the main bottleneck: the 160-step observation only let deepseek reach 8 more checkpoints and complete +1; qwen/glm added 0 (observation item, not on the leaderboard).
5. "Ground-truth hint 10/10" sits in the same column as the three ground-truth-reading scripts (astar 30/30, greedy 26/30, random 0/30 — pre-registered baseline data, not a new run), "Baselines & ceiling (reads ground truth · non-visual)", and is not on the model leaderboard.

Real-robot column: anchor pending (Edition 02).
Open call: sim re-runs under the protocol (`protocol-v0-prereg`) + registration of intent for real-robot re-runs; the real-robot protocol v0 is published before Edition 02.

Leaderboard, protocol, raw logs and unedited video: https://physicalaipg.github.io/proving-ground/

Chapters
0:00 Headline
<CH_REPLAY> Three models side by side with A* and random
<CH_TABLE> Three-class failure modes
<CH_REAL> Real-robot column: anchor pending · open call
<CH_END> Links

## 说明（中文）

物理AI实验场首期。公开、可复现的物理AI评测。仿真为主，真机为锚。

本片内容：Course 01「看图走路」，协议 v0（预注册，git tag `protocol-v0-prereg`）。被测三家各一：qwen3-vl-plus、glm-5v-turbo、deepseek-flash，均思考关·官方端点，各 N=30 回合，同一冻结种子集。纯仿真渲染（第一人称回放＋俯视），无旁白，双语字幕，失败回合不剪。

首期讲法 v1 五句：
① 三家模型在协议 v0 冻结跑批中完成 0～2/30，这个数不来自通路：图像逐字节送达（930/930）、动作「原文→解析→执行」0 不一致（4134 步）、每步附真值规划提示即 10/10（三家，碰撞 0）。
② 单帧探针（定性，1 种子×3 模型）：三家都答对首帧可见检查点牌的数量与颜色——看得见牌，看不懂路；失败落在跨步空间推理与路径决策，不在感知前端、不在 harness。
③ 判据脚注：0.40 m 位移门≈两步（未碰前进单步中位 0.186 m）；F2＝模型自行 stop 或原地转向，F3＝碰撞或超步。
④ 80 步预算不是主瓶颈：160 步观察只让 deepseek 多到达 8 次、完成 +1，qwen/glm 新增 0（观察项，不进榜）。
⑤ 「附真值提示 10/10」与三条读真值脚本（astar 30/30、greedy 26/30、random 0/30，预注册基线数据、非新跑）同列「基线与天花板（读真值·非视觉）」，不进模型榜。

真机列：待锚（第二期）。
公开征集：仿真按协议复跑（protocol-v0-prereg）＋真机复跑意向登记；真机协议 v0 第二期前发布。

榜单、协议、原始日志与未剪辑视频：https://physicalaipg.github.io/proving-ground/

## Tags / 标签

physical AI, embodied AI, vision-language model, robot navigation, benchmark, simulation, MuJoCo, reproducible, 物理AI, 具身智能, 评测
