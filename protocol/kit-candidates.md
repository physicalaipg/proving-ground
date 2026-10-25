# Course 01「看图走路」廉价移动底盘候选清单

## 清单 v2 · 09-27 裁定

> 依据：10-01 硬件 go/no-go 已于 2026-09-27 办结（裁定 2026-09-27-10；内部工单＋修订1）。首季锚点＝微雪 UGV02；自有麦轮车 no-go，不作首季锚点、不作备机。下方原候选表保留不改。
> 09-28 改（裁定 2026-09-28-01；内部工单）：上一行「不作备机」一句改为——旧车＝RIG 国庆台架冲刺对象＋10-04 兜底桥接平台，备机地位恢复；10-04 前 UGV02 未到手才启桥接。首季锚点＝UGV02 维持，清单 v2 不变。若兜底触发、首季真机锚点为旧车，协议真机段须标「非参考平台（板卡厂商麦轮按差速运行）」。

- **沿用件**：无。
- **补购件**：UGV02（含国标适配器配置）／18650×3（≥2200 mAh、4C）／UVC 相机 640×480 约 70°／USB 线＋3–5 m 延长线／导轨相机支架 0.15 m／场地件（3×3 m 单色地面、胶带、5 检查点标识）。
- **不用件（留 RIG）**：
  - Pi 4B：属旧车控制链的上位机，首季走笔记本有线直连，控制链不匹配。
  - RPLIDAR C1：Twin-01 已冻结，只有机载相机一路观测，加雷达即改仪器。（10-14 已物理装车，顶部离地 18 cm；本季不接入观测链，照片见 内部治理仓 `35_papers/p5-realbot/fieldwork/measure-2026-10-14/`。）
  - 板卡厂商麦轮车＋YB-EET01：micro-ROS 链与 UGV02 的 JSON 串口链不匹配；从未上电，未验证；麦轮运动学与冻结的 Twin-01 不符。
  - 板卡厂商 7.4 V 2000 mAh 2S 电池包：UGV02 只认 3S 18650 仓。
  - OV5647 CSI 相机 Rev 1.3：非 UVC、约 54° 视场。
- **下单回执＋配置截图：待主理人。** 回执到后由维护者填实际价与驱动板版本。
- 09-28：UGV02 下单暂缓，候旧车固件路线真相表（裁定 2026-09-28-04；内部工单）。
- 09-28 定路线（裁定 2026-09-28-05；内部工单）：首套＝旧车 YB-EET01 V2.0 刷 JSON 串口固件，采购 0；UGV02 转兜底，备份日与三门任一失守当日下单。固件在 `real/firmware/yb-eet01-json/`，已编译未烧录。协议真机段标「非参考平台（板卡厂商麦轮按差速运行）」。上面「不用件」里旧车一条与本行不符处以本行为准。
- 09-28 补购裁定（裁定 2026-09-28-07；内部工单）：「采购 0」只指底盘。上限 ¥250。CSI 相机不能直连笔记本。真机拖线件定型三件（内部工单；参数见 `real/README.md`「真机拖线件」节），上面补购件里相机与延长线两项以本行为准：
  - 相机：MF-200 1080P＋2.8 mm 无畸变镜头＋金属外壳（京喜自营），USB 2.0 UVC；09-28 下单。
  - 延长线：绿联 USB3.0 公对母信号放大延长线 5 m（20826／US175）；09-28 下单。
  - hub：主理人自有绿联 USB3.0 hub，型号待核；不购。
- 铜柱（内部工单）：主理人自有一袋，**长铜柱 3 cm**（主理人 09-28 报数，规格螺纹未报）。修订3 的相机布置写的是四根 M3×50，比手头的长 2 cm。购否候审定方定，未下单。
  - **本项作废**（内部工单，09-28；上文保留不删）：铜柱不购。布置改用手头 M3×30 铜柱，公母型则 30＋20 叠至 50，母母型 30 单用；见 `real/README.md`「真机拖线件」节布置段。
