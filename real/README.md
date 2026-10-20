# 内部工单：UGV02 mock 串口驱动

> 内部工单 本体（2026-10-05 起）：固定布局 L1 与场地登记见 `real/course/README.md`；相机实测常量 `real/config/camera.yaml`（`python -m real.camera_measure`）；俯拍离线计分 `real/score_overhead/`（`markers`→PDF、`track`→track.csv、`score`→与孪生同键的 score.json）；黄金用例 oracle `real/oracle.py`；真机段冻结件与 tag 程序 `protocol/real-v0.md`。

实现依据仅为只读的 `real/docs/ugv02-protocol.md`。本卡未连接真实设备、未调用外部接口、未安装依赖。

## 离线运行

在仓根执行：

```bash
PYTHONDONTWRITEBYTECODE=1 python -m real.smoke --mock
PYTHONDONTWRITEBYTECODE=1 pytest tests/real -q -p no:cacheprovider
```

需要已有的 numpy 与 pytest；mock 不导入 pyserial 或 OpenCV。测试使用 FakeClock，不 sleep、不读取墙钟。禁用字节码与 pytest 缓存，避免在白名单外生成文件。

## 接线与到货运行

由 CC 在到货后核实 USB 串口设备路径与 USB 相机编号。主机 USB 接底盘控制板的串口接口，USB 相机接主机；底盘电源、接插件及物理断电操作按到货手册核对，本卡不推断管脚或电压。串口使用 115200、8N1、逐行 JSON。

CC 核实固件、型号、闭环行为与物理急停后，可使用以下 API 组装环境（本卡未执行）：

```python
from real.ugv02 import UGV02, UGV02Config
from real.camera import Camera, CameraConfig
from real.real_env import RealRobotUGV02

driver = UGV02.connect(port, config=UGV02Config())
camera = Camera(CameraConfig(), index=camera_index)
robot = RealRobotUGV02(driver, camera, course=calibrated_course)
# 调用 robot.reset(seed, instruction)、observe()、act(Action.*)。
# 最终调用 robot.close()。
```

`UGV02Config` 集中保存轮径、编码器脉冲数、轮距、型号、闭环状态、急停命令和超时。型号与闭环字段记录待核实的物理配置，不自动改写固件型号。默认急停始终发 T=1 零轮速；可附加经核实的非运动急停命令。`CameraConfig` 的前五个字段与 twin 同名，取值独立配置，其余字段见「真机拖线件」节；注入 `frame_source` 时必须返回配置尺寸的 RGB uint8 图，USB OpenCV 帧由 BGR 转 RGB。

### 到货核对（CC 合并 X1 时追加，2026-09-27；协议量另见 `real/docs/ugv02-protocol.md` §5）

1. **相机缓冲旧帧。** `Camera.read()` 每次只取一帧，USB 相机驱动有缓冲，停稳后取到的可能是运动中的旧帧。实机核对观测帧的时刻，必要时先丢弃缓冲帧再取。
2. **开串口复位 ESP32，丢头几条指令。** 打开串口可能触发底盘 ESP32 复位，`UGV02.__init__` 开头发的关回显、设看门狗、零速三条可能在启动期间丢失。实机核对开口后的就绪时间，确认三条均生效。
3. **分辨率不认时 `read()` 报错。** 相机不接受配置的宽高时 `set()` 不报错，帧尺寸与配置不符，`read()` 抛 `ValueError`。实机核对相机实际支持的分辨率并写入 `CameraConfig`。
4. **开环型号转向 PWM≈46 可能低于死区。** 缺省型号 2 为开环，转向轮速换算出的 PWM 约 46，可能带不动电机。实机核对原地转向是否起转、转角是否达 `turn_deg`。

#### 到货首测卡（内部工单 P3，2026-09-28；四条按序做，命令未经实机执行；第 8 条为 内部工单 所加）

每条的「其他」分支都一样：停下，把屏幕或照片原样贴回，不猜修。两段脚本要用 pyserial 与 opencv-python，当前 `.venv` 里都没有，到货前由 CC 装。

5. **开机 OLED 版本行。** 装好电池后开机，拍下 OLED 四行。
   - 显示 `UGV Rover Version:0.96`：免烧录，进第 6 条。
   - 不是这一行：抄下四行原文，只记录、不烧录，报 CSO。固件源码 `ugv_base_ros` 开机写的是 `ugv_base_ros.git`／`version: 0.96` 两行，见到这一组也按本分支记录。
   - 其他（屏不亮、乱码、电池模块上的反接灯亮）：关电，停下贴回。
