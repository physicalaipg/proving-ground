> 所用模型：gpt-6-astra ｜ effort：low ｜ codex 0.157.1

# 内部工单 审查报告

## 范围与基线

只评不改。分支 `codex/内部工单`，开工 HEAD 为 `8461b5628d3452ec1c0bdd3c15f67168ea3952e6`（补丁1）。下文行号和宿主测试均针对此提交；首行按卡照抄，不作为运行时模型配置的独立核验。

开工时 `main` 已到 `69cbc77bb801d8c532061f7b407de1ac9e77ca35`，比本工作区多三个提交。只读核过 `git diff HEAD main`：固件、驱动、real_env、备份脚本不变；卡内 smoke 的后续差异为相机预设、选择参数和元数据，未改变下述路径与里程问题。没有为同步基线修改白名单外文件；后续相机修订的完整运行测试未核实，106 项通过不能称为当前 main 的 110 项通过。由 CC 在合并前核对基线并重跑。

## 发现（每条一行）

X3-01｜阻断首通电｜`real/firmware/yb-eet01-json/main/main.c:106–108,125–131,32–35`｜串口任务持有 proto_lock 时卡住，控制环无限等锁，既不检查心跳也不调用刹车，低压采样也等同一锁｜handle_line 的回显、错帧、反馈都同步调用 uart_write_bytes；control_task 使用 portMAX_DELAY，不能保证 README 所述“串口任务卡住时照样生效”；正常断开主机是否导致 UART 阻塞未核实，不把普通拔线等同于此故障｜把输出移出协议锁，并让控制环获取状态失败时有独立、有界的刹停路径。
X3-02｜阻断首通电｜`real/firmware/yb-eet01-json/main/drive.c:112–119,154–165`｜只有双侧目标同时为零才清 PID、刹车；单侧目标归零且编码器静止时，历史输出仍可持续驱动该侧，解除堵转可能突然转动｜按原公式从零状态以目标 0.1 m/s、实测 0 连算 100 拍，再把该侧目标改零且另一侧非零，前三拍 PID 为 100.841、101.859、101.859，对应 PWM 300、301、301/400｜按轮对零目标刹车并清该轮 PID 状态。
X3-03｜首通电后修｜`real/ugv02.py:203–207,249`、`real/firmware/yb-eet01-json/main/drive.c:168–185`｜停止后立即读到的 100 ms 平均残余轮速被保持到下一次采样并积分，静置时间被算成移动；小于零速阈值的残余还可跨较长观察间隔继续累积，影响 smoke 到达判断｜注入 L=R=0.1 的反馈，FakeClock 前进 10 秒，再注入零反馈，实际 driver.odometry 返回 distance_m=1.0；默认 settle_s=0.30 时同样会把残余值外推整段静置，理想目标轮速 mock 测不到｜停车阶段持续采样到确认静止，并界定积分有效时间，禁止无限外推过期轮速。
X3-04｜阻断首通电｜`tools/yb_backup.sh:92–115,123–136`｜两次同样的截短读出仍可被称为“4 MB 整片备份成立”，restore 也接受并进入写入；哈希一致只保证文件一致，不保证完整或来自目标板｜临时 fake esptool 报 4 MB，两次仅产出 32770 字节（偏移 0 为 E9、0x8000 为 AA50，其余零），LC_ALL=C 下 backup 返回 0；同文件 restore 返回 0 且到达 MOCK WRITE REACHED；未访问设备｜核实两次文件长度等于探测容量并逐步检查落盘成功，回退校验目标芯片/容量及备份身份后才写。
X3-05｜阻断首通电｜`tools/yb_backup.sh:96`｜本机默认 locale 下 backup 在首次 read_flash 前因未定义变量退出，现有四条 self-test 不覆盖此路径｜bash 3.2.57、LC_ALL=C.UTF-8，fake probe 成功后 stderr 为 `line 96: size_hex…: unbound variable`、退出 1；将 LC_ALL=C 后继续；原因是变量名后紧跟全角右括号，未用花括号定界｜将此处及相邻非 ASCII 文本前的变量引用改为明确的花括号定界，并增加 backup 成功路径的离线覆盖。
X3-06｜首通电后修｜`real/real_env.py:31–35,81–83,99–100`｜observe 阶段收到低压会锁存驱动并抛错，却不设置 void_reason；smoke 将它记录成 aborted=1、void=0，偏离“低压回合作废”｜_note_void 仅在 act 和开启电压门槛的 reset 路径调用，observe→_verify_stopped→feedback 的 LowVoltageError 未记作废｜在所有反馈入口统一记录低压作废状态并继续传播异常。
X3-07｜建议｜`real/smoke.py:99–100,151–161,204–207`｜CLI 顶层拒绝 episodes 输出，但可导入的 run_real_episode/finalize 无同等保护，预先存在的 logs/frames/results.csv 子路径符号链接也可绕过顶层目录检查｜函数直接 mkdir/write，未逐一验证最终写入目标；仅做静态审查，未向 episodes 写入复现｜让所有写入口共用最终路径检查，限制在专用 smoke 目录并拒绝逃逸符号链接。

## §5 前五项逐问核查

### 1. 心跳与急停

- 上位机锁存：正常从 `set_wheels`/`move_for` 进入时，已核，未见解除锁存前再次发非零的新路径；`emergency_stop` 先置事件再等线锁。已经通过检查的在途写可能先完成，随后零速写才到达，不能把事件置位解释为硬件立即静止。固件不知道上位机急停状态：绕开该驱动直接发送合法非零 T=1，仍能清心跳锁存并转动；这是 X2 将急停锁存放上位机的边界，不是固件具有急停锁存。
- 超时边界：已核，未见问题。`yb_proto.c:221` 与 `mock_serial.py:49` 均为 `>`；恰等于 3000 ms 不停，3001 ms 后停。板上还受 10 ms 调度和 X3-01 影响。
- T=136：缺省 3000 ms 与预算一致；下限夹到 100 ms 只延长小超时配置，上限不与配置的 <=3 秒冲突。但 Python 在发送前截断到整数毫秒（ugv02.py:102），预算按原浮点校验；如 timeout=.1009、period=.0503、read=.0503，配置通过，实际 100 ms 小于预算 100.6 ms。极端自定义预算有不到 1 ms 的差异，建议 CC 按实际发送值校验；默认不受影响。mock 本身不夹范围。
- 回绕：已核，未见通常回绕问题。uint32_t 差值允许跨一次毫秒回绕，低压计时相同；不能据此保证超过完整 2^32 ms 不运行检查后仍正确。正常 10 ms 检查远短于约 49.7 天周期。
- 串口任务卡死：无锁时卡在接收不妨碍控制；持锁卡死则不能自停，见 X3-01。测试只覆盖纯 C 状态机，未模拟 FreeRTOS 锁和 UART 驱动故障。

### 2. 反馈字段、范围与真实轮速

字段逐项核对（`yb_proto.c:169–181`、`ugv02.py:190–208`）：

- `T`：首字段，整数 1001；上位机据它选帧，不依赖字段次序。
- `L`、`R`：第二、三字段，JSON 数字，四位小数、m/s；来自同侧两轮最近十拍平均实测脉冲。目标夹到 ±0.5 不等于实测限幅；驱动要求有限且绝对值 <=2，超范围抛 SafetyError 并急停。两轮平均可能掩盖单轮异常，单轮符号与反馈必须上板逐路核对。
- `r`、`p`、`y`：依次为横滚、俯仰、航向，JSON 数字，两位小数、度。正常 atan2 给 roll 约 ±180、pitch 约 ±90，yaw 每拍作 ±180 回绕；驱动不校验也不用于航位积分。
- `temp`：一位小数，摄氏度；`v`：两位小数，伏，最近一次 200 ms 电压采样值（启动采样前是零）。两者均无协议范围裁剪；默认驱动不验证，开启电压门槛才检 v 的数值、有限性和下限。6.5～8.4 V 是预期电池工作值，不是固件保证的取值范围。
- `low_voltage`：末字段、整数 0/1，stop==LOW_VOLTAGE 时为 1；上位机按真值处理并抛 LowVoltageError。旧帧缺此字段保持原行为。
- 全部浮点在输出前用 finite_or_zero 将非有限值变成零，传感器失败时可能报零或旧值，不能当作传感器健康证明。正常物理范围下帧小于 192 字节；极端有限大数导致缓冲区不足时整帧不发、上位机超时，而非发送截断 JSON。

实测与 mock 的差异：停止后 100 ms 窗口仍可非零；默认 0.30 秒等待通常足以冲掉窗口，但机械惯性、调度停顿、编码器噪声仍可能触发 `_verify_stopped`。停稳判据是左右均值 <=0.01，不保证每只轮子静止。里程问题见 X3-03；超过 ±2 实测会被急停，目标限速 mock 不能覆盖它。`host_test/proto_host.c:23–27` 同样把目标作为反馈，因此 106 项全过没有验证真实闭环、滤波或惯性。这里没有物理场地越界检测；smoke 的位姿和到达判定均基于该里程，不能据其成绩证明真车未越界。

夹帧：开机无 T 的标识行、回显、非运动错帧均会跳过；针对 got=1/11/13 的错帧不会跳过，而是按类型抛错急停，符合补丁1的新语义。超过 256 行或读取期限会超时急停，不保证无限噪声下仍找到反馈。

### 3. PID 与编码器

- 输出与饱和：已核，累计输出每拍夹在 ±200，没有另一个无限积累的积分变量；反向误差会减少输出，未见“隐藏积分项”造成无限 windup。但并非全部停车情形会清状态，单侧归零存在 X3-02；堵转、死区造成的振荡和制动距离仍未核实。
- 双侧非零转双零：已核，未见问题。下一次 drive_step 四轮 brake 并 memset(pid)，braked 防止重复处理；此结论以控制环能运行、驱动调用成功为前提。
- 单侧零：仍进 PID，不单独刹车，见 X3-02。
- int16_t 窗口：0.5 m/s、65 mm、1040 count/rev、10 ms 对应约 25.5 count/拍；32768 count/拍约等于 643 m/s，正常车速不致溢出。但长时间失调度后累计差值、噪声可超过窗口，强转没有检测；PCNT 累计 int 和 `count-last_count` 的长期溢出也未处理。当前无正常一拍溢出的证据，作为异常恢复/长时运行后续项，不假称已上板验证。
- 死区：已核，未见超 PWM 周期。绝对 PID 输出 <=200，取整后加 200，最高 400，等于 10 MHz/25 kHz 周期计数；零输出直接 brake。400 边界在实际 bdc_motor 组件上的全占空比行为未核实。

### 4. 低压锁存与优先级

