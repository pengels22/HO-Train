/* Dedicated XIAO ESP32-C6 rotary tipper controller.
 *
 * No GPIO numbers are guessed here. The build must provide the logical pin
 * macros after the owner's C6 harness is verified, for example with
 * -DTIPPER_MOTOR_IN1=<validated pin>. Until then all actuator writes remain
 * disabled and the controller reports pin_map_unverified.
 *
 * USB newline JSON is the primary control path. ESTOP is always accepted as a
 * plain line. Commands are ESTOP, STOP, STATUS, REARM, LOCK, UNLOCK,
 * DECOUPLER OFF, ROTATE CW/CCW, and HOME.
 */
#include <Arduino.h>

#ifndef TIPPER_MOTOR_IN1
#define TIPPER_MOTOR_IN1 -1
#endif
#ifndef TIPPER_MOTOR_IN2
#define TIPPER_MOTOR_IN2 -1
#endif
#ifndef TIPPER_LOCK_OUTPUT
#define TIPPER_LOCK_OUTPUT -1
#endif
#ifndef TIPPER_DECOUPLER_OUTPUT
#define TIPPER_DECOUPLER_OUTPUT -1
#endif
#ifndef TIPPER_IR_FRONT_CLEAR
#define TIPPER_IR_FRONT_CLEAR -1
#endif
#ifndef TIPPER_IR_BACK_CLEAR
#define TIPPER_IR_BACK_CLEAR -1
#endif
#ifndef TIPPER_HALL_BACK
#define TIPPER_HALL_BACK -1
#endif
#ifndef TIPPER_HALL_FRONT
#define TIPPER_HALL_FRONT -1
#endif
#ifndef TIPPER_HALL_CLEAR
#define TIPPER_HALL_CLEAR -1
#endif
#ifndef TIPPER_ENCODER
#define TIPPER_ENCODER -1
#endif

constexpr unsigned long WATCHDOG_MS = 500;
constexpr unsigned long ROTATION_TIMEOUT_MS = 30000;
constexpr uint8_t MAX_ROTATION_PWM = 255;
constexpr size_t MAX_LINE = 192;

enum TipperState { STARTUP_DISARMED, IDLE, ROTATING, HOMING, FAULT };
TipperState state = STARTUP_DISARMED;
bool estopLatched = true;
bool communicationFault = true;
bool locked = true;
bool decouplerOff = true;
int rotationDirection = 0;
uint8_t rotationPwm = 0;
volatile uint32_t encoderTicks = 0;
unsigned long lastControlMs = 0;
unsigned long rotationDeadline = 0;
String responseTransaction;
String lastTransaction;
char serialBuffer[MAX_LINE];
size_t serialLength = 0;
bool serialOverflow = false;

bool configured(int pin) { return pin >= 0; }
bool allPinsConfigured() {
  return configured(TIPPER_MOTOR_IN1) && configured(TIPPER_MOTOR_IN2) &&
         configured(TIPPER_LOCK_OUTPUT) && configured(TIPPER_DECOUPLER_OUTPUT) &&
         configured(TIPPER_IR_FRONT_CLEAR) && configured(TIPPER_IR_BACK_CLEAR) &&
         configured(TIPPER_HALL_BACK) && configured(TIPPER_HALL_FRONT) &&
         configured(TIPPER_HALL_CLEAR) && configured(TIPPER_ENCODER);
}

void encoderISR() { ++encoderTicks; }

void motorOff() {
  if (configured(TIPPER_MOTOR_IN1)) digitalWrite(TIPPER_MOTOR_IN1, LOW);
  if (configured(TIPPER_MOTOR_IN2)) digitalWrite(TIPPER_MOTOR_IN2, LOW);
  rotationDirection = 0;
  rotationPwm = 0;
}

void setMotor(int direction, uint8_t pwm) {
  if (!allPinsConfigured()) { motorOff(); return; }
  // No motion is permitted until the local lock is released and the Pi has
  // explicitly rearmed this board.
  if (estopLatched || communicationFault || locked) { motorOff(); return; }
  uint8_t bounded = min(pwm, MAX_ROTATION_PWM);
  digitalWrite(TIPPER_MOTOR_IN1, direction > 0 ? HIGH : LOW);
  digitalWrite(TIPPER_MOTOR_IN2, direction < 0 ? HIGH : LOW);
  rotationDirection = direction;
  rotationPwm = bounded;
  analogWrite(TIPPER_MOTOR_IN1, direction > 0 ? bounded : 0);
  analogWrite(TIPPER_MOTOR_IN2, direction < 0 ? bounded : 0);
}

