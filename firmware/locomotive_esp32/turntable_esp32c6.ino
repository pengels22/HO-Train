/* XIAO ESP32-C6 turntable controller.
 * USB is the primary newline-delimited command path. UDP is optional and
 * uses the same safety latch; it is never required for normal operation.
 * Commands: ESTOP, STATUS, ENTRY AUTH, CLEARANCE, TURN, POLARITY NORMAL,
 * POLARITY REVERSED, POWER ON, EXIT COMPLETE, REARM AUTH, STOP.
 */
#include <Arduino.h>
#include <WiFiUdp.h>

constexpr uint8_t ALL_TRAINS = 0xFF, ESTOP_FLAG = 0x80, VERSION = 1;
constexpr unsigned long WATCHDOG_MS = 500, ROTATION_TIMEOUT_MS = 30000;
constexpr unsigned long PULSE_LOCKOUT_MS = 250, PULSE_COOLDOWN_MS = 500;
constexpr uint16_t UDP_PORT = 4210;
constexpr int HOME_SWITCH = D0, ROTATED_SWITCH = D1, MOTOR_IN1 = D2, MOTOR_IN2 = D3;
constexpr int POLARITY_RELAY = D4, TRACK_POWER_RELAY = D5, REED_END_A = D6, REED_END_B = D7;

WiFiUDP udp;
enum TurntableState { EMPTY_READY, TRAIN_ENTERING, TRAIN_LOADED, TURNING, ALIGNED_LOADED, TRAIN_EXITING, FAULT };
TurntableState state = FAULT;
bool estopLatched = false, communicationFault = true, trackPowerEnabled = false;
bool reedAActive = false, reedBActive = false;
bool stationaryConfirmed = false, gapClearanceConfirmed = false;
uint8_t countA = 0, countB = 0;
unsigned long lastPulseA = 0, lastPulseB = 0, cooldownA = 0, cooldownB = 0;
unsigned long lastValidPacketMs = 0, lastControlMs = 0, rotationDeadline = 0;
int rotationDirection = 1;
bool nextForward = true;
const char *targetAlignment = "";
bool polaritySelected = false;
const char *faultText = "startup_disarmed";
String responseTransaction;

uint16_t crc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) { crc ^= data[i]; for (uint8_t b=0;b<8;++b) crc=(crc>>1)^((crc&1)?0xA001:0); }
  return crc;
}

const char *alignmentName() {
  bool home = digitalRead(HOME_SWITCH) == LOW, rotated = digitalRead(ROTATED_SWITCH) == LOW;
  if (home && !rotated) return "HOME";
  if (!home && rotated) return "ROTATED";
  return "INVALID";
}

void stopTurntableMotor(bool fault = false) {
  digitalWrite(MOTOR_IN1, LOW); digitalWrite(MOTOR_IN2, LOW);
  trackPowerEnabled = false; digitalWrite(TRACK_POWER_RELAY, LOW);
  if (fault) state = FAULT;
}

void latchEstop(const char *source) {
  (void)source; estopLatched = true; faultText = "estop";
  stopTurntableMotor(true); Serial.println("OK ESTOP");
}

void reportStatus() {
  Serial.print("{\"controller\":\"turntable\",\"state\":\"");
  Serial.print(state == EMPTY_READY ? "EMPTY_READY" : state == TRAIN_ENTERING ? "TRAIN_ENTERING" : state == TRAIN_LOADED ? "TRAIN_LOADED" : state == TURNING ? "TURNING" : state == ALIGNED_LOADED ? "ALIGNED_LOADED" : state == TRAIN_EXITING ? "TRAIN_EXITING" : "FAULT");
  Serial.print("\",\"transaction\":\""); Serial.print(responseTransaction);
  Serial.print("\",\"alignment\":\""); Serial.print(alignmentName());
  Serial.print("\",\"estop\":"); Serial.print(estopLatched ? "true" : "false");
  Serial.print(",\"motor\":"); Serial.print(state == TURNING ? "true" : "false");
  Serial.print(",\"track_power\":"); Serial.print(trackPowerEnabled ? "true" : "false");
  Serial.print(",\"fault\":\""); Serial.print(faultText);
  Serial.print("\",\"count_a\":"); Serial.print(countA); Serial.print(",\"count_b\":"); Serial.print(countB);
  Serial.println("}");
  responseTransaction = "";
}