- 已核，未见协议命令解除低压锁存的问题：共用 `stop` 枚举，心跳是 1、低压是 2。进入 latch 同时清双目标；T=1 低压分支在清心跳之前返回，零速仅刷新时间，非零返回错帧（超 ±2 提前静默忽略亦不改目标）；130/136/143 与未知命令均不能清它，任何这些命令的组合也不能清。
- 电压回升不清；只有 init/reset 重新初始化状态。这里“不可软件清除”指所暴露的串口命令，不排除整机复位。
- 两者同时成立低压优先：心跳仅在 stop==NONE 时写入，低压采样可覆盖 HEARTBEAT；后续 tick 不覆盖 LOW_VOLTAGE。
- 去抖：电压 >=阈值时 below=false，下次低压重新记 below_since；连续采样低于阈值达 >=2000 ms 才锁存。200 ms 采样不能证明两采样间绝无短暂回升，实际从物理越阈到触发约 2.0～2.2 秒加调度延迟。
- clear_estop：先发零速、再 feedback；反馈标志或先前非零错帧引发 LowVoltageError，进入 emergency_stop，执行不到 `_estop.clear()`，上位机仍锁存。协议层成立不代表执行器能越过 X3-01 的等锁问题；observe 作废标记另见 X3-06。

### 5. UGV02 兼容

- 对不发错帧、无 low_voltage 的 UGV02：已核，未见反馈解析、L/R 校验、里程算法、错误急停、clear_estop 与运动发送行为因本补丁变化；两段新分支均不命中，已有不认识的 T 与开机行继续跳过。与补丁前源码 diff 核对过。
- 其它合法帧：依据仓内协议摘要，没有合法帧同时具备 T=-1、err、got=1/11/13，未见误认；实机固件全部扩展帧未核实。坏类型 err 可能变成解析 SafetyError，不能等同于合法帧兼容性失败。
- min_start_voltage_v 缺省 0，reset 的门槛函数直接返回，不多发反馈、不新增电压拒绝条件；已核，未见默认电压路径变化。严格说完整输出并非逐字零变化：ActResult.extra 新增 void/void_reason，配置对象新增字段，配置错误提示文字也变了；不能把“运动行为相同”扩大成全部序列化输出相同。

## §5 其余核查

### 6. smoke 与发布路径

CLI 默认落到 smoke_runs；`real_main` resolve 后拒绝仓外及 episodes 自身/后代路径，默认流程不会向 episodes 写。位姿来自左右轮里程中点积分，交给既有 harness 计分；未重写、包装计分逻辑。库入口与子路径符号链接例外见 X3-07。

`tools/build_site.py:133–149,186–202` 按 episodes 的 runs.csv 索引读 summary.csv，不自动扫描 smoke_runs；smoke 不生成 summary.csv、不更新 runs.csv，正常不会被站点摄取。但 load_run 未拒绝 run_rel 中的 `..`，不能声称任何人工索引/符号链接场景下都绝对不可读到；此既有发布工具边界不在本卡修改范围，只记后续。未运行站点构建。

### 7. 管脚逐脚

已核，yb_config.h 与仓内 pins.md 未见 GPIO 数字不一致：M1 PWM 4/5、编码器 6/7；M2 15/16、47/48；M3 9/10、11/12；M4 13/14、1/2；BOOT 0、KEY1 42、LED 45、舵机 8/21、雷达 TX/RX 17/18、IMU INT 41、SDA/SCL 40/39、UART TX/RX 43/44、蜂鸣器 46。电池表写 GPIO3，代码 ADC1/CHANNEL_2，与代码注释一致；芯片实际映射和厂商原件未独立核实。

方向注释有歧义：yb_config.h:37 称左侧 PWM 与编码器 AB 对调，实际 drive.c:52、70 是左 PWM、右编码器对调，README 与实现一致；GPIO 表本身不能证明方向正确。由 CC 校正文句并逐轮上板确认，未改文件。

### 8. 备份与回退

明确 read_flash 非零退出会返回 3，两哈希不同返回 4，坏头返回 5，restore 哈希不一致返回 6、未确认不写；这些拒绝路径已核。缺少文件长度与目标身份核验，见 X3-04；默认环境实际 backup 还被 X3-05 阻断。

此外 `set -uo pipefail` 没有使所有失败自动退出：sha 的状态、mv/rm 结果、sha256 文件写入及 tee 日志落盘失败未完整检查，不能仅凭最后成功提示证明备份及回退所需旁文件都落盘成功。restore 接受任意拥有匹配旁文件及两处魔数的镜像，不核对板身份、不要求长度等于目标容量；拿另一块兼容板的备份可通过这些检查。自测 4 项仅覆盖版本比对、改应用、空片、错误哈希，未覆盖这些成功路径缺口。

## 离线复现依据

X3-02 用系统 Python 指定环境在标准输入中直接按 drive.c:114–118 的原式计算（未保存测试或改固件）：k=pi*0.065/1040/0.01；初始 out=e1=e2=0，100 拍 err=0.1/k，然后 3 拍 err=0；逐拍夹 out 到 [-200,200] 并更新 e2/e1。输出如发现行所列。

X3-03 实际驱动复现核心（`PYTHONDONTWRITEBYTECODE=1 ../proving-ground/.venv/bin/python -`，标准输入执行）：

```python
from collections import deque
from real.mock_serial import FakeClock, MockSerial
from real.ugv02 import UGV02
c = FakeClock(); s = MockSerial(c); d = UGV02(s, clock=c)
s.replay = deque([dict(T=1001,L=.1,R=.1), dict(T=1001,L=0,R=0)])
d.feedback(); c.sleep(10); d.feedback()
print(d.odometry())  # distance_m: 1.0
```

X3-04/05 使用系统临时目录中的 fake esptool：flash_id 只打印 `Chip is ESP32-S3`、`Detected flash size: 4MB`；read_flash 仅用指定虚拟环境 python3 将 `bytearray(32770)` 的 [0]=233、[32768:32770]=bytes([170,80]) 写到最后一个参数路径；write_flash 仅打印 `MOCK WRITE REACHED`。YB_VENDOR_DIR 指向临时空目录、YB_BACKUP_DIR 指向临时目录、ESPTOOL 指向该 stub，串口参数为 /dev/null（只用于存在性检查，stub 不打开它），YB_CONFIRM=RESTORE。默认 locale 的 backup 退出 1；LC_ALL=C 下 backup 与 restore 均退出 0。所有样本为人工全零加魔数，不读板上镜像或凭证；临时目录已清理。

## 上板核对项（未核实）

- 四轮离地逐轮核轮位、电机/编码器正负反馈、刹车状态、零目标与 PID 响应；测控制周期、制动距离和满占空比边界。宿主测试没有编译 drive.c/main.c/sensors.c。
- IMU WHO_AM_I、寄存器量程/速率与温度比例，启动静置一秒零偏；运行读失败目前保留旧值。未获取外部手册，不把源码注释当成独立证据。
- 电池芯数、ADC 通道、分压与校准、实际低压持续两秒及回升不解锁；ADC 失败报零会约两秒后触发锁存，启动首次采样前反馈也为零。
- DTR/RTS 是否复位及启动三条配置是否丢失，开机帧交错、UART 故障时独立停止、任务创建成功和调度最坏延迟；四项任务/驱动的实机故障恢复均未验证。
- 修完备份脚本后由 CC 按规程执行整片备份、身份与长度核对、回退验证。这里仅 fake 工具运行，未执行真实串口、相机、ESP-IDF 编译、烧录或回退。

## 验收命令与交付说明

- `PYTHONDONTWRITEBYTECODE=1 ../proving-ground/.venv/bin/python -m pytest tests/real -q -p no:cacheprovider`：退出 0；尾行 `106 passed in 2.16s`。禁用字节码及 pytest 缓存以免写白名单外路径；pytest 内使用系统 cc 编译协议核心到临时目录。
- `PATH="<仓根>/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 bash tools/yb_backup.sh --self-test`：退出 0；尾行 `结果：4 过 / 0 失败`。脚本内 python3 同属指定虚拟环境。
- `git diff --stat main...HEAD`：报告提交后实跑，退出 0；仅含 `real/firmware/yb-eet01-json/docs/review-X3.md`；尾行 `1 file changed, 126 insertions(+)`。回填本行不改变报告行数；最终提交后复跑核对。

未跑三基线、prereg_check、真实设备或外部接口，未安装依赖。仓内只新建本报告，无修复代码或新增测试。发现交由 CC 复核修复，测试通过不是本卡自验收。

待办／下一令：CC 复核发现、修阻断项并覆盖对应离线故障路径；核对 main 后续修订、重跑验收后决定合并。移交主理人：物理操作（上板时四轮离地、量电压、核芯数与断电）；拍板（由 CC 复核后决定是否进门一）。

本轮执行：内部工单。

结论：修完阻断项后可以首通电。


# 第二轮
> 所用模型：gpt-6-astra ｜ effort：low ｜ codex 0.157.1

## 范围与基线

本轮只执行卡 §11，代码基线 `95cace00cf69031d3071bd376e24ac8ec1f5245c`；开工 HEAD 与 main 均为 `cf9c84493bb12c19a2556e359d6985cd135f3f56`，分支 `codex/内部工单`，工作区干净。开工命令 `git diff --stat 95cace0 HEAD` 只列 `docs/x-dev/内部工单.md`，尾行 `1 file changed, 37 insertions(+), 1 deletion(-)`，满足前置条件。模型行按卡照抄，不作为运行时配置的独立核验。首轮正文保持原字节；没有重审本轮范围外事项。

## 四个阻断项复核判词

### X3-01：REGRESSED

原来的“持协议锁写 UART，控制环无限等同一锁”已消除：`main/main.c:40–46,94–98,118–125,139–149` 将写串口移到锁外，电池、串口、控制三处都用有界等待；控制拿不到锁时以本拍局部零目标调用 drive_step。但新增“超时就丢整行”对无回包的运动／急停指令不安全，见 X3-08，因此总判 REGRESSED。

- 缓冲边界：已核，未见半截 JSON。io_write 装不下时不拷贝该段；`yb_proto.c:165,181,241–245` 的每次调用均为完整错帧、反馈或含换行的回显，且 snprintf 超长时整帧不发。缓冲为 LINE_MAX+1+192，正常回显加一帧可容纳。可能只剩完整回显而没有反馈，上位机随后读反馈超时；这不是发出半截 JSON。UART 本身传输故障未核实。
- 丢行的含义：丢 T=130 会反馈超时急停；丢 T=1、T=136 或 T=143 不一定被发现，因为上位机只核 serial.write 的字节数，不逐条等 ACK。尤其 emergency_stop 只置上位机锁存并发零速，不自动 feedback；“上位机读不到回包会自己超时急停”不能概括全部命令。丢零速可保留前一运动目标；控制若也曾等锁失败则只是暂刹，后续成功拿锁仍可恢复旧目标，直到心跳超时。
- 5 ms 与 10 ms：`yb_config.h:62–63`、`sdkconfig.defaults:9` 为 10 ms／5 ms、1000 Hz，默认换算为 5 tick，不是无限等锁；等待预算已用掉半个周期，余下 drive_step、调度与蜂鸣调用必须在剩余预算内。该值可作为有界故障退让，不能仅据大小关系认定满足最坏执行时间；实际调度延迟与连续丢锁须上板量测。vTaskDelayUntil 不保证超期后每拍仍相隔 10 ms。
- 其它停摆路径：并非硬件独立看门狗。`drive.c:132–138` 在刹车前读四路 PCNT，底层调用若卡死或 ESP_ERROR_CHECK 触发 abort，不能保证到达刹车；`drive.c:160–170`、`sensors.c:125–140` 仍有跨核临界区，反馈在 proto_lock 内取它们。正常短临界区未见锁序成环，但持 spinlock 的核停摆、关中断或控制任务不获调度，均非此次协议锁超时能覆盖。原有这些硬件故障边界本轮不另列修复任务；发生概率及板上失效状态未核实。

