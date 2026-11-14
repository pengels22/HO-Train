/*
 * HO Railroad - Nano 11-channel IR INPUT DIAGNOSTIC (not a decoder).
 *
 * Channels: D2..D12. Demodulated 38kHz receiver outputs idle HIGH and
 * pulse LOW when IR carrier is seen. This sketch prints transition timing
 * so the receiver wiring and field of view can be checked on the bench.
 *
 * IMPORTANT: It DOES NOT decode train IDs / 4-byte IR payloads.
 * An actual multichannel protocol decoder still needs an agreed beacon
 * waveform, carrier/duty timing, verified receiver hardware, and tests.
 * This diagnostic is intentionally non-actuating.
 */
#include <Arduino.h>

constexpr uint8_t CHANNELS = 11;
constexpr uint8_t FIRST_PIN = 2;
constexpr uint32_t MIN_EDGE_REPORT_US = 100; // suppress very short glitches
constexpr uint32_t SERIAL_BAUD = 115200;
uint8_t lastLevel[CHANNELS];
uint32_t lastEdgeUs[CHANNELS];

void setup() {
  Serial.begin(SERIAL_BAUD);
  for (uint8_t i = 0; i < CHANNELS; ++i) {
    pinMode(FIRST_PIN + i, INPUT_PULLUP);
    lastLevel[i] = digitalRead(FIRST_PIN + i);
    lastEdgeUs[i] = micros();
  }
  Serial.println(F("{\"type\":\"diagnostic_ready\",\"channels\":11}"));
}

void loop() {
  for (uint8_t i = 0; i < CHANNELS; ++i) {
    const uint8_t level = digitalRead(FIRST_PIN + i);
    if (level == lastLevel[i]) continue;
    const uint32_t now = micros();
    const uint32_t elapsed = now - lastEdgeUs[i];
    if (elapsed < MIN_EDGE_REPORT_US) continue;
    lastLevel[i] = level;
    lastEdgeUs[i] = now;
    Serial.print(F("{\"channel\":"));
    Serial.print(i + 1);
    Serial.print(F(",\"pin\":"));
    Serial.print(FIRST_PIN + i);
    Serial.print(F(",\"level\":"));
    Serial.print(level);
    Serial.print(F(",\"elapsed_us\":"));
    Serial.print(elapsed);
    Serial.println('}');
  }
}
