// yb-eet01-json —— 板卡厂商 YB-EET01 V2.0 板的 JSON 串口固件（UGV02 指令子集）
// 三个任务：串口收行并分发；控制环 10 ms 一拍（含心跳检查）；传感器 20 ms 一拍。
// 任务之间不共享状态、不加锁（内部工单）：只经三个单槽覆盖队列与一个原子量交换，收发一律不等待。
//   指令槽  串口 → 控制：串口侧最新指令快照，控制环每拍取最新
//   遥测槽  控制 → 串口：控制环每拍覆盖，串口回反馈帧时取
//   电压槽  传感器 → 控制：每 200 ms 一次采样
//   停车序号 串口 → 控制：收到零速指令即写入它的序号，控制环下一拍必按零目标刹停；零速的快照晚到也不再出旧目标
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "bootloader_random.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_attr.h"
#include "esp_err.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include "drive.h"
#include "selftest.h"
#include "sensors.h"
#include "yb_boot.h"
#include "yb_config.h"
#include "yb_proto.h"

#define UART_PORT       UART_NUM_0
#define UART_RX_BUF     1024
#define SENSOR_PERIOD_MS 20

static yb_link_t link_state;    // 只有串口任务碰
static yb_ctrl_t ctrl;          // 开任务之后只有控制任务碰
static QueueHandle_t cmd_slot, telem_slot, volt_slot;
static atomic_uint_least32_t brake_seq;     // 待办停车的序号；0 表示没有
static bool imu_ready;

// boot 计数放在复位不清的 RTC 区，带魔数与 CRC（内部工单-2，逻辑在 components/proto/yb_boot.c）：
// 校验过则加一，校验不过才取随机起点；不看复位原因。运行期不写闪存
static RTC_NOINIT_ATTR yb_boot_rtc_t boot_rtc;

static uint32_t now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

// 一行指令至多写出一条回显加一帧（反馈帧或错帧）
typedef struct {
    char data[YB_PROTO_LINE_MAX + 1 + 256];
    size_t len;
} out_buf_t;

static out_buf_t uart_out;

// 协议核心只往缓冲里写，整行处理完再写串口。装不下的整段丢弃，不截断 JSON
static void io_write(const char *data, size_t len, void *ctx)
{
    out_buf_t *out = ctx;
    if (len > sizeof(out->data) - out->len) return;
    memcpy(out->data + out->len, data, len);
    out->len += len;
}

static void io_feedback(yb_feedback_t *fb, void *ctx)
{
    (void)ctx;
    sensors_get(&fb->roll, &fb->pitch, &fb->yaw, &fb->temp);
}

static const yb_io_t io = {io_write, io_feedback, &uart_out};

static esp_timer_handle_t beep_timer;

static void beep_off(void *arg)
{
    (void)arg;
    gpio_set_level(YB_BEEP_GPIO, 0);
}

// 鸣一声，不阻塞调用方
static void beep_once(void)
{
#if YB_BEEP_ENABLE
    gpio_set_level(YB_BEEP_GPIO, 1);
    esp_timer_stop(beep_timer);
    esp_timer_start_once(beep_timer, YB_BEEP_MS * 1000);
#endif
}

static void beep_init(void)
{
    const gpio_config_t conf = {
        .pin_bit_mask = 1ULL << YB_BEEP_GPIO,
        .mode = GPIO_MODE_OUTPUT,
    };
    const esp_timer_create_args_t args = {.callback = beep_off, .name = "beep"};
    ESP_ERROR_CHECK(gpio_config(&conf));
    gpio_set_level(YB_BEEP_GPIO, 0);
    ESP_ERROR_CHECK(esp_timer_create(&args, &beep_timer));
}