6. **台架首动。** 四轮离地，物理断电随手可及。串口以 0.1 s 间隔发 `{"T":1,"L":0.1,"R":0.1}`，三秒后停发，看固件心跳自停。
   ```bash
   .venv/bin/python - <<'EOF'
   import json, serial, time
   s = serial.Serial("<串口设备>", 115200, timeout=0.2); s.setRTS(False); s.setDTR(False)
   time.sleep(2)
   start = time.monotonic()
   while time.monotonic() - start < 3:
       s.write((json.dumps({"T": 1, "L": 0.1, "R": 0.1}) + "\n").encode()); time.sleep(0.1)
   print("停发", time.strftime("%X"))
   EOF
   ```
   - 预期：发指令期间四轮同向慢转；屏上印出「停发」后约 3 秒轮子自己停下。
   - 记录：从「停发」到轮停的时长，录像按帧读数，做三次。这个数是真机常量候选，不进冻结区。
   - 其他（轮不转、某轮反向、停发后 5 秒仍在转）：物理断电，停下贴回。
7. **相机拖线。** 相机经 3–5 m 延长线接主机，1280×720 连续取帧 60 秒（内部工单 改，原为 640×480；口径见「采集口径」节）。
   ```bash
   .venv/bin/python - <<'EOF'
   import cv2, time
   cap = cv2.VideoCapture(<相机编号>); cap.set(3, 1280); cap.set(4, 720)
   ok = bad = 0; start = time.monotonic()
   while time.monotonic() - start < 60:
       good, frame = cap.read()
       if good and frame.shape[:2] == (720, 1280): ok += 1
       else: bad += 1
   print(f"取到 {ok} 帧，失败 {bad} 次，{ok / 60:.1f} 帧/秒")
   EOF
   ```
   - 预期：末行印出帧数、失败次数与帧率。
   - 记录：末行原文。掉帧数＝失败次数；帧率另与不接延长线时的同一脚本结果对比。
   - 10-06 实跑（MF-200 → hub → Mac，**未经 5 m 延长线**，主理人 10-06 报）：`取到 1750 帧，失败 0 次，29.2 帧/秒`；另 5 秒样本 30.8 帧/秒。这是无延长线的对照值。**经 5 m 有源延长线（Mac → hub → 延长线 → MF-200，主理人 10-06 接）同脚本再跑**：`取到 1742 帧，失败 0 次，29.0 帧/秒`，帧间隔中位 33.1 ms、最大 70 ms、无 >100 ms 停顿；`uvc-util -d` 仍列出（LocationID 变 0x01110000），控制读回 `8 157 true 4600`。掉帧 0，延长线不影响取帧与 UVC 控制；本条办完。
   - 其他（打不开相机、帧尺寸不是 1280×720、中途卡住不出末行）：停下贴回。
8. **控制项清单与回读比对。**（裁定 2026-09-28-13）相机直连主机，先装 `uvc-util`（CC 办）。命令与控制项次序见下文「曝光与白平衡」节。
   ```bash
   uvc-util -l                                   # 找到相机的 VID:PID
   uvc-util -V <VID:PID> -c                      # 控制项清单
   uvc-util -V <VID:PID> -s auto-exposure-mode=1 -s exposure-time-abs=<值> -s auto-white-balance-temp=0 -s white-balance-temp=<值>
   uvc-util -V <VID:PID> -o exposure-time-abs -o white-balance-temp     # 回读
   ```
   - 预期：清单里有上面四个控制项名；回读的两个数与所设的相同。
   - 记录：清单原文贴进回执；所设值与回读值各两个数。控制项名以这份清单为准，与上面写的不一致就照清单改。
   - 回读相符之后 CC 才补代码：`meta.json` 的 `uvc_lock` 改记设后回读值，回读与所设不一致即报错不开回合；在此之前 `MF200` 预设的两个锁定值留空，按自动跑。
   - 其他（清单里没有这几项、设不进去、回读与所设不同、取帧开始后回读值变了）：保持自动，两个字段留空，把输出贴回。

## 真机 smoke（内部工单，2026-09-28；未经实机执行）

