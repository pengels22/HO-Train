/*
 * HO Railroad - Arduino Nano ESP32 single IR bench receiver.
 *
 * Board: Arduino Nano ESP32
 * Sensor: one demodulated IR receiver output on D2
 * Serial: USB CDC, 115200 baud
 *
 * This is a non-actuating bench instrument. It decodes the M5 beacon's
 * compact speed/locomotive-ID payload and validates its CRC-8. SET ENDPOINT
 * selects which logical layout receiver the one physical sensor represents.
 * Settings are retained in ESP32 NVS.
 */
#include <Arduino.h>
#include <Preferences.h>

constexpr uint8_t IR_SENSOR_PIN = D2;
constexpr uint32_t SERIAL_BAUD = 115200;
// The M5 transmitter sends 1 ms symbols.  A demodulated receiver is LOW
// only while carrier is present, so a complete frame is not continuously
// LOW for the 40 ms needed by a beam-break debounce.  Detect a carrier burst
// instead and close it after the inter-symbol/frame idle gap.
constexpr uint32_t BURST_START_MS = 1;
constexpr uint32_t BURST_IDLE_MS = 8;
constexpr uint32_t MIN_EVENT_GAP_MS = 80;
constexpr uint32_t IR_SYMBOL_US = 1000;
constexpr uint8_t IR_FRAME_BYTES = 3;
constexpr uint32_t CAPTURE_SAMPLE_US = 100;
constexpr uint32_t CAPTURE_LENGTH_US = 80000;
constexpr uint32_t CAPTURE_WAIT_US = 250000;
constexpr size_t MAX_LINE = 96;

struct Endpoint { const char *id; const char *name; };
const Endpoint ENDPOINTS[] = {
  {"tunnel_entrance", "Tunnel Entrance"},
  {"yard_entrance", "Yard Entrance"},
  {"ski_entrance", "Ski Entrance"},
  {"tunnel_exit_east", "Tunnel Exit East"},
  {"tunnel_exit_west", "Tunnel Exit West"},
  {"underground_entrance", "Underground Entrance"},
  {"tipper_entrance", "Tipper Entrance"},
  {"stall_1a", "Stall 1A"},
  {"stall_1b", "Stall 1B"},
  {"stall_2", "Stall 2"},
  {"stall_3", "Stall 3"},
  {"mine_station", "Mine Station"},
  {"farm_station", "Farm Station"},
  {"town_station", "Town Station"},
};
constexpr size_t ENDPOINT_COUNT = sizeof(ENDPOINTS) / sizeof(ENDPOINTS[0]);

Preferences preferences;
char lineBuffer[MAX_LINE];
size_t lineLength = 0;
size_t endpointIndex = 0;
uint8_t trainId = 1;
bool sensorActive = false;
uint32_t activeSince = 0;
uint32_t lastCarrierMs = 0;
uint32_t lastEvent = 0;
bool burstActive = false;
bool captureRequested = false;
uint32_t lastPulseUs = 0;
uint8_t flashCount = 0;
bool countingFrame = false;
uint32_t frameStartMs = 0;
uint32_t lastEmptyReportMs = 0;
uint8_t sampleIds[3] = {};
uint8_t sampleCount = 0;
uint8_t syncPulses = 0;
bool dataStarted = false;
uint8_t dataBit = 0;
bool decodingFrame = false;
uint8_t frame[IR_FRAME_BYTES] = {};
uint8_t frameBit = 0;
uint32_t nextSampleUs = 0;
uint8_t lastDecodedTrainId = 0;
int16_t lastDecodedSpeed = 0;
uint8_t lastDecodedFlags = 0;

void printStatus() {
  Serial.print(F("{\"controller\":\"ir_bench_nano_esp32\",\"pin\":\"D2\",\"endpoint_id\":\""));
  Serial.print(ENDPOINTS[endpointIndex].id);
  Serial.print(F("\",\"receiver\":\""));
  Serial.print(ENDPOINTS[endpointIndex].name);
  Serial.print(F("\",\"train_id\":"));
  Serial.print(lastDecodedTrainId ? lastDecodedTrainId : trainId);
  Serial.print(F(",\"train_id_source\":\""));
  Serial.print(lastDecodedTrainId ? F("m5_frame") : F("bench_config"));
  Serial.print(F("\""));
  Serial.print(F(",\"active\":"));
  Serial.print(sensorActive ? F("true") : F("false"));
  Serial.println(F(",\"outputs_disabled\":true}"));
}