### X3-02：FIXED

`components/proto/yb_wheel.c:10–12` 对单轮零目标立即清 out/e1/e2；`main/drive.c:141–151` 独立刹该轮，不再等两侧都归零。非零→零→非零时 PID 历史干净，重新起步与初始状态一致（相同实测输入下）。速度滑动窗口仍保留用于反馈，这不是 PID 历史未清。

目标非零而浮点输出取整为 0 时，`drive.c:144,149–150,118–119` 经 motor_set 的零分支实际刹车；此时 braked 标志为 false，下一拍目标归零会再刹一次并清 PID，不会误跳刹车。目标持续非零时保留 PID 历史，是控制律的正常积累，不等同零目标清状态。

`host_test/wheel_host.c:9–18` 使用固件增益；`tests/real/test_yb_eet01_proto.py:50–61` 堵转 100 拍、归零三拍、重新起步，既断言全状态清零，也断言起步等于首拍。另在系统临时目录去掉 yb_wheel_step 零目标分支、保持原增量公式，用系统 cc 编译宿主壳并喂同样输入：归零三拍输出分别为 `100.8406 0.0000 5.0930`、`101.8592 0.0000 0.0000`、`101.8592 0.0000 0.0000`，重新起步与首拍不相等，旧公式确实违反该断言。未修改仓内源文件。这项测试覆盖控制律，不覆盖四路映射、bdc_motor 调用或实际刹车电气效果；后者仍须上板核对。

### X3-04：FIXED（原截短／缺少目标身份核对路径；旁文件混配边界另见 X3-10）

`tools/yb_backup.sh:102–110` 每次读出都核完整字节数，`112–129` 核两哈希长度与一致性，并用 && 链检查 mv、rm、两个旁文件写入、最终镜像哈希与旁文件非空。`restore:142–151,158–170` 要求同名哈希、镜像头、.id、镜像长度与身份记录容量一致，再核目标 chip/mac/size 全文一致；缺任何身份字段拒绝。正常文件组不被改配的前提下，两次同样截短、只换镜像而保留原哈希、整套换成其它板备份、目标板 MAC 或容量不同，均不能写入。

自测后五条（`tools/yb_backup.sh:221–243`）确实走独立脚本子进程和 fake esptool：UTF-8 备份成功、截短备份拒绝、同板回退成功、换板拒绝、截短回退拒绝，实跑全部通过。它们未覆盖磁盘失败注入、旁文件混配或探测后更换设备的竞态，不能扩大为所有错误场景都安全。identify 的 tee 落盘失败仍只检查 PIPESTATUS[0]（131–132）；可能缺判版日志，但镜像、哈希和身份落盘已先检查，记作后续而不扩大本轮修复范围。

board_id（36–42）只接收行首 `Chip is ESP32-S3 ...`／`Chip type: ESP32-S3 ...`、`MAC: ...`、包含 `Detected flash size: NMB` 的文本；chip 取首个无空格词、MAC 转小写。带前导空白、不同标签、不同容量单位的输出不保证可解析。没有逐版本离线输出夹具或本轮外部查证，因此“esptool 所有版本都取得到”标未核实；解析缺项时 backup 返回 3，restore 拒绝写入，是拒绝继续而非跳过身份检查。探测与实际读写为不同进程，期间换板／换文件的竞态未消除；现流程依赖作业期间设备和文件不变。

### X3-05：FIXED

原 backup 与 restore 中变量紧邻全角括号的引用已用 `${size_hex}`、`${image}` 等定界（`tools/yb_backup.sh:103,150,152`）；逐行检查并运行 `rg -n '\$[A-Za-z_][A-Za-z_0-9]*[^\x00-\x7F]' tools/yb_backup.sh`，无匹配、退出 1。剩余 `$image.id` 等引用后接 ASCII 点，不属于本问题。自测 fake 函数明确 `LC_ALL=en_US.UTF-8`（232），成功走完备份与回退；本机未再出现 unbound variable。

## §5 第 9 项逐问回答

- 裁切：已核，未见指定口径问题。`camera.py:31–48,105,130–134` 在实际帧严格等于配置采集尺寸后，按输出宽高比裁最大居中窗口；1280×720 到 4:3 留 960×720、左右各去 160，再 INTER_AREA 缩到 640×480，并 BGR→RGB。帧尺寸不符（包括实际宽高比不符）直接 ValueError，不悄悄缩放冒充预设；set 返回 false 本身不报错，首次 read 按真实尺寸兜底。通用 center_crop 对宽图裁左右、窄图裁上下，整数除法可能差一像素，随后缩到精确输出尺寸；MF200 此处整除。注入 frame_source 是直接供成品 RGB，必须为输出尺寸，不走 USB 裁切。测试覆盖色带边界、窄长图和拒绝 640×480 采集帧。
- 设备下标：不能认定一定一致，见 X3-09。list_cameras 仅排序 system_profiler 的 unique-id 字符串；没有从实际 VideoCapture 校验 unique-id，也没有证明两种枚举的设备集合、排序语义和时间点相同。README 引用 OpenCV 5.x 源文件的说法，本轮无本地该源码证据、未出网，标未核实。即使某版本同样排序，两次枚举间插拔或接力相机上线也会使旧下标指向另一台；设备仅在两个 read 之间变化时后端是否重绑未核实，不声称一定重绑。
- 零／多匹配：已核，未见静默择一。产品串大小写不敏感子串匹配，VID:PID 解析十六进制输入并匹配型号中的十进制 VendorID/ProductID；命中数非 1 即 OSError。设备字段缺失会报错或不匹配，不是默认选 0。`tests/real/test_camera.py:107–113` 覆盖零／多匹配；但传入手工 DEVICES，不测试 system_profiler 排序与 AVFoundation 的一致性。
- uvc-util：已核，未见“可执行文件缺失／退出非零后悄悄退自动”。`camera.py:83–97,117–121` 用 check=True，异常转 OSError 并 release；按编号且配置锁定也拒绝。两值均 None 时不调用工具，明确使用默认自动。测试 89–104 用假 run 验证失败。工具返回 0 只表明进程成功，本代码不读回控制值；部分控制已生效而后失败也不会回滚，之后重开设备的实际模式未核实。控制项名称、目标选择语义及开始取帧后是否复位均属上板核对项；本轮未安装或运行 uvc-util。

## 新发现（每条一行）

X3-08｜阻断首通电｜`real/firmware/yb-eet01-json/main/main.c:119–127,139–149`、`real/ugv02.py:123–133,155–168`｜有界等锁超时会静默丢弃零速／急停命令，上位机已锁存但固件可能继续旧目标，或短暂按零刹车后恢复旧目标直到心跳超时｜锁超时分支既不清协议目标也不通知上位机；对 MockSerial 注入一次“返回写入长度但不分发命令”，emergency_stop 后 estopped=True 而 wheels=(0.1,0.1)，2.9 秒仍非零，3.001 秒才由心跳清零；此实验验证丢行后果，不冒充实际 FreeRTOS 时序测试｜将命令处理超时送入控制环可见且不依赖协议锁的停止故障通道，清除旧目标并要求明确恢复后再允许运动。
X3-09｜首通电后修｜`real/camera.py:51–70,111`、`tests/real/test_camera.py:76,92,107–113`｜产品串／VID:PID 最终被转换为另一套枚举的数字下标，没有验证打开设备身份，可能成功打开错误相机且通过帧尺寸检查｜system_profiler 完成后才 VideoCapture；其间枚举顺序／集合改变即使两边原本同排序也可错位；测试替换 VideoCapture 并忽略参数，不能检出错选；未实机确认发生概率｜用实际后端设备唯一标识绑定并核验打开设备，不能保证时拒绝继续，落地采集前按规程遮挡车载镜头核对。
X3-10｜建议｜`tools/yb_backup.sh:126–128,142–170`｜.id 记录未绑定镜像哈希，另一份同容量合法头镜像连同其 .sha256 若误配目标板的 .id，仍可写入；不能将旁文件存在视为证明镜像确由该板备份｜临时生成 4194304 字节零填充镜像，仅置 E9／AA50 魔数及一个应用字节，配其真实 SHA256 与目标板三行 .id，fake esptool 报相同身份，restore 返回 0 且出现 MOCK WRITE REACHED；无真实镜像或设备参与；这是旁文件混配条件，不是单换镜像可绕过原哈希｜将镜像哈希与板身份一起记录并在 restore 交叉核对，固定备份文件组，明确不抵御人工同时篡改全部记录。

## 离线复现与上板边界

X3-08 复现：用指定虚拟环境 Python，继承 MockSerial，在一次 write 中直接 return len(data) 而不调用父类；先 UGV02.set_wheels(.1,.1)，置丢一次标志，再 emergency_stop；用 FakeClock 前进 2.9 和 .101 秒并读取 wheels。未改 MockSerial 或仓内测试。

X3-02 旧公式反证：临时副本删除 yb_wheel.c 的 target==0 清状态分支，以 `cc -std=c11 -I <components/proto> -I <main> <临时old.c> <host_test/wheel_host.c> -o <临时old>` 编译；输入与已有测试相同，输出见上。未编译 ESP-IDF 固件。

X3-10 复现：系统临时目录创建合成镜像与两旁文件；fake esptool 的 flash_id 只输出三行模拟身份，write_flash 只输出 MOCK WRITE REACHED；ESPTOOL／YB_VENDOR_DIR 指向临时位置，YB_CONFIRM=RESTORE，调用 `bash tools/yb_backup.sh restore /dev/null <临时replacement.bin>`。/dev/null 仅通过脚本存在性检查，stub 不打开设备。临时目录自动清理。

上板核对项（未核实）：5 ms 等锁与 10 ms 控制的最坏延迟、UART 故障下刹车及恢复、四轮独立零目标制动、PCNT／电机 API 故障状态、实际相机身份与插拔变化、曝光／白平衡读回。相机只用于本 smoke 帧存档，不参与脚本 oracle 控制（real/README.md:87），故 X3-09 不单独升级为首通电阻断，但不能据现有测试批准落地数据口径。首轮 X3-03、X3-06、X3-07 本轮不重复报、不升级。

## 验收命令与交付说明

- `PYTHONDONTWRITEBYTECODE=1 ../proving-ground/.venv/bin/python -m pytest tests/real -q -p no:cacheprovider`：退出 0；尾行 `113 passed in 2.01s`。等价执行卡内 pytest，禁字节码与缓存，宿主 cc 产物在临时目录。
- `PATH="<仓根>/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 bash tools/yb_backup.sh --self-test`：退出 0；尾行 `结果：9 过 / 0 失败`。
- `git diff --stat main...HEAD`：提交后实跑，退出 0；只含 `real/firmware/yb-eet01-json/docs/review-X3.md`，尾行 `1 file changed, 75 insertions(+)`；回填不改变行数，最终提交后复跑。