- **下单回执＋实价**：相机 ¥213、延长线 ¥95，合计 ¥308（主理人 09-28 报数；**截图已入** 内部治理仓 `35_papers/p5-realbot/fieldwork/purchase-2026-09-28/`，两张，金额与报数相符）。**超上限 ¥58**（上限 ¥250，裁定 2026-09-28-07）；主理人 09-28 确认已下单、超限属实（裁定 2026-09-28-12）。首套预算 ≤¥1,500 内，底盘采购 0。

### 下单前核对 · 09-27（维护者；主理人提供国内官网商品页截图）

> 来源：国内官网商品页截图（waveshare.net，主理人 09-27 截）；英文 wiki <https://www.waveshare.com/wiki/UGV02>（09-27 落盘逐条 grep，sha256 前 12 位 `e60140a0aec3`）；英文商品页 <https://www.waveshare.com/ugv02.htm>（经摘要工具读取，未落盘）。中文 wiki 由主理人 09-27 存成 PDF 提供（2 页，sha256 前 12 位 `31056c1a7535`），抽出文字后逐条核过，与英文 wiki 在下表各项上一致；PDF 里「配置清单」与「板载接口」两处图片未渲染出来。中文商品页被站点防火墙拦截；「配置清单」页签由主理人另截一图提供（同日）。

| 项 | 值 | 来源 |
|---|---|---|
| 型号／SKU／品牌 | UGV02／24687／Waveshare | 截图 |
| 价格 | ¥856.48（含普票，1 件）；2 件起 ¥846.38 | 截图 |
| 退换 | 7 天无理由退换 | 截图 |
| 外形／重量 | 252×230×94 mm／2 kg | 英文商品页 |
| 轮 | 六轮四驱；胎径 80 mm、胎宽 42 mm | 英文商品页 |
| 行驶速度 | 0.05～1.3 m/s | 英文商品页 |
| 电机 | JGB37-520 直流减速电机，减速比 1:30，空载 333 RPM，额定 12 V | 英文 wiki |
| 编码器 | 四个电机都驱动，从控板只读前轮两路编码器 | 英文 wiki FAQ 2 |
| 配置清单（国内商品页） | 包装盒；越野套件（整机出货）；配件包；电源 12.6 V 2 A；USB 线；赠品三件＝鱼骨导轨、扩展平台、摄像头支架。**清单里没有电池** | 配置清单截图 |
| 电池 | 18650×3 串联，**不随货，须另买**；建议 ≥2200 mAh、4C 放电。「不带保护板」只见于英文 wiki 的 FAQ；中文 wiki 写 UPS 模块自带保护电路 | 配置清单截图、中英文 wiki |
| 充电器 | 12.6 V 2 A，中文 wiki 写「配套」，英文 wiki 写随货；首次使用须先插充电器激活 UPS 模块才有输出 | 中英文 wiki |
| 出厂固件 | 开机 OLED 显示 `UGV Rover Version:0.96` 即新版；否则须用官方下载工具更新（工具是 Windows 程序） | 中文 wiki |
| 上位机连接 | 从控板 USB（接口⑥，CP2102 转串口），**须拆开底盘才够得到**；或 40PIN 上的 UART。115200 | 英文 wiki |
| 心跳 | 3 秒内无新运动指令自动停 | 英文 wiki |

对清单 v2 的三处补充：

1. 电池须另买（配置清单无电池），选不带保护板的。反接时电池模块上的 LED 会亮；反接禁止充电，wiki 原文写有几率引起爆炸。
2. 「含国标适配器配置」：电源 12.6 V 2 A 随货（配置清单）。国内商品页没有插头选项，截图上看不出插头制式，到货核对；英文商品页有 EU／US 两个插头选项。
3. USB 线随货一根（配置清单），长度与接口制式图上看不出；连从控板须从底盘内部引出，3–5 m 延长线仍须另买，走线与固定方式到货后定。
4. 赠品含摄像头支架一件，能否替代清单 v2 的「导轨相机支架 0.15 m」到货后量高度再定，支架先不另买。

与仓内既有表述的出入（均列到货核对，不因此改驱动）见 `real/docs/ugv02-protocol.md` §7。预算：首套 ≤¥1,500，底盘 ¥856.48 后余 ¥643.52，供电池、相机、线材、支架与场地件。

### 新版驱动板核对 · 09-28（维护者；内部工单 P2）

