// yb_config.h —— YB-EET01 V2.0 板级与车体常量。全部可用编译选项 -DXXX=... 覆盖。
// 管脚逐脚见 docs/pins.md；来源是厂商《microROS控制板简介.md》的 GPIO 管脚分配表，原件不入本仓。
// 车体尺寸 2026-09-28 由主理人供图回填：轮径取麦轮商品页标称值，轴距取照片上的卷尺读数，轮距是按电机尺寸估的、待实量。
#pragma once

// 自检钩子（内部治理仓 内部工单）：缺省关，只由构建开关 -D YB_SELFTEST=1 打开（main/CMakeLists.txt）。
// selftest 构建的版本带后缀，上位机据此不与生产版的数据混放
#ifndef YB_SELFTEST
#define YB_SELFTEST     0
#endif

#define YB_FW_NAME      "yb-eet01-json"
#if YB_SELFTEST
#define YB_FW_VERSION   "0.2.0-selftest"
#else
#define YB_FW_VERSION   "0.2.0"
#endif
#define YB_FW_PROTO     "ugv02-subset-1"

// ── 串口：Type-C 经 CP2102 接 UART0 ──
#define YB_UART_TX_GPIO         43
#define YB_UART_RX_GPIO         44
#define YB_UART_BAUD            115200

// ── 本版固件不驱动、只登记的管脚（同一张管脚表）──
#define YB_BOOT_KEY_GPIO        0
#define YB_KEY1_GPIO            42
#define YB_LED_GPIO             45
#define YB_SERVO_S1_GPIO        8
#define YB_SERVO_S2_GPIO        21
#define YB_LIDAR_TXD1_GPIO      17
#define YB_LIDAR_RXD1_GPIO      18
#define YB_IMU_INT_GPIO         41

// ── 电机 PWM（每路两脚）与编码器（AB 相）；下标 0..3 对应板上 Motor1..Motor4 ──
// PWM 资源照厂商例程：乐鑫 bdc_motor 组件走 MCPWM，25 kHz，计数时钟 10 MHz
#define YB_MOTOR_A_GPIOS        {4, 15, 9, 13}
#define YB_MOTOR_B_GPIOS        {5, 16, 10, 14}
#define YB_ENC_A_GPIOS          {6, 47, 11, 1}
#define YB_ENC_B_GPIOS          {7, 48, 12, 2}
// 一个 MCPWM 组最多带三路电机：前三路用组 0，第四路用组 1
#define YB_MOTOR_MCPWM_GROUPS   {0, 0, 0, 1}

// ── 轮位映射：厂商约定 Motor1 左前、Motor2 左后、Motor3 右前、Motor4 右后（待门一核对）。车头＝相机所装的一头，T:1 的前进方向按此定；与厂商约定的车头不在同一头时，左右两组与正负号一并对调 ──
#define YB_LEFT_WHEELS          {0, 1}
#define YB_RIGHT_WHEELS         {2, 3}
// 方向：1 表示该路按厂商例程的接法（左侧两路 PWM 的 AB 脚对调，右侧两路编码器的 AB 相对调），-1 表示再取反。待门一核对
#define YB_MOTOR_SIGNS          {1, 1, 1, 1}
#define YB_ENC_SIGNS            {1, 1, 1, 1}

