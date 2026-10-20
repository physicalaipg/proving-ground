# real/course ｜ 真机固定布局 L1（内部工单 A，2026-10-05）

- `L1.yaml`：L1 真源。`twin:` 块＝Twin-01 种子 **1017** 的布局（`python -m real.course.layout --seed 1017` 生成，`tests/real/test_course.py` 钉死），`physical:` 实物建议，`markers:` 回位十字，`cameras:` 机位建议，`registration:` 登记阈值。Twin-01 同种子布局＝真机对照布局，保真度对比只用 L1（令文 A4）。
- `make_card.py`：一页布局卡 → `L1-card.html`（仓内，可审）＋ `~/Downloads/内部工单-layout-card.pdf`（Chrome headless 打印）。
- `register.py`：场地登记。`points <登记照>` 点选四角与各件脚下十字 → `points.json`；`solve points.json --write` 以四角做单应量实际坐标，全部偏差 ≤ 0.05 m 且起点朝向 ±10° 才写 `L1-measured.yaml`（实测值即常量）；超阈列出要移的件、不改孪生。`load_course()` 给真机 `Robot.course()`：有实测取实测、无则取 twin 值。
- 坐标系：场地中心为原点，x 右 y 上（俯视），yaw 自 +x 逆时针；起点坐标＝车体中心，车头＝相机所装的一头。