String jsonField(const String &line, const char *name) {
  String marker = String("\"") + name + "\":\"";
  int start = line.indexOf(marker);
  if (start < 0) return "";
  start += marker.length();
  int end = line.indexOf('"', start);
  return end < 0 ? "" : line.substring(start, end);
}

bool jsonBool(const String &line, const char *name) {
  String marker = String("\"") + name + "\":";
  int start = line.indexOf(marker);
  return start >= 0 && line.substring(start + marker.length()).startsWith("true");
}

void resetCounts() { countA = countB = 0; lastPulseA = lastPulseB = cooldownA = cooldownB = 0; reedAActive = reedBActive = false; stationaryConfirmed = gapClearanceConfirmed = false; }

void countReed(bool endA, bool active, unsigned long now) {
  bool &previous = endA ? reedAActive : reedBActive;
  unsigned long &last = endA ? lastPulseA : lastPulseB;
  unsigned long &cooldown = endA ? cooldownA : cooldownB;
  uint8_t &count = endA ? countA : countB;
  if (!active) { if (previous && count == 4) cooldown = now + PULSE_COOLDOWN_MS; previous = false; return; }
  if (previous) return;
  previous = true;
  if (now < cooldown || (last && now - last < PULSE_LOCKOUT_MS)) return;
  if (count >= 4) { faultText = "extra_reed_pulse"; stopTurntableMotor(true); return; }
  last = now; ++count;
}

bool safeAlignment() { return strcmp(alignmentName(), "INVALID") != 0; }

void beginTurn() {
  if (estopLatched || communicationFault || state != TRAIN_LOADED || !safeAlignment()) { Serial.println("ERR TURN interlock"); return; }
  targetAlignment = strcmp(alignmentName(), "HOME") == 0 ? "ROTATED" : "HOME";
  state = TURNING; rotationDirection = nextForward ? 1 : -1; nextForward = !nextForward;
  rotationDeadline = millis() + ROTATION_TIMEOUT_MS; digitalWrite(TRACK_POWER_RELAY, LOW); trackPowerEnabled = false;
  digitalWrite(MOTOR_IN1, rotationDirection > 0 ? HIGH : LOW); digitalWrite(MOTOR_IN2, rotationDirection < 0 ? HIGH : LOW);
  Serial.println("OK TURN");
}

void handleSerialLine(String line) {
  line.trim();
  const bool isJson = line.startsWith("{");
  if (isJson) {
    stationaryConfirmed = jsonBool(line, "train_stopped");
    gapClearanceConfirmed = jsonBool(line, "gap_clear");
    responseTransaction = jsonField(line, "transaction");
    line = jsonField(line, "command");
  }
  if (line == "ESTOP" || line == "STATUS" || line == "STOP" || line == "REARM AUTH" || line == "ENTRY AUTH" || line == "CLEARANCE" || line == "TURN" || line == "POLARITY NORMAL" || line == "POLARITY REVERSED" || line == "POWER ON" || line == "EXIT COMPLETE") {
    lastControlMs = millis(); communicationFault = false;
  }
  if (line == "ESTOP") { latchEstop("USB"); return; }
  if (line == "STATUS") { reportStatus(); return; }
  if (line == "STOP") { stopTurntableMotor(false); Serial.println("OK STOP"); return; }
  if (line == "REARM AUTH") {
    if (communicationFault || !safeAlignment() || trackPowerEnabled || state == TURNING ||
        (strcmp(faultText, "") != 0 && strcmp(faultText, "estop") != 0 && strcmp(faultText, "startup_disarmed") != 0)) { Serial.println("ERR REARM interlock"); return; }
    estopLatched = false; faultText = ""; resetCounts(); state = EMPTY_READY; reportStatus(); return;
  }
  if (line == "REARM") { Serial.println("ERR REARM_AUTH_REQUIRED"); return; }
  if (line == "ENTRY AUTH") {
    if (estopLatched || communicationFault || state != EMPTY_READY || !safeAlignment()) { Serial.println("ERR ENTRY interlock"); return; }
    resetCounts(); trackPowerEnabled = true; digitalWrite(TRACK_POWER_RELAY, HIGH); state = TRAIN_ENTERING; Serial.println("OK ENTRY"); return;
  }
  if (line == "CLEARANCE") {
    const uint8_t count = strcmp(alignmentName(), "HOME") == 0 ? countA : countB;
    const unsigned long cooldown = strcmp(alignmentName(), "HOME") == 0 ? cooldownA : cooldownB;
    if (state != TRAIN_ENTERING || count != 4 || reedAActive || reedBActive || millis() < cooldown || !stationaryConfirmed || !gapClearanceConfirmed) { Serial.println("ERR CLEARANCE interlock"); return; }
    stopTurntableMotor(false); state = TRAIN_LOADED; Serial.println("OK LOADED"); return;
  }
  if (line == "POLARITY NORMAL" || line == "POLARITY REVERSED") {
    if (trackPowerEnabled || state != ALIGNED_LOADED) { Serial.println("ERR POLARITY interlock"); return; }
    digitalWrite(POLARITY_RELAY, line == "POLARITY REVERSED" ? HIGH : LOW); polaritySelected = true; Serial.println("OK POLARITY"); return;
  }
  if (line == "POWER ON") {
    if (state != ALIGNED_LOADED || !safeAlignment() || !polaritySelected || estopLatched || communicationFault) { Serial.println("ERR POWER interlock"); return; }
    resetCounts(); trackPowerEnabled = true; digitalWrite(TRACK_POWER_RELAY, HIGH); state = TRAIN_EXITING; Serial.println("OK POWER"); return;
  }
  if (line == "EXIT COMPLETE") {
    const uint8_t count = strcmp(alignmentName(), "HOME") == 0 ? countB : countA;
    const unsigned long cooldown = strcmp(alignmentName(), "HOME") == 0 ? cooldownB : cooldownA;
    if (state != TRAIN_EXITING || count != 4 || reedAActive || reedBActive || millis() < cooldown || !stationaryConfirmed || !gapClearanceConfirmed) { Serial.println("ERR EXIT interlock"); return; }
    stopTurntableMotor(false); resetCounts(); polaritySelected = false; state = EMPTY_READY; Serial.println("OK EMPTY"); return;
  }
  if (line == "TURN") { beginTurn(); return; }
  Serial.println("ERR UNKNOWN_COMMAND");
}

