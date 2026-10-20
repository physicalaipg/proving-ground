// yb_boot —— boot 计数的混合逻辑（纯 C，不依赖 ESP-IDF，宿主机可编译自检）
// 计数放在复位不清的 RTC 区，带魔数与 CRC（内部工单-2）：校验过则加一；
// 校验不过（上电、RESET 键清了 RTC 区、首刷）才用随机种子重起。
// 看门狗复位链上逐次加一、可计次；RTC 区跨 RESET 键保留则照常加一，不保留则换新种子，两种都不撞号。
#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define YB_BOOT_MAGIC   0x59424254u     // "YBBT"
#define YB_BOOT_MASK    0x3FFFFFFFu     // 计数只用低 30 位

typedef struct {
    uint32_t magic;
    uint32_t count;
    uint32_t crc;       // magic 与 count 八个字节的 CRC-32
} yb_boot_rtc_t;

// *r 是不是上一次开机留下的有效记录
bool yb_boot_valid(const yb_boot_rtc_t *r);

// 本次开机的 boot 计数，不为 0，并改写 *r。seed 只在校验不过时用
uint32_t yb_boot_next(yb_boot_rtc_t *r, uint32_t seed);

#ifdef __cplusplus
}
#endif