> 来源（2026-09-28 curl 落盘后 grep，括号内为 sha256 前 12 位）：英文 wiki <https://www.waveshare.com/wiki/UGV02>（`f702f6d92905`）；英文商品页 <https://www.waveshare.com/ugv02.htm>（`27b9c8a42d52`）；从控板 wiki <https://www.waveshare.com/wiki/General_Driver_for_Robots>（`6817c254192b`）；固件源码 <https://github.com/waveshareteam/ugv_base_ros> 提交 `2e7df97`（2025-11-28）。国内商品页 <https://www.waveshare.net/shop/UGV02.htm> 与中文 wiki <https://www.waveshare.net/wiki/UGV02> 仍被站点防火墙拦截，未取到内容。英文 wiki 的落盘哈希与 09-27 那次（`e60140a0aec3`）不同，两次文件没有逐行比过。

| 项 | 结果 | 来源 |
|---|---|---|
| 串口 JSON 速度命令 | 两条都在：`{"T":1,"L":0.5,"R":0.5}`（范围 ±0.5 m/s，闭环）与 `{"T":13,"X":0.1,"Z":0.3}`（m/s、rad/s） | 英文 wiki「JSON Command Set」；`ugv_base_ros` `ROS_Driver/json_cmd.h` 第 80–87 行 |
| 主机侧口 | 两条路：从控板 USB（Type-C，CP2102，接口⑥），**须拆开底盘**；或 40PIN 上的 UART，wiki 未写要拆壳。115200 | 英文 wiki「Serial/USB Communication」与 FAQ 4；从控板 wiki |
| 电池 | 18650×3 串联，不随货；建议 ≥2200 mAh、4C；FAQ 1 写用不带保护板的电池 | 英文 wiki「Precautions」与 FAQ 1；英文商品页「Battery support」 |

三项与 09-27 下单前核对一致，清单 v2 不因本节改动。商品页与 wiki 都没有「新版驱动板」字样：商品页写从控板是 General Driver for Robots，wiki 另提到 ROS Driver for Robots。到货的是哪一块板，拆壳后看板上丝印。

`ugv_base_ros`（wiki 的从控程序链接指向这一支）与 `real/docs/ugv02-protocol.md` 的差异。本节只报不改，记 X2 内部工单候发；出厂固件属哪一支到货才知道：

| 项 | `real/docs/ugv02-protocol.md`（据 `ugv_base_general`） | `ugv_base_ros` `2e7df97` | 对驱动层的影响 |
|---|---|---|---|
| 回显缺省 | 开（§1） | 关（`ugv_config.h`：`uartCmdEcho = 0`） | 无，驱动开头本就发关回显 |
| 连续反馈缺省 | 关（§2） | 开，附加间隔 50 ms（`baseFeedbackFlow = 1`） | `feedback()` 发 `T=130` 后读到的可能是连续流里的旧帧；驱动未关连续反馈 |
| `T=13` 刷新心跳 | 刷新（§2） | 不刷新，`uart_ctrl.h` 的 `CMD_ROS_CTRL` 分支没有更新 `lastCmdRecvTime` | 驱动只发 `T=1`，不受影响；mock 把 `T=13` 当作刷新 |
| 反馈字段 | `L`、`R`、`r`、`p`、`y`、`temp`、`v`；无累计里程（§3） | `L`、`R`、加速度、角速度、磁力计各三轴、`odl`、`odr`（累计里程，厘米）、`v`（×100 的整数）；`r`、`p`、`y` 被注释掉 | 驱动只读 `L`、`R`，不受影响；里程可改读板端累计值 |
| 每圈脉冲数 | 1650（§5） | 660 | 驱动只把它存在 `UGV02Config` 里，不参与换算；默认值 1650 到货核对 |
| 速度闭环 | 只在型号编号 3 走 PID（§5） | `setGoalSpeed` 对所有型号走 PID | 与 wiki「闭环」说法一致 |
| `{"T":0}` 急停 | 本固件无（§4） | 有，`CMD_EMERGENCY_STOP`，处理后把目标速度置 0 | 可作急停附加命令，到货核对后再定 |
| 开机 OLED | 未记 | 源码写 `ugv_base_ros.git`／`version: 0.96` 两行，与 wiki 的 `UGV Rover Version:0.96` 字样不同 | 见 `real/README.md` 到货首测卡第 ① 条 |

