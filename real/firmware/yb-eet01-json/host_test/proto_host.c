// 宿主机自检用的协议外壳：把 yb_proto 的串口侧与控制侧接到标准输入输出，时间由调用方逐行注入，不读墙钟。
// 两侧之间照 main.c 的做法只传快照：指令槽、遥测槽各一格，外加停车序号。
// 输入每行：<毫秒><空格><内容>。缺省每条输入之前先走一拍控制环（取指令槽、心跳检查、出遥测）。
// 内容为 "?" 时只走这一拍并报本拍下发的目标轮速；"V<伏>" 送入一次电压采样；以 "!" 起头的指令行不先走那一拍，
// 用来摆出「同一拍之内连到几行」；否则当作一行指令。
// "H<指令行>" 摆出串口任务停在「写停车序号」与「投指令槽」之间：照常处理这一行并写停车序号，快照压住不投；
// "P" 把压住的快照按先后放一张进指令槽。压着快照时又直接投了槽，压着的作废（真机上它们先投，已被盖掉）。两者都可前缀 "!"。
// 输出：每写出一段回 "O <原文>"；"?" 回 "W <左> <右> <停车锁存：0 无 1 心跳 2 低压 4 复位>"；每条输入以单独一行 "." 结束。
// 测得轮速取本拍下发的目标（理想被控对象），其余字段取固定值。
// 命令行参数：固件限幅、低压阈值、开机电压、boot 计数、复位原因。开机时刻为 0。
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "yb_proto.h"

static yb_link_t link_state;
static yb_ctrl_t ctrl;
static yb_cmd_t cmd_slot;
static yb_telem_t telem_slot;
static bool cmd_posted;
static uint32_t brake_seq;
// 压住未投的快照，先进先出
#define HELD_MAX 4
static yb_cmd_t held[HELD_MAX];
static size_t held_n;
static float out_l, out_r;

static void out_write(const char *data, size_t len, void *ctx)
{
    (void)ctx;
    fputs("O ", stdout);
    fwrite(data, 1, len, stdout);
    if (len == 0 || data[len - 1] != '\n') fputc('\n', stdout);
}

static void out_feedback(yb_feedback_t *fb, void *ctx)
{
    (void)ctx;
    fb->temp = 25.0f;
}

// 控制环的一拍，次序同 main.c 的 control_task
static void beat(uint32_t ms)
{
    if (cmd_posted) yb_ctrl_command(&ctrl, &cmd_slot, ms);
    cmd_posted = false;
    yb_ctrl_tick(&ctrl, ms, brake_seq, &out_l, &out_r);
    brake_seq = 0;
    yb_ctrl_telem(&ctrl, out_l, out_r, ms, &telem_slot);
}

int main(int argc, char **argv)
{
    static char line[1024];
    const yb_io_t io = {out_write, out_feedback, NULL};
    float limit = argc > 1 ? (float)atof(argv[1]) : 0.5f;
    float low_volt = argc > 2 ? (float)atof(argv[2]) : 6.5f;
    float volt = argc > 3 ? (float)atof(argv[3]) : 7.4f;

    yb_link_init(&link_state, argc > 4 ? (uint32_t)strtoul(argv[4], NULL, 10) : 1,
                 argc > 5 ? (uint32_t)strtoul(argv[5], NULL, 10) : 1);
    yb_ctrl_init(&ctrl, limit, low_volt, 0);
    yb_ctrl_voltage_sample(&ctrl, volt, 0);
    yb_telem_boot(&telem_slot);
    while (fgets(line, sizeof(line), stdin)) {
        char *rest = NULL;
        unsigned long ms = strtoul(line, &rest, 10);
        unsigned flags = 0;
        size_t len;
        if (rest == line || *rest != ' ') {
            puts(".");
            fflush(stdout);
            continue;
        }
        rest++;
        len = strlen(rest);
        while (len && (rest[len - 1] == '\n' || rest[len - 1] == '\r')) len--;
        if (len >= 1 && rest[0] == '!') {
            rest++;
            len--;
        } else {
            beat((uint32_t)ms);
        }
        if (len == 1 && rest[0] == '?') {
            printf("W %.6f %.6f %d\n", (double)out_l, (double)out_r, (int)ctrl.stop);
        } else if (len >= 2 && rest[0] == 'V') {
            yb_ctrl_voltage_sample(&ctrl, (float)atof(rest + 1), (uint32_t)ms);
        } else if (len == 1 && rest[0] == 'P') {
            if (held_n > 0) {
                cmd_slot = held[0];
                cmd_posted = true;
                memmove(held, held + 1, --held_n * sizeof(held[0]));
            }
        } else if (len >= 2 && rest[0] == 'H') {
            yb_link_handle_line(&link_state, rest + 1, len - 1, (uint32_t)ms, &telem_slot, &io, &flags);
            if (flags & YB_LINK_STOP) brake_seq = link_state.cmd.motion_seq;
            // 压满了就盖掉最后一张，同指令槽的覆盖
            if (flags & YB_LINK_POST) held[held_n < HELD_MAX ? held_n++ : HELD_MAX - 1] = link_state.cmd;
        } else {
            yb_link_handle_line(&link_state, rest, len, (uint32_t)ms, &telem_slot, &io, &flags);
            if (flags & YB_LINK_STOP) brake_seq = link_state.cmd.motion_seq;
            if (flags & YB_LINK_POST) {
                cmd_slot = link_state.cmd;
                cmd_posted = true;
                held_n = 0;
            }
        }
        puts(".");
        fflush(stdout);
    }
    return 0;
}
