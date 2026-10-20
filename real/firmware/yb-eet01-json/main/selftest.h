// selftest —— 台架自检钩子（内部治理仓 内部工单）：让控制任务按四种方式停摆，实测看门狗复位报什么、多久复位。
// 编译门控，缺省关：只有以 -D YB_SELFTEST=1 配置的构建才编进 selftest.c；生产构建里下面两个入口是空函数，镜像里没有钩子命令名。
// selftest 构建的固件版本带后缀（yb_config.h），只在台架烧、轮子离地，用完刷回生产版；它的数据不进任何回合。
#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "yb_config.h"

#if YB_SELFTEST
// 串口任务调用：这一行是钩子命令就登记下来并返回真，该行不再交给协议核心
bool selftest_line(const char *line, size_t len);
// 控制任务每拍调用：有登记的钩子就在本任务里停摆，不再返回
void selftest_beat(void);
#else
static inline bool selftest_line(const char *line, size_t len)
{
    (void)line;
    (void)len;
    return false;
}

static inline void selftest_beat(void)
{
}
#endif
