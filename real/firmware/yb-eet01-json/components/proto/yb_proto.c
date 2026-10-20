#include "yb_proto.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ── 极简 JSON：只认一层对象，值为数字／字符串／true／false／null；嵌套一律判坏行 ──

#define MAX_FIELDS 8
#define KEY_MAX    8

typedef struct {
    char key[KEY_MAX];
    bool is_num;
    double num;
} field_t;

static const char *skip_ws(const char *s, const char *end)
{
    while (s < end && (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n')) s++;
    return s;
}

// 跳过一个字符串，s 指向开头的引号；key 非空时把内容抄出（超长即判坏）。返回结尾引号之后，坏则 NULL
static const char *skip_string(const char *s, const char *end, char *key)
{
    size_t n = 0;
    s++;
    while (s < end && *s != '"') {
        if ((unsigned char)*s < 0x20) return NULL;
        if (*s == '\\') {
            if (key || s + 1 >= end) return NULL;   // 键里不接受转义
            s++;
        } else if (key) {
            if (n + 1 >= KEY_MAX) return NULL;
            key[n++] = *s;
        }
        s++;
    }
    if (s >= end) return NULL;
    if (key) key[n] = 0;
    return s + 1;
}

// JSON 数字：-?digits(.digits)?([eE][+-]?digits)?；不接受 inf、nan、十六进制
static const char *parse_number(const char *s, const char *end, double *out)
{
    char buf[40];
    const char *p = s;
    if (p < end && *p == '-') p++;
    if (p >= end || *p < '0' || *p > '9') return NULL;
    while (p < end && *p >= '0' && *p <= '9') p++;
    if (p < end && *p == '.') {
        p++;
        if (p >= end || *p < '0' || *p > '9') return NULL;
        while (p < end && *p >= '0' && *p <= '9') p++;
    }
    if (p < end && (*p == 'e' || *p == 'E')) {
        p++;
        if (p < end && (*p == '+' || *p == '-')) p++;
        if (p >= end || *p < '0' || *p > '9') return NULL;
        while (p < end && *p >= '0' && *p <= '9') p++;
    }
    size_t n = (size_t)(p - s);
    if (n >= sizeof(buf)) return NULL;
    memcpy(buf, s, n);
    buf[n] = 0;
    *out = strtod(buf, NULL);
    if (!isfinite(*out)) return NULL;
    return p;
}

static bool match_lit(const char **s, const char *end, const char *lit)
{
    size_t n = strlen(lit);
    if ((size_t)(end - *s) < n || memcmp(*s, lit, n) != 0) return false;
    *s += n;
    return true;
}

// 返回字段数；坏行返回 -1
static int parse_object(const char *s, size_t len, field_t *f)
{
    const char *end = s + len;
    int n = 0;
    s = skip_ws(s, end);
    if (s >= end || *s != '{') return -1;
    s = skip_ws(s + 1, end);
    if (s < end && *s == '}') {
        s++;
    } else {
        for (;;) {
            field_t cur = {0};
            if (s >= end || *s != '"') return -1;
            s = skip_string(s, end, cur.key);
            if (!s) return -1;
            s = skip_ws(s, end);
            if (s >= end || *s != ':') return -1;
            s = skip_ws(s + 1, end);
            if (s >= end) return -1;
            if (*s == '"') {
                s = skip_string(s, end, NULL);
                if (!s) return -1;
            } else if (*s == '-' || (*s >= '0' && *s <= '9')) {
                s = parse_number(s, end, &cur.num);
                if (!s) return -1;
                cur.is_num = true;
            } else if (!(match_lit(&s, end, "true") || match_lit(&s, end, "false") ||
                         match_lit(&s, end, "null"))) {
                return -1;   // 含嵌套对象与数组
            }
            if (n >= MAX_FIELDS) return -1;
            f[n++] = cur;
            s = skip_ws(s, end);
            if (s < end && *s == ',') {
                s = skip_ws(s + 1, end);
                continue;
            }
            if (s < end && *s == '}') {
                s++;
                break;
            }
            return -1;
        }
    }
    s = skip_ws(s, end);
    return s == end ? n : -1;
}

// 同名键取最后一个（与 Python json.loads 一致）
static const field_t *find(const field_t *f, int n, const char *key)
{
    const field_t *hit = NULL;
    for (int i = 0; i < n; i++) {
        if (strcmp(f[i].key, key) == 0) hit = &f[i];
    }
    return hit;
}

static bool get_num(const field_t *f, int n, const char *key, double *out)
{
    const field_t *hit = find(f, n, key);
    if (!hit || !hit->is_num) return false;
    *out = hit->num;
    return true;
}

static float clampf(float v, float lim)
{
    if (v > lim) return lim;
    if (v < -lim) return -lim;
    return v;
}

static float finite_or_zero(float v)
{
    return isfinite(v) ? v : 0.0f;
}

static void send_error(const yb_io_t *io, const char *err, long got)
{
    char buf[64];
    int n = snprintf(buf, sizeof(buf), "{\"T\":-1,\"err\":\"%s\",\"got\":%ld}\n", err, got);
    if (n > 0 && (size_t)n < sizeof(buf)) io->write(buf, (size_t)n, io->ctx);
}

static void send_feedback(const yb_link_t *k, const yb_telem_t *t, const yb_io_t *io)
{
    yb_feedback_t fb = {0};
    char buf[256];
    io->feedback(&fb, io->ctx);
    // 前八个字段与次序同 UGV02 的 T=1001：L R r p y temp v；low_voltage、reset_reason、boot、tl、tr 是新增字段，排在最后。
    // tl、tr 是控制侧当前目标（审查 X3-08）：上位机发零速后读到 tl=tr=0 且 L、R 停稳，才算停车已确认
    int n = snprintf(buf, sizeof(buf),
        "{\"T\":1001,\"L\":%.4f,\"R\":%.4f,\"r\":%.2f,\"p\":%.2f,\"y\":%.2f,\"temp\":%.1f,\"v\":%.2f,"
        "\"low_voltage\":%d,\"reset_reason\":%lu,\"boot\":%lu,\"tl\":%.4f,\"tr\":%.4f}\n",
        (double)finite_or_zero(t->l), (double)finite_or_zero(t->r),
        (double)finite_or_zero(fb.roll), (double)finite_or_zero(fb.pitch),
        (double)finite_or_zero(fb.yaw), (double)finite_or_zero(fb.temp),
        (double)finite_or_zero(t->volt), t->stop == YB_STOP_LOW_VOLTAGE ? 1 : 0,
        (unsigned long)k->reset_reason, (unsigned long)k->boot,
        (double)finite_or_zero(t->tl), (double)finite_or_zero(t->tr));
    if (n > 0 && (size_t)n < sizeof(buf)) io->write(buf, (size_t)n, io->ctx);
}

// ── 串口侧 ──

void yb_link_init(yb_link_t *k, uint32_t boot, uint32_t reset_reason)
{
    memset(k, 0, sizeof(*k));
    k->cmd.heartbeat_ms = YB_PROTO_HEARTBEAT_DEFAULT_MS;
    k->boot = boot;
    k->reset_reason = reset_reason;
}

void yb_telem_boot(yb_telem_t *t)
{
    memset(t, 0, sizeof(*t));
    t->stop = YB_STOP_BOOT;
    t->quiet = true;
}

void yb_link_handle_line(yb_link_t *k, const char *line, size_t len, uint32_t now_ms,
                         const yb_telem_t *telem, const yb_io_t *io, unsigned *flags)
{
    field_t f[MAX_FIELDS];
    double t = 0, a = 0, b = 0;

    *flags = 0;
    if (len == 0 || len >= YB_PROTO_LINE_MAX) return;
    int n = parse_object(line, len, f);
    if (n < 0) return;                       // 坏行静默丢弃

    if (k->echo) {
        char buf[YB_PROTO_LINE_MAX + 1];
        memcpy(buf, line, len);
        buf[len] = '\n';
        io->write(buf, len + 1, io->ctx);
    }
    if (!get_num(f, n, "T", &t) || t != floor(t) || fabs(t) > 100000) {
        send_error(io, "bad_args", -1);
        return;
    }

    switch ((long)t) {
    case 1:     // 左右轮速度
        if (!get_num(f, n, "L", &a) || !get_num(f, n, "R", &b)) {
            send_error(io, "bad_args", 1);
            return;
        }
        if (fabs(a) > YB_PROTO_REJECT_MPS || fabs(b) > YB_PROTO_REJECT_MPS) return;
        if (a != 0 || b != 0) {
            // 低压锁存与开机静默期间零速指令照收，非零一律拒绝
            if (telem->stop == YB_STOP_LOW_VOLTAGE) {
                send_error(io, "low_voltage", 1);
                return;
            }
            if (telem->quiet) {
                send_error(io, "boot_quiet", 1);
                return;
            }
        } else {
            *flags |= YB_LINK_STOP;
        }
        k->cmd.l = (float)a;
        k->cmd.r = (float)b;
        k->cmd.motion_ms = now_ms;
        if (++k->cmd.motion_seq == 0) k->cmd.motion_seq = 1;   // 0 留给「还没有收到过」
        *flags |= YB_LINK_POST;
        break;
    case 130:   // 查询一次反馈
        send_feedback(k, telem, io);
        break;
    case 136:   // 心跳超时设置
        if (!get_num(f, n, "cmd", &a)) {
            send_error(io, "bad_args", 136);
            return;
        }
        if (a < YB_PROTO_HEARTBEAT_MIN_MS) a = YB_PROTO_HEARTBEAT_MIN_MS;
        if (a > YB_PROTO_HEARTBEAT_MAX_MS) a = YB_PROTO_HEARTBEAT_MAX_MS;
        k->cmd.heartbeat_ms = (uint32_t)a;
        *flags |= YB_LINK_POST;
        break;
    case 143:   // 回显开关
        if (!get_num(f, n, "cmd", &a)) {
            send_error(io, "bad_args", 143);
            return;
        }
        k->echo = (a != 0);
        break;
    default:
        send_error(io, "unknown_cmd", (long)t);
        break;
    }
}

// ── 控制侧 ──

static void latch(yb_ctrl_t *c, yb_stop_t reason)
{
    c->stop = reason;
    c->target_l = 0.0f;
    c->target_r = 0.0f;
}

void yb_ctrl_init(yb_ctrl_t *c, float limit_mps, float low_volt_v, uint32_t now_ms)
{
    memset(c, 0, sizeof(*c));
    c->limit_mps = limit_mps;
    c->low_volt_v = low_volt_v;
    c->boot_ms = now_ms;
    c->last_motion_ms = now_ms;
    c->heartbeat_ms = YB_PROTO_HEARTBEAT_DEFAULT_MS;
    c->stop = YB_STOP_BOOT;
}

bool yb_ctrl_quiet(const yb_ctrl_t *c, uint32_t now_ms)
{
    if (c->stop != YB_STOP_BOOT) return false;
    return (uint32_t)(now_ms - c->boot_ms) < YB_PROTO_BOOT_QUIET_MS || c->below;
}

void yb_ctrl_command(yb_ctrl_t *c, const yb_cmd_t *cmd, uint32_t now_ms)
{
    c->heartbeat_ms = cmd->heartbeat_ms;
    if (cmd->motion_seq == c->seen_seq) return;      // 只是设置变了
    c->seen_seq = cmd->motion_seq;
    if (c->hold_seq != 0) {
        // 停车先于它的快照到了（审查 X3-15）：早于那条停车的快照不取目标、不刷新心跳。无符号相减转有符号，序号回绕时仍成立
        if ((int32_t)(cmd->motion_seq - c->hold_seq) < 0) return;
        c->hold_seq = 0;
    }
    if (c->stop == YB_STOP_LOW_VOLTAGE || yb_ctrl_quiet(c, now_ms)) {
        // 没有任何指令能清掉低压锁存；静默期内复位锁存也清不掉。零速指令照收，只刷新心跳
        if (cmd->l == 0.0f && cmd->r == 0.0f) c->last_motion_ms = cmd->motion_ms;
        return;
    }
    c->stop = YB_STOP_NONE;      // 心跳锁存与静默期后的复位锁存由有效运动指令清除
    c->target_l = clampf(cmd->l, c->limit_mps);
    c->target_r = clampf(cmd->r, c->limit_mps);
    c->last_motion_ms = cmd->motion_ms;
}

bool yb_ctrl_voltage_sample(yb_ctrl_t *c, float volt, uint32_t now_ms)
{
    c->volt = volt;
    if (c->low_volt_v <= 0.0f || c->stop == YB_STOP_LOW_VOLTAGE) return false;
    if (!(volt < c->low_volt_v)) {
        c->below = false;
        return false;
    }
    if (!c->below) {
        c->below = true;
        c->below_since_ms = now_ms;
        return false;
    }
    if ((uint32_t)(now_ms - c->below_since_ms) < YB_PROTO_LOW_VOLT_DEBOUNCE_MS) return false;
    latch(c, YB_STOP_LOW_VOLTAGE);
    return true;
}

void yb_ctrl_tick(yb_ctrl_t *c, uint32_t now_ms, uint32_t stop_seq, float *out_l, float *out_r)
{
    bool brake = stop_seq != 0;

    // 无符号相减，毫秒计数回绕时仍成立
    if ((uint32_t)(now_ms - c->last_motion_ms) > c->heartbeat_ms) {
        // 低压锁存与复位锁存优先，不被心跳锁存盖掉
        if (c->stop == YB_STOP_NONE && (c->target_l != 0.0f || c->target_r != 0.0f)) {
            latch(c, YB_STOP_HEARTBEAT);
        }
        c->target_l = 0.0f;
        c->target_r = 0.0f;
    }
    // 停车序号先到、零速的快照还没到：清掉旧目标，下一拍不再出力（审查 X3-15）。无符号相减转有符号，序号回绕时仍成立
    if (brake && (int32_t)(c->seen_seq - stop_seq) < 0) {
        c->target_l = 0.0f;
        c->target_r = 0.0f;
        c->hold_seq = stop_seq;
    }
    *out_l = brake ? 0.0f : c->target_l;
    *out_r = brake ? 0.0f : c->target_r;
}

void yb_ctrl_telem(const yb_ctrl_t *c, float l, float r, uint32_t now_ms, yb_telem_t *out)
{
    out->l = l;
    out->r = r;
    out->volt = c->volt;
    out->stop = c->stop;
    out->quiet = yb_ctrl_quiet(c, now_ms);
    out->tl = c->target_l;
    out->tr = c->target_r;
}