void printHelp() {
  Serial.println(F("Commands: STATUS | CAPTURE | LIST | SET ENDPOINT <id> | SET TRAIN <1-4> | HELP"));
}

int endpointFor(const char *value) {
  for (size_t i = 0; i < ENDPOINT_COUNT; ++i) {
    if (strcasecmp(value, ENDPOINTS[i].id) == 0 || strcasecmp(value, ENDPOINTS[i].name) == 0) return i;
  }
  return -1;
}

void printList() {
  Serial.print(F("{\"endpoints\":["));
  for (size_t i = 0; i < ENDPOINT_COUNT; ++i) {
    if (i) Serial.print(',');
    Serial.print(F("\"")); Serial.print(ENDPOINTS[i].id); Serial.print(F("\""));
  }
  Serial.println(F("]}"));
}

void saveSettings() {
  preferences.putString("endpoint", ENDPOINTS[endpointIndex].id);
  preferences.putUChar("train", trainId);
}

void handleCommand(char *command) {
  while (*command == ' ') ++command;
  if (strcasecmp(command, "STATUS") == 0) { printStatus(); return; }
  if (strcasecmp(command, "CAPTURE") == 0) { captureRequested = true; Serial.println(F("{\"capture\":\"armed\"}")); return; }
  if (strcasecmp(command, "LIST") == 0) { printList(); return; }
  if (strcasecmp(command, "HELP") == 0) { printHelp(); return; }
  if (strncasecmp(command, "SET TRAIN ", 10) == 0) {
    const int value = atoi(command + 10);
    if (value < 1 || value > 4) { Serial.println(F("{\"ok\":false,\"error\":\"train_id must be 1-4\"}")); return; }
    trainId = static_cast<uint8_t>(value); saveSettings(); printStatus(); return;
  }
  if (strncasecmp(command, "SET ENDPOINT ", 13) == 0) {
    const int value = endpointFor(command + 13);
    if (value < 0) { Serial.println(F("{\"ok\":false,\"error\":\"unknown endpoint; use LIST\"}")); return; }
    endpointIndex = static_cast<size_t>(value); saveSettings(); printStatus(); return;
  }
  Serial.println(F("{\"ok\":false,\"error\":\"unknown command\"}"));
}

void readCommands() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') { lineBuffer[lineLength] = '\0'; handleCommand(lineBuffer); lineLength = 0; continue; }
    if (lineLength + 1 < MAX_LINE) lineBuffer[lineLength++] = c;
  }
}

void emitEvent() {
  if (millis() - lastEvent < MIN_EVENT_GAP_MS) return;
  lastEvent = millis();
  Serial.print(F("{\"station_id\":\"")); Serial.print(ENDPOINTS[endpointIndex].id);
  Serial.print(F("\",\"train_id\":")); Serial.print(lastDecodedTrainId ? String(lastDecodedTrainId) : String(trainId));
  Serial.println(F("}"));
}

void emitEmpty() {
  if (millis() - lastEmptyReportMs < 500) return;
  lastEmptyReportMs = millis();
  Serial.print(F("{\"station_id\":\"")); Serial.print(ENDPOINTS[endpointIndex].id);
  Serial.println(F("\",\"train_id\":\"no_train\"}"));
}

void recordTrainSample(uint8_t id, int16_t speed = 0) {
  if (id < 1 || id > 4) return;
  sampleIds[sampleCount++] = id;
  if (sampleCount < 3) return;
  uint8_t bestId = sampleIds[0];
  uint8_t bestVotes = 0;
  for (uint8_t candidate = 1; candidate <= 4; ++candidate) {
    uint8_t votes = 0;
    for (uint8_t i = 0; i < 3; ++i) if (sampleIds[i] == candidate) ++votes;
    if (votes > bestVotes) { bestVotes = votes; bestId = candidate; }
  }
  sampleCount = 0;
  lastDecodedTrainId = bestId;
  lastDecodedFlags = 0;
  lastDecodedSpeed = speed;
  emitEvent();
}