void handleSerial() {
  static String line;
  while (Serial.available()) { char c = char(Serial.read()); if (c == '\n') { handleSerialLine(line); line = ""; } else if (line.length() < 32) line += c; }
}

void handleUdpPacket(const uint8_t *p, size_t length) {
  if (length != 12 || p[0] != 'H' || p[1] != 'C' || p[2] != VERSION || crc16(p,10) != (uint16_t(p[11])<<8 | p[10])) return;
  if (p[3] != ALL_TRAINS) return;
  lastValidPacketMs = millis(); communicationFault = false;
  if (p[9] & ESTOP_FLAG) latchEstop("UDP");
}

void setup() {
  pinMode(HOME_SWITCH, INPUT_PULLUP); pinMode(ROTATED_SWITCH, INPUT_PULLUP); pinMode(REED_END_A, INPUT_PULLUP); pinMode(REED_END_B, INPUT_PULLUP);
  pinMode(MOTOR_IN1, OUTPUT); pinMode(MOTOR_IN2, OUTPUT); pinMode(POLARITY_RELAY, OUTPUT); pinMode(TRACK_POWER_RELAY, OUTPUT);
  digitalWrite(POLARITY_RELAY, LOW); Serial.begin(115200); stopTurntableMotor(true); resetCounts(); udp.begin(UDP_PORT);
}

void loop() {
  const unsigned long now = millis(); handleSerial();
  int packetSize = udp.parsePacket(); if (packetSize > 0 && packetSize <= 64) { uint8_t p[64]; handleUdpPacket(p, size_t(udp.read(p,sizeof(p)))); }
  countReed(true, digitalRead(REED_END_A) == LOW, now); countReed(false, digitalRead(REED_END_B) == LOW, now);
  if (state == TURNING) {
    if (strcmp(alignmentName(), targetAlignment) == 0) { stopTurntableMotor(false); state = ALIGNED_LOADED; Serial.println("OK ALIGNMENT"); }
    else if (now >= rotationDeadline) { faultText = "rotation_timeout"; stopTurntableMotor(true); Serial.println("ERR ROTATION_TIMEOUT"); }
  }
  const unsigned long lastControl = max(lastControlMs, lastValidPacketMs);
  if (lastControl == 0 || now - lastControl > WATCHDOG_MS) { communicationFault = true; stopTurntableMotor(true); }
  if (estopLatched || communicationFault) stopTurntableMotor(true);
}