`python -m real.smoke --port <串口> --camera <产品串或 VID:PID> --firmware-ver <版本> --out smoke_runs/<名字> --episode <k>` 在真车上跑一个回合，连跑三次后 `python -m real.smoke --finalize --out smoke_runs/<名字> --measured <k>=<厘米>` 出判定。不带 `--port` 时仍是原来的 mock 四步回合；`--port mock` 走真机模式的通路但不碰设备。

- `--firmware-ver` 在真串口上必填，填固件开机标识行里的 `ver`（现为 `0.2.0`），记进 `meta.json` 的 `firmware_ver`。同一个 `--out` 目录里已有别的版本（或没记版本）的回合，就拒跑，0.1.x 与 0.2.0 的数据不混算（内部工单-1）。驱动层碰巧读到开机标识行时，原样记进 `firmware_banner`，读不到记 `null`。
- 动作由脚本化 oracle 按已知检查点坐标走，位姿取自轮式里程计的航位推算，**不是真值**，也不读相机；相机每步取一帧存档。
- 交给计分器的到达判定因此是「里程计认为到了」。主理人卷尺量的终点偏差另记一列 `measured_error_cm`，不进判定。
- 速度缺省 0.10 m/s、30 度/秒，比协议速度慢；步长不变。
- 产物在 `smoke_runs/` 下，在 `episodes/` 之外，站点构建不读。帧与逐步日志不入库，`results.csv`、`verdict.json`、`meta.json`、`SHA256SUMS` 入库。
- 判据：三个回合里至少两个判到达，且清单校验通过；作废回合不计入。
- `--camera` 可以指笔记本自带摄像头，只许台架用；落地回合须用车载 UVC 相机。真机模式不带 `--camera` 即退出；纯数字当编号用，只许台架。

### 固件的三种停车锁存（内部工单／R2，2026-09-28；未经实机执行）

旧车固件 `yb-eet01-json` 里三种锁存共用一个状态量，锁存期间目标速度恒为 0。UGV02 固件没有后两种。原「等锁」一行随协议锁退役（修订5 R1），`lock_faults` 字段固件不再发。

| 锁存 | 触发 | 清除 | 优先级 | 蜂鸣 | 帧内字段（`T=1001`） | 上位机的处置 |
|---|---|---|---|---|---|---|
| 心跳 | 超过心跳超时（缺省 3000 ms）没有收到有效 `T:1`，且当时目标非零 | 下一条有效 `T:1` | 低。只在没有别的锁存时才进 | 进锁存时一声 | 无 | 无感知；驱动层按 0.1 s 续发，正常不触发 |
| 低压 | 电压连续 2 秒低于 6.5 V（每芯 3.25 V × 2） | 软件清不掉，只有芯片复位（RESET 键或断电重启）；复位后电压仍低则 2 秒静默期内重新锁上 | 高。盖掉另两种，不被它们盖掉 | 进锁存时一声 | `low_voltage`：锁存中为 1，否则 0 | 驱动层抛 `LowVoltageError` 并锁存急停；回合作废，`void_reason="low_voltage"` |
| 复位 | 任何复位（上电、RESET 键、看门狗、panic），开机即在 | 静默期内清不掉；开机满 2 秒且低压去抖段已落定之后，下一条有效 `T:1` | 中。不被心跳锁存盖掉，会被低压锁存盖掉 | 不鸣 | `reset_reason`：本次开机的复位原因；`boot`：本次开机的 boot 计数，回合内变了就是复位过。两者缺字段记 NA（内部工单-1；10-02 勘误，原「缺省 0」） | 回合内 `boot` 变了即急停并作废，`void_reason="reset"`，该回合号重跑；静默期内发非零 `T:1` 收到错帧 `boot_quiet`，驱动层抛 `BootQuietError` 并锁存急停，回合同样记 `reset` |

