#include "drive.h"

#include <math.h>
#include <string.h>

#include "bdc_motor.h"
#include "driver/pulse_cnt.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"

#include "yb_config.h"
#include "yb_wheel.h"

#define WHEELS 4
#define PCNT_LIMIT 1000

static const int motor_a[WHEELS] = YB_MOTOR_A_GPIOS;
static const int motor_b[WHEELS] = YB_MOTOR_B_GPIOS;
static const int enc_a[WHEELS] = YB_ENC_A_GPIOS;
static const int enc_b[WHEELS] = YB_ENC_B_GPIOS;
static const int mcpwm_group[WHEELS] = YB_MOTOR_MCPWM_GROUPS;
static const int motor_sign[WHEELS] = YB_MOTOR_SIGNS;
static const int enc_sign[WHEELS] = YB_ENC_SIGNS;
static const int left_wheels[2] = YB_LEFT_WHEELS;
static const int right_wheels[2] = YB_RIGHT_WHEELS;

static const yb_wheel_gains_t gains = {YB_PID_KP, YB_PID_KI, YB_PID_KD, YB_PID_OUT_MAX};

static bdc_motor_handle_t motors[WHEELS];
static pcnt_unit_handle_t encoders[WHEELS];
static int last_count[WHEELS];
static yb_wheel_pid_t pid[WHEELS];
static bool braked[WHEELS] = {true, true, true, true};   // drive_init 已把四路置于刹停

// 每拍脉冲数的滑动窗口，用于上报轮速
static int16_t window[WHEELS][YB_SPEED_AVG_SAMPLES];
static int window_pos;
static portMUX_TYPE speed_lock = portMUX_INITIALIZER_UNLOCKED;
static float speed_mps[WHEELS];

// 一拍内一个脉冲对应的速度，m/s
static float mps_per_pulse(void)
{
    return (float)M_PI * YB_WHEEL_DIAMETER_M / YB_ENCODER_COUNTS_PER_REV /
           (YB_CTRL_PERIOD_MS / 1000.0f);
}

static void motor_init(int i)
{
    // 左侧两路（下标 0、1）的 AB 脚对调，与厂商例程一致
    bool swap = (i == left_wheels[0] || i == left_wheels[1]);
    bdc_motor_config_t motor_config = {
        .pwm_freq_hz = YB_PWM_FREQ_HZ,
        .pwma_gpio_num = swap ? motor_b[i] : motor_a[i],
        .pwmb_gpio_num = swap ? motor_a[i] : motor_b[i],
    };
    bdc_motor_mcpwm_config_t mcpwm_config = {
        .group_id = mcpwm_group[i],
        .resolution_hz = YB_PWM_RESOLUTION_HZ,
    };
    ESP_ERROR_CHECK(bdc_motor_new_mcpwm_device(&motor_config, &mcpwm_config, &motors[i]));
    ESP_ERROR_CHECK(bdc_motor_enable(motors[i]));
    ESP_ERROR_CHECK(bdc_motor_brake(motors[i]));
}

static void encoder_init(int i)
{
    // 右侧两路（下标 2、3）的 AB 相对调，与厂商例程一致：车前进时四路计数都增大
    bool swap = (i == right_wheels[0] || i == right_wheels[1]);
    int a = swap ? enc_b[i] : enc_a[i];
    int b = swap ? enc_a[i] : enc_b[i];
    pcnt_unit_config_t unit_config = {
        .high_limit = PCNT_LIMIT,
        .low_limit = -PCNT_LIMIT,
        .flags.accum_count = true,
    };
    pcnt_glitch_filter_config_t filter_config = {.max_glitch_ns = 1000};
    pcnt_chan_config_t chan_a_config = {.edge_gpio_num = a, .level_gpio_num = b};
    pcnt_chan_config_t chan_b_config = {.edge_gpio_num = b, .level_gpio_num = a};
    pcnt_channel_handle_t chan_a = NULL, chan_b = NULL;

    ESP_ERROR_CHECK(pcnt_new_unit(&unit_config, &encoders[i]));
    ESP_ERROR_CHECK(pcnt_unit_set_glitch_filter(encoders[i], &filter_config));
    ESP_ERROR_CHECK(pcnt_new_channel(encoders[i], &chan_a_config, &chan_a));
    ESP_ERROR_CHECK(pcnt_new_channel(encoders[i], &chan_b_config, &chan_b));
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(chan_a, PCNT_CHANNEL_EDGE_ACTION_DECREASE,
                                                 PCNT_CHANNEL_EDGE_ACTION_INCREASE));
    ESP_ERROR_CHECK(pcnt_channel_set_level_action(chan_a, PCNT_CHANNEL_LEVEL_ACTION_KEEP,
                                                  PCNT_CHANNEL_LEVEL_ACTION_INVERSE));
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(chan_b, PCNT_CHANNEL_EDGE_ACTION_INCREASE,
                                                 PCNT_CHANNEL_EDGE_ACTION_DECREASE));
    ESP_ERROR_CHECK(pcnt_channel_set_level_action(chan_b, PCNT_CHANNEL_LEVEL_ACTION_KEEP,
                                                  PCNT_CHANNEL_LEVEL_ACTION_INVERSE));
    ESP_ERROR_CHECK(pcnt_unit_add_watch_point(encoders[i], PCNT_LIMIT));
    ESP_ERROR_CHECK(pcnt_unit_add_watch_point(encoders[i], -PCNT_LIMIT));
    ESP_ERROR_CHECK(pcnt_unit_enable(encoders[i]));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(encoders[i]));
    ESP_ERROR_CHECK(pcnt_unit_start(encoders[i]));
}

