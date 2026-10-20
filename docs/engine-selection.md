# Twin-01 引擎选型记录（内部工单 P1，2026-09-25）

> 约束（裁定 2026-09-25-05）：①第一人称相机图 ②摩擦与碰撞 ③CPU 可跑 ④域随机化（光照/纹理/摆放/摩擦，带种子）；候选 MuJoCo／Genesis／PyBullet。本机＝Apple M2 Pro，12 核，16 GB，macOS 25.6，Python 3.13.12。
> 结论：**MuJoCo 3.14.0**。先出本记录再写代码；有异议 CSO 改。

## 一、四条约束逐项对照

| 约束 | MuJoCo 3.14 | PyBullet 3.2.x | Genesis 0.3.x |
|---|---|---|---|
| ①第一人称相机图（离屏、无窗口） | `mujoco.Renderer` ＋ `MUJOCO_GL=cgl`（macOS 原生离屏，Linux 用 `egl`）；**本机实测 640×480 ≈ 2.0–2.3 ms/帧，320×240 ≈ 1.7 ms/帧**（含一步物理） | `getCameraImage(..., ER_TINY_RENDERER)` 纯 CPU 软件光栅；实测见 §三 | Rasterizer 基于 PyRender/OpenGL；官方以 GPU 为主，CPU 后端可跑但非主路径；实测见 §三 |
| ②摩擦与碰撞 | 每 geom 独立 `friction`（滑/滚/扭三系数）、软接触求解器、`forcerange` 限力（底盘顶到障碍即停不穿模）；碰撞事件从 `data.contact` 逐步读出 | Bullet 刚体接触，`changeDynamics` 设摩擦；接触点 `getContactPoints` | 刚体求解器可用；接触查询 API 尚在变动 |
| ③CPU 可跑 | 单 wheel（≈几十 MB），无 torch；物理与渲染全 CPU；Python 3.13 直装成功 | 单 wheel；Python 3.13 需现场编译（见 §三） | 依赖 torch＋taichi 等，安装体积大（数百 MB～GB 级）；CPU 后端为降级模式 |
| ④域随机化带种子 | 场景由 Python 按种子生成 MJCF（光照位/色、材质 rgba/纹理、物体摆放、摩擦系数全是 XML 参数），零额外机制 | 可做，但 URDF 装配式随机化要自己拼；纹理换贴图较绕 | 可做（Python 场景构建），但 API 在 0.2→0.3 间有破坏性变动 |

## 二、否决理由与最终选择

- **PyBullet 否决**：①维护停滞（上游 bullet3 近两年无功能版本），Python 3.13 无预编译 wheel，本机源码编译失败（§三）；②TinyRenderer 为软件光栅，帧时不可能低于 MuJoCo 的原生 GL；③随机化要绕 URDF。**保留为兜底**：若 MuJoCo 在 Linux 跑测机上 EGL 不可用，可换 PyBullet，接口层（`harness/interface.py`）不变。
- **Genesis 否决**：①安装重（torch，环境 2.8 GB）、以 GPU 为设计目标，CPU 后端实测 32 ms/帧（§三），与「CPU 可跑」冲突；②版本年轻、API 变动快，7 个工作日时限内不宜承担迁移风险；③本任务是 2×2 米平面导航，不需要它的可微/多物理特性。
- **MuJoCo 选定**：四条约束全部满足且本机已实测；DeepMind 维护、LeRobot 社区仿真同源（后续 LeKiwi 类底盘可直接用 MJCF 描述）；单进程 2 ms/帧意味着 3 模型×N=100 的仿真耗时可忽略，瓶颈只在模型 API 时延。

## 三、本机实测（同一台 M2 Pro，CPU，无窗口）

| 引擎 | 安装 | 320×240 | 640×480 | 备注 |
|---|---|---|---|---|
| MuJoCo 3.14.0 | `pip install mujoco` 一次成功 | 1.7 ms/帧 | 2.0 ms/帧（default）／2.3 ms/帧（cgl） | 场景＝平面＋圆柱底盘＋2 障碍，每帧含 1 步物理 |
| PyBullet 3.2.7 | **失败**：Python 3.13 无预编译 wheel，`pip install pybullet` 源码编译报错（22:44 重试同样失败） | — | — | 未能实测；需另建 3.11 环境才可装，本任务不再投入 |
| Genesis（pip 装得 `genesis-world`，需手装 torch，环境 2.8 GB） | 首次失败（缺 torch），补装 torch 后成功 | 32.1 ms/帧 | — | CPU 后端＋Rasterizer；帧时 ≈ MuJoCo 的 19 倍，且渲染告警 cube map 不可加载 |

## 四、随选型一起定下的实现约束（写进 `twin/`）

1. 场景不手写 XML：`twin/mjcf.py` 从 `twin/configs/course01.yaml` ＋ 种子生成；套件到货后改配置值不改码（P3）。
2. 底盘＝平面三自由度（x、y、yaw 三关节＋速度执行器＋限力），前进/转向为定时定速的离散有界动作，动作结束归零速度并静置；与真机固件「限速＋离散有界」同构。
3. 相机挂在底盘体上，高度/视场/分辨率取配置；渲染后端 macOS `cgl`、Linux `egl`（环境变量 `MUJOCO_GL`）。
4. 碰撞＝底盘 geom 与任一障碍/墙 geom 的接触在本动作内出现过（边沿触发，一动作最多记 1 次）。