仅追加指定报告，首轮字节前缀校验通过；没有修代码、增加仓内测试、联网、安装依赖、调用真实设备、运行 uvc-util、编译固件或运行 prereg_check。测试通过不替代 CC 验收。

待办／下一令：CC 复核 X3-08 并修复急停丢行故障路径；处理相机身份验证与备份旁文件混配建议，重跑验收后决定合并。移交主理人：物理操作（上板核对、相机遮挡与设备插拔）；拍板（CC 复核后决定门一是否继续）。

结论：修完阻断项后可以首通电。
本轮执行：内部工单（第二轮）


# 第三轮
> 所用模型：gpt-6-astra ｜ effort：low ｜ codex codex-cli 0.158.0

## 范围、版本与基线

只执行卡 §13。代码基线 `11df588d7d07f3c2df894061b85db454341155f5`；开工 HEAD/main 均为 `bf7b21e9fa3017d563c89b0f026c57da7e6e2611`，分支 `codex/内部工单`，工作区干净。`git diff --stat 11df588 HEAD` 只列 `docs/x-dev/内部工单.md`，尾行 `1 file changed, 17 insertions(+), 14 deletions(-)`，前置条件通过。

`codex --version` 的原始输出如下；实际先运行了命令，但命令前发过一句进度说明，因此没有严格满足“第一条回复即原始输出”的顺序要求，在此如实记录。模型与 effort 按卡照抄，不作为运行时配置的独立核验。

```text
WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)
codex-cli 0.158.0
```

前两轮原文件为 32047 字节、201 行，SHA256 `b38db8d124fc5096d6a951923cbc2959d1a4a79bd1a09d0e900c1c40ace3b271`；本轮只追加，交付前按此字节前缀核验。

## X3-08 复核判词：NOT FIXED（端到端安全要求尚未闭合）

原来“等锁超时立即丢掉手中整行、控制恢复时直接沿用 proto 旧目标”的直接路径已修：`main/main.c:128–136` 保留当前行，迟到处理后在同一协议锁内再次清目标；`155–166` 消费故障旗并清目标，拿不到锁则以本拍局部零目标调用 drive_step。纯 C 锁存规则成立。但不能把它扩写成“指令绝不丢、故障即实际刹车、上位机一见次数增长即急停”；任务时序、独立刹车与消费计数的缺口如下。没有发现必须判为 REGRESSED 的新协议锁死循环；本判词针对卡要求核验的完整链路，不否认上述局部修复。

### 丢行、旧目标与无限等锁

- `main.c:118–123` 仍主动丢超长行，协议核心 `yb_proto.c:246–248,267` 仍忽略坏行／越硬限的运动行，这是已有输入规则。对正常长度有效行，已经读入 line 的一行不再因那次超时而丢弃。但串口任务在 `131` 无限等锁，期间不再收字节；接收缓存只有 1024（`21,214`），无硬件流控（`206`），持续输入超过有限缓冲后不能保证后续完整指令保留。未在真实 UART 复现溢出或核定驱动丢弃粒度；不能承诺“一行不丢”。
- 无限等锁可以使串口任务永久停在 `131`，查询与急停都无法分发；不是新的环形锁依赖，且不会单凭该等待把仍可调度的控制任务一起阻塞。控制的协议锁等待仍为 5 tick（配置 1000 Hz、等待 5 ms），失败后局部目标为零。只有“等协议锁”有界；drive_step 先读 PCNT 再刹车，控制任务自身卡死的风险没有被有界等待覆盖。
- 原 proto 非零目标在故障旗被消费后被清掉；没有无新 T:1 而从该状态自动恢复目标的代码。但是 `main.c:157` exchange 之后，另核 UART 可超时置旗，控制仍会把本次 `159–160` 的旧快照送进 `166`。这是一个待下一拍处理的窗口，不是 atomic_bool 内存数据竞争；下一拍能运行才会清掉。不能保证旗置位即本拍电机输出为零，也不能把 5 ms 等锁预算当成刹车总时限。

### 故障旗、迟到行与随后指令的次序

- C11 默认顺序一致的 atomic_store/exchange 保证：置位若排在 exchange 前，本次读取 true；排在它后则留下 true 供下次消费。只有控制任务清旗，未见普通非原子读改写造成置位丢失。多次置 true 会合并，见 X3-14。
- UART 迟到行在持锁内先处理、再 fault、再放锁，控制不能在二者之间读到其非零目标，这一点已核，未见问题。迟到的是 T:130 时，反馈却在 `133` 内生成，计数在 `135` 才加；发出的这一帧可能仍是故障前次数，须等后续查询才能看见。
- 控制可能先消费旗并刹车，然后 UART 才拿到锁处理迟到行；UART 再 fault 后，紧随的正常 T:1 又能清锁存。如果两条行均在下一控制拍前处理完，控制可完全看不到这次锁存。另一种次序是 UART 先处理后续 T:1、控制再消费尚未清的旗，于是这条正常新目标又被清掉。两种次序均与现代码相容，实际发生频率未核实。
- 因而“随后按时 T:1 可恢复”在协议上是有意允许的，并不区分故障前已排在 RX 队列的旧续发与操作者知情后的恢复。上位机每 0.1 s 自动续发也满足清除条件；在计数已被反馈读到后仍继续续发的实证见 X3-12。锁存曾经置位不等于电机至少实际刹过一拍。

### 优先级、计数与兼容

- 已核，低压最高：`yb_proto.c:235–237` 先记次数，低压时直接返回、不覆盖低压；电压采样 `215–217` 可覆盖已有等锁／心跳锁存。等锁可盖心跳；tick `225–227` 仅在 NONE 且目标非零时产生心跳锁存，不覆盖等锁。有效 T:1 清等锁／心跳，低压分支先返回、不能清低压。查询、回显设置、超时设置不清锁存。
- 次数在协议核心每次 fault 调用增加，UINT32_MAX 饱和，不因 T:1 清零，init/复位则清零；帧新增整数 lock_faults。驱动只在通过低压、L/R 校验之后保存该整数（`ugv02.py:198–211`）；缺字段按零，非法类型／负值不更新，回退值不拒绝。复位或缺字段可令差值为负，饱和后新故障也无增长；这些边界不满足跨复位或无限运行的单调事件记录，实机复位检测未核实。
- `real_env.py:95–103` 只在 observe 停稳检查成功后、或 act 末尾执行计数比较；并非每帧消费。遗漏与延迟见 X3-12/13。最后一帧生成以后发生的故障、迟到 T:130 在生成帧之后才加的次数、close 的零速命令遇故障，都可能没有再查询；smoke 的 meta 是“最后已见差值”，不是回合结束时固件总数的确认快照。
- 始终不带字段的 UGV02：已核，driver.lock_faults 始终 0，起点及差值均 0，不新增急停、拒绝或协议命令；L/R 校验、里程积分、clear_estop 的原行为不变，已有测试覆盖正常动作。序列化输出并非逐字相同：ActResult.extra 新增 lock_faults，smoke meta 新增按回合号的记录。混用带字段与缺字段帧不是这一兼容结论覆盖的情形。

### README 锁存表逐格核对

- 心跳行：触发、清除、优先级、无专门反馈旗、正常驱动续发的描述与代码相符。蜂鸣不是每次进锁存必有：`main.c:161,167–168` 只看控制采样的布尔 tripped 上升沿，锁存若在两拍之间被 T:1 清掉会漏鸣。
- 低压行：默认启用时阈值 6.5 V、连续采样去抖 2 秒、仅复位清除、最高优先级、low_voltage 字段与驱动抛错相符；电池任务在新锁存时调用 beep_once。表中“回合作废”不能覆盖所有 observe 异常路径（前轮 X3-06，按卡不重复报）。电压保护可由编译配置关闭，表描述的是默认配置。
- 等锁行：5 ms 等待、有效 T:1 清除、中优先级、帧中次数而非锁存旗与实现方向一致；蜂鸣同样取决于控制采样上升沿，HEARTBEAT→LOCK_FAULT 时 tripped 一直 true，不额外鸣。累计次数不能视为逐次超时精确计数（X3-14）；“增长即急停作废”不成立（X3-12/13）；meta 写的是最新已见差值。基线注释“第一帧”在启用起步电压检查时不符（X3-13）。因此表不是逐格都成立。

## 新加一问：独立急停与累计升级

现有应用代码没有不经控制任务的运行期刹车路径。`main.c:225–227` 创建的任务中，UART／传感器仅置故障旗或改协议状态；运行期 bdc_motor_brake 只在 drive_step／motor_set 内，均由 control_task 调用。若控制环持协议锁卡死，另两任务超时后只能置旗，UART 随后无限等锁，没有任务能把旗执行成刹车。已有 PWM 不能因变量变零而自行停止。`sdkconfig.defaults` 没有对这种故障指定看门狗停机／电机安全态；本轮未编译，也未核定 IDF 默认看门狗是否启用、监视对象、复位时限及复位期间电机管脚状态，不能将其认作已验证后备刹车，见 X3-11。

判断：首通电前必须闭合这个单点失效的停止保证；否则带新固件运行时，上位机急停和心跳都可同时失效，软件无可证明的停车上界。具体采用硬件禁止驱动、独立监控控制进度的看门狗，或经验证的复位安全态，由 CSO 裁定；本报告不改方案。四轮离地和可直接断电是物理核对条件，不证明现固件具备独立急停。

累计升级：建议对重复等锁故障升级为仅复位可清，避免每条自动续发反复解锁；但不能先随意指定 N 次。须先定义一次“故障事件”、去重计数，并确定恢复授权（正常续发不是知情恢复）。当前布尔合并又双记的计数不适合作为可靠升级阈值。此策略也不能替代首次故障的独立刹车或逐帧急停；是否采用及阈值由 CSO 拍板。

## 新发现（每条一行）