// ── 车体 ──
#ifndef YB_WHEEL_DIAMETER_M
#define YB_WHEEL_DIAMETER_M     (0.065f)     // 65 mm 尼龙麦轮标称外径（商品页 Φ65）；门二标定后改成实测值
#endif
// 下面三个量本版固件的四条指令都用不到，登记在此供上位机与 T=13 取用
#ifndef YB_WHEEL_BASE_M
#define YB_WHEEL_BASE_M         (0.119f)     // 轴距：同侧前后轮心距，照片卷尺读数 12.1 − 0.25 cm，±3 mm
#endif
#ifndef YB_TRACK_WIDTH_M
#define YB_TRACK_WIDTH_M        (0.1486f)    // 轮距：同轴左右轮中面距，10-02 实量外端面距 178／180 mm 均值减轮宽 30.4（B0 步 5）
#endif
// 麦轮按差速跑时的转向等效宽度＝轴距＋轮距（麦轮运动学在横移速度为 0 时的结果）；上位机 track_width_m 填这个数
#define YB_TURN_WIDTH_M         (YB_WHEEL_BASE_M + YB_TRACK_WIDTH_M)
#define YB_ENCODER_COUNTS_PER_REV   (1040.0f)   // 13 线 × 减速比 20 × 4 倍频（厂商《310电机参数》）

// ── 限幅 ──
#ifndef YB_MAX_WHEEL_MPS
#define YB_MAX_WHEEL_MPS        (0.5f)       // 固件侧轮速限幅；协议层另有 ±2.0 的整条忽略线
#endif

// ── 控制环 ──
#define YB_CTRL_PERIOD_MS       10
#define YB_CTRL_WDT_MS          300          // 任务看门狗只监视控制任务：这么久没喂即 panic 复位，复位后静默 2 s 不出力
#define YB_SPEED_AVG_SAMPLES    10           // 上报轮速取最近 100 ms 的均值
#define YB_PWM_FREQ_HZ          25000
#define YB_PWM_RESOLUTION_HZ    10000000
#define YB_PWM_TICK_MAX         (YB_PWM_RESOLUTION_HZ / YB_PWM_FREQ_HZ)   // 400
#define YB_PWM_DEAD_ZONE        200          // 电机起转死区，取厂商例程值
#define YB_PID_OUT_MAX          (YB_PWM_TICK_MAX - YB_PWM_DEAD_ZONE)      // PID 输出限幅 ±200
#define YB_PID_KP               (1.0f)
#define YB_PID_KI               (0.2f)
#define YB_PID_KD               (0.2f)

// ── IMU：ICM-42670-P，I2C ──
#define YB_I2C_PORT             0
#define YB_I2C_SDA_GPIO         40
#define YB_I2C_SCL_GPIO         39
#define YB_I2C_FREQ_HZ          400000
#define YB_IMU_ADDR             0x68

// ── 电池电压：GPIO3＝ADC1 通道 2；分压系数取厂商例程值 ──
#define YB_BAT_ADC_CHANNEL      ADC_CHANNEL_2
#define YB_BAT_DIVIDER          (4.03f)
// 校准系数：首通电拿万用表比对板读电压，偏差超过 0.15 V 时改这里（＝万用表读数÷板读数）
#ifndef YB_BAT_CAL
#define YB_BAT_CAL              (1.0f)
#endif
#define YB_BAT_SAMPLE_MS        200

// ── 低压保护（裁定 2026-09-28-08）──
// 阈值＝每芯 3.25 V × 芯数；板卡厂商 2S 7.4 V 电池包即 6.5 V。芯数 10-01 看电池标签核。
// 连续 2 秒低于阈值即锁存，只有断电或复位重启才清；不设预警级。去抖时长在协议核心里。
#ifndef YB_LOW_VOLT_PROTECT
#define YB_LOW_VOLT_PROTECT     1            // 0＝关闭低压保护
#endif
#ifndef YB_BAT_CELLS
#define YB_BAT_CELLS            2
#endif
#define YB_LOW_VOLT_PER_CELL_V  (3.25f)
#define YB_LOW_VOLT_V           (YB_BAT_CELLS * YB_LOW_VOLT_PER_CELL_V)

// ── 蜂鸣器：GPIO46，有源，高电平响（厂商例程 beep.h）──
#define YB_BEEP_GPIO            46
#ifndef YB_BEEP_ENABLE
#define YB_BEEP_ENABLE          1            // 0＝心跳锁存与低压锁存触发时不鸣
#endif
#define YB_BEEP_MS              200
