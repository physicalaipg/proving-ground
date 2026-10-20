// 宿主机自检用的单轮控制律外壳：增益与限幅取 main/yb_config.h 的固件实值。
// 输入每行：<目标> <实测>，单位每拍脉冲数；输出每行：<PID 输出> <前一拍误差> <前两拍误差>。
#include <stdio.h>

#include "yb_config.h"
#include "yb_wheel.h"

int main(void)
{
    const yb_wheel_gains_t gains = {YB_PID_KP, YB_PID_KI, YB_PID_KD, YB_PID_OUT_MAX};
    yb_wheel_pid_t pid = {0};
    float target, measured;

    while (scanf("%f %f", &target, &measured) == 2) {
        float out = yb_wheel_step(&pid, &gains, target, measured);
        printf("%.4f %.4f %.4f\n", (double)out, (double)pid.e1, (double)pid.e2);
        fflush(stdout);
    }
    return 0;
}
