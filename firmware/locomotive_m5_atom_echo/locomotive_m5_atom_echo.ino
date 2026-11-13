/* M5 Atom Echo locomotive receiver.
 * Motor driver: GPIO19 forward PWM, GPIO22 reverse PWM.
 * IR transmitter: GPIO23.  The dispatcher supplies the explicit UDP rearm
 * handshake; simulation never runs this firmware or sends UDP.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_system.h>

#ifndef LOCOMOTIVE_ID
#define LOCOMOTIVE_ID 1
#endif
constexpr uint8_t LOCOMOTIVE_ID_VALUE = LOCOMOTIVE_ID;
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
WiFiUDP telemetryUdp;
enum LocomotiveState { DISARMED, ARMED, ESTOP_LATCHED, COMMUNICATION_FAULT };
LocomotiveState state = DISARMED;
unsigned long lastApplicableCommandMs = 0;
unsigned long lastWifiAttemptMs = 0;
bool udpStarted = false, communicationFault = true;
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
const char *WIFI_SSID = "Lab 42";
const char *WIFI_PASSWORD = "NerdsRock!";

uint16_t crc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ ((crc & 1) ? 0xA001 : 0);
  }
  return crc;
}

constexpr uint16_t TELEMETRY_PORT = 4211;
const IPAddress TELEMETRY_BROADCAST(10, 77, 0, 255);
uint16_t lastAcceptedSequence = 0;
uint32_t telemetrySequence = 0;
String bootSession;
String rearmTransaction;
String lastRearmTransaction;
unsigned long lastTelemetryMs = 0;

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
  irFrame[0] = 'H'; irFrame[1] = 'R'; irFrame[2] = VERSION; irFrame[3] = LOCOMOTIVE_ID_VALUE;
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
  const uint16_t sequence = uint16_t(p[4]) | uint16_t(p[5]) << 8;
  const int16_t speed = int16_t(uint16_t(p[6]) | uint16_t(p[7]) << 8);
  commandedTarget = p[8];
  if (trainId == ALL_TRAINS && (p[9] & ESTOP_FLAG)) {
    communicationFault = false; state = ESTOP_LATCHED; setMotorSpeed(0); return;
  }
  if (trainId == ALL_TRAINS && (p[9] & REARM_FLAG) && speed == 0) {
    // This packet is the explicit dispatcher handshake. A normal zero speed
    // packet never changes either latch.
    communicationFault = false; state = ARMED; setMotorSpeed(0); lastApplicableCommandMs = millis(); return;
  }
  if (trainId != LOCOMOTIVE_ID_VALUE) return;
  lastAcceptedSequence = sequence;
  lastApplicableCommandMs = millis();
  communicationFault = false;
  if (state != ARMED) {
    setMotorSpeed(0);
    return;
  }
  setMotorSpeed(speed);
}

void handleRearmPacket(const uint8_t *p, size_t length) {
  if (length < 3 || p[0] != 'H' || p[1] != 'R' || p[2] != '{') return;
  String body;
  for (size_t i = 2; i < length; ++i) body += char(p[i]);
  if (body.indexOf("\"version\":1") < 0 || body.indexOf("\"id\":255") < 0) return;
  int marker = body.indexOf("\"transaction\":\"");
  if (marker < 0) return;
  int start = marker + 15, end = body.indexOf('"', start);
  if (end <= start) return;
  String transaction = body.substring(start, end);
  // A separate, versioned rearm message cannot be confused with a zero-speed
  // heartbeat. It is accepted only in a safe local state.
  if (transaction == lastRearmTransaction || transaction.length() == 0 || transaction.length() > 128 || commandedSpeed != 0) return;
  // HR is the dispatcher authorization after its physical switch, stop-cause,
  // and controller-health checks. The controller validates only local safety.
  if (state != ESTOP_LATCHED && state != COMMUNICATION_FAULT && state != DISARMED && state != ARMED) return;
  state = ARMED;
  rearmTransaction = transaction;
  lastRearmTransaction = transaction;
  communicationFault = false;
  lastApplicableCommandMs = millis();
  setMotorSpeed(0);
}

void sendTelemetry() {
  if (WiFi.status() != WL_CONNECTED || millis() - lastTelemetryMs < 100) return;
  lastTelemetryMs = millis();
  const char *stateName = state == ARMED ? "ARMED" : state == ESTOP_LATCHED ? "ESTOP_LATCHED" : state == COMMUNICATION_FAULT ? "COMMUNICATION_FAULT" : "DISARMED";
  String body = String("HT{\"version\":1,\"id\":") + LOCOMOTIVE_ID_VALUE +
    ",\"state\":\"" + stateName + "\",\"estop\":" + (state == ESTOP_LATCHED ? "true" : "false") +
    ",\"communication_fault\":" + (state == COMMUNICATION_FAULT ? "true" : "false") +
    ",\"armed\":" + (state == ARMED ? "true" : "false") + ",\"speed\":" + commandedSpeed +
    ",\"sequence\":" + String(telemetrySequence++) + ",\"last_command_sequence\":" + lastAcceptedSequence +
    ",\"session\":\"" + bootSession + "\",\"uptime_ms\":" + millis();
  if (rearmTransaction.length()) body += ",\"rearm_transaction\":\"" + rearmTransaction + "\"";
  body += "}";
  telemetryUdp.beginPacket(TELEMETRY_BROADCAST, TELEMETRY_PORT);
  telemetryUdp.write((const uint8_t *)body.c_str(), body.length());
  telemetryUdp.endPacket();
}

void setup() {
  pinMode(MOTOR_FORWARD_PIN, OUTPUT); pinMode(MOTOR_REVERSE_PIN, OUTPUT);
  configureIrTransmitter();
  if (REARM_BUTTON_PIN >= 0) pinMode(REARM_BUTTON_PIN, INPUT_PULLUP);
  setMotorSpeed(0); lastApplicableCommandMs = 0;
  bootSession = String((uint32_t)esp_random(), HEX) + String((uint32_t)esp_random(), HEX);
  WiFi.disconnect(true);
}

void loop() {
  connectWifi();
  if (WiFi.status() == WL_CONNECTED) {
    if (!udpStarted) { udp.begin(UDP_PORT); udpStarted = true; }
    const int packetSize = udp.parsePacket();
    if (packetSize > 0 && packetSize <= 128) { uint8_t p[128]; size_t n = udp.read(p, sizeof(p)); if (n >= 2 && p[0] == 'H' && p[1] == 'R') handleRearmPacket(p, n); else handleCommand(p, n); }
  } else if (udpStarted) {
    udp.stop();
    udpStarted = false;
    communicationFault = true; state = COMMUNICATION_FAULT;
    setMotorSpeed(0);
  }
  if (lastApplicableCommandMs == 0 || millis() - lastApplicableCommandMs > WATCHDOG_MS) {
    communicationFault = true; state = COMMUNICATION_FAULT;
    setMotorSpeed(0);
  }
  serviceIrTransmission();
  sendTelemetry();
}