X3-11｜阻断首通电｜`real/firmware/yb-eet01-json/main/main.c:98–100,128–135,155–166,225–227`、`main/drive.c:132–146`、`sdkconfig.defaults:1–9`｜控制任务持锁卡死时没有独立执行刹车的应用路径，心跳、故障旗及上位机零速均不能保证电机停下｜运行期刹车调用都依赖 control_task；UART／传感器仅置旗，已有看门狗的配置及复位电气安全态未核实；这是 §13 新问要求评定的既有边界，不冒称本次修复引入｜增加并验证独立于协议锁及控制任务的停止保障，给出故障到停机的最坏时限。
X3-12｜阻断首通电｜`real/ugv02.py:209–212,229–255`、`real/real_env.py:66–78,95–103`｜已读到 lock_faults 增长仍在整个动作中续发非零 T:1，可反复清固件故障锁存，直到动作结束才急停作废｜离线注入每帧 count=1，基线 0：首个故障反馈在 FakeClock 0.3 s，仍共发 10 条非零指令、最后在 1.2 s，1.6 s 才完成作废；当前五条测试只断言 act 返回结果，漏测中途续发｜在每帧更新后、下一次非零发送前比较回合计数并锁存急停。
X3-13｜首通电后修｜`real/real_env.py:27–37,95–110,119–123`、`real/smoke.py:117–139`｜次数增长可不作废：observe 停稳检查抛错跳过计数检查；启用电压门槛时第一帧之后的增长被第二帧基线吞掉｜离线分别得到 count=1、delta=1、void_reason=''、estopped=True；及首帧 0、第二帧 1、baseline=1、delta=0、void_reason=''；smoke 捕获异常仅记 aborted，meta 可记正次数而 void=0｜从回合真正第一帧建立基线，在所有反馈入口及异常收尾统一记录故障与作废状态。
X3-14｜建议｜`real/firmware/yb-eet01-json/main/main.c:99,130–135,157,164`、`components/proto/yb_proto.c:233–237`、`real/README.md:102`｜lock_faults 统计的是 fault 调用次数，既可合并多个超时又可把一次 UART 超时记两次，不是精确超时次数｜多个 atomic_store(true) 在一次 exchange 前合为一次；一次 UART 超时既置旗又在迟到行处理后直接 fault，控制随后消费旗再 fault；饱和及复位另有边界｜明确事件定义并单点、去重计数后再用于诊断或累计升级阈值。

## 离线证据与测试覆盖边界

上述 Python 复现使用 `PYTHONDONTWRITEBYTECODE=1 ../proving-ground/.venv/bin/python -` 标准输入，runpy 只读加载现有 `tests/real/test_yb_eet01_proto.py` 的 robot_on，FakeClock、MockSerial 与注入相机；不存测试、不访问设备。可复现步骤：

- X3-12：robot_on(MockSerial(clock), clock).reset(1) 后，将 serial.replay 设为 100 帧 `dict(T=1001,L=0,R=0,v=7.4,lock_faults=1)`，执行 act(Action.FORWARD)，检查 serial.commands 中非零 T:1 的时间；输出 `first_fault_feedback_at=0.3 last_nonzero_at=1.2 nonzero_commands=10 end=1.6 void=True`。这是上位机控制流复现，不模拟实际 FreeRTOS 调度。
- X3-13a：同样 reset 后只注入一帧 `dict(T=1001,L=.1,R=.1,v=7.4,lock_faults=1)`，调用 observe 并捕获 SafetyError；输出 `count=1 delta=1 void='' estopped=True`。计数合法、轮速也在合法范围内，但超过停稳阈值。
- X3-13b：UGV02Config(min_start_voltage_v=7.0)，MockSerial 预置两帧合法零速、7.4 V 反馈，count 分别 0、1；构建 RealRobotUGV02 并 reset(1)，输出 `first_frame_count=0 second_frame_count=1 baseline=1 delta=0 void=''`。

`host_test/proto_host.c:55–56` 的 F 直接同步调用 yb_proto_fault；五条用例（`tests/real/test_yb_eet01_proto.py:305–373`）覆盖锁存到下一有效 T:1、计数跨清锁存保留、动作返回作废、UGV02 无字段兼容、低压优先。这些用例有价值，但不编译 main.c，不覆盖三任务／atomic 的时序、无限等待、UART 缓冲溢出、独立刹车及实际 PWM，也没有断言计数增长后下一条非零是否被拒绝。

上板核对项均未核实：控制持锁停摆时实际电机状态及独立停机时限；迟到查询与续发交错的计数／刹车；连续故障时蜂鸣与调度；复位后的输出安全态。未重审卡外项目；X3-03、X3-06、X3-07、X3-09 不重复报、不升级，X3-10 不复审（仅按卡跑完整备份自测）。

## 验收命令与交付说明

- `PYTHONDONTWRITEBYTECODE=1 ../proving-ground/.venv/bin/python -m pytest tests/real -q -p no:cacheprovider`：退出 0；尾行 `118 passed in 4.58s`。等价执行卡内 pytest；禁字节码与缓存，宿主 cc 产物在系统临时目录。
- `PATH="<仓根>/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 bash tools/yb_backup.sh --self-test`：退出 0；尾行 `结果：10 过 / 0 失败`。
- `git diff --stat main...HEAD`：提交后实跑，退出 0；只含 `real/firmware/yb-eet01-json/docs/review-X3.md`，尾行 `1 file changed, 87 insertions(+)`；回填本行不改变行数，最终提交后复跑。

仅追加指定报告；前两轮原始字节前缀交付前核验。没有修代码、加仓内测试、出网、安装依赖、编译固件、触碰真实串口／相机、运行三基线或 prereg_check。测试通过不替代 CC 验收，本报告由 CC 复核。

待办／下一令：CC 复核 X3-11～X3-14，修复获准项并重跑验收，补齐任务时序及故障上报检查；由 CC 处理文档与计数口径。移交主理人：拍板（独立停止保障、恢复授权及累计升级策略）；物理操作（获准后的离地上板、断电与故障注入核对）。

结论：修完阻断项后可以首通电。
本轮执行：内部工单（第三轮）

# 第四轮
> 所用模型：gpt-6-astra ｜ effort：low ｜ codex codex-cli 0.158.0

## 范围、版本与前置检查

本轮只执行卡 §14；代码对象 `bd2b9fb863a99052965ec1b3e2565fd8463d458b`。开工 HEAD/main 为 `25aaf7d06a3f40644bbe94d740218381d3b857be`，分支 `codex/内部工单`，工作区干净。`git diff --stat bd2b9fb HEAD` 只列 `docs/x-dev/内部工单.md`，尾行 `1 file changed, 10 insertions(+), 6 deletions(-)`，前置条件通过。按卡查看 `11df588..bd2b9fb` 改动面，以及 `c3dd656..65cc93e`、`65cc93e..bd2b9fb` 两组补丁，结论限于 §14 对象。

`codex --version` 原始输出如下。本轮先发了进度说明、读了卡，再运行版本命令，没有严格遵守“首条回复先报版本”的顺序；如实留记。模型与 effort 行按卡照抄，不作为运行时配置的独立核验。

```text
WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)
codex-cli 0.158.0
```

前三轮前缀实测为 46893 字节、288 行，SHA256 `613a4ee3c6e51f788715be5d11d4ad167425d0fdd83809fd67e6380256cee266`，与卡相符。本轮只在其后追加。以下固件短路径均相对于 `real/firmware/yb-eet01-json/`。

## 1. 三条不变量与必答停车时限

### ① 不成立（任意交错与端到端一拍保证）

正常完整投递后，零速有两份信息：`main/main.c:131–132` 先 atomic_store(true)，再覆盖指令槽；`155–160` 的控制拍先收快照、再 exchange(false)、再 drive_step。C11 原子默认顺序一致，不存在普通读改写把旗丢掉的问题：store 在 exchange 前则本次消费，在其后则下一次消费。后到非零不能清旗；零、非零都投递完再跑控制拍时，至少有一拍零输出，这部分宿主用例已核。

但两个通道不是一个原子事务。反例：已有非零目标，UART 在置旗后、投零快照前暂停；控制消费旗，刹一拍；UART 仍未运行时再走一拍，`yb_ctrl_tick` 只把上一拍的输出临时置零，没有清掉 `target_l/r`，于是旧目标重新出力（X3-15）。无需随后任何非零指令。单槽队列与原子旗各自正确，不能推出组合协议正确。两核任务间没有保证 UART 必在下一控制拍前执行完这两条语句的机制。

副作用：多个零速在同一次 exchange 前合并成一拍，不能解释为 N 条零速对应 N 拍；零速后马上发新非零会强制一拍刹车、清 PID，再于后拍重新起步，这是有意的运动扰动。更严重的非预期副作用是上面的旧目标恢复。把 STOP 定义为零速 T:1 与上位机当前映射一致，没有独立硬件 STOP 通道。

**必答：有零速或 STOP 延后超过一个控制周期的路径。** 逐条边界如下，不能把 10 ms 周期常量当硬实时上界：

- 卡片 README 将“到达”定义为 UART 收完整行；在收换行后到 `main.c:131` 之间被抢占／中断占用，刹车旗尚未置位，控制仍运行并喂狗，没有监视 UART 进度的 10 ms 时限。置旗与投槽之间暂停还可触发 X3-15 的停止后恢复；这是源码允许的交错，发生概率未核实。
- 控制已在 `159` 消费旧旗并取出非零局部 l/r 后，UART 才置旗，只能下一拍处理。若本拍的 PCNT/PWM 驱动、队列内部临界区或调度拖过周期，下一拍亦晚到；`vTaskDelayUntil` 不是 deadline enforcement。若控制停摆，兜底是约 300 ms 看门狗超时及其后的复位链，显然不是一个 10 ms 周期。
- 若以物理 RX 收到为起点（比 README 定义更强），前一行回包的 `uart_write_bytes`、字节收取、串口积压均可推迟读到 STOP；1024 字节 RX 缓冲、无流控也不能承诺任意输入速率下不丢完整行。这不重复报旧协议锁问题，但必须限制“一拍”的起点。
- 心跳停止是 `yb_ctrl_tick` 同拍检查；低压停止取决于 200 ms 电压槽采样及 2 s 去抖，传感器延迟不能当作已经判定 STOP；二者判定后仍需控制与 drive_step 正常执行。上位机急停／Action.STOP 发的是同一零速 T:1，没有另一个绕开上述路径的入口。

### ② 不成立（字面绝对要求）；设置快照与最后目标语义成立

`yb_proto.c:244–261` 将运动及心跳设置保存在 link 的持久快照，T:136 不清运动序号，T:1 不清 heartbeat_ms；覆盖队列不会因运动更新丢掉最新心跳设置。T:143 的 echo 在 link 本地立即更新，根本不走控制槽。多条 T:136 也是最后值生效。设置快照重复包含旧运动时，`302–306` 的 seen_seq 阻止当作新运动重执行。

同拍多条非零 T:1 只执行末条，不保证每条都在电机端呈现；按 README 已明确的“后条取代前条”语义不算实现缺陷。零速则额外保留旗，但只是一拍、且有 X3-15。`test_commands_inside_one_beat_all_take_effect` 证明串行模型下设置保留、echo 顺序与末目标，并非证明每条指令都得到独立执行。

旧遥测与控制重判：UART 用 `telem.stop/quiet` 判收，控制先处理新电压再收运动。如果 UART 见旧健康帧而控制已经低压锁存，命令会在 `yb_ctrl_command:307–310` 被消费并拒绝，控制不向 UART 回发错误，上位机该次写成功但无运动 ACK，后续 T:130 才看到 low_voltage。反过来，UART 见仍 quiet 的旧快照会回 boot_quiet，即使控制侧已经满 2 s；上位机将急停并记 reset。保护是保守的，但“收完即全部生效／绝无延后”不成立；反馈正常时旧约一拍，控制停摆时遥测可一直陈旧，不能无条件称“至多旧 10 ms”。

### ③ 成立（没有显式跨任务的阻塞等待）；不等于所有调用无阻塞

`main.c` 已无 xSemaphore、proto_lock；三个槽，Receive/Peek 的 timeout 全为 0，写全是 Overwrite。UART 不等待控制产出新快照，控制也不等 UART 投递；没有旧协议锁依赖。FreeRTOS 的零等待只是不阻塞等待队列数据／空位，队列内部仍有自旋临界区，不等于 lock-free 算法。

