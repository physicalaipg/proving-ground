// sensors —— ICM-42670-P 姿态与电池电压
#pragma once

#include <stdbool.h>

// 返回 IMU 是否就绪；不就绪时姿态与温度一律报 0，不影响运动控制
bool sensors_init(void);

// 周期调用（20 ms 一次）：读 IMU、积分航向
void sensors_poll(float dt_s);

void sensors_get(float *roll_deg, float *pitch_deg, float *yaw_deg, float *temp_c);

// 电池电压，V；读失败返回 0
float sensors_battery_volt(void);
