#include "yb_boot.h"

// CRC-32（多项式 0xEDB88320），按小端逐字节算，与宿主机字节序无关
static uint32_t crc_words(uint32_t a, uint32_t b)
{
    const uint32_t words[2] = {a, b};
    uint32_t crc = 0xFFFFFFFFu;

    for (int w = 0; w < 2; w++) {
        for (int i = 0; i < 4; i++) {
            crc ^= (words[w] >> (8 * i)) & 0xFFu;
            for (int bit = 0; bit < 8; bit++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
        }
    }
    return ~crc;
}

bool yb_boot_valid(const yb_boot_rtc_t *r)
{
    return r->magic == YB_BOOT_MAGIC && r->count != 0 && (r->count & ~YB_BOOT_MASK) == 0 &&
           r->crc == crc_words(r->magic, r->count);
}

uint32_t yb_boot_next(yb_boot_rtc_t *r, uint32_t seed)
{
    uint32_t count = yb_boot_valid(r) ? r->count + 1 : seed;

    count &= YB_BOOT_MASK;
    if (count == 0) count = 1;
    r->magic = YB_BOOT_MAGIC;
    r->count = count;
    r->crc = crc_words(r->magic, r->count);
    return count;
}
