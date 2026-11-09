/* M5 Atom Echo locomotive receiver.
 * Motor driver: GPIO19 forward PWM, GPIO22 reverse PWM.
 * IR transmitter: GPIO23.  The dispatcher supplies the explicit UDP rearm
 * handshake; simulation never runs this firmware or sends UDP.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

constexpr uint8_t LOCOMOTIVE_ID = 1;
constexpr uint8_t ALL_TRAINS = 0xFF;
constexpr uint8_t ESTOP_FLAG = 0x80;
constexpr uint8_t REARM_FLAG = 0x40;
constexpr uint8_t VERSION = 1;
constexpr int MOTOR_FORWARD_PIN = 19;
constexpr int MOTOR_REVERSE_PIN = 22;
constexpr int IR_TRANSMITTER_PIN = 23;
constexpr int REARM_BUTTON_PIN = -1; // assign only after validating the build
constexpr unsigned long WATCHDOG_MS = 500;
constexpr uint16_t UDP_PORT = 4210;
WiFiUDP udp;
enum LocomotiveState { DISARMED, ARMED, ESTOP_LATCHED, COMMUNICATION_FAULT };
LocomotiveState state = DISARMED;
unsigned long lastApplicableCommandMs = 0;
unsigned long lastWifiAttemptMs = 0;
bool udpStarted = false;
int16_t commandedSpeed = 0;
uint8_t commandedTarget = 0;
uint8_t irFrame[8];
uint8_t irByte = 0, irBit = 0;
bool irSending = false;
unsigned long irNextFrameMs = 0, irSymbolStartedUs = 0;
// The repository specifies the frame fields and 38 kHz carrier, but does not
// specify receiver symbol width. Keep it configurable until receiver timing
// is validated on the bench rather than silently choosing a new protocol.
constexpr unsigned long IR_SYMBOL_US = 1000;

// Credentials are intentionally supplied at build/deployment time, never
// committed to the repository.
const char *WIFI_SSID = "YOUR_SSID";
const char *WIFI_PASSWORD = "YOUR_PASSWORD";

uint16_t crc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ ((crc & 1) ? 0xA001 : 0);
  }
  return crc;
}

void irDuty(uint32_t duty);

void configureIrTransmitter() {
  pinMode(IR_TRANSMITTER_PIN, OUTPUT);
  // The existing IR identification protocol uses a 38 kHz carrier.  The
  // transistor and resistor values remain part of the approved hardware BOM.
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(IR_TRANSMITTER_PIN, 38000, 8);
#else
  ledcSetup(0, 38000, 8);
  ledcAttachPin(IR_TRANSMITTER_PIN, 0);
#endif
  irDuty(0);
}

void irDuty(uint32_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(IR_TRANSMITTER_PIN, duty);
#else
  ledcWrite(0, duty);
#endif
}

uint8_t crc8(const uint8_t *data, size_t length) {
  uint8_t crc = 0;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) crc = (crc & 0x80) ? uint8_t((crc << 1) ^ 0x07) : uint8_t(crc << 1);
  }
  return crc;
}

void beginIrFrame() {
  // HR, version, locomotive ID, direction/status, destination, magnitude, CRC.
  irFrame[0] = 'H'; irFrame[1] = 'R'; irFrame[2] = VERSION; irFrame[3] = LOCOMOTIVE_ID;
  irFrame[4] = commandedSpeed < 0 ? 0x01 : 0x00;
  irFrame[5] = commandedTarget;
  irFrame[6] = uint8_t(constrain(abs(int(commandedSpeed)), 0, 255));
  irFrame[7] = crc8(irFrame + 2, 5);
  irByte = irBit = 0; irSending = true; irSymbolStartedUs = micros();
  irDuty((irFrame[0] & 1) ? 128 : 0);
}

void serviceIrTransmission() {
  const unsigned long nowMs = millis();
  if (!irSending && nowMs >= irNextFrameMs) beginIrFrame();
  if (!irSending || micros() - irSymbolStartedUs < IR_SYMBOL_US) return;
  irSymbolStartedUs += IR_SYMBOL_US;
  irBit++;
  if (irBit >= 8) { irBit = 0; irByte++; }
  if (irByte >= sizeof(irFrame)) {
    irDuty(0); irSending = false; irNextFrameMs = nowMs + 100; return;
  }
  const bool one = (irFrame[irByte] & (uint8_t(1) << irBit)) != 0;
  irDuty(one ? 128 : 0);
}

void setMotorSpeed(int16_t speed) {
  // Two-input H-bridge: zero both pins for an immediate stop.
  int duty = constrain(abs(int(speed)), 0, 255);
  if (speed > 0) { analogWrite(MOTOR_FORWARD_PIN, duty); analogWrite(MOTOR_REVERSE_PIN, 0); }
  else if (speed < 0) { analogWrite(MOTOR_FORWARD_PIN, 0); analogWrite(MOTOR_REVERSE_PIN, duty); }
  else { analogWrite(MOTOR_FORWARD_PIN, 0); analogWrite(MOTOR_REVERSE_PIN, 0); }
  commandedSpeed = speed;
}

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastWifiAttemptMs < 5000) return;
  lastWifiAttemptMs = millis();
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void handleCommand(const uint8_t *p, size_t length) {
  if (length != 12 || p[0] != 'H' || p[1] != 'C' || p[2] != VERSION ||
      crc16(p, 10) != (uint16_t(p[11]) << 8 | p[10])) return;
  const uint8_t trainId = p[3];
  const int16_t speed = int16_t(uint16_t(p[6]) | uint16_t(p[7]) << 8);
  commandedTarget = p[8];
  if (trainId == ALL_TRAINS && (p[9] & ESTOP_FLAG)) {
    state = ESTOP_LATCHED; setMotorSpeed(0); return;
  }
  if (trainId == ALL_TRAINS && (p[9] & REARM_FLAG) && speed == 0) {
    // This packet is the explicit dispatcher handshake. A normal zero speed
    // packet never changes either latch.
    state = ARMED; setMotorSpeed(0); lastApplicableCommandMs = millis(); return;
  }
  if (trainId != LOCOMOTIVE_ID) return;
  lastApplicableCommandMs = millis();
  if (state != ARMED) {
    setMotorSpeed(0);
    return;
  }
  setMotorSpeed(speed);
}

void setup() {
  pinMode(MOTOR_FORWARD_PIN, OUTPUT); pinMode(MOTOR_REVERSE_PIN, OUTPUT);
  configureIrTransmitter();
  if (REARM_BUTTON_PIN >= 0) pinMode(REARM_BUTTON_PIN, INPUT_PULLUP);
  setMotorSpeed(0); lastApplicableCommandMs = 0;
  WiFi.disconnect(true);
}

void loop() {
  connectWifi();
  if (WiFi.status() == WL_CONNECTED) {
    if (!udpStarted) { udp.begin(UDP_PORT); udpStarted = true; }
    const int packetSize = udp.parsePacket();
    if (packetSize > 0 && packetSize <= 64) { uint8_t p[64]; handleCommand(p, size_t(udp.read(p, sizeof(p)))); }
  } else if (udpStarted) {
    udp.stop();
    udpStarted = false;
    state = COMMUNICATION_FAULT;
    setMotorSpeed(0);
  }
  if (lastApplicableCommandMs == 0 || millis() - lastApplicableCommandMs > WATCHDOG_MS) {
    state = COMMUNICATION_FAULT;
    setMotorSpeed(0);
  }
  serviceIrTransmission();
}
