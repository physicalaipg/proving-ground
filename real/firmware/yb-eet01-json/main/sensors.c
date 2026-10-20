#include "sensors.h"

#include <math.h>

#include "driver/i2c.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "freertos/FreeRTOS.h"

#include "yb_config.h"

// 寄存器地址与复位值见 TDK《ICM-42670-P》数据手册寄存器表
#define REG_TEMP_DATA1      0x09    // 其后依次为温度低字节、加速度 XYZ、角速度 XYZ，高字节在前
#define REG_PWR_MGMT0       0x1F
#define REG_GYRO_CONFIG0    0x20
#define REG_ACCEL_CONFIG0   0x21
#define REG_WHO_AM_I        0x75
#define WHO_AM_I_VALUE      0x67

#define PWR_GYRO_ACCEL_LN   0x0F    // 陀螺与加速度计都进低噪声模式
#define GYRO_500DPS_100HZ   0x49    // 量程位 10＝±500 dps，输出率 1001＝100 Hz
#define ACCEL_4G_100HZ      0x49    // 量程位 10＝±4 g，输出率 1001＝100 Hz
#define GYRO_LSB_PER_DPS    65.5f
#define ACCEL_LSB_PER_G     8192.0f

#define I2C_TIMEOUT         pdMS_TO_TICKS(20)
#define BIAS_SAMPLES        50      // 开机静置约 1 秒估陀螺零偏

static bool imu_ok;
static float roll, pitch, yaw, temp;
static float gyro_z_bias;
static int bias_count;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;

static adc_oneshot_unit_handle_t adc;
static adc_cali_handle_t adc_cali;

static esp_err_t imu_read(uint8_t reg, uint8_t *buf, size_t len)
{
    return i2c_master_write_read_device(YB_I2C_PORT, YB_IMU_ADDR, &reg, 1, buf, len, I2C_TIMEOUT);
}

static esp_err_t imu_write(uint8_t reg, uint8_t value)
{
    uint8_t buf[2] = {reg, value};
    return i2c_master_write_to_device(YB_I2C_PORT, YB_IMU_ADDR, buf, sizeof(buf), I2C_TIMEOUT);
}

static bool imu_init(void)
{
    uint8_t id = 0;
    i2c_config_t conf = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = YB_I2C_SDA_GPIO,
        .scl_io_num = YB_I2C_SCL_GPIO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = YB_I2C_FREQ_HZ,
    };
    if (i2c_param_config(YB_I2C_PORT, &conf) != ESP_OK) return false;
    if (i2c_driver_install(YB_I2C_PORT, I2C_MODE_MASTER, 0, 0, 0) != ESP_OK) return false;
    if (imu_read(REG_WHO_AM_I, &id, 1) != ESP_OK || id != WHO_AM_I_VALUE) return false;
    if (imu_write(REG_GYRO_CONFIG0, GYRO_500DPS_100HZ) != ESP_OK) return false;
    if (imu_write(REG_ACCEL_CONFIG0, ACCEL_4G_100HZ) != ESP_OK) return false;
    if (imu_write(REG_PWR_MGMT0, PWR_GYRO_ACCEL_LN) != ESP_OK) return false;
    return true;
}

static void battery_init(void)
{
    adc_oneshot_unit_init_cfg_t unit = {.unit_id = ADC_UNIT_1};
    adc_oneshot_chan_cfg_t chan = {.bitwidth = ADC_BITWIDTH_DEFAULT, .atten = ADC_ATTEN_DB_11};
    adc_cali_curve_fitting_config_t cali = {
        .unit_id = ADC_UNIT_1,
        .chan = YB_BAT_ADC_CHANNEL,
        .atten = ADC_ATTEN_DB_11,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    if (adc_oneshot_new_unit(&unit, &adc) != ESP_OK) {
        adc = NULL;
        return;
    }
    if (adc_oneshot_config_channel(adc, YB_BAT_ADC_CHANNEL, &chan) != ESP_OK) {
        adc = NULL;
        return;
    }
    if (adc_cali_create_scheme_curve_fitting(&cali, &adc_cali) != ESP_OK) adc_cali = NULL;
}

bool sensors_init(void)
{
    battery_init();
    imu_ok = imu_init();
    return imu_ok;
}

static int16_t be16(const uint8_t *p)
{
    return (int16_t)((p[0] << 8) | p[1]);
}

void sensors_poll(float dt_s)
{
    uint8_t raw[14];
    if (!imu_ok || imu_read(REG_TEMP_DATA1, raw, sizeof(raw)) != ESP_OK) return;

    float t = be16(raw) / 128.0f + 25.0f;
    float ax = be16(raw + 2) / ACCEL_LSB_PER_G;
    float ay = be16(raw + 4) / ACCEL_LSB_PER_G;
    float az = be16(raw + 6) / ACCEL_LSB_PER_G;
    float gz = be16(raw + 12) / GYRO_LSB_PER_DPS;
    float new_yaw;

    if (bias_count < BIAS_SAMPLES) {
        gyro_z_bias += gz / BIAS_SAMPLES;
        bias_count++;
        new_yaw = 0.0f;
    } else {
        new_yaw = yaw + (gz - gyro_z_bias) * dt_s;
        if (new_yaw > 180.0f) new_yaw -= 360.0f;
        if (new_yaw < -180.0f) new_yaw += 360.0f;
    }

    portENTER_CRITICAL(&lock);
    temp = t;
    roll = atan2f(ay, az) * 180.0f / (float)M_PI;
    pitch = atan2f(-ax, sqrtf(ay * ay + az * az)) * 180.0f / (float)M_PI;
    yaw = new_yaw;
    portEXIT_CRITICAL(&lock);
}

void sensors_get(float *roll_deg, float *pitch_deg, float *yaw_deg, float *temp_c)
{
    portENTER_CRITICAL(&lock);
    *roll_deg = roll;
    *pitch_deg = pitch;
    *yaw_deg = yaw;
    *temp_c = temp;
    portEXIT_CRITICAL(&lock);
}

float sensors_battery_volt(void)
{
    int raw = 0, mv = 0;
    if (!adc || adc_oneshot_read(adc, YB_BAT_ADC_CHANNEL, &raw) != ESP_OK) return 0.0f;
    if (adc_cali) {
        if (adc_cali_raw_to_voltage(adc_cali, raw, &mv) != ESP_OK) return 0.0f;
    } else {
        mv = raw * 3100 / 4095;   // 无校准数据时的粗算
    }
    return mv / 1000.0f * YB_BAT_DIVIDER * YB_BAT_CAL;
}