`main.c:115` UART 读最多等 100 ms；`133,197` 同步串口写可等待发送（TX buffer 配为 0）；`168,186` 是显式周期延时；传感器含 I2C、ADC 调用；控制调用 PCNT/PWM 驱动与看门狗、蜂鸣定时器。这些需要区分外设等待与跨协议任务等待。应用层 speed_lock 仅拷贝四个浮点数，且当前 drive_get_speeds 与写方都在控制任务；姿态 lock 跨 sensor/UART，`sensors.c:125–130` 不只是拷数，还在锁内算 atan2f/sqrtf，README 的“两处都只拷数”不精确。正常代码没有无限循环或 I/O 位于这两段临界区，正常执行预计短，但未测最坏占用时间，持锁核异常停摆时也不能给自旋等待绝对上界。

`test_no_task_waits_for_another` 只搜 main.c 的字符串、队列 timeout 及 reset 次数，不分析被调函数、编译后的临界区或调度，也不模拟 atomic/queue 交错，不能作为硬实时证明。前三条测试对 `host_test/proto_host.c:39–47,80–89` 的单线程模型有效，该模型把投旗与投槽连着做、整拍连着做，无法进入 X3-15 的中间点。

## 2. 后备刹车链

**配置与启动。** `sdkconfig.defaults:12–15` 指定任务看门狗 panic、两核 idle 不登记、silent reboot；`main.c:211–215,228` 将 timeout 改为 300 ms、idle mask 0、trigger_panic=true；控制任务 `147` 自登记，应用内没有第二个订阅者。主检出 `build/project_description.json` 指向本机 `~/esp/esp-idf-v5.1.2`，本轮只读该 SDK 与生成配置，没有构建。主检出 sdkconfig:953–961 已启用 IWDT（两核、300 ms）与 TWDT 的启动初始化，TWDT 初值 5 s、idle 两项关；`components/freertos/app_startup.c:185–199` 按这套配置初始化，之后才进 app_main。登记控制任务之前还没有该控制任务的 300 ms 进度保障，不能把启动全过程说成受它监视；drive_init 在 reconfigure 之前先刹车。

`CONFIG_ESP_SYSTEM_PANIC_SILENT_REBOOT=y` 且日志默认／最大等级为 0，支持“不走常规打印诊断后再复位”的配置意图，不是“300 ms 内实际电机已停”的测量。SDK 的 TWDT ISR、跨核异常处理、IWDT 和复位还有各自时序；控制核关中断时不能假定同一条 TWDT 软件异常链仍按普通调度及时完成，需四种自检分别实测。

**喂狗位置。** 每拍在 `main.c:154` 先喂再执行 selftest、读槽、驱动；若之后永久卡住，没有下一拍喂狗，故配置上可检测控制不前进。这与 X3-11 原来没有专门后备链不同。不过它检测循环存活，不验证四路 PWM 实际更新、轮子确实响应或一次刹车事务完成；驱动返回成功却电机仍异常的“环在转但输出不对”可持续喂狗。若一次调用很慢但每次小于阈值也可能周期超限而持续喂狗。`esp_task_wdt_reset()` 返回值未检查，注册调用则有 ESP_ERROR_CHECK；未据此推定实际登记失败。

**复位态与最坏多久。** 卡死之前的 PWM 硬件继续最后占空比，直到后备复位／其它硬件机制介入；变量归零无效。重新进入 app_main 后 `drive_init` 逐路初始化、enable、brake，随后才开串口和任务。复位中 GPIO 是否高阻、外部 H 桥如何解释、PWM 被哪个复位阶段撤掉、电机是刹还是滑、从停摆到物理停轮最坏多久：均未核实，列入上板项。300 ms 是喂狗超时配置，不含异常传播、复位启动和机械惯性，不得填成物理停车上限。代码链已补上，电气层尚不能宣称 X3-11 全部验毕；本轮遵循卡明示门一A 例外层次，不把待上板本身重新当作代码阻断项。

**静默与低压。** `yb_ctrl_init` 进入 YB_STOP_BOOT；`yb_ctrl_quiet:296–300` 要求开机满 2000 ms 且 below 为假才结束静默。初始电压在任务创建前采样，低压晚到 2 s 后才锁存时 below 仍使静默顺延，没有“仍低但低压尚未锁即放行”的正常采样逻辑空窗。控制每拍先电压后指令；LOW_VOLTAGE 盖 BOOT，T:1 无法清低压；设置不会清 BOOT。静默中零速照收、刷新心跳并置刹车旗，但不解除 BOOT；非零返回 boot_quiet；期满不会自行启动，需新的有效运动序号。静默起点是 yb_ctrl_init，而非物理复位瞬间，前面的初始化额外延长不出力期。电压采样任务不再产出或实际电压在采样间突变的检测上界未核实，不把离散采样解释成连续电压真值。

**原因与 boot。** link 保存 esp_reset_reason 原值；yb_boot_next 只看 RTC 魔数、非零 30 位 count 与 CRC，合法则加一，非法才采用 seed 低 30 位，零映到 1，运行期不写闪存。上电、RESET、WDT、panic、欠压均走同一初始化，不按原因漏掉某类。若 RTC 保留且计数未回绕，WDT 链逐次 +1 可计次；到 0x3fffffff 后回 1，严格单调有限。RTC 不保留则只有随机标记，不能当次数。

不能保证“看见每一种复位、RESET 永不撞号”：RTC 清除后新种子低位可能等于旧值，0 与 1 又均映到 1；内部熵源降低重复概率，不消灭碰撞。`test_reset_key_never_repeats_a_boot_value` 人为选了不同 seed，仅证明那些样例；把第二次清 RTC 后的 seed 也设 500，结果仍可为 500。正常近均匀种子的碰撞量级约 2^-30（值 1 的映射概率略高），README 已提概率，故不新报缺陷，但“两个分支都不撞号”的绝对措辞不成立。反馈基线 NA、回合前后发生、尚未收到新反馈、多个复位间无查询，也影响上位机能看见什么；reset_reason 是最后一次原因，不是事件队列。RTC 各复位类型的真实保留行为、随机性质量与欠压下 CRC/写入状况未核实。

## 3. X3-12：FIXED（原自动续发缺陷）；显式恢复边界见 X3-17

驱动每帧先保存合法非负整数／NA，再调用 `_check_episode_mark`，在同一 RLock 下比较、设置 episode_fault、emergency_stop 发零；move_for 的下一轮检查 estopped，set_wheels 本身也拒绝非零。现有三组用例断言首个偏离帧后非零数为 0，并断言同一时刻紧随查询发零，覆盖 fault 增长、boot 变化、boot 中途缺失。正常 episode 调用链无需等动作结束便停止，原 X3-12 已修。

逐问的“还有没有任何路径”答案仍为有：主动 `clear_estop()` 会在同一故障回合解除 `_estop`；由于 `_check_episode_mark:247` 见 episode_fault 已有值就 return，其健康检查没有再次阻止清除，后续 act 仍能发非零，虽最终 void 仍真。这不是自动续发回归，也不是本轮新加恢复 API；但在新的逐帧故障锁存规则下，不能将“此后不再发非零”写成无条件保证，见 X3-17。本轮未通过私有 `_send` 人为绕过 API 来制造发现。

boot_quiet 错帧排在 T:1001 前时，feedback 先抛 BootQuietError 并急停，不会继续读后面的反馈；act 的异常分支 `_note_void` 记 reset，boot/reset_reason 可仍是旧值或 NA，错帧不能提供新计数。observe 等异常入口既有的作废收尾问题按卡保留（X3-06/13），不重复报、不升级；不能据正常 act 测试宣称每个外层调用都落了 void。

NA 规则已核：基线 boot 有值，后帧缺失、负数、非整数都归 None 并判 reset；基线 faults 有值，后帧缺失或增长判 lock_fault；boot 偏离优先。基线 NA 的字段永不参与本回合比对，后来出现也不补建基线，因此首帧异常缺字段可漏判后续复位／次数变化；这是卡给定规则的直接代价，不是代码偏离。合法计数临时缺字段可保守误判复位／锁故障；faults 下降不判增长，复位靠 boot，旧固件无 boot 时无法补全。reset_reason 只记录／分类，不独立参与基线判定。以非法 L/R 或低压先抛错的帧不会走标记比对，仍急停，外层原因不一定记 reset。X3-13 的首帧基线问题照旧。

始终缺这些字段的 UGV02：基线为 (None,None)，不新增该规则引起的急停／作废；原 T:1/130、速度校验、里程与显式急停语义保留。记录值由 0 改为 None/null，新增分类为 None，输出形状并非逐字相同。混合缺失与出现不属于稳定旧固件兼容的保证。

smoke 真端口必填 firmware-ver，mock 用 mock；check_firmware 比对同目录已有非空 meta 的版本，不同或已有 meta 缺版本会拒跑。版本来自人工参数，不是已核验的设备握手：标识行未到则 firmware_banner=null；已有 results 而 meta 丢失、空对象或 JSON 损坏时 read_meta 返回 {}，版本检查放行，因此“同目录绝不混版本”只在元数据完整且参数真实时成立。此边界一并记入 X3-16 的版本隔离范围，未修改目录、回合或计分器。

## 4. 旧编号归宿（逐条）

- X3-01：原协议共享锁及持锁做输出的路径已消灭，整段输出仍缓冲后写串口；不能由此宣称整条运行链绝不阻塞。
- X3-08：**NOT FIXED（端到端停止保证）**；原“等锁超时丢行”分支确随 c3dd656 删除，但新 flag/slot 交错可在 STOP 后恢复旧目标（X3-15），三条宿主不变量测试不足以关闭原安全要求，仍按阻断项处理，不以“尚未上板”作为本判词依据。
- X3-11：代码与配置层已补专门的控制任务 WDT、panic 复位与启动静默；复位期间电气停车与最坏时限未核实，故不能称端到端已消灭，待按卡的门一A例外及上板门控验证。
- X3-14：原等锁计数的合并／双记机制随字段和故障入口删除已消灭；新 brake_flag 合并的是停拍请求，并不是原 fault 计数机制，相关问题另见 X3-15。

## 5. 自检钩子门控与用例：门控成立，数据隔离整体不成立

**编译门控成立。** yb_config.h 缺省 YB_SELFTEST=0；main/CMakeLists.txt 只在开关真时加入 selftest.c 并设置组件宏，且 CMAKE_BINARY_DIR 不以 build-selftest 结尾就 FATAL_ERROR。因此正常受支持构建流程在 build/ 开该开关会被拒绝，关时头文件的两个入口为恒假／空函数，生产命令走协议 default。后缀是同一宏选择的 0.2.0-selftest。未发现不改构建文件／注入额外编译手段而让受支持 build/ 产出带钩子固件的分支；不把主动篡改构建规则算绕过。

