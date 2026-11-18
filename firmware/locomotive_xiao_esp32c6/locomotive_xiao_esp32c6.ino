/* XIAO ESP32-C6 locomotive controller variant.
 *
 * This target intentionally reuses the proven M5 locomotive protocol and
 * command/watchdog/telemetry implementation. Only the board identity and
 * validated bench pin map differ:
 *   XIAO D7 / GPIO17 -> motor driver IN1 (forward PWM)
 *   XIAO D8 / GPIO19 -> motor driver IN2 (reverse PWM)
 *   XIAO D9 / GPIO20 -> IR transmitter driver
 *
 * D7 and D8 are ESP32-C6 GPIOs and are valid LEDC/analogWrite outputs with
 * the Arduino-ESP32 core. Confirm the driver wiring and electrical levels
 * before connecting a motor. Startup remains motor-off and disarmed.
 */
#define LOCO_MOTOR_FORWARD_PIN 17
#define LOCO_MOTOR_REVERSE_PIN 19
#define LOCO_IR_TRANSMITTER_PIN 20
#define LOCOMOTIVE_READY_LABEL "XIAO_C6_LOCO_READY ID="

// Set LOCOMOTIVE_ID through an Arduino CLI build flag, for example:
//   --build-property 'build.extra_flags=-DLOCOMOTIVE_ID=1'
#include "../locomotive_m5_atom_echo/locomotive_m5_atom_echo.ino"