- 回合内的比对在驱动层，逐帧做：读到 `boot` 变了（或帧里带 `lock_faults` 而次数增长），同一拍发零速，此后不再发非零 `T:1`（审查 X3-12）。
- 以回合第一帧反馈的读数为起点。
- 帧里缺哪个字段，驱动层就把它记作 NA（`None`，写进 JSON 为 `null`），不记 0；NA 不参与比对（内部工单-1）。UGV02 的反馈帧没有这几个字段，行为与原来相同；0.2.0 固件的帧没有 `lock_faults`，`meta.json` 里该回合的次数记 `null`。
- 控制任务停摆由任务看门狗兜底：300 ms 没喂即复位，复位后进上面的复位锁存。细节在固件 README「安全行为」。
- 作废回合的收口（审查 X3-17，裁定 2026-10-02-06；内部工单 F，2026-10-06）：回合一旦作废（`void_reason` 非空），`clear_estop()` 只结束该回合（`extra.episode_ended=true`），此后 `act()` 一律 `rejected`、不发非零；续动须 `reset()` 开新回合，且新回合首帧的 `boot` 必须不同于作废回合基线（新 reset key；RESET 键或断电换 key），相同即急停并抛 `SafetyError`，`boot` 缺字段（UGV02 固件）不查。未 `clear_estop()` 就 `reset()` 亦抛错。手动急停（未作废）的 `clear_estop()` 行为不变。
- 低压分类（裁定 2026-10-02-19；内部工单 F）：`void_reason="low_voltage"` 之外另带 `extra.void_detail={"phase","source"}`——`phase`＝`start_gate`（开回合电压门槛，回合未打开）／`reset`（开回合时读到锁存帧）／`observe`（取图前停稳核验读到）／`act`（动作内）；`source`＝`feedback_flag`（反馈帧 `low_voltage=1`）／`motion_refused`（非零 `T:1` 收到 `low_voltage` 错帧）／`start_gate`。`reset`／`lock_fault` 作废同样带 `phase`，`source="feedback_frame"`。`real.smoke` 结果表新增 `void_phase`、`void_source` 两列。`observe()` 里读到的低压或复位与 `act()` 同一出口记作废（审查 X3-06 ①）。
- 自检固件的即时隔离（审查 X3-16；内部工单 F）：驱动层读到 `ver` 带 `-selftest` 后缀的标识行（或操作者直接设 `driver.firmware`）当拍锁存急停、`firmware_rejected=True`，`clear_estop()` 拒绝清除，`real_env.reset()` 不开回合；`real.smoke` 的目录版本门改为：`meta.json` 存在但读不出或缺 `firmware_ver` 即拒绝续写。标识行只在开机打印一次，开口晚于开机就读不到——`extra.firmware_ver` 为 `null`（NA）时身份未经验证，仍靠门一步 0 的烧录前置补偿；固件侧加版本查询指令属固件改动，未做。
- 复位原因按类判，不按单值（内部治理仓 内部工单）：上电或外部（1、2）、软件（3）、异常（4～7，各看门狗与 panic）、掉电（9）。`ActResult.extra` 里 `reset_class` 与 `reset_reason` 并列，单值只作记录。看门狗复位的台架实测走自检固件与 `real.stallcheck`，见固件 README「自检钩子」；自检固件不进回合数据。

## 真机拖线件（内部工单，2026-09-28；未经实机执行）

参数来源＝京东店铺规格页截图与绿联官方页，由令文转述，截图未入库。标「算」的是按传感器有效面推算的数，标「待实测」的到货后由 CC 实测覆盖。

| 件 | 型号与参数 | 状态 |
|---|---|---|
| 相机 | MF-200 1080P＋2.8 mm 无畸变镜头＋金属外壳（京喜自营）。传感器 1/2.7"、像素 3 µm、原生 1920×1080，有效面 5.76×3.24 mm；USB 2.0 UVC 免驱，缺省 MJPG、可选 YUY2；模式 640×480@30、1280×720@30（YUY2 10）、1920×1080@30（YUY2 5）；手动对焦，成像 1 cm～∞；卷帘快门；自动曝光／增益／白平衡，UVC 可控饱和度、锐度、亮度、对比度、伽马、白平衡；工作电流 150–200 mA@5 V；自带线 1.5 m USB-A；外壳 36×36×20 mm（镜头另计），底座 Ø38 mm 带长槽，3 mm 螺丝 | 09-28 下单 |
| 延长线 | 绿联 USB3.0 公对母信号放大延长线 5 m（20826／US175），创惟 GL3521 芯片（USB3.0 hub 控制器，2.0 通道同样经芯片中继），A 公→A 母，总线供电。算一级 hub | 09-28 下单 |
| hub | 主理人自有绿联 USB3.0 hub，型号待核（照片：铝壳、3×USB-A 3.0、Micro-USB 辅助供电口、自带 A 公线），随附 A 母转 C 公转接头。算第二级 hub | 自有 |