---

用途：2×2 m 室内场地、5 个视觉标记检查点、3–5 个障碍；停-看-想-动回路（静止取图→调多模态模型→前/左/右/停固定步长离散动作）；不上机械臂。
首套预算 ≤ ¥1,500（底盘＋相机＋主控板；电池／树莓派另计处均已标明）。
汇率假设：1 USD ≈ ¥7.1（2026-09 粗算，非查证值；官网美元价 × 7.1 仅作预算参考，实际到手价以国内渠道为准）。

---

## ① 结论与推荐项

**推荐：微雪 Waveshare UGV02（六轮四驱、带编码器、ESP32 从控、JSON 串口协议），官网 $149.99（≈ ¥1,065），另配 USB 相机 ≈ ¥48–100 → 底盘＋相机＋主控板合计约 ¥1,110–1,170，在预算内；三节 18650 电池与树莓派另计（本课可不装树莓派，见下）。**

推荐理由：
1. **离散有界动作有硬件基础**：UGV02 四个驱动电机带编码器，从控 ESP32 做 PID 闭环速度控制，`{"T":13,"X":0.1,"Z":0.3}` 直接以 m/s／rad/s 下发线速度与角速度；板载 9 轴 IMU 可读航向角（`{"T":130}`）。「前进固定距离／转固定角度」可在上位机 Python 用「闭环速度 × 时间」＋ IMU 航向校正实现。同系的 WAVE ROVER **无编码器**（官方 wiki 原话：速度值只是 PWM 占空比），做不到闭环，故不选。
2. **急停与限速现成**：固件内置心跳——3 秒内无新运动指令自动停车（官方 wiki）；`{"T":0}` 为急停指令（`ugv_rpi/base_ctrl.py` 中的 `gimbal_emergency_stop`）；速度上限由上位机在 X/Z 数值上限幅即可。
3. **原生 Python，不需要 ROS**：ESP32 通过 GPIO UART 或 USB 串口 @115200 收 JSON，官方 `ugv_rpi` 仓库就是 Python（`base_ctrl.py`）；也支持 HTTP/ESP-NOW。上位机可以是树莓派，也可以直接是笔记本。
4. **2×2 m 场地允许「有线」配置**：本课不需要机载算力——USB 相机＋USB 串口各接一根 3 m 线到笔记本即可（LeKiwi 官方也提供同思路的「wired version」），省下树莓派 ¥410 与 WiFi 联调；后续要无线再加 Pi。
5. 国内可购：微雪在 waveshare.net 官网商城、天猫／京东有官方店（本轮官网商城页被 WAF 拦截，人民币价未取到，见「未查到」标注）。

预算内怎么配（不含电池／树莓派）：
| 件 | 价 | 备注 |
|---|---|---|
| UGV02 底盘（含 ESP32 通用驱动板、UPS 电源模块、IMU、OLED） | $149.99 ≈ ¥1,065（官网美元价） | 国内人民币价未查到，预计低于美元换算价 |
| USB 相机（LeKiwi BOM 淘宝同款 1080p）或微雪 IMX219-160 CSI 相机 | ¥48（USB，LeKiwi BOM 淘宝价）；IMX219-160 价未查到 | 有线方案选 USB；上 Pi 再选 CSI |
| 3 m USB 延长线 ×2（有线方案） | ≈ ¥25×2（LeKiwi BOM 淘宝价参考） | 可选 |
| **小计** | **≈ ¥1,110–1,170** | 电池 3×18650 约 ¥30–60、树莓派 5 4GB ¥410（LeKiwi BOM 淘宝价）另计 |

备选（若要严格走 LeRobot 社区标准或已有 3D 打印机）：LeKiwi 有线版底盘，BOM 国内价 ¥963.9（含 2 个 USB 相机，不含 3D 打印约 34 小时与树莓派）。

---

## ② 候选对比表