static void uart_task(void *arg)
{
    static char line[YB_PROTO_LINE_MAX];
    size_t len = 0;
    bool overflow = false;
    uint8_t ch;

    (void)arg;
    for (;;) {
        if (uart_read_bytes(UART_PORT, &ch, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (ch != '\n') {
            // 超长行整条丢弃，直到下一个换行
            if (len + 1 < sizeof(line)) line[len++] = (char)ch;
            else overflow = true;
            continue;
        }
        // 自检钩子命令不交给协议核心；生产构建里 selftest_line 是恒假的空函数（selftest.h）
        if (!overflow && len > 0 && !selftest_line(line, len)) {
            yb_telem_t telem;
            unsigned flags;
            uart_out.len = 0;
            // 遥测槽只看不取；还没有过快照就按开机静默算
            if (xQueuePeek(telem_slot, &telem, 0) != pdTRUE) yb_telem_boot(&telem);
            yb_link_handle_line(&link_state, line, len, now_ms(), &telem, &io, &flags);
            // 先写停车序号再投指令槽：零速最早在控制环下一拍生效。序号是这条零速的 motion_seq，不为 0；
            // 本任务停在这两句之间时，控制侧凭序号清掉旧目标，不等快照（审查 X3-15）
            if (flags & YB_LINK_STOP) atomic_store(&brake_seq, link_state.cmd.motion_seq);
            if (flags & YB_LINK_POST) xQueueOverwrite(cmd_slot, &link_state.cmd);
            if (uart_out.len > 0) uart_write_bytes(UART_PORT, uart_out.data, uart_out.len);
        }
        len = 0;
        overflow = false;
    }
}

static void control_task(void *arg)
{
    TickType_t wake = xTaskGetTickCount();
    bool was_tripped = false;

    (void)arg;
    // 后备刹车（修订5 R2）：任务看门狗只监视本任务，每拍喂一次；本任务停摆 YB_CTRL_WDT_MS 即 panic 复位
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
    for (;;) {
        yb_cmd_t cmd;
        yb_telem_t telem;
        float volt, l, r, speed_l, speed_r;
        uint32_t now = now_ms();

        esp_task_wdt_reset();
        selftest_beat();    // 生产构建里是空函数
        if (xQueueReceive(volt_slot, &volt, 0) == pdTRUE && yb_ctrl_voltage_sample(&ctrl, volt, now)) beep_once();
        if (xQueueReceive(cmd_slot, &cmd, 0) == pdTRUE) yb_ctrl_command(&ctrl, &cmd, now);
        // 每条零速指令至少换来一拍刹车，哪怕同一拍里后面又到了非零指令
        yb_ctrl_tick(&ctrl, now, atomic_exchange(&brake_seq, 0), &l, &r);
        drive_step(l, r);

        drive_get_speeds(&speed_l, &speed_r);
        yb_ctrl_telem(&ctrl, speed_l, speed_r, now, &telem);
        xQueueOverwrite(telem_slot, &telem);

        if (ctrl.stop == YB_STOP_HEARTBEAT && !was_tripped) beep_once();
        was_tripped = ctrl.stop == YB_STOP_HEARTBEAT;
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(YB_CTRL_PERIOD_MS));
    }
}

static void sensor_task(void *arg)
{
    TickType_t wake = xTaskGetTickCount();
    int n = 0;

    (void)arg;
    for (;;) {
        sensors_poll(SENSOR_PERIOD_MS / 1000.0f);
        // 每 200 ms 采一次电池电压投进电压槽；去抖与锁存都在协议核心的控制侧
        if (++n >= YB_BAT_SAMPLE_MS / SENSOR_PERIOD_MS) {
            float volt = sensors_battery_volt();
            n = 0;
            xQueueOverwrite(volt_slot, &volt);
        }
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(SENSOR_PERIOD_MS));
    }
}

static void print_banner(void)
{
    char buf[160];
    // 标识行不带 T=1001，上位机解析器会跳过
    int n = snprintf(buf, sizeof(buf),
        "{\"fw\":\"%s\",\"ver\":\"%s\",\"proto\":\"%s\",\"board\":\"YB-EET01\",\"imu\":%d}\n",
        YB_FW_NAME, YB_FW_VERSION, YB_FW_PROTO, imu_ready ? 1 : 0);
    if (n > 0 && (size_t)n < sizeof(buf)) uart_write_bytes(UART_PORT, buf, (size_t)n);
}

void app_main(void)
{
    const uart_config_t uart_config = {
        .baud_rate = YB_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    const esp_task_wdt_config_t wdt_config = {
        .timeout_ms = YB_CTRL_WDT_MS,
        .idle_core_mask = 0,            // 不监视空闲任务，只监视控制任务（它自己登记）
        .trigger_panic = true,
    };
    esp_reset_reason_t reason = esp_reset_reason();
    uint32_t seed;
    float volt;

    // 先把电机置于刹停，再开串口
    drive_init();
    // boot 计数的随机种子：应用起来之后没开 RF 时 esp_random() 只是伪随机，RESET 清了 RTC 区的话可能与上次撞号。
    // 取种子这一下临时打开内部熵源；它占用 SAR ADC，须在 sensors_init() 开 ADC 之前关掉
    bootloader_random_enable();
    seed = esp_random();
    bootloader_random_disable();
    beep_init();
    ESP_ERROR_CHECK(esp_task_wdt_reconfigure(&wdt_config));

    ESP_ERROR_CHECK(uart_driver_install(UART_PORT, UART_RX_BUF, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_PORT, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(UART_PORT, YB_UART_TX_GPIO, YB_UART_RX_GPIO,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    imu_ready = sensors_init();
    cmd_slot = xQueueCreate(1, sizeof(yb_cmd_t));
    telem_slot = xQueueCreate(1, sizeof(yb_telem_t));
    volt_slot = xQueueCreate(1, sizeof(float));
    configASSERT(cmd_slot && telem_slot && volt_slot);
    yb_link_init(&link_state, yb_boot_next(&boot_rtc, seed), (uint32_t)reason);
    yb_ctrl_init(&ctrl, YB_MAX_WHEEL_MPS, YB_LOW_VOLT_PROTECT ? YB_LOW_VOLT_V : 0.0f, now_ms());
    // 开机即采一次电压：低压去抖自开机起算，与开机静默同时到点
    volt = sensors_battery_volt();
    yb_ctrl_voltage_sample(&ctrl, volt, now_ms());
    print_banner();

    xTaskCreatePinnedToCore(control_task, "control", 4096, NULL, 10, NULL, 1);
    xTaskCreatePinnedToCore(sensor_task, "sensor", 4096, NULL, 6, NULL, 1);
    xTaskCreatePinnedToCore(uart_task, "uart", 4096, NULL, 8, NULL, 0);
}
