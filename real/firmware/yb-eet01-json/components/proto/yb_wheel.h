// yb_wheel —— 单轮一拍的控制律（纯 C，不依赖 ESP-IDF，宿主机可编译自检）
// 从 main/drive.c 拆出（审查 X3-02）：零目标的处置按轮做，不等两侧同时为零。
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float e1, e2;   // 前一拍、前两拍的误差
    float out;      // 累计输出，PWM 计数
} yb_wheel_pid_t;

typedef struct {
    float kp, ki, kd;
    float out_max;  // 输出限幅 ±out_max
} yb_wheel_gains_t;

// 单轮一拍，目标与实测都以每拍脉冲数计。返回限幅后的 PID 输出。
// 目标为 0 时清掉该轮的 PID 状态并返回 0，调用方据此刹车：历史输出不带进零目标，也不带进下一次起步。
float yb_wheel_step(yb_wheel_pid_t *s, const yb_wheel_gains_t *g, float target, float measured);

#ifdef __cplusplus
}
#endif