| 项 | 1. 微雪 UGV02（推荐） | 2. LeKiwi 底盘（有线版／12V 版） | 3. 板卡厂商 Raspbot V2（**09-28 核否**，依据与来源见 ③-3） |
|---|---|---|---|
| **名称／官方页／开源仓** | UGV02 六轮四驱底盘；官网 https://www.waveshare.com/ugv02.htm ；wiki https://www.waveshare.com/wiki/UGV02 ；固件 https://github.com/waveshareteam/ugv_base_ros ；上位机 https://github.com/waveshareteam/ugv_rpi | LeKiwi（SIGRobotics-UIUC × HF LeRobot）；仓库 https://github.com/SIGRobotics-UIUC/LeKiwi ；文档 https://huggingface.co/docs/lerobot/lekiwi ；套件 https://www.seeedstudio.com/Lekiwi-Kit-p-6501.html | Raspbot V2 AI 视觉小车；官网 （厂商官网产品页，链接略） ；海外店 （厂商官网产品页，链接略） ；教程 （厂商官网产品页，链接略） ；仓库 （厂商 GitHub 仓，链接略） |
| **价格** | 官网（waveshare.com，2026-09-25）$149.99；国内官网商城／淘宝价：**未查到**（waveshare.net 被 WAF 拦截） | BOM 国内价（GitHub BOM.md，2026-09-25）：有线版底盘 ¥963.9（含 2 USB 相机，不含 Pi）；12V 底盘 ¥1,501（含 Pi 5 ¥410、2 相机、SD 卡）；5V 底盘 ¥1,571。Seeed 国际站 12V 底盘套件（含打印件＋电池，不含相机／Pi）$175；LeKiwi 12V 整套（含臂）页抓到 $240／$305。淘宝成套：**未查到** | 海外店（category.板卡厂商.net，2026-09-25）$134.99；V1 Raspbot（Pi 5 版）$94.99；天猫／京东人民币价：**未查到**（官网页面 JS 渲染） |
| **到货期** | 国内现货（微雪深圳发货；官网公告 9/25–27 中秋停发）；整机成品，免打印 | 需 3D 打印（官方估约 34 小时）＋自组装；或 Seeed 含打印件套件海外／深圳发货，天数**未查到** | 国内现货（天猫／京东官方旗舰店） |
| **社区规模** | ugv_base_ros 38★、ugv_base_general 42★、ugv_rpi 142★；官方 wiki 中英文完整（JSON 指令集逐条列出）；非 LeRobot 标准 | LeKiwi 仓库 1,438★（2026-09-25）；HF LeRobot 官方文档页；**LeRobot 社区标准移动底盘** | 板卡厂商Technology/Raspbot 15★；官网课程页＋视频；非 LeRobot 标准 |
| **底盘尺寸／轮／驱动；相机** | 252×230×94 mm（官网页）；胎径 80 mm、胎宽 42.5 mm（同系 WAVE ROVER／UGV Rover 参数，UGV02 单独数据未查到）；六轮四驱、差速（原地转向）；**相机不含**，需另购（USB 或 IMX219-160 CSI，安装高度自定） | 三轮 Kiwi 全向（4 寸=约 100 mm 全向轮）；底板直径／整机尺寸**未查到**（CAD 见仓库 Fusion 360 链接）；相机：通用 USB 1080p（BOM）或 Arducam 5MP 广角；安装高度**未查到** | 麦克纳姆轮全向；尺寸**未查到**；相机：110° 广角、100 万像素（官网页描述）；安装高度**未查到** |
| **Python 控制／主控** | 原生：ESP32 从控收 JSON（GPIO UART 或 USB 串口 @115200、HTTP、ESP-NOW），官方 ugv_rpi 为 Python；**不需要 ROS**；上位机可为树莓派 4B/5、Jetson 或笔记本 | 原生：LeRobot Python（ZMQ；`LeKiwiHost` 跑在树莓派 5，客户端在笔记本；有线版可全在笔记本跑）；不需要 ROS；电机为 Feetech STS3215 总线舵机经微雪电机控制板（USB） | Python3／OpenCV（官网）；驱动板经 I2C 与树莓派 5 通信；海外店标 ROS2 Humble；是否可脱离 ROS 直接 Python 驱动：文档标题显示有 Python 课程，细节**未查到** |
| **限速／离散有界动作／急停** | 限速：`{"T":13,"X":..,"Z":..}` 上位机限幅（m/s、rad/s，闭环）；离散：编码器闭环速度 × 时间 ＋ IMU 航向（`{"T":130}`），无原生「走 N 米」指令；急停：`{"T":0}` ＋ 3 秒无指令自动停 | 限速：键盘遥控三档 0.1／0.25／0.4 m/s、30／60／90 °/s（HF 文档）；离散：速度指令 × 时间（`x.vel/y.vel/theta.vel`），舵机有位置反馈但 LeRobot 用速度模式；急停：host 看门狗 `watchdog_timeout_ms` 超时自动 `stop_base()` | 限速／离散／急停：**未查到**（教程有「速度控制」章节，无编码器与看门狗描述） |

