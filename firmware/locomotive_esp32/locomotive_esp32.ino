/* XIAO ESP32-C6 accessory-controller prototype (not a locomotive receiver).
 *
 * The motor-driver pins and Wi-Fi credentials are intentionally placeholders.
 * This sketch is not used by the simulation dashboard.  Before bench use,
 * select validated pins and set REARM_BUTTON_PIN to a normally-open local
 * safety button.  A stopped locomotive never re-arms from packet silence.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

constexpr uint8_t MAGIC0 = 'H';
constexpr uint8_t MAGIC1 = 'C';
constexpr uint8_t VERSION = 1;
constexpr uint8_t ESTOP_FLAG = 0x80;
constexpr uint8_t ALL_TRAINS = 0xFF;
constexpr unsigned long WATCHDOG_MS = 500;
constexpr int REARM_BUTTON_PIN = -1;  // configure only after hardware validation
constexpr uint8_t LOCOMOTIVE_ID = 1;  // set per mock locomotive

WiFiUDP udp;
bool estopLatched = false;
unsigned long lastCommandMs = 0;

uint16_t crc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ ((crc & 1) ? 0xA001 : 0);
  }
  return crc;
}

void setMotorSpeed(int16_t speed) {
  // Deliberately zero-only until a validated motor driver/pin mapping exists.
  // A production bench build replaces this with an immediate driver write.
  (void)speed;
}

bool rearmButtonHeld() {
  return REARM_BUTTON_PIN >= 0 && digitalRead(REARM_BUTTON_PIN) == LOW;
}

bool safeRearm(int16_t speed) {
  // Explicit local action plus a valid zero-speed command is required.
  return speed == 0 && rearmButtonHeld();
}

void handlePacket(const uint8_t *packet, size_t length) {
  if (length != 12 || packet[0] != MAGIC0 || packet[1] != MAGIC1 ||
      packet[2] != VERSION || crc16(packet, 10) != (uint16_t(packet[11]) << 8 | packet[10]))
    return;

  const uint8_t trainId = packet[3];
  const int16_t speed = int16_t(uint16_t(packet[6]) | uint16_t(packet[7]) << 8);
  const uint8_t flags = packet[9];
  lastCommandMs = millis();

  if (trainId == ALL_TRAINS && (flags & ESTOP_FLAG)) {
    estopLatched = true;
    setMotorSpeed(0);  // no ramp on emergency stop
    return;
  }
  if (trainId != LOCOMOTIVE_ID) return;

  if (estopLatched) {
    setMotorSpeed(0);
    if (safeRearm(speed)) estopLatched = false;
    return;
  }
  setMotorSpeed(speed);
}

void setup() {
  if (REARM_BUTTON_PIN >= 0) pinMode(REARM_BUTTON_PIN, INPUT_PULLUP);
  setMotorSpeed(0);
  lastCommandMs = millis();
  // Wi-Fi credentials and validated motor configuration are supplied only in
  // an explicitly enabled bench build.
}

void loop() {
  int packetSize = udp.parsePacket();
  if (packetSize > 0 && packetSize <= 64) {
    uint8_t packet[64];
    int length = udp.read(packet, sizeof(packet));
    handlePacket(packet, size_t(length));
  }
  if (millis() - lastCommandMs > WATCHDOG_MS) setMotorSpeed(0);
}