两份现存镜像 SHA256 与卡完全相同，生产 266160 字节、自检 266544 字节；strings 用例本轮未跳过，生产无四个命令名和 selftest、自检有全部名字。缺生产镜像时 skip 是检验缺口，不是固件后门，不能拿 145 passed/1 skipped 证明生产隔离；自检镜像缺失也会略过阳性对照。本轮两份俱在，验收有效，但字符串检查本身不是任意隐蔽调试入口的形式证明。

selftest.c 的四条逐字节命令仅置 pending，控制任务喂狗后执行阻塞、开中断空转、关中断空转、abort；生产两处空调用不改变 cmd_slot/brake_flag/control 的顺序，也不修复上述不变量缺口。源内未发现其它应用调试命令或运行期打开此门控的入口；JTAG/芯片 ROM 下载等不等于此应用协议钩子、未作硬件关闭核验。9101–9104 不在本仓生产协议 switch／列出的 UGV02 子集中，生产宿主收到回 unknown_cmd；“上游 json_cmd.h 全表最大 1041”仅有仓内文字，本轮未出网取得原表，完整上游号码无冲突未核实，测试集合相交不能证明完整上游表。

**数据隔离不成立（X3-16）。** CLI 对带后缀参数确实拒跑；驱动 feedback 读标识仅保存 firmware，不急停、不抛错、不设 episode_fault/void。smoke 在 run_episode 完成或捕获 SafetyError 后才将 row 标 selftest_firmware，之前动作、日志与图像已经产生。使用 RealRobotUGV02 而不经 smoke 收尾则没有该自检版本作废；正常 smoke 若确实读到后缀，最终结果被标 void，不应误说该路径最终有效。若未读到一次性标识且参数误填生产版，两种固件的 T:1001 没有可查询版本区别，当前靠操作者填值／刷回后核版本，代码不能保证自检数据不混进有效回合。

复位分类表已与本机 IDF 5.1.2 `components/esp_system/include/esp_system.h:24–35` 对照：1/2 上电或外部、3 软件、4–7 panic/各 WDT、9 brownout；0/8/10 等归 unknown，缺字段 None。分类吻合所选范围，但 brownout 指欠压，不代表所有断电都报 9；RESET 实际报 1 还是其它要实测。stallcheck 的最终接受条件用 fault 类而非单个 EXPECTED 值，符合要求；boot 是否恰好 +1 只是 rtc_kept 推断，随机重播碰巧 +1 或计数回绕会误导，不能代替 RTC 实测。

stallcheck 为串口台架记录，不是物理停车仪器：计时在 hook write/flush 完成后起算，记录收到 banner/反馈的时刻，含传输与轮速均值窗口；复位后新窗口归零不能单独证明机械已停。源文件自身要求目测／视频，保留为上板核对，不运行真串口。其宿主 StallSerial 人工规定复位延迟与原因，不能用该测试证明 WDT 在板上真的复位或 2 s 内停轮。

## 6. 取种序：成立（四条分别成立）

- 次序成立：main.c:224 enable →225 esp_random →226 disable →235 sensors_init；后者 sensors.c:93 battery_init →80 adc_oneshot_new_unit，首个应用 ADC 读取在 main.c:243 →sensors.c:146。
- 关熵源前没有应用 ADC 读：这段之前只有 drive_init；drive.c 初始化 BDC/PWM 与 PCNT，无 ADC/sensors 路径。内部熵源自己占用 SAR ADC 不应误称禁止的应用 ADC 采样。
- 同函数成对成立：两个调用都在 app_main，各一次，没有任务并发取种或重复开启路径。
- 中间无早退成立：enable 与 disable 之间只有 `seed = esp_random();`，无 return、分支、ESP_ERROR_CHECK。drive_init 的 ESP_ERROR_CHECK 失败在 enable 之前 panic，不属于“已经开启但未关闭”的早退；随机模块内部硬件故障或异步复位的真实行为未核实，不据此否定正常源码次序。

新增断言核对一次性、同一函数、调用排列、中间 token、前段没有 return/sensors/adc，以及 drive.c 无 adc/sensors 名字，能守住当前简单写法；它是词法测试，不能沿任意改名 helper 的传递调用证明无 ADC、也不测 IDF 熵源实现或随机性质量。人工读当前调用链补足了这一层，本轮未发现四条件不符。

## 7. 新发现（每条一行）

X3-15｜阻断首通电｜`real/firmware/yb-eet01-json/main/main.c:131–132,157–160`、`components/proto/yb_proto.c:336–348`｜STOP 的旗可先被控制消费，而零速快照未投槽，下一拍无新非零指令也恢复旧目标，UART 延迟时一直持续到零快照或心跳生效｜宿主 C 对真实 yb_ctrl 执行合法跨任务切点：已有 0.1 目标，置旗后暂停 UART，2110 ms tick(brake=true) 输出 0，2120 ms tick(false) 输出 0.1；host_test 没有该交错切点｜将停车请求与目标代际关联并保持停止，直到已消费不早于该 STOP 的快照，再只允许明确更晚的非零指令恢复。
X3-16｜首通电后修｜`real/ugv02.py:217–219`、`real/smoke.py:112–125,146–158`｜自检版本的驱动层即时隔离不存在，smoke 只事后作废；未读到标识且版本填错可混入有效回合，元数据缺失也使目录版本门槛失效｜离线注入 selftest banner 后 feedback 返回，再 act(FORWARD) 得 nonzero=10、estopped=False、void=False；生产与自检反馈均无 ver，check_firmware 在 meta={} 时放行｜在开回合前取得可验证的固件身份并拒绝自检或不明身份，在驱动读到后缀时立即锁存拒动，已有回合而版本元数据不完整时拒绝续写。
X3-17｜首通电后修｜`real/ugv02.py:190–195,245–259`、`real/real_env.py:55–68`｜故障回合显式 clear_estop 后可继续发非零，episode_fault 已有值反而跳过后续检查，违反“读到变化后该回合不再非零”的无条件表述｜离线基线 boot=7，反馈 boot=8 后 estopped=True；调用公开 clear_estop，再 act(FORWARD) 发非零 10 条，最终 void=True；不是自动续发回归｜将回合故障不可恢复状态与可手动清除的急停分离，故障回合只能结束并新建基线，或明确收窄并记录允许同回合恢复的规范。

## 离线复现与覆盖边界

未新增仓内测试。X3-15 用系统 cc 临时编译纯 C 协议核心，临时目录在系统临时区，退出即清理；关键复现体如下（它证明所列合法交错的控制状态结果，不冒称执行了真实双核调度）：

```c
yb_ctrl_t c; float l, r;
yb_ctrl_init(&c, .5f, 6.5f, 0);
yb_cmd_t moving = {.l=.1f, .r=.1f, .motion_ms=2100, .motion_seq=1, .heartbeat_ms=3000};
yb_ctrl_command(&c, &moving, 2100);
/* main.c:131 已置 true，UART 在 :132 前暂停；控制已消费此旗。 */
yb_ctrl_tick(&c, 2110, true, &l, &r);  /* 0.0 0.0 */
yb_ctrl_tick(&c, 2120, false, &l, &r); /* 0.1 0.1，无新运动命令 */
```

编译形式 `cc -std=c11 -I real/firmware/yb-eet01-json/components/proto <临时目录>/race.c real/firmware/yb-eet01-json/components/proto/yb_proto.c -lm -o <临时目录>/race`。实得两行 `brake beat: 0.0 0.0`、`next beat without new motion: 0.1 0.1`。

Python 复现均用 `PYTHONDONTWRITEBYTECODE=1 ../proving-ground/.venv/bin/python -`，runpy 只读加载 tests/real/test_yb_eet01_proto.py，复用 FakeClock/MockSerial/robot_on，未访问硬件。X3-16：reset 后向 serial._replies 追加一行 `{ "fw":"yb-eet01-json", "ver":"0.2.0-selftest" }`，driver.feedback，再 robot.act(Action.FORWARD)，统计追加后所有非零 T:1。X3-17：以 boot=7 的合法反馈 reset，再设 `serial.replay=deque([dict(T=1001,L=0,R=0,v=7.4,boot=8)]*100)`；driver.feedback、clear_estop、act(FORWARD)，统计末步非零指令。首次探索误将 replay 设 list，引发桩的 popleft AttributeError，已改用 deque 后重跑；该工具使用错误不作为产品发现。

未将 X3-03、06、07、09、13 重复报或升级。取种、boot、版本与故障计数的宿主用例证明纯软件规则；真实 ADC、UART、PWM、ESP-IDF 跨核调度和复位行为不在这些用例覆盖内。

## 上板核对项（均未核实）

- CC 先复核并修复 X3-15，再验证 STOP 与后续目标在两核抢占／发送积压下的顺序、最长从收行到实际刹车时间；不要把单线程宿主结果填成板测。
- 四种钩子的 WDT/panic 原因类、停摆到复位／标识时长、复位中 H 桥输入、PWM 及机械停轮时长；视频／测量与串口日志相互核对，区分复位后反馈零与物理轮速零。
- 上电、RESET、WDT、panic、欠压分别核 RTC 保留及 boot 变化、初始电压与静默衔接；熵源采样及实际随机碰撞不能由几条不同种子的宿主样例证明。
- 刷回生产镜像后核版本与两份镜像身份；标识漏读、错误参数与元数据缺失的隔离应由 CC 先补软件验证。

## 验收命令与交付说明

- 先执行 `shasum -a 256 ../proving-ground/real/firmware/yb-eet01-json/build/yb-eet01-json.bin ../proving-ground/real/firmware/yb-eet01-json/build-selftest/yb-eet01-json.bin`：生产 `a9206aeb50ba307ec052327d0c8ffd7ef7bab2cc70b0f2356c3b1833e8eea28a`；自检 `670e82c2c2c6785de8373d548d6f5ec2ff7922777669a41002e3f721160e82cf`，均匹配卡值。
- `YB_FW_IMAGES=../proving-ground/real/firmware/yb-eet01-json PYTHONDONTWRITEBYTECODE=1 ../proving-ground/.venv/bin/python -m pytest tests/real -q -p no:cacheprovider`：退出 0，尾行 `146 passed in 3.84s`。使用主检出 .venv，禁仓内字节码与 pytest 缓存，镜像用例未跳过。
- `PATH="<仓根>/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 bash tools/yb_backup.sh --self-test`：退出 0，尾行 `结果：10 过 / 0 失败`。
- `git diff --stat main...HEAD`：提交后实跑，退出 0，只含 `real/firmware/yb-eet01-json/docs/review-X3.md`；尾行 `1 file changed, 156 insertions(+)`。回填本行后行数不变，最终提交后复跑。

交付前重新核对前三轮字节前缀哈希；仅追加本报告、只提交到 codex/内部工单，不合并、不推送。未改代码、治理件、监视件或 episodes；未出网、装依赖、编译固件、碰真实设备；没有重跑三基线或 prereg_check。完整验收命令通过不等于本卡自行验收，报告由 CC 复核。

待办／下一令：CC 复核 X3-15～17、修复获准项、补交错与恢复入口用例，校正绝对时限／版本识别的文档表述；CC 组织后备刹车链及复位测量。移交主理人：物理操作（获准后离地上板、断电与测量）；拍板（同故障回合是否允许显式恢复，以及首通电门控）。

