# protocol/ · 协议与冻结物

| 文件 | 说明 |
|---|---|
| `v0.md` | Course 01「看图走路」协议 v0，**中文真源、中文为准**（英文与中文不一致处以本文为准；harness 常量、提示边界、参考单元＝UGV02 底盘规格、基线与天花板、模型单价、正式 N 规则） |
| `v0.en.md` | 英文渲染（**便利译本，非规范性**；文首印 "Chinese version governs; English is a convenience translation"），由 `tools/render_en.py build protocol/v0.md` 生成；`<!-- MT-UNREVIEWED -->` 标记＝机译未经人工校对，校对流程见工具文首 |
| `i18n/v0.tm.json` | 翻译记忆（块键＝中文块 sha256 前 12 位；中文改一字即失效重译） |
| `glossary.csv` | 术语表（zh,en,check,note）；build 时逐块核对，不符打 `<!-- GLOSSARY -->` 标记 |
| `prompt_v0.md` | 提示模板（冻结物，sha256 见 `v0.md` 头部） |
| `kit-candidates.md` | 廉价底盘候选清单（内部工单 P0c；UGV02 推荐） |

校对怎么做：直接改 `v0.en.md` 里标记块下的英文 → `python3 tools/render_en.py review protocol/v0.md --from-en --by <名>` → `build` 去标记。术语改动改 `glossary.csv` 再 build。

回译自检（内部工单 P1②）：英文块盲回译成中文（回译者不看中文真源）→ 与中文真源逐块比对 → 语义漂移块重译 → review 去标。逐块记录见 `i18n/v0.backtranslation-2026-09-25.md`。
