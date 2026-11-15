/*
 * HO Railroad - Arduino Nano ESP32 single IR bench receiver.
 *
 * Board: Arduino Nano ESP32
 * Sensor: one demodulated IR receiver output on D2
 * Serial: USB CDC, 115200 baud
 *
 * This is a non-actuating bench instrument. It cannot decode the M5 beacon's
 * train identity; SET TRAIN selects the identity to report for test-track
 * events. SET ENDPOINT selects which logical layout receiver the one physical
 * sensor represents. Settings are retained in ESP32 NVS.
 */
#include <Arduino.h>
#include <Preferences.h>

constexpr uint8_t IR_SENSOR_PIN = D2;
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t DEBOUNCE_MS = 40;
constexpr uint32_t MIN_EVENT_GAP_MS = 300;
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
bool stableActive = false;
bool candidateActive = false;
uint32_t candidateSince = 0;
uint32_t lastEvent = 0;

void printStatus() {
  Serial.print(F("{\"controller\":\"ir_bench_nano_esp32\",\"pin\":\"D2\",\"endpoint_id\":\""));
  Serial.print(ENDPOINTS[endpointIndex].id);
  Serial.print(F("\",\"receiver\":\""));
  Serial.print(ENDPOINTS[endpointIndex].name);
  Serial.print(F("\",\"train_id\":"));
  Serial.print(trainId);
  Serial.print(F(",\"active\":"));
  Serial.print(stableActive ? F("true") : F("false"));
  Serial.println(F(",\"outputs_disabled\":true}"));
}

void printHelp() {
  Serial.println(F("Commands: STATUS | LIST | SET ENDPOINT <id> | SET TRAIN <1-4> | HELP"));
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
  Serial.print(F("{\"receiver\":\"")); Serial.print(ENDPOINTS[endpointIndex].name);
  Serial.print(F("\",\"endpoint_id\":\"")); Serial.print(ENDPOINTS[endpointIndex].id);
  Serial.print(F("\",\"train_id\":")); Serial.print(trainId);
  Serial.println(F(",\"speed\":0,\"source\":\"bench_nano_esp32\"}"));
}

void sampleSensor() {
  const bool active = digitalRead(IR_SENSOR_PIN) == LOW;
  const uint32_t now = millis();
  if (active != candidateActive) { candidateActive = active; candidateSince = now; }
  if (candidateActive != stableActive && now - candidateSince >= DEBOUNCE_MS) {
    stableActive = candidateActive;
    if (stableActive) emitEvent();
  }
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
  stableActive = digitalRead(IR_SENSOR_PIN) == LOW;
  candidateActive = stableActive;
  Serial.println(F("{\"ready\":true,\"controller\":\"ir_bench_nano_esp32\",\"outputs_disabled\":true}"));
  printStatus();
}

void loop() {
  readCommands();
  sampleSensor();
}