void setLock(bool engaged) {
  locked = engaged;
  if (configured(TIPPER_LOCK_OUTPUT)) digitalWrite(TIPPER_LOCK_OUTPUT, engaged ? HIGH : LOW);
  if (engaged) motorOff();
}

void setDecouplerOff() {
  decouplerOff = true;
  if (configured(TIPPER_DECOUPLER_OUTPUT)) digitalWrite(TIPPER_DECOUPLER_OUTPUT, LOW);
}

void latchEstop(const char *reason) {
  (void)reason;
  estopLatched = true; communicationFault = false; state = FAULT;
  motorOff(); setDecouplerOff(); setLock(true);
  Serial.println("OK ESTOP");
}

String jsonField(const String &line, const char *name) {
  String marker = String("\"") + name + "\":\"";
  int start = line.indexOf(marker);
  if (start < 0) return "";
  start += marker.length();
  int end = line.indexOf('"', start);
  return end < 0 ? "" : line.substring(start, end);
}

bool validTransaction(const String &transaction) {
  if (transaction.length() == 0 || transaction.length() > 64) return false;
  for (size_t i = 0; i < transaction.length(); ++i) {
    char c = transaction[i];
    if (!isAlphaNumeric(c) && c != '-' && c != '_') return false;
  }
  return true;
}

bool jsonComplete(const String &line) {
  return line.length() >= 2 && line[0] == '{' && line[line.length() - 1] == '}';
}

const char *stateName() {
  switch (state) {
    case IDLE: return "IDLE"; case ROTATING: return "ROTATING";
    case HOMING: return "HOMING"; case FAULT: return "FAULT";
    default: return "STARTUP_DISARMED";
  }
}

void reportStatus() {
  Serial.print("{\"controller\":\"tipper\",\"state\":\""); Serial.print(stateName());
  Serial.print("\",\"transaction\":\""); Serial.print(responseTransaction);
  Serial.print("\",\"estop\":"); Serial.print(estopLatched ? "true" : "false");
  Serial.print(",\"communication_fault\":"); Serial.print(communicationFault ? "true" : "false");
  Serial.print(",\"motor\":"); Serial.print(rotationDirection != 0 ? "true" : "false");
  Serial.print(",\"locked\":"); Serial.print(locked ? "true" : "false");
  Serial.print(",\"decoupler\":"); Serial.print(decouplerOff ? "false" : "true");
  Serial.print(",\"pin_map_verified\":"); Serial.print(allPinsConfigured() ? "true" : "false");
  Serial.print(",\"encoder_ticks\":"); Serial.print(encoderTicks);
  Serial.println("}");
  responseTransaction = "";
}

void handleCommand(String line) {
  line.trim();
  if (line == "ESTOP") { latchEstop("serial"); return; }
  const bool isJson = line.startsWith("{");
  if (isJson) {
    if (!jsonComplete(line)) { Serial.println("{\"ok\":false,\"error\":\"malformed_json\"}"); return; }
    responseTransaction = jsonField(line, "transaction");
    String command = jsonField(line, "command");
    if (command.length() == 0) { Serial.println("{\"ok\":false,\"error\":\"missing_command\"}"); return; }
    if (command != "STATUS" && command != "ESTOP" && command != "STOP" && !validTransaction(responseTransaction)) {
      Serial.println("{\"ok\":false,\"error\":\"authorization_required\"}"); return;
    }
    if (command != "STATUS" && responseTransaction == lastTransaction) {
      Serial.println("{\"ok\":false,\"error\":\"duplicate_transaction\"}"); return;
    }
    line = command;
  }
  lastControlMs = millis(); communicationFault = false;
  if (line == "STATUS") { reportStatus(); return; }
  if (line == "STOP") { motorOff(); state = IDLE; Serial.println("OK STOP"); return; }
  if (line == "REARM") {
    if (!validTransaction(responseTransaction) || !allPinsConfigured() || !locked || rotationDirection != 0) {
      Serial.println("ERR REARM interlock"); return;
    }
    lastTransaction = responseTransaction; estopLatched = false; communicationFault = false;
    state = IDLE; reportStatus(); return;
  }
  if (line == "LOCK") { motorOff(); setLock(true); state = IDLE; Serial.println("OK LOCK"); return; }
  if (line == "UNLOCK") { if (estopLatched || communicationFault) { Serial.println("ERR UNLOCK interlock"); return; } setLock(false); Serial.println("OK UNLOCK"); return; }
  if (line == "DECOUPLER OFF") { motorOff(); setDecouplerOff(); Serial.println("OK DECOUPLER"); return; }
  if (line == "ROTATE CW" || line == "ROTATE CCW") {
    if (estopLatched || communicationFault || locked || !allPinsConfigured()) { Serial.println("ERR ROTATE interlock"); return; }
    rotationDeadline = millis() + ROTATION_TIMEOUT_MS; state = ROTATING;
    setMotor(line == "ROTATE CW" ? 1 : -1, 255); Serial.println("OK ROTATE"); return;
  }
  if (line == "HOME") {
    if (estopLatched || communicationFault || locked || !allPinsConfigured()) { Serial.println("ERR HOME interlock"); return; }
    rotationDeadline = millis() + ROTATION_TIMEOUT_MS; state = HOMING; setMotor(-1, 255); Serial.println("OK HOME"); return;
  }
  Serial.println("ERR UNKNOWN_COMMAND");
}