void drive_init(void)
{
    for (int i = 0; i < WHEELS; i++) {
        motor_init(i);
        encoder_init(i);
    }
}

static void motor_set(int i, int out)
{
    out *= motor_sign[i];
    if (out > 0) {
        ESP_ERROR_CHECK(bdc_motor_forward(motors[i]));
        ESP_ERROR_CHECK(bdc_motor_set_speed(motors[i], (uint32_t)(out + YB_PWM_DEAD_ZONE)));
    } else if (out < 0) {
        ESP_ERROR_CHECK(bdc_motor_reverse(motors[i]));
        ESP_ERROR_CHECK(bdc_motor_set_speed(motors[i], (uint32_t)(-out + YB_PWM_DEAD_ZONE)));
    } else {
        ESP_ERROR_CHECK(bdc_motor_brake(motors[i]));
    }
}

void drive_step(float target_l, float target_r)
{
    float target[WHEELS];
    int pulses[WHEELS];
    float k = mps_per_pulse();

    target[left_wheels[0]] = target[left_wheels[1]] = target_l;
    target[right_wheels[0]] = target[right_wheels[1]] = target_r;

    for (int i = 0; i < WHEELS; i++) {
        int count = 0;
        ESP_ERROR_CHECK(pcnt_unit_get_count(encoders[i], &count));
        pulses[i] = (count - last_count[i]) * enc_sign[i];
        last_count[i] = count;
        window[i][window_pos] = (int16_t)pulses[i];
    }
    window_pos = (window_pos + 1) % YB_SPEED_AVG_SAMPLES;

    // 零目标按轮处置：哪一路目标为零就刹哪一路并清它的 PID 状态，不等两侧同时为零
    for (int i = 0; i < WHEELS; i++) {
        float want = target[i] / k;   // 目标换成每拍脉冲数
        int out = (int)yb_wheel_step(&pid[i], &gains, want, (float)pulses[i]);
        if (target[i] == 0.0f) {
            if (!braked[i]) ESP_ERROR_CHECK(bdc_motor_brake(motors[i]));
            braked[i] = true;
        } else {
            braked[i] = false;
            motor_set(i, out);
        }
    }

    float avg[WHEELS];
    for (int i = 0; i < WHEELS; i++) {
        int sum = 0;
        for (int j = 0; j < YB_SPEED_AVG_SAMPLES; j++) sum += window[i][j];
        avg[i] = (float)sum / YB_SPEED_AVG_SAMPLES * k;
    }
    portENTER_CRITICAL(&speed_lock);
    memcpy(speed_mps, avg, sizeof(avg));
    portEXIT_CRITICAL(&speed_lock);
}

void drive_get_speeds(float *left, float *right)
{
    float s[WHEELS];
    portENTER_CRITICAL(&speed_lock);
    memcpy(s, speed_mps, sizeof(s));
    portEXIT_CRITICAL(&speed_lock);
    *left = (s[left_wheels[0]] + s[left_wheels[1]]) / 2;
    *right = (s[right_wheels[0]] + s[right_wheels[1]]) / 2;
}