结论：修完阻断项后可以首通电。
本轮执行：内部工单（第四轮）

# 第五轮
> 所用模型：gpt-6-astra ｜ effort：low ｜ codex-cli 0.160.0

## 范围与开工核对

只评不改。本轮按 §15 只审 `52a7e28..f24ebf7` 在 `real/` 与 `tests/real/` 的两笔修复：`eef3098` 的停车序号，以及 `f24ebf7` 的停车确认。开工命令 `git diff --stat f24ebf7 HEAD -- real tests docs/x-dev` 只显示 `docs/x-dev/内部工单.md | 37 ++++++++++++++++++++++++++++++++++++-`，符合卡文要求；未把中间夹着的 docs/site/tools/protocol/episodes 提交纳入对象。前四轮前缀复核为 74119 字节、444 行、sha256 `a7d47059f79967d6cec7091019fbda5e162e028b8b1128959ebaf27da0ededff`。

`codex --version` 实得 `codex-cli 0.160.0`。说明：本轮实际首条对话先发了读卡进度说明，未严格按 §15 先原样贴版本输出；本报告按实得版本填写，不把这一点隐去。

## 本轮发现

无新增编号发现。X3-15 判 `FIXED`；X3-08 判 `FIXED`。未发现新增「阻断首通电」项。

## 四项审查

### 1. 停车序号

已核，X3-15 修法成立。`yb_link_handle_line()` 对每条有效 `T:1` 递增 `motion_seq`，并在回绕到 0 时跳到 1，所以停车序号不会与“无停车”的 0 混同（`yb_proto.c:249`、`yb_proto.h:45`）。串口任务在投指令槽前先 `atomic_store(&brake_seq, link_state.cmd.motion_seq)`，控制任务每拍用 `atomic_exchange(&brake_seq, 0)` 取走（`main.c:130-133,157-160`）。因此串口任务停在“写停车序号之后、投零速快照之前”时，控制环下一拍仍能拿到非 0 `stop_seq`。

控制侧在 `yb_ctrl_tick()` 中把 `stop_seq` 视作本拍刹车请求；若 `seen_seq` 早于该停车序号，就清 `target_l/target_r` 并记 `hold_seq`（`yb_proto.c:343-363`）。之后 `yb_ctrl_command()` 对早于 `hold_seq` 的快照直接返回，不刷新目标和心跳；到达该零速快照或更晚快照时清掉保持态（`yb_proto.c:304-322`）。这覆盖了第四轮 X3-15 的合法交错：旧目标不会在第二拍恢复。

回绕比较式是常见的 32 位半区序关系：只要待比较两序号差小于 `2^31`，`(int32_t)(a - b) < 0` 对跨 0 回绕仍成立。若同一个保持窗口内控制侧错过 `2^31` 条或更多有效运动快照，数学上会出现新旧关系歧义；当前 115200 串口吞吐、10 ms 控制环、任务看门狗复位链下，这不是门一可执行状态，也未见首通电阻断。`hold_seq=seen_seq=0` 的开机态不误判：无停车时 `stop_seq=0`，分支不进；第一条零速的序号非 0。

### 2. 原子序与双核可见性

判词：离线代码顺序成立；双核调度本身列为上板核对项。`atomic_store` 与 `atomic_exchange` 未显式放松内存序，按 C 原子默认顺序执行；串口任务顺序是写停车序号、再投单槽指令快照，控制任务顺序是取指令槽、再取停车序号、再 `drive_step()`。最坏切点下分三类：

- 串口任务停在写序号后、投槽前：控制侧本拍 `brake=true`，清目标并记 `hold_seq`，此后无新快照时一直输出 0。
- 零速快照已投槽：控制侧先收零速，目标已经是 0，再取停车序号，本拍仍输出 0。
- 零速后又来了更晚的非零快照并覆盖槽：控制侧可在一拍内处理更晚目标，但同拍仍被停车序号压成 0；下一拍才恢复更晚非零。这与既有不变量“同一拍内后到指令下一拍生效”一致。

宿主用例覆盖 `test_stop_seq_without_its_snapshot_keeps_wheels_at_zero`、`test_snapshot_older_than_the_stop_is_not_taken`、`test_later_command_in_the_beat_of_a_stop_still_takes_effect`。真实 ESP32 双核缓存、FreeRTOS 队列与原子实现未上板验证，不把宿主用例写成板测证明。

### 3. 保持态下的遥测与口径

已核，未见与门一口径冲突。保持态发生在停车序号先到、零速快照未到：`yb_ctrl_tick()` 清控制侧目标但不写 `stop`，因此反馈中的停车锁存仍可为 0；心跳分支只有在目标非零时才进入 `YB_STOP_HEARTBEAT`，目标已清零时不会仅因保持态触发心跳锁存（`yb_proto.c:347-360`）。`yb_ctrl_telem()` 输出的是控制侧当前目标，保持态下 `tl=tr=0`（`yb_proto.c:366-374`）。

这与 `real/README.md` 的门一“停发约 3 秒轮子自己停下”和急停三层口径不冲突：保持态表示已收到明确零速停车请求，车已经不应继续靠心跳锁存来证明停车；急停确认仍要求反馈目标为 0 且实测轮速低于阈值。卡文提到的 `protocol/safety-protocol.md` 当前仓库不存在，本项对该路径记为未核实。

### 4. X3-08 再判

判词：`FIXED`。吸收它的代码行是固件反馈帧新增 `tl/tr` 并由 `yb_ctrl_telem()` 填控制侧目标（`yb_proto.c:173-183,366-374`），上位机 `emergency_stop()` 发零速后进入 `_confirm_stop()`，用 `_read_frame()` 读反馈并由 `_frame_shows_stopped()` 同时检查轮速与目标（`real/ugv02.py:185-236,255-296`），回合结束停稳核验也改用同一判据（`real/real_env.py:132-137`）。对应用例为 `tests/real/test_yb_eet01_proto.py` 的「审查 X3-08」段：`test_feedback_reports_the_control_target`、`test_emergency_stop_is_confirmed_against_firmware_feedback`、`test_emergency_stop_resends_zero_speed_until_feedback_shows_stopped`、`test_emergency_stop_reports_unconfirmed_when_no_frame_shows_stopped`、`test_fault_seen_while_confirming_keeps_the_first_reason`、`test_frame_shows_stopped_rule`、`test_verify_stopped_after_motion_also_requires_target_zero`，以及 `tests/real/test_x2.py::test_additional_emergency_command_follows_zero_speed`。

逐问回答：

- 零速那一行在串口上丢了时，上位机现在能读出来：若固件目标仍非零或轮速仍高于阈值，`_frame_shows_stopped()` 不确认，循环再发零速再问；到上限仍无确认则 `stop_confirmed=False`，不再静默当作已停。
- `stop_confirm_tries * read_timeout_s` 是上位机确认循环的有界等待，默认 3 × 0.2 s；它不是物理停车上界。物理停车仍以确认帧、固件 ≤3 s 心跳兜底和主理人物理断电兜底为边界。
- 确认期间读到 boot/故障计数变化会经 `_check_episode_mark()` 记录 `episode_fault`，`_confirming` 防止递归急停覆盖第一原因（`real/ugv02.py:189-190,294-312`）。低压帧在 `raise_low_voltage=False` 的确认读里不抛错；若低压是外层反馈触发的原始故障，外层仍会传播并由 real_env 记作废。确认读单独遇到低压而外层没有再读到的分类未上板验证，但急停锁存本身没有被吞掉。
- `tl/tr` 至多旧 10 ms 时，刚收下零速但这一拍目标尚未清会造成一次未确认或继续重发，不会误判成已停；刚清目标但轮速未降也不会确认，因为轮速仍要低于阈值。保持态用例证明停车序号先到时 `tl/tr` 已为 0。
- UGV02 旧固件没有 `tl/tr` 时，`_frame_shows_stopped()` 在两个字段均缺失时回到只看 `L/R`，原行为逐项保留；字段缺一、布尔或字符串都不算新固件确认。

## 回归核对

X3-01～X3-14 中与对象 diff 同文件者复核后判词不变。X3-08 由本轮改判 `FIXED`；X3-12 仍为已修；X3-01 与 X3-14 的原机制仍已随去锁和后备刹车改动消灭；X3-11 仍是代码与配置层已补、电气层候上板。`ugv02.py`/`real_env.py` 相关的 X3-03、X3-06、X3-13 未见因本轮停车确认改动而改变判词。X3-16、X3-17 是第四轮新项，不在 §15 要求的 X3-01～X3-14 回归集合内，本轮未重审。

## 上板核对项（均未核实）

- ESP32 双核上 `brake_seq` 原子量、FreeRTOS 单槽队列与 10 ms 控制环在真实 UART 积压／抢占下的最长停车延迟；宿主只证明状态机交错，不证明板上调度。
- `tl/tr` 与真实编码器轮速的时间关系：确认帧显示目标归零后，机械轮速降到阈值的实测时长仍要离地录像／日志核对。
- 低压帧只在急停确认读中出现、外层不再读到时，回合作废分类是否满足门一记录口径；本轮只确认急停锁存不会被吞。
- `protocol/safety-protocol.md` 路径当前缺失；急停三层只按仓内 `real/README.md` 与固件 README 口径核对。

## 验收命令与交付说明

- 先执行 `shasum -a 256 ../proving-ground/real/firmware/yb-eet01-json/build/yb-eet01-json.bin ../proving-ground/real/firmware/yb-eet01-json/build-selftest/yb-eet01-json.bin`：生产 `476540c6ea9894fea502051567b477fc3e1d6e50d1ca93093b0b31df93e21c0a`，266208 字节；自检 `4ec5d1481579a52f3f5bd7da2b614ddf251428f09b508f6e27922bec68fe6266`，266592 字节；均匹配卡值。
- `YB_FW_IMAGES=../proving-ground/real/firmware/yb-eet01-json PYTHONDONTWRITEBYTECODE=1 ../proving-ground/.venv/bin/python -m pytest tests/real -q -p no:cacheprovider`：退出 0，尾行 `164 passed in 3.29s`。
- `PATH="<仓根>/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 bash tools/yb_backup.sh --self-test`：退出 0，尾行 `结果：10 过 / 0 失败`。
- `git diff --stat main...HEAD`：提交后实跑，退出 0，只含 `real/firmware/yb-eet01-json/docs/review-X3.md`；尾行 `1 file changed, 76 insertions(+)`。

仅追加本报告，未改代码、卡文、治理件、监视件或 episodes；未出网、装依赖、编译固件、碰串口或相机。完整验收命令通过不等于本卡自行验收，报告由 CC 复核并合并。

待办／下一令：CC 复核第五轮报告，补齐 `real/firmware/yb-eet01-json/docs/review-X3-summary.md` 的一级采信摘要并按门一流程组织上板核对。移交主理人：物理操作（离地上板、物理断电、录像／日志测量）；拍板（若低压只出现在确认读中的回合作废口径需要收窄或补充）。

结论：可以首通电。
本轮执行：内部工单（第五轮）