void handleSerial() {
  while (Serial.available()) {
    char c = char(Serial.read());
    if (c == '\n') {
      if (serialOverflow) Serial.println("{\"ok\":false,\"error\":\"line_too_long\"}");
      else { serialBuffer[serialLength] = '\0'; handleCommand(String(serialBuffer)); }
      serialLength = 0; serialOverflow = false;
    } else if (!serialOverflow) {
      if (serialLength + 1 >= MAX_LINE) serialOverflow = true;
      else serialBuffer[serialLength++] = c;
    }
  }
}

void setup() {
  if (configured(TIPPER_MOTOR_IN1)) pinMode(TIPPER_MOTOR_IN1, OUTPUT);
  if (configured(TIPPER_MOTOR_IN2)) pinMode(TIPPER_MOTOR_IN2, OUTPUT);
  if (configured(TIPPER_LOCK_OUTPUT)) pinMode(TIPPER_LOCK_OUTPUT, OUTPUT);
  if (configured(TIPPER_DECOUPLER_OUTPUT)) pinMode(TIPPER_DECOUPLER_OUTPUT, OUTPUT);
  if (configured(TIPPER_IR_FRONT_CLEAR)) pinMode(TIPPER_IR_FRONT_CLEAR, INPUT);
  if (configured(TIPPER_IR_BACK_CLEAR)) pinMode(TIPPER_IR_BACK_CLEAR, INPUT);
  if (configured(TIPPER_HALL_BACK)) pinMode(TIPPER_HALL_BACK, INPUT_PULLUP);
  if (configured(TIPPER_HALL_FRONT)) pinMode(TIPPER_HALL_FRONT, INPUT_PULLUP);
  if (configured(TIPPER_HALL_CLEAR)) pinMode(TIPPER_HALL_CLEAR, INPUT_PULLUP);
  if (configured(TIPPER_ENCODER)) { pinMode(TIPPER_ENCODER, INPUT_PULLUP); attachInterrupt(digitalPinToInterrupt(TIPPER_ENCODER), encoderISR, RISING); }
  Serial.begin(115200); motorOff(); setLock(true); setDecouplerOff();
  lastControlMs = 0;
}

void loop() {
  handleSerial();
  const unsigned long now = millis();
  if (lastControlMs == 0 || now - lastControlMs > WATCHDOG_MS) {
    communicationFault = true; motorOff(); setDecouplerOff(); state = FAULT;
  }
  if ((state == ROTATING || state == HOMING) && now >= rotationDeadline) {
    motorOff(); communicationFault = true; state = FAULT; Serial.println("ERR ROTATION_TIMEOUT");
  }
  // Dedicated feedback is required for physical completion; this firmware
  // never infers home/clearance from a missing or unconfigured input.
  if (state == HOMING && configured(TIPPER_HALL_CLEAR) && digitalRead(TIPPER_HALL_CLEAR) == LOW) {
    motorOff(); state = IDLE; Serial.println("OK HOME");
  }
}