---

## ③ 各候选备注与风险

### 1. 微雪 UGV02（推荐）
- 优点：整机金属成品、免打印；带编码器闭环＋IMU；JSON 协议简单可 curl 级调试；心跳自动停车是「模型在环」最需要的安全网（模型调用卡住时车自停）。
- 风险：
  - 国内人民币价未取到；需主理人在 waveshare.net／天猫核价后再定。
  - 无原生「走固定距离」指令，离散动作要在上位机自己写「闭环速度 × 时间 ＋ IMU 校正」并实测标定。
  - 不含相机；有线方案需 3 m 级 USB 线，转弯时线缆缠绕要留人看护。
  - 3S 18650 电池需自购，反接有炸裂风险（官方 wiki 警告）；按 rig-safety 硬门走首次上电。
- 同系替代：WAVE ROVER $89.99（194×168×100 mm，N20 无编码器，开环 PWM）——更便宜但闭环不成立，仅作预算兜底；RaspRover（4WD N20 编码器电机、0.65 m/s、PT 版含 160° 5MP 相机）官网页抓到 $174.99／$419.99，搜索摘要另见 $109.99，价格口径未核清；UGV Rover $244.99／$486.99、UGV Beast $264.99／$501.99 均超本课需要。

### 2. LeKiwi 底盘
- 优点：LeRobot 社区标准，后续接 SO-101 臂或做数据采集零迁移；全向底盘转向不打滑；BOM 给了完整淘宝／拼多多链接；host 看门狗现成。
- 风险：
  - 必须 3D 打印（约 34 小时）＋自组装；无打印机则只能买 Seeed 含打印件套件（海外站 $175，国内渠道未查到）。
  - 不装树莓派的有线版需 USB hub＋延长线，桌面级线缆管理；装 Pi 5 版则超出「不含 Pi ¥1,500」中的 Pi 部分（Pi 5 4GB ¥410 另计）。
  - 底盘尺寸与相机安装高度公开资料未给数值，需从 CAD 量。
  - 电机为总线舵机轮式模式，负载与电池匹配（5V／12V 二选一）要按 BOM 走，不能混。

### 3. 板卡厂商 Raspbot V2（09-28 核否）
- **09-28 核否**（裁定 2026-09-28-04；内部工单）：TT 电机开环、无编码器／IMU，同 WAVE ROVER 否决理由；Pi 为唯一主脑经 I2C、Pi 4B 官方未测；底层固件闭源、无心跳记载；相机 110°。
  - 来源：（厂商官网产品页，链接略）；（厂商官网产品页，链接略）（含问答）；Amazon B0FF1V3QSG；<（厂商 GitHub 仓，链接略）
  - 维护者 09-28 落盘后 grep：海外店问答命中两条——Pi 4 官方答「haven’t tested it ourselves」、底层固件官方答「not open source」；GitHub 仓 215 个路径里没有含 encoder、heartbeat、watchdog 的文件名。电机类型、无 IMU、I2C、相机 110° 四项在落盘页的文字里没有命中（商品页以图为主，国内页靠脚本渲染，Amazon 页未取到可读正文），按令文所记。
- 优点：国内品牌，天猫／京东现货最快；麦轮全向；相机内置（110°、1MP）。
- 风险：
  - 关键字段大量未查到（人民币价、尺寸、编码器、看门狗／急停）；官网页为 JS 渲染，本轮无法落盘核对。
  - GitHub 社区很小（15★），文档偏课程视频；相机 1MP 对视觉标记识别偏低。
  - 树莓派 5 为必需主控（I2C 驱动板），不能有线到笔记本。

