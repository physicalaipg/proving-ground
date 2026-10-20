// drive —— 四路电机 PWM、四路 PCNT 编码器与速度闭环
#pragma once

#include <stdbool.h>

void drive_init(void);

// 控制环每拍调用一次：读编码器、按左右目标轮速（m/s）做闭环。两侧目标都为 0 时刹停并清 PID 状态。
void drive_step(float target_l, float target_r);

// 最近 100 ms 的左右轮平均速度，m/s；同侧两轮取均值
void drive_get_speeds(float *left, float *right);
