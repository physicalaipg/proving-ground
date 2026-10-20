#include "yb_wheel.h"

#include <string.h>

// 增量式 PID，输出限幅 ±out_max
float yb_wheel_step(yb_wheel_pid_t *s, const yb_wheel_gains_t *g, float target, float measured)
{
    float err = target - measured;

    if (target == 0.0f) {
        memset(s, 0, sizeof(*s));
        return 0.0f;
    }
    s->out += g->kp * (err - s->e1) + g->ki * err + g->kd * (err - 2 * s->e1 + s->e2);
    if (s->out > g->out_max) s->out = g->out_max;
    if (s->out < -g->out_max) s->out = -g->out_max;
    s->e2 = s->e1;
    s->e1 = err;
    return s->out;
}
