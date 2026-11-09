/* XIAO ESP32-C6 turntable safety receiver.
 * Receives the same binary broadcast frame as locomotives.  Any broadcast
 * ESTOP latches the turntable controller and invokes the local stop hook.
 * The actual turntable driver interface is intentionally not guessed here.
 */
#include <Arduino.h>
#include <WiFiUdp.h>

constexpr uint8_t ALL_TRAINS = 0xFF, ESTOP_FLAG = 0x80, VERSION = 1;
constexpr unsigned long WATCHDOG_MS = 500;
constexpr uint16_t UDP_PORT = 4210;
WiFiUDP udp;
bool estopLatched = false;
unsigned long lastPacketMs = 0;

uint16_t crc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) { crc ^= data[i]; for (uint8_t b=0;b<8;++b) crc=(crc>>1)^((crc&1)?0xA001:0); }
  return crc;
}

void stopTurntableMotor() {
  // Bind this hook to the validated turntable controller interface before use.
}

void handlePacket(const uint8_t *p, size_t length) {
  if (length != 12 || p[0] != 'H' || p[1] != 'C' || p[2] != VERSION || crc16(p,10) != (uint16_t(p[11])<<8 | p[10])) return;
  lastPacketMs = millis();
  if (p[3] == ALL_TRAINS && (p[9] & ESTOP_FLAG)) { estopLatched = true; stopTurntableMotor(); }
}

void setup() { stopTurntableMotor(); lastPacketMs = millis(); udp.begin(UDP_PORT); }
void loop() {
  int n=udp.parsePacket(); if(n>0 && n<=64){uint8_t p[64];handlePacket(p,size_t(udp.read(p,sizeof(p))));}
  if (millis()-lastPacketMs > WATCHDOG_MS) stopTurntableMotor();
  if (estopLatched) stopTurntableMotor();
}