- **可疑口**：hub 最右口内芯颜色与另两口不同，疑为充电专用口，未验前不接数据设备。
- **拓扑**：MacBook USB-C ←转接头← 5 m 有源线 ←hub（控制板左侧边条）← 相机自带线；hub ← A 转 C 短线 → YB-EET01 Type-C（CP2102）。
- **布置**（修订3 T1，09-28 改判；尺寸为 CSO 据照片所给，未经实物核对）：
  - 车头空板区约 94×70 mm，只放相机：底座居中，中心孔对准前区大孔，或两槽各一颗 M3；手头 M3×30 铜柱抬高（公母型则 30＋20 叠至 50，母母型 30 单用），镜头压前缘。天线座若与底座相碰即拧掉，JSON 串口路线不用 WiFi。（修订4 补丁2 R1，09-28 改判：原写「四根 M3×50 铜柱」，不另购。）
  - hub 放控制板左侧边条（约 3 cm 宽、中段约 11 cm、无螺丝），纵向魔术贴，口朝车尾。A 转 C 短线沿板尾绕到右后 Serial 口。
  - 延长线接头扎在同一边条尾端，出线车尾正中，再绕一圈扎带。
  - 镜头离地高与俯仰仍待实测。不为凑 0.15 m 以外的理由再垫。
- **供电**：下游合计约 300–350 mA，走总线供电；掉线才给 hub 辅助口接充电宝。
- **视场（算，待实测）**：全幅 16:9 水平约 92°（店表标 85°）；中心裁 4:3 后水平约 75°、垂直约 60°。这组数假定 1280×720 模式是全幅缩小而不是裁切。孪生的视场与高度常量不因本节改动。
  - 10-06 目视核（内部工单 B）：1920×1080 与 1280×720 两模式画面范围一致（720p＝全幅缩），原生 640×480 模式明显更窄＝居中裁；故「抓 720p 自己裁 4:3」的口径成立。三模式各能开、各按设定尺寸出帧。10-06 实测（装车后，卷尺竖贴墙、墙距镜头 0.50 m，画面高 57.4 cm）：垂直 **59.8°**，按方像素换算全幅水平 91.2°、裁 4:3 后水平 **74.9°**（±1.5°），与算值一致；填 `real/config/camera.yaml`。镜头高 0.124 m、前移 0.0595 m（镜头在前轮轴正上方）、俯仰 0。
  - 10-14 硬件升级（主理人报，照片入 内部治理仓 `35_papers/p5-realbot/fieldwork/measure-2026-10-14/`）：加一层上层底盘板，相机改装于上层板前缘 L 形支架，**镜头高实测 0.141 m、镜头在前轮轴前方约 5 cm（前移 0.1095 m）、平视**（10-14 主理人卷尺，`camera.yaml` 定稿；首报加高 2.2 cm 算得 0.146 作废；上层板厂商规格 148×228×2 mm、板面离地 10.5 cm；整车外廓实量长 0.235、宽＝轮外缘到外缘 0.173 回填 `L1.yaml` footprint）；新装 RPLIDAR C1（相机正后方，顶部离地 18 cm，不进相机视场、本季不进观测链）、树莓派 4B 4G＋TF 64G（原装电源供电；装车不改 Mac 直连链路）；电池为 6600 包。视场常量不因此改。

### 采集口径

抓 1280×720 → 中心裁 960×720 → `INTER_AREA` 缩到 640×480。不用模组自带的 640×480 模式，那个模式是裁还是压不确定。macOS 走 AVFoundation 后端，MJPG 由系统协商。上面到货首测卡第 7 条的取帧脚本已按本节改抓 1280×720。

`real/camera.py` 的 `MF200` 预设带这组口径，`real.smoke` 真机模式用它：

| 令文键 | `CameraConfig` 字段 | 取值 |
|---|---|---|
| capture 1280×720 | `capture_width`、`capture_height` | 1280、720；缺省 0＝按输出尺寸直接抓、不裁 |
| crop 4:3 居中 | 无字段，按输出宽高比居中裁 | — |
| out 640×480 | `width`、`height` | 640、480 |
| fov_h_deg | `hfov_deg` | 75（算，待实测） |
| cam_height_m | `height_m` | 待实测，现为缺省 0.15 |
| pitch_deg | `pitch_deg` | 待实测，现为缺省 0 |
| exposure／wb 锁定值 | `exposure`、`wb_temperature` | 缺省空＝自动；锁定是可选项，见「曝光与白平衡」 |

