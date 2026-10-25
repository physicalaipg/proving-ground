# YB-EET01 V2.0 管脚表（维护者自写）

> 来源：板卡厂商随产品分发的《microROS控制板简介.md》里的「GPIO管脚分配」表。厂商原件不入本仓（sha256 前 16 位 `20cac9032a91ea81`）。
> 本表只列管脚号与功能，逐脚对应 `main/yb_config.h`。模组 ESP32-S3-WROOM-1U-N4R2。

| 功能 | GPIO | 本版固件 | `yb_config.h` 里的名字 |
|---|---|---|---|
| 电机 M1 PWM A／B | 4／5 | 驱动 | `YB_MOTOR_A_GPIOS[0]`／`YB_MOTOR_B_GPIOS[0]` |
| 电机 M1 编码器 A／B | 6／7 | 驱动 | `YB_ENC_A_GPIOS[0]`／`YB_ENC_B_GPIOS[0]` |
| 电机 M2 PWM A／B | 15／16 | 驱动 | `…[1]` |
| 电机 M2 编码器 A／B | 47／48 | 驱动 | `…[1]` |
| 电机 M3 PWM A／B | 9／10 | 驱动 | `…[2]` |
| 电机 M3 编码器 A／B | 11／12 | 驱动 | `…[2]` |
| 电机 M4 PWM A／B | 13／14 | 驱动 | `…[3]` |
| 电机 M4 编码器 A／B | 1／2 | 驱动 | `…[3]` |
| BOOT 按键 | 0 | 只登记 | `YB_BOOT_KEY_GPIO` |
| 自定义按键 KEY1 | 42 | 只登记 | `YB_KEY1_GPIO` |
| 电池电压检测 | 3 | 驱动（ADC1 通道 2） | `YB_BAT_ADC_CHANNEL` |
| MCU 指示灯 | 45 | 只登记 | `YB_LED_GPIO` |
| 蜂鸣器 | 46 | 驱动 | `YB_BEEP_GPIO` |
| 舵机 S1／S2 | 8／21 | 只登记 | `YB_SERVO_S1_GPIO`／`YB_SERVO_S2_GPIO` |
| IMU 中断 | 41 | 只登记 | `YB_IMU_INT_GPIO` |
| IMU I2C SCL／SDA | 39／40 | 驱动 | `YB_I2C_SCL_GPIO`／`YB_I2C_SDA_GPIO` |
| 雷达串口 1 TXD1／RXD1 | 17／18 | 只登记 | `YB_LIDAR_TXD1_GPIO`／`YB_LIDAR_RXD1_GPIO` |
| Type-C 串口 0 TXD0／RXD0 | 43／44 | 驱动（协议口） | `YB_UART_TX_GPIO`／`YB_UART_RX_GPIO` |

轮位：Motor1 左前、Motor2 左后、Motor3 右前、Motor4 右后（来源同上文档的例程说明，待门一核对）。
