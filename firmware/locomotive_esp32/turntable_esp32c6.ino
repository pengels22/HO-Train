/* XIAO ESP32-C6 turntable safety receiver.
 * Receives the same binary broadcast frame as locomotives.  Any broadcast
 * ESTOP latches the turntable controller and invokes the local stop hook.
 * The actual turntable driver interface is intentionally not guessed here.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

constexpr uint8_t ALL_TRAINS = 0xFF, ESTOP_FLAG = 0x80, VERSION = 1;
constexpr unsigned long WATCHDOG_MS = 500;
constexpr uint16_t UDP_PORT = 4210;
WiFiUDP udp;
bool estopLatched = false;
bool communicationFault = true;
bool trackPowerEnabled = false;
enum TurntableState { HOME, TURNING, ROTATED, FAULT };
TurntableState state = FAULT;
unsigned long lastValidPacketMs = 0;

constexpr int HOME_SWITCH = D0;
constexpr int ROTATED_SWITCH = D1;
constexpr int MOTOR_IN1 = D2;
constexpr int MOTOR_IN2 = D3;
constexpr int POLARITY_RELAY = D4;
constexpr int TRACK_POWER_RELAY = D5;
constexpr int REED_END_A = D6;
constexpr int REED_END_B = D7;

uint16_t crc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) { crc ^= data[i]; for (uint8_t b=0;b<8;++b) crc=(crc>>1)^((crc&1)?0xA001:0); }
  return crc;
}

void stopTurntableMotor() {
  digitalWrite(MOTOR_IN1, LOW); digitalWrite(MOTOR_IN2, LOW);
  trackPowerEnabled = false;
  digitalWrite(TRACK_POWER_RELAY, LOW);
}

void enableTrackPower(bool enable) {
  if (enable && (estopLatched || communicationFault)) return;
  trackPowerEnabled = enable;
  digitalWrite(TRACK_POWER_RELAY, enable ? HIGH : LOW);
}

bool alignmentValid() {
  // Both active at once is mechanically inconsistent; neither is an unknown
  // alignment and cannot be used for dispatch.
  const bool home = digitalRead(HOME_SWITCH) == LOW;
  const bool rotated = digitalRead(ROTATED_SWITCH) == LOW;
  return home != rotated;
}

void driveMotor(int direction) {
  if (estopLatched || communicationFault || !alignmentValid()) { stopTurntableMotor(); return; }
  state = TURNING;
  digitalWrite(MOTOR_IN1, direction > 0 ? HIGH : LOW);
  digitalWrite(MOTOR_IN2, direction < 0 ? HIGH : LOW);
}

void handleSerialRearm() {
  static String line;
  while (Serial.available()) {
    const char c = char(Serial.read());
    if (c == '\n') {
      if (line == "REARM" && !communicationFault && alignmentValid()) {
        estopLatched = false;
        state = digitalRead(HOME_SWITCH) == LOW ? HOME : ROTATED;
      }
      line = "";
    } else if (line.length() < 32) line += c;
  }
}

void handlePacket(const uint8_t *p, size_t length) {
  if (length != 12 || p[0] != 'H' || p[1] != 'C' || p[2] != VERSION || crc16(p,10) != (uint16_t(p[11])<<8 | p[10])) return;
  if (p[3] != ALL_TRAINS) return;
  lastValidPacketMs = millis();
  communicationFault = false;
  if (p[9] & ESTOP_FLAG) { estopLatched = true; stopTurntableMotor(); }
}

void setup() {
  pinMode(HOME_SWITCH, INPUT_PULLUP); pinMode(ROTATED_SWITCH, INPUT_PULLUP);
  pinMode(REED_END_A, INPUT_PULLUP); pinMode(REED_END_B, INPUT_PULLUP);
  pinMode(MOTOR_IN1, OUTPUT); pinMode(MOTOR_IN2, OUTPUT);
  pinMode(POLARITY_RELAY, OUTPUT); pinMode(TRACK_POWER_RELAY, OUTPUT);
  digitalWrite(POLARITY_RELAY, LOW); stopTurntableMotor();
  Serial.begin(115200);
  WiFi.mode(WIFI_STA); // credentials and connection policy are deployment config
  udp.begin(UDP_PORT);
  lastValidPacketMs = 0;
}
void loop() {
  handleSerialRearm();
  int n=udp.parsePacket(); if(n>0 && n<=64){uint8_t p[64];handlePacket(p,size_t(udp.read(p,sizeof(p))));}
  if (lastValidPacketMs == 0 || millis()-lastValidPacketMs > WATCHDOG_MS) { communicationFault = true; stopTurntableMotor(); }
  if (estopLatched || communicationFault) stopTurntableMotor();
}