视场与高度两个字段沿用与 twin 同名的旧名，没有按令文键名改。抓到的帧不是配置的抓取尺寸时 `read()` 抛 `ValueError`。

### 设备选择

按 USB 产品串或 `VID:PID`（四位十六进制）选相机，不按编号：笔记本自带摄像头和接力的手机相机会占前面的编号。`find_camera()` 读 `system_profiler SPCameraDataType -json`，按唯一标识排序后取下标；OpenCV 的 AVFoundation 后端也是按唯一标识排序取设备（OpenCV 5.x `cap_avfoundation_mac.mm`）。产品串匹配不到或匹配到多台即报错。

10-06 实测：`system_profiler` 报名 `USB Camera`、型号串 `UVC Camera VendorID_3141 ProductID_25451`（十进制）→ 十六进制 **`0c45:636b`**（`real.camera.MF200_VID_PID`；`uvc-util -d` 报名 `USB 2.0 Camera`）；按唯一标识排序排第 0（iPhone 接力相机、FaceTime 在后）。`find_camera("0c45:636b")` 选中即手持的 MF-200（画面里有扶相机的手），遮镜头核对不必再做。首次打开要给终端相机权限（macOS 弹框）。

### 曝光与白平衡

**首季口径（内部工单）：自动曝光＋自动白平衡是缺省，记为已知条件；场地靠灯光打匀。锁定是可选增强，不是门槛。** 修订1 的「回合全程不许自动」一句由本段取代。

- `exposure`、`wb_temperature` 两个字段缺省为空，即自动。`meta.json` 记 `exposure_mode`、`white_balance_mode`（`auto` 或 `locked`）与 `uvc_lock`（实际设下去的控制项，自动时为空表）。
- OpenCV 的 AVFoundation 后端对相机只认宽、高、帧率三项设置（同上源文件），曝光与白平衡经它设不进去。锁定走 `uvc-util`（命令行工具，直接发 UVC 控制请求）：相机打开之后、取第一帧之前用 `subprocess` 设一次。不引 libuvc、pyuvc，不改 OpenCV 后端。
- 设的控制项与次序：`auto-exposure-mode=1`（手动）、`exposure-time-abs=<值>`、`auto-white-balance-temp=0`、`white-balance-temp=<值>`。第三项是 CC 加的：自动白平衡开着时色温多半设不进去。
- 两个字段填了值而 `uvc-util` 不在、设不进去、或相机是按编号选的，`Camera` 打不开并报错，不会悄悄退回自动；要按自动跑就把两个字段清空。这样 `meta.json` 记的与实际的曝光条件不会两样。

**10-06 实机已试（MF-200 接 Mac，内部工单 B）**：`uvc-util` brew 没有，自 GitHub jtfrey/uvc-util（`8110da7`，2024-02-26）源码 `clang -fno-objc-arc -framework Foundation -framework IOKit` 编译，装在 `~/.local/bin/uvc-util`（PATH 内）。实际用法与下面原记不同：列设备是 `-d`（不是 `-l`），`-V` 的 VID:PID **必须带 `0x` 前缀**（`0c45:636b` 会被当十进制、报 `invalid product id`；`real/camera.py` 的 `uvc_target()` 已按此拼）。MF-200 控制项 14 个，含 `auto-exposure-mode`（位图，当前 8＝光圈优先，手动＝1）、`exposure-time-abs`（1–5000，缺省 157）、`auto-white-balance-temp`（布尔，缺省 true）、`white-balance-temp`（2800–6500，缺省 4600）。锁定往返：设手动 1／157／false／4600 读回逐项相符，改 200／5000 亦相符；自动模式下 `exposure-time-abs` 写入报错（正常）；已复原自动。首季仍按自动跑，两个字段留空；读回原文记 `real/config/camera.yaml`。取帧开始后锁定值是否被复位**仍待实测**（装车后在回合里核）。

原记（到货前写，命令形式已被上面取代）：

```bash
uvc-util -l                                   # 列设备，找到相机的 VID:PID
uvc-util -V <VID:PID> -c                      # 列这台相机支持的控制项
uvc-util -V <VID:PID> -s auto-exposure-mode=1 -s exposure-time-abs=<值> -s auto-white-balance-temp=0 -s white-balance-temp=<值>
uvc-util -V <VID:PID> -o exposure-time-abs -o white-balance-temp     # 读回核对
```

