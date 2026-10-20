// 自检钩子，见 selftest.h。只在 selftest 构建里编译。
// 四条钩子命令只做四种停摆，除此没有别的入口。指令号在 UGV02 指令集之外（上游 json_cmd.h 全表最大 1041），
// 须整行逐字节相符才认；生产固件收到同一行只回 unknown_cmd 错帧。
#include "selftest.h"

#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

enum { STALL_NONE, STALL_BLOCK, STALL_SPIN, STALL_SPIN_NOIRQ, STALL_ABORT };

static const char *const hooks[] = {
    [STALL_BLOCK] = "{\"T\":9101,\"hook\":\"yb_stall_block\"}",             // 阻塞：永久等待
    [STALL_SPIN] = "{\"T\":9102,\"hook\":\"yb_stall_spin\"}",               // 空转，中断开
    [STALL_SPIN_NOIRQ] = "{\"T\":9103,\"hook\":\"yb_stall_spin_noirq\"}",   // 空转，中断关
    [STALL_ABORT] = "{\"T\":9104,\"hook\":\"yb_stall_abort\"}",             // abort
};

static atomic_int pending;

bool selftest_line(const char *line, size_t len)
{
    for (int kind = STALL_BLOCK; kind <= STALL_ABORT; kind++) {
        if (len == strlen(hooks[kind]) && memcmp(line, hooks[kind], len) == 0) {
            atomic_store(&pending, kind);
            return true;
        }
    }
    return false;
}

// 停摆发生在控制任务里、喂狗之后：PWM 停在上一拍的占空比，看门狗自这一拍的喂狗起算
void selftest_beat(void)
{
    switch (atomic_load(&pending)) {
    case STALL_BLOCK:
        for (;;) vTaskDelay(portMAX_DELAY);
    case STALL_SPIN:
        for (volatile unsigned n = 0;; n++) {
        }
    case STALL_SPIN_NOIRQ:
        portDISABLE_INTERRUPTS();
        for (volatile unsigned n = 0;; n++) {
        }
    case STALL_ABORT:
        abort();
    default:
        return;
    }
}
