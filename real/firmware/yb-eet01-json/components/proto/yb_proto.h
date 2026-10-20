// yb_proto —— UGV02 指令子集的行协议核心（纯 C，不依赖 ESP-IDF，宿主机可编译自检）
// 依据：real/docs/ugv02-protocol.md §1–§4；驱动层 real/ugv02.py 实际发出的四条指令。
// 分两半，各归一个任务独占，之间不共享状态、不加锁（内部工单）：
//   yb_link —— 串口任务：解析一行、回显、设置、回包；产出指令快照
//   yb_ctrl —— 控制任务：目标、停车锁存、心跳、低压去抖；产出遥测快照
// 两个快照各走一个单槽覆盖队列，由 main.c 投递。三条不变量见 README「运动通路」。
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// 协议层硬上限：超出即整条忽略、不回包（与 UGV02 固件一致）
#define YB_PROTO_REJECT_MPS        (2.0f)
// 心跳超时的可设范围，单位 ms。上限 3000：不允许把自停关掉或放长
#define YB_PROTO_HEARTBEAT_MIN_MS  (100u)
#define YB_PROTO_HEARTBEAT_MAX_MS  (3000u)
#define YB_PROTO_HEARTBEAT_DEFAULT_MS (3000u)
// 低压去抖：电压连续低于阈值满这么久才锁存
#define YB_PROTO_LOW_VOLT_DEBOUNCE_MS (2000u)
// 开机静默：任何复位后这么久之内不出力。与低压去抖等长，复位清掉的低压锁存在静默期内重新锁上
#define YB_PROTO_BOOT_QUIET_MS     (2000u)
// 一行指令的最大长度（含结尾 0）
#define YB_PROTO_LINE_MAX          (256)

// 停车锁存：心跳超时、低压、复位共用这一个状态量。非 NONE 时目标速度恒为 0。
// 只差清除规则：心跳锁存由下一条有效 T:1 清除（同 UGV02）；低压锁存软件清不掉，只有断电或复位重启才清；
// 复位锁存开机即在，静默期过后由下一条有效 T:1 清除。
typedef enum {
    YB_STOP_NONE = 0,
    YB_STOP_HEARTBEAT = 1,
    YB_STOP_LOW_VOLTAGE = 2,
    // 3 原为等锁故障锁存（审查 X3-08），随互斥锁退役，号不复用
    YB_STOP_BOOT = 4,
} yb_stop_t;

// 指令槽（串口任务 → 控制任务）：串口任务所知的最新指令快照。后到的盖掉先到的，设置与运动同在一张快照里，覆盖不丢设置
typedef struct {
    float l, r;              // 最近一条有效 T:1 的目标，m/s，未限幅
    uint32_t motion_ms;      // 它的到达时刻
    uint32_t motion_seq;     // 每收一条有效 T:1 加一；0 表示开机以来还没有收到过
    uint32_t heartbeat_ms;   // 心跳超时设置
} yb_cmd_t;

// 遥测槽（控制任务 → 串口任务）：控制任务每拍的状态快照
typedef struct {
    float l, r;              // 左右轮速度，m/s（编码器测得）
    float volt;              // 电池电压，V，最近一次采样值
    yb_stop_t stop;          // 停车锁存
    bool quiet;              // 开机静默中：非零 T:1 一律不收
    float tl, tr;            // 控制侧当前目标轮速，m/s；零速已收下、保持态、各种锁存时都是 0（审查 X3-08：上位机凭它确认停车）
} yb_telem_t;

// 反馈帧里不经控制任务的量
typedef struct {
    float roll, pitch, yaw;  // 度
    float temp;              // 摄氏度
} yb_feedback_t;

typedef struct {
    // 写出一段字节（一帧或一条回显，已含结尾 \n）
    void (*write)(const char *data, size_t len, void *ctx);
    // 取一次姿态与温度
    void (*feedback)(yb_feedback_t *out, void *ctx);
    void *ctx;
} yb_io_t;

// ── 串口侧 ──

typedef struct {
    yb_cmd_t cmd;               // 指令快照
    bool echo;                  // 回显开关，缺省关
    uint32_t boot;              // 本次开机的 boot 计数，随反馈帧上报
    uint32_t reset_reason;      // 本次开机的复位原因，随反馈帧上报
} yb_link_t;

// yb_link_handle_line 的返回位
#define YB_LINK_POST   (1u)     // 指令快照有更新，须投进指令槽
#define YB_LINK_STOP   (2u)     // 这一行是零速指令，须把它的序号记作停车序号

void yb_link_init(yb_link_t *k, uint32_t boot, uint32_t reset_reason);

// 开机以来遥测槽还没有过快照时用它：静默中、复位锁存
void yb_telem_boot(yb_telem_t *t);

// 处理一行（不含结尾换行）。坏行静默丢弃；未知指令与参数不全回错帧。telem 是手头最新的遥测快照，可以旧一拍。
void yb_link_handle_line(yb_link_t *k, const char *line, size_t len, uint32_t now_ms,
                         const yb_telem_t *telem, const yb_io_t *io, unsigned *flags);

// ── 控制侧 ──

typedef struct {
    float target_l, target_r;   // 目标轮速，m/s，已限幅
    float limit_mps;            // 固件侧限幅常量，来自 config
    uint32_t boot_ms;           // 开机时刻
    uint32_t last_motion_ms;    // 最近一条有效运动指令的到达时刻
    uint32_t heartbeat_ms;      // 心跳超时
    uint32_t seen_seq;          // 已处理到的运动指令序号
    uint32_t hold_seq;          // 先于快照到达的那条停车的序号，早于它的快照不取；0 表示没有
    yb_stop_t stop;             // 停车锁存
    float low_volt_v;           // 低压阈值，V；不大于 0 表示关闭低压保护
    float volt;                 // 最近一次电压采样，V
    bool below;                 // 当前是否处在连续低压段内
    uint32_t below_since_ms;    // 这一段低压的起始时刻
} yb_ctrl_t;

// 开机即在复位锁存里
void yb_ctrl_init(yb_ctrl_t *c, float limit_mps, float low_volt_v, uint32_t now_ms);

// 开机静默中：开机未满 YB_PROTO_BOOT_QUIET_MS，或低压去抖段还没落定（等它锁存或回升）
bool yb_ctrl_quiet(const yb_ctrl_t *c, uint32_t now_ms);

// 收下一张指令快照。串口侧按旧一拍的遥测放过来的非零目标，在这里按当拍的锁存再判一次
void yb_ctrl_command(yb_ctrl_t *c, const yb_cmd_t *cmd, uint32_t now_ms);

// 送入一次电压采样。连续低于阈值满去抖时长即锁存低压。返回值为真表示这一次采样刚好触发了锁存。
bool yb_ctrl_voltage_sample(yb_ctrl_t *c, float volt, uint32_t now_ms);

// 一拍：心跳检查，给出本拍实际下发的目标。stop_seq 是本拍取到的停车序号（那条零速 T:1 的 motion_seq），0 表示没有。
// 非 0 时本拍按零目标刹停。已收下的快照早于这条停车（零速的快照还没到）时一并清掉目标并记下序号，
// 此后只认不早于它的快照（审查 X3-15）；否则已收下的目标留到下一拍。
void yb_ctrl_tick(yb_ctrl_t *c, uint32_t now_ms, uint32_t stop_seq, float *out_l, float *out_r);

// 出一张遥测快照；l、r 是测得轮速
void yb_ctrl_telem(const yb_ctrl_t *c, float l, float r, uint32_t now_ms, yb_telem_t *out);

#ifdef __cplusplus
}
#endif