能设且读回相符，就把两个值填进 `real/camera.py` 的 `MF200` 预设；设不进去就保持自动，两个字段留空。待实测：控制项的名字是否与上面一致、取帧开始后锁定值是否被相机复位。

### 视场实测法

相机正对卷尺，镜头到尺面的距离记 D。读裁切后画面最左到最右在尺上的实宽 W，水平视场＝2·atan(W/2D)。垂直视场同法做一次，卷尺竖放。

## 行为与安全边界

- `act()` 按 MotionSpec 换算前进／转向时间，以首条运动指令发出时刻建立周期调度，睡眠扣除本轮反馈耗时并截断为非负；0／20／50 ms mock 下续发间隔为 0.1 s。到时限先发零速，再查反馈、静置并核验停稳。反馈阻塞超过周期时无法保证准点续发或停车。无独立后台心跳；低层 `set_wheels()` 是协议原语，回合必须经 `RealRobotUGV02.act()` 执行。
- 停稳阈值为 `UGV02Config.stopped_speed_threshold_mps`（默认 0.01 m/s，绝对轮速不大于阈值）；时间容差为同节的 `duration_tolerance_s`（默认 0.1 s）。从首条非零速到零速发出超过动作时限加容差时归零并锁存，`ActResult.extra` 报告 `motion_duration_s`、`duration_limit_s`、`duration_tolerance_s`、`duration_exceeded`。负剩余时间本身不是故障。异常或中断（含 `KeyboardInterrupt`、`SystemExit`）退出先归零并锁存，未转换为既有 `SafetyError` 的异常原样抛出。
- 锁存共用 `estopped`／`clear_estop()`；后续动作返回 `extra.rejected=true`。急停附加命令在 `UGV02Config` 构造时校验，非法即抛 `ValueError`，不等急停时静默丢弃。
- 超限指令报错并锁存，不裁剪；串口断开、短写、写失败、读失败与反馈超时均锁存急停。物理断线时无法保证零速命令到达，依靠固件 ≤3 s 看门狗和人工物理断电兜底。急停后驱动层读反馈确认停车（审查 X3-08）：一帧同时满足固件目标 `tl`＝`tr`＝0（UGV02 固件无此字段则只看轮速）且轮速低于 `stopped_speed_threshold_mps` 才记 `stop_confirmed=True`，否则每次再发一次零速再问，至多 `stop_confirm_tries` 次（缺省 3，每次受 `read_timeout_s` 约束）后记 `False`；`ActResult.extra.stop_confirmed` 带出，`None` 表示本回合没有急停过。动作结果报告 `estopped` 只是上位机已锁存，`stop_confirmed` 才是读到过车停的证据；两者都不是物理轮速的测量。
- 急停不等待回合动作锁；已排队动作获取锁后重新检查锁存。`reset()` 不解锁，须显式 `clear_estop()`，并通过零速写入与反馈检查恢复通信。回合终止由调用侧判定。
- 里程是对反馈轮速按主机采样间隔作前值保持积分，累计于驱动实例；仅进入 `ActResult.extra.odometry`。Observation 不含里程、位姿或地图。碰撞与位姿均返回 None；未提供俯拍标定时 `course()` 明确报错。
- mock 支持分片行、坏行丢弃、默认回显及关闭、T=1/T=13、轮速限幅拒收、查询反馈与心跳超时；`replay` 接收字典或原始字节行序列，耗尽即读超时。`latency_s` 默认 0，每次 `readline()` 通过注入时钟推进指定时延（含回显行）；`pause_at_s` 指定一次性写阻塞的起始时刻（首个不早于该时刻的写），`pause_duration_s` 指定阻塞时长：指令记录后通过注入时钟推进，默认不阻塞。不模拟惯性。`python -m real.smoke --mock --latency 50` 以毫秒指定时延。

## 交付说明

已完成串口封装、注入式 RGB 相机、Robot 契约适配、可回放 mock、四步 smoke 回合，以及契约／心跳超时／急停优先／故障测试。所有新增文件限于 real/ 与 tests/real/；只读协议摘要未改。由 CC 验收，本执行结果不替代验收。

验收命令及输出尾行（运行时设置 `PYTHONDONTWRITEBYTECODE=1`；pytest 加 `-p no:cacheprovider` 避免白名单外缓存）：

