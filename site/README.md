# site/ · 双语静态榜单站（内部工单）

- **数据源只有 `episodes/`**：`python3 tools/build_site.py` 读 `episodes/editions.csv` 与各期 `runs.csv` 所引 run 的 `summary.csv`／`meta.json`，写 `site/data/leaderboard.json`（＋所引 CSV 副本）；页面 `app.js` 只渲染这个 JSON。`--check` 在 CI 里挡住手改与忘重建。
- **三列榜单**：仿真分／真机分／迁移差（真机 − 仿真，头条）；另列成功率、碰撞、路程比、每次成功美元、每步延迟（均值，P95 悬停）、N；KPI 行：孪生保真度（|迁移差| 均值，≥5 模型加 Spearman）、发布用时（对照 48h／72h）、人手小时、本期 API 花费。
- **双语**：界面词表 `i18n/ui.json`（zh 真源、en 标签）；`?lang=en` 或右上切换，记在 localStorage；正文（协议、发布说明）的英文由 `tools/render_en.py` 生成，站点只链接。
- 无框架、无构建步骤、无外链脚本；深浅色随系统；手机宽度表格横向滚动。

## 本地预览

```bash
python3 tools/build_site.py
python3 -m http.server -d site 8000      # 打开 http://localhost:8000/ （file:// 打不开：fetch 需要 HTTP）
```

## 部署（GitHub Pages）

- 工作流 `.github/workflows/pages.yml`：push 到 `main` → `build_site.py --check`＋`selftest_site.py` → 上传 `site/` → 部署。
- 仓库 Settings → Pages → Source 选 **GitHub Actions**（一次性，主理人或维护者经 `gh` 办）。私有仓的 Pages 需付费方案；本仓 10-22 13:00Z 随首期公开，公开后即免费可用。预期地址 `https://<用户名>.github.io/proving-ground/`（公开后写入 内部治理仓 护照 PG 锚点节）。
- 页面资源全部相对路径，子路径部署无需改动。