### 已查但未入清单
- **SunFounder PiCar-X**：官网 $89.99（2026-09-25），含 5MP OV5647 相机；但为**阿克曼前轮转向**（`picarx.py` 中 `DIR_MAX = 30`°），不能原地转固定角度，与「左/右」离散动作模型不匹配；淘宝价未查到。GitHub sunfounder/picar-x 77★。
- **Freenove 4WD Smart Car for Raspberry Pi**：官方店 $69.99（2026-09-25），不含 Pi 与 2×18650；4 直流电机无编码器；含 Pi 相机；GitHub 188★；淘宝价未查到。便宜但开环，且树莓派必需。

---

## ④ 对照项：Duckietown DB21

Duckiebot DB-J（DB21J 系）官方店 get.duckietown.com 标价 From $429 USD（另一变体 From $599 USD；2026-09-25 抓取），主控 NVIDIA Jetson Nano 4GB，含标定相机与完整自动驾驶课程栈（docs.duckietown.com opmanual）。作为「课程化机器人评测」的形态参照价值高（标定、赛道、评分都有成熟规范），但：单价超本课预算 2 倍以上；Jetson Nano 供货与国内直邮周期未查到；国内无官方渠道（搜索结果仅显示海外店与 ozrobotics 转售）。结论：只作 Course 设计对照，不作采购项。

---

## ⑤ 来源清单（均 2026-09-25 curl 落盘于 scratchpad/kits/ 后 grep）

- LeKiwi 仓库与 BOM：https://github.com/SIGRobotics-UIUC/LeKiwi ；https://raw.githubusercontent.com/SIGRobotics-UIUC/LeKiwi/main/BOM.md ；3D 打印 https://raw.githubusercontent.com/SIGRobotics-UIUC/LeKiwi/main/3DPrinting.md
- LeKiwi HF 文档（速度档位）：https://huggingface.co/docs/lerobot/lekiwi
- LeRobot 源码（看门狗、速度接口）：https://raw.githubusercontent.com/huggingface/lerobot/main/src/lerobot/robots/lekiwi/lekiwi_host.py ；…/lekiwi.py
- Seeed LeKiwi：https://www.seeedstudio.com/Lekiwi-Kit-p-6501.html ；https://www.seeedstudio.com/LeKiwi-Full-Kit-12V-Verision.html
- 微雪 UGV02：https://www.waveshare.com/ugv02.htm ；https://www.waveshare.com/wiki/UGV02
- 微雪 WAVE ROVER：https://www.waveshare.com/wave-rover.htm ；https://www.waveshare.com/wiki/WAVE_ROVER ；尺寸参数经 RobotShop 等转售页（搜索摘要）
- 微雪 UGV Rover／UGV Beast／RaspRover：https://www.waveshare.com/ugv-rover.htm ；https://www.waveshare.com/wiki/UGV-Rover ；https://www.waveshare.com/ugv-beast.htm ；https://www.waveshare.com/rasprover.htm ；https://www.waveshare.com/wiki/RaspRover ；UGV Rover 尺寸经 electropeak／openhardware.directory 搜索摘要
- 微雪固件与上位机：https://github.com/waveshareteam/ugv_base_general ；https://github.com/waveshareteam/ugv_base_ros ；https://github.com/waveshareteam/ugv_rpi ；https://raw.githubusercontent.com/waveshareteam/ugv_rpi/main/base_ctrl.py
- 微雪国内商城（被 WAF 拦截，未取到内容）：https://www.waveshare.net/shop/WAVE-ROVER.htm ；https://www.waveshare.net/shop/UGV02.htm
- SunFounder PiCar-X：https://www.sunfounder.com/products/picar-x ；https://github.com/sunfounder/picar-x ；https://raw.githubusercontent.com/sunfounder/picar-x/v2.0/picarx/picarx.py
- Freenove 4WD：https://store.freenove.com/products/fnk0043 ；https://github.com/Freenove/Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi
- 板卡厂商 Raspbot：（厂商官网产品页四条，链接略）；（厂商 GitHub 仓，链接略）
- Duckietown：https://get.duckietown.com/ ；https://docs.duckietown.com/daffy/opmanual-duckiebot/intro.html

查证日期 2026-09-25；未查到项已标注。