- `pytest tests/real -q`：`20 passed in 0.09s`（退出 0）。
- `tools/prereg_check.sh`：`✘ ~/.brew/bin/python3 缺 mujoco／numpy，无法重跑三基线（装 .venv 或设 PYTHON=）`（退出 3）。监视件相对本卡起点 main 无改动；相对预注册 tag 存在三处已登记的既有差异：harness/run_batch.py、harness/scoring.py、protocol/v0.md。本卡未处理这些差异，不能宣称预注册检查全过。
- `python -m real.smoke --mock`：`episode complete: 4 steps, stopped`（退出 0）。
- `git diff --stat main...HEAD`：`8 files changed, 714 insertions(+)`（仅 real/ 与 tests/real/）。

未核实：实机固件版本、轮径／脉冲数／轮距、型号编号、速度闭环、急停命令、相机标定、实际固定步长精度。源码默认型号 2 为开环，定时速度指令在 mock 上满足步长，实机精度不可据此确认。采样与串口时延也会影响里程积分和实际动作时长。

待办／下一令（CC）：准备含 mujoco／numpy 的离线环境，重跑预注册核对；真实串口／相机使用前准备 pyserial 与 opencv-python（当前 Python 两者均未安装）；到货后核实配置并验收实机行为、完成俯拍标定；按卡验收后合并。四条验收命令尚未全过，当前提交为待 CC 补验产物。

移交主理人：到货后的物理接线与断电验证。

本轮执行：内部工单。

## 交付说明（X2）

> 所用模型：gpt-6-astra ｜ effort：low ｜ codex 0.157.1

四项返修完成：截止先零速、周期扣除反馈耗时；可配置停稳阈值；非负睡眠、时间越界报告与共用锁存、意外异常先停车再原样抛出；构造时校验急停附加命令。mock 与 smoke 支持注入时延。新增 55 条测试，X1 原有 20 条未改且通过。分支 `codex/内部工单`，由 CC 验收后合并。

验收命令使用主检出 `<仓根>/.venv/bin/` 的 Python／pytest；设置 `PYTHONDONTWRITEBYTECODE=1`，pytest 加 `-p no:cacheprovider`，避免白名单外缓存：

- `pytest tests/real -q`：`75 passed in 0.11s`（退出 0）。
- `python -m real.smoke --mock --latency 50`：`episode complete: 4 steps, stopped`（退出 0）。
- `git diff --stat main...HEAD`：`6 files changed, 294 insertions(+), 31 deletions(-)`（退出 0，仅 `real/` 与 `tests/real/`）。

① `tests/real/test_x2.py::test_heartbeat_latency_regression`；③ `tests/real/test_x2.py::test_deadline_stop_latency_regression`。均按 0／20／50 ms 参数化。在内存加载 `git show 06968e4:real/ugv02.py` 与 `git show 06968e4:real/real_env.py`，保留新增时延 mock 与测试，选取这两个用例：`2 failed, 4 passed, 28 deselected in 0.03s`；仅 `[0.05]` 失败，分别测得续发间隔 0.20 s 和 0.12 s 动作停车时刻 0.17 s。返修后六档实例均通过；另有三档严格 0.1 s 续发及先零速后反馈断言。

R1：`act()` 外层捕获异常与中断，运动循环也捕获 `BaseException`，先尝试零速并锁存，再原样抛出；急停写入失败不覆盖原始异常。`test_unexpected_exception_stops_before_reraise` 在反馈、读、写、静置、停稳核验五阶段分别注入 `RuntimeError`、`KeyboardInterrupt`、`SystemExit`，核对原对象、末条零速与锁存。

R2／③a：`test_duration_overrun_latches_with_write_pause` 按 0／20／50 ms 与 0.83／1.0／1.17 s 时限组合测试，在时限前 0.15 s 配置一次 0.3 s 写阻塞，验证实际时长报告、零速、锁存及显式清除。不靠常时延与短时限相位触发。常时延 50 ms 的正常动作不锁存；独立 `test_constant_150ms_latency_is_self_consistent` 仅验证末条零速及 `duration_exceeded` 与 `estopped` 同真同假。R3：首行照抄卡片模型行。

未核实：实机通信、固件与停车精度；模型行按卡片声明填写，未独立核实启动参数与 CLI 版本。本轮仅离线 mock 自测，未运行预注册核对与三基线。

待办／下一令（CC）：按卡验收，合并时运行预注册核对。无新增依赖缺口。

移交主理人：无。

本轮执行：内部工单。
