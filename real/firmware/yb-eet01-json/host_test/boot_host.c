// 宿主机自检用的 boot 计数外壳：一块假 RTC 区跨行保留，模拟一次次开机。
// 输入每行：K <种子>        RTC 区保留（看门狗、panic、软件复位，或 RESET 键没清 RTC）后开机；
//           W <种子> <魔数> <计数> <CRC>  先把 RTC 区写成给定的三个字（十进制；模拟上电乱码、RESET 键清零、首刷）再开机。
// 输出每行：<本次 boot 计数> <开机前 RTC 区校验过否：0 或 1>
#include <stdio.h>
#include <stdlib.h>

#include "yb_boot.h"

int main(void)
{
    yb_boot_rtc_t rtc = {0, 0, 0};
    char kind;
    unsigned long seed;

    while (scanf(" %c %lu", &kind, &seed) == 2) {
        if (kind == 'W') {
            unsigned long magic, count, crc;
            if (scanf("%lu %lu %lu", &magic, &count, &crc) != 3) return 1;
            rtc.magic = (uint32_t)magic;
            rtc.count = (uint32_t)count;
            rtc.crc = (uint32_t)crc;
        }
        int valid = yb_boot_valid(&rtc);
        printf("%lu %d\n", (unsigned long)yb_boot_next(&rtc, (uint32_t)seed), valid);
        fflush(stdout);
    }
    return 0;
}