uint8_t crc8(const uint8_t *data, size_t length) {
  uint8_t crc = 0;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc & 0x80) ? uint8_t((crc << 1) ^ 0x07) : uint8_t(crc << 1);
  }
  return crc;
}

void finishFrame() {
  decodingFrame = false;
  if (frame[1] < 1 || frame[1] > 4 || crc8(frame, 2) != frame[2]) return;
  recordTrainSample(frame[1], frame[0]);
}

void sampleFrame() {
  while (decodingFrame && int32_t(micros() - nextSampleUs) >= 0) {
    if (digitalRead(IR_SENSOR_PIN) == LOW)
      frame[frameBit / 8] |= uint8_t(1u << (frameBit % 8));
    ++frameBit;
    nextSampleUs += IR_SYMBOL_US;
    if (frameBit >= IR_FRAME_BYTES * 8) finishFrame();
  }
}

void sampleSensor() {
  const bool active = digitalRead(IR_SENSOR_PIN) == LOW;
  sensorActive = active;
  if (!countingFrame && millis() - lastEvent >= 500) emitEmpty();
  if (countingFrame && millis() - frameStartMs >= 500) {
    recordTrainSample(flashCount);
    countingFrame = false; flashCount = 0; lastPulseUs = 0;
  }
  static bool previousActive = false;
  if (!active || previousActive) { previousActive = active; return; }
  previousActive = true;
  const uint32_t now = micros();
  if (lastPulseUs == 0) {
    flashCount = 1; countingFrame = true; frameStartMs = millis(); lastCarrierMs = frameStartMs; lastPulseUs = now; return;
  }
  const uint32_t interval = now - lastPulseUs;
  lastPulseUs = now;
  if (interval <= 300000 && millis() - frameStartMs < 500) { ++flashCount; lastCarrierMs = millis(); }
}

void captureRawBurst() {
  captureRequested = false;
  const uint32_t waitStart = micros();
  while (digitalRead(IR_SENSOR_PIN) != LOW && micros() - waitStart < CAPTURE_WAIT_US) yield();
  if (digitalRead(IR_SENSOR_PIN) != LOW) {
    Serial.println(F("IR_CAPTURE_TIMEOUT"));
    return;
  }
  const uint32_t start = micros();
  uint32_t next = start;
  bool previous = false;
  uint16_t run = 0;
  Serial.print(F("IR_CAPTURE sample_us=100 runs="));
  while (micros() - start < CAPTURE_LENGTH_US) {
    while (int32_t(micros() - next) < 0) yield();
    const bool active = digitalRead(IR_SENSOR_PIN) == LOW;
    if (active == previous) {
      ++run;
    } else {
      if (run) { Serial.print(previous ? '1' : '0'); Serial.print(':'); Serial.print(run); Serial.print(','); }
      previous = active;
      run = 1;
    }
    next += CAPTURE_SAMPLE_US;
  }
  if (run) { Serial.print(previous ? '1' : '0'); Serial.print(':'); Serial.print(run); }
  Serial.println();
}

void setup() {
  pinMode(IR_SENSOR_PIN, INPUT_PULLUP);
  Serial.begin(SERIAL_BAUD);
  preferences.begin("bench-ir", false);
  const String saved = preferences.getString("endpoint", ENDPOINTS[0].id);
  const int savedEndpoint = endpointFor(saved.c_str());
  if (savedEndpoint >= 0) endpointIndex = static_cast<size_t>(savedEndpoint);
  const uint8_t savedTrain = preferences.getUChar("train", 1);
  if (savedTrain >= 1 && savedTrain <= 4) trainId = savedTrain;
  sensorActive = digitalRead(IR_SENSOR_PIN) == LOW;
  if (sensorActive) { lastCarrierMs = millis(); activeSince = millis(); }
  Serial.println(F("{\"ready\":true,\"controller\":\"ir_bench_nano_esp32\",\"outputs_disabled\":true}"));
  printStatus();
}

void loop() {
  readCommands();
  if (captureRequested) { captureRawBurst(); return; }
  sampleSensor();
}
