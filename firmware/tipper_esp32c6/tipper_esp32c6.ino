/* Dedicated XIAO ESP32-C6 rotary tipper controller.
 *
 * GPIOs follow the validated dedicated XIAO C6 tipper harness:
 * D2/GPIO2 Hall Front, D3/GPIO21 Hall Rear, D4/GPIO22 Hall Clear,
 * D5/GPIO23 encoder, D6/GPIO16 and D7/GPIO17 rotation motor,
 * D8/GPIO19 and D9/GPIO20 gripper motor IN3/IN4, and D10/GPIO18
 * magnetic decoupler relay. Forward gripper motion unlocks; reverse locks.
 *
 * The destination IR system is independent; no train-clearance IR inputs
 * are connected to this controller. Encoder uses 40 slots on a 1.125-inch wheel.
 * USB newline JSON is the primary control path. ESTOP is always accepted as a
 * plain line. Commands are ESTOP, STOP, STATUS, REARM, LOCK, UNLOCK,
 * DECOUPLER OFF/ON, ROTATE CW/CCW, and HOME.
 */
#include <Arduino.h>

#ifndef TIPPER_MOTOR_IN1
#define TIPPER_MOTOR_IN1 16
#endif
#ifndef TIPPER_MOTOR_IN2
#define TIPPER_MOTOR_IN2 17
#endif
#ifndef TIPPER_LOCK_IN3
#define TIPPER_LOCK_IN3 19
#endif
#ifndef TIPPER_LOCK_IN4
#define TIPPER_LOCK_IN4 20
#endif
#ifndef TIPPER_DECOUPLER_OUTPUT
#define TIPPER_DECOUPLER_OUTPUT 18
#endif
#ifndef TIPPER_HALL_BACK
#define TIPPER_HALL_BACK 21
#endif
#ifndef TIPPER_HALL_FRONT
#define TIPPER_HALL_FRONT 2
#endif
#ifndef TIPPER_HALL_CLEAR
#define TIPPER_HALL_CLEAR 22
#endif
#ifndef TIPPER_ENCODER
#define TIPPER_ENCODER 23
#endif

constexpr unsigned long WATCHDOG_MS = 500;
constexpr unsigned long ROTATION_TIMEOUT_MS = 30000;
constexpr unsigned long LOCK_PULSE_MS = 800;
constexpr unsigned long DECOUPLER_PULSE_MS = 250;
// D10/GPIO18 is an active-low relay: HIGH is OFF, LOW is ON.
// Keep the relay output disabled until bench verification is completed.
#ifndef TIPPER_DECOUPLER_ACTIVE_HIGH
#define TIPPER_DECOUPLER_ACTIVE_HIGH 0
#endif
// 40 encoder slots on a 1.125" diameter wheel: 0.08836" per rising edge.
// Calibrate barrel travel using short JOG steps, MARK START and SET 120.
constexpr unsigned long JOG_DURATION_MS = 200;
constexpr uint8_t JOG_PWM = 80;
constexpr unsigned long ENCODER_STALL_TIMEOUT_MS = 1500;
constexpr uint8_t MAX_ROTATION_PWM = 255;
constexpr size_t MAX_LINE = 192;

enum TipperState { IDLE, ROTATING, HOMING, JOGGING, FAULT };
TipperState state = IDLE;
bool communicationFault = false;
bool locked = true;
bool decouplerOff = true;
bool lockMotionActive = false, lockTarget = true;
unsigned long lockDeadline = 0;
int rotationDirection = 0;
uint8_t rotationPwm = 0;
volatile uint32_t encoderTicks = 0;
volatile int32_t positionTicks = 0;
volatile int8_t encoderDirection = 0;
bool startMarked = false;
uint32_t calibrated120Ticks = 0;
int32_t targetPosition = 0;
unsigned long lastControlMs = 0;
unsigned long rotationDeadline = 0;
unsigned long decouplerOffDeadline = 0;
uint32_t previousEncoderTicks = 0;
unsigned long previousEncoderMs = 0;
String responseTransaction;
String lastTransaction;
char serialBuffer[MAX_LINE];
size_t serialLength = 0;
bool serialOverflow = false;

bool configured(int pin) { return pin >= 0; }
bool allPinsConfigured() {
  return configured(TIPPER_MOTOR_IN1) && configured(TIPPER_MOTOR_IN2) &&
         configured(TIPPER_LOCK_IN3) && configured(TIPPER_LOCK_IN4) &&
         configured(TIPPER_DECOUPLER_OUTPUT) &&
         configured(TIPPER_HALL_BACK) && configured(TIPPER_HALL_FRONT) &&
         configured(TIPPER_HALL_CLEAR) && configured(TIPPER_ENCODER);
}

void encoderISR() { ++encoderTicks; positionTicks += encoderDirection; }

void motorOff() {
  if (configured(TIPPER_MOTOR_IN1)) digitalWrite(TIPPER_MOTOR_IN1, LOW);
  if (configured(TIPPER_MOTOR_IN2)) digitalWrite(TIPPER_MOTOR_IN2, LOW);
  rotationDirection = 0;
  rotationPwm = 0;
  encoderDirection = 0;
}

void gripperMotorOff() {
  if (configured(TIPPER_LOCK_IN3)) digitalWrite(TIPPER_LOCK_IN3, LOW);
  if (configured(TIPPER_LOCK_IN4)) digitalWrite(TIPPER_LOCK_IN4, LOW);
  lockMotionActive = false;
}

void setMotor(int direction, uint8_t pwm) {
  if (!allPinsConfigured()) { motorOff(); return; }
  // The installed lock has a timed actuator, not a position sensor.
  if (communicationFault || locked || lockMotionActive) { motorOff(); return; }
  uint8_t bounded = min(pwm, MAX_ROTATION_PWM);
  digitalWrite(TIPPER_MOTOR_IN1, direction > 0 ? HIGH : LOW);
  digitalWrite(TIPPER_MOTOR_IN2, direction < 0 ? HIGH : LOW);
  rotationDirection = direction;
  encoderDirection = direction > 0 ? 1 : -1;
  rotationPwm = bounded;
  analogWrite(TIPPER_MOTOR_IN1, direction > 0 ? bounded : 0);
  analogWrite(TIPPER_MOTOR_IN2, direction < 0 ? bounded : 0);
}

void setLockState(bool engaged) {
  locked = engaged;
  gripperMotorOff();
  if (engaged) motorOff();
}

bool startLockMotion(bool engage) {
  if (communicationFault || state == ROTATING || state == HOMING || state == JOGGING ||
      !configured(TIPPER_LOCK_IN3) || !configured(TIPPER_LOCK_IN4)) return false;
  lockTarget = engage;
  // Keep the interlock engaged throughout the 800 ms pulse, including while
  // opening; rotation may begin only after the unlock pulse completes.
  locked = true;
  lockMotionActive = true;
  lockDeadline = millis() + LOCK_PULSE_MS;
  // Forward is unlock; reverse is lock.
  digitalWrite(TIPPER_LOCK_IN3, engage ? LOW : HIGH);
  digitalWrite(TIPPER_LOCK_IN4, engage ? HIGH : LOW);
  return true;
}

void setDecouplerOff() {
  decouplerOff = true;
  decouplerOffDeadline = 0;
  if (configured(TIPPER_DECOUPLER_OUTPUT))
    digitalWrite(TIPPER_DECOUPLER_OUTPUT, TIPPER_DECOUPLER_ACTIVE_HIGH ? LOW : HIGH);
}

bool pulseDecoupler() {
  if (communicationFault || state != IDLE || rotationDirection != 0 || lockMotionActive ||
      !configured(TIPPER_DECOUPLER_OUTPUT)) return false;
  digitalWrite(TIPPER_DECOUPLER_OUTPUT, TIPPER_DECOUPLER_ACTIVE_HIGH ? HIGH : LOW);
  decouplerOff = false;
  decouplerOffDeadline = millis() + DECOUPLER_PULSE_MS;
  return true;
}

bool trainPositionConfirmed() {
  return configured(TIPPER_HALL_FRONT) && configured(TIPPER_HALL_BACK) &&
         configured(TIPPER_HALL_CLEAR) &&
         digitalRead(TIPPER_HALL_FRONT) == LOW &&
         digitalRead(TIPPER_HALL_BACK) == LOW &&
         digitalRead(TIPPER_HALL_CLEAR) == LOW;
}

void stopAll() {
  motorOff(); gripperMotorOff(); setDecouplerOff();
  state = IDLE; communicationFault = false;
}

bool startJog(int direction) {
  if (communicationFault || state != IDLE || locked || lockMotionActive ||
      !decouplerOff || !allPinsConfigured()) return false;
  state = JOGGING;
  previousEncoderTicks = encoderTicks;
  previousEncoderMs = millis();
  rotationDeadline = millis() + JOG_DURATION_MS;
  setMotor(direction, JOG_PWM);
  return rotationDirection != 0;
}

bool startCountedMove(int direction, int32_t target) {
  if (communicationFault || state != IDLE || locked || lockMotionActive ||
      !decouplerOff || !allPinsConfigured() || !startMarked ||
      calibrated120Ticks == 0) return false;
  targetPosition = target;
  state = target == 0 ? HOMING : ROTATING;
  previousEncoderTicks = encoderTicks;
  previousEncoderMs = millis();
  rotationDeadline = millis() + ROTATION_TIMEOUT_MS;
  setMotor(direction, MAX_ROTATION_PWM);
  return rotationDirection != 0;
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
    case HOMING: return "HOMING"; case JOGGING: return "JOGGING";
    case FAULT: return "FAULT"; default: return "IDLE";
  }
}

void reportStatus() {
  Serial.print("{\"controller\":\"tipper\",\"state\":\""); Serial.print(stateName());
  Serial.print("\",\"transaction\":\""); Serial.print(responseTransaction);
  Serial.print("\",\"estop\":"); Serial.print("false");
  Serial.print(",\"communication_fault\":"); Serial.print(communicationFault ? "true" : "false");
  Serial.print(",\"motor\":"); Serial.print(rotationDirection != 0 ? "true" : "false");
  Serial.print(",\"locked\":"); Serial.print(locked ? "true" : "false");
  Serial.print(",\"decoupler\":"); Serial.print(decouplerOff ? "false" : "true");
  Serial.print(",\"pin_map_verified\":"); Serial.print(allPinsConfigured() ? "true" : "false");
  Serial.print(",\"rotation_calibrated\":"); Serial.print(calibrated120Ticks > 0 ? "true" : "false");
  Serial.print(",\"start_marked\":"); Serial.print(startMarked ? "true" : "false");
  Serial.print(",\"position_ticks\":"); Serial.print(positionTicks);
  Serial.print(",\"calibrated_120_ticks\":"); Serial.print(calibrated120Ticks);
  Serial.print(",\"encoder_ticks\":"); Serial.print(encoderTicks);
  Serial.println("}");
  responseTransaction = "";
}

void handleCommand(String line) {
  line.trim();
  if (line == "ESTOP") { stopAll(); Serial.println("OK ESTOP"); return; }
  if (line.startsWith("{")) {
    if (!jsonComplete(line)) { Serial.println("{\"ok\":false,\"error\":\"malformed_json\"}"); return; }
    responseTransaction = jsonField(line, "transaction");
    const String command = jsonField(line, "command");
    if (!validTransaction(responseTransaction)) {
      Serial.println("{\"ok\":false,\"error\":\"transaction_required\"}"); return;
    }
    if (command != "STATUS" && responseTransaction == lastTransaction) {
      Serial.println("{\"ok\":false,\"error\":\"duplicate_transaction\"}"); return;
    }
    line = command;
  }
  lastControlMs = millis();
  if (line == "STATUS") { reportStatus(); return; } // read only
  // Existing upstream ESTOP and REARM commands remain compatible but local
  // STOP is not latched. STOP is the explicit operator recovery step.
  if (line == "STOP" || line == "REARM" || line == "ESTOP") {
    stopAll();
    lastTransaction = responseTransaction;
    if (line == "REARM") reportStatus();
    else Serial.println(line == "ESTOP" ? "OK ESTOP" : "OK STOP");
    return;
  }
  if (communicationFault || state == FAULT) {
    Serial.println("ERR FAULT use_STOP"); return;
  }
  if (line == "LOCK") {
    motorOff();
    if (!startLockMotion(true)) { Serial.println("ERR LOCK interlock"); return; }
    state = IDLE; Serial.println("OK LOCK"); return;
  }
  if (line == "UNLOCK") {
    if (!startLockMotion(false)) { Serial.println("ERR UNLOCK interlock"); return; }
    state = IDLE; Serial.println("OK UNLOCK"); return;
  }
  if (line == "DECOUPLER OFF") {
    setDecouplerOff(); Serial.println("OK DECOUPLER OFF"); return;
  }
  if (line == "DECOUPLER ON") {
    if (!pulseDecoupler()) { Serial.println("ERR DECOUPLER interlock"); return; }
    Serial.println("OK DECOUPLER ON"); return;
  }
  if (line == "JOG CW" || line == "JOG CCW") {
    if (!startJog(line == "JOG CW" ? 1 : -1)) {
      Serial.println("ERR JOG interlock"); return;
    }
    Serial.println("OK JOG"); return;
  }
  if (line == "MARK START") {
    // Visually align the tipper to the starting rail before marking.
    if (state != IDLE || rotationDirection || lockMotionActive) {
      Serial.println("ERR MARK START moving"); return;
    }
    noInterrupts(); positionTicks = 0; interrupts();
    startMarked = true;
    calibrated120Ticks = 0;
    Serial.println("OK MARK START"); return;
  }
  if (line == "SET 120") {
    // Operator visually verifies the 120-degree dump endpoint.
    const int32_t current = positionTicks;
    if (!startMarked || state != IDLE || rotationDirection || lockMotionActive ||
        current == 0) { Serial.println("ERR SET 120 interlock"); return; }
    calibrated120Ticks = uint32_t(current < 0 ? -current : current);
    Serial.println("OK SET 120"); return;
  }
  if (line == "ROTATE CW" || line == "ROTATE CCW") {
    if (!trainPositionConfirmed() || !startMarked || !calibrated120Ticks ||
        positionTicks != 0) { Serial.println("ERR ROTATE positioning_or_calibration"); return; }
    const int direction = line == "ROTATE CW" ? 1 : -1;
    if (!startCountedMove(direction, direction * int32_t(calibrated120Ticks))) {
      Serial.println("ERR ROTATE interlock"); return;
    }
    Serial.println("OK ROTATE"); return;
  }
  if (line == "HOME") {
    // Encoder-counted return to operator-marked start; visually check alignment.
    const int32_t current = positionTicks;
    if (!startMarked || !calibrated120Ticks || current == 0) {
      Serial.println("ERR HOME no_marked_start"); return;
    }
    if (!startCountedMove(current > 0 ? -1 : 1, 0)) {
      Serial.println("ERR HOME interlock"); return;
    }
    Serial.println("OK HOME"); return;
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
  if (configured(TIPPER_LOCK_IN3)) pinMode(TIPPER_LOCK_IN3, OUTPUT);
  if (configured(TIPPER_LOCK_IN4)) pinMode(TIPPER_LOCK_IN4, OUTPUT);
  // Inactive HIGH for the active-low relay; avoid startup LOW pulse.
  if (configured(TIPPER_DECOUPLER_OUTPUT)) {
    digitalWrite(TIPPER_DECOUPLER_OUTPUT, HIGH);
    pinMode(TIPPER_DECOUPLER_OUTPUT, OUTPUT);
  }
  if (configured(TIPPER_HALL_BACK)) pinMode(TIPPER_HALL_BACK, INPUT_PULLUP);
  if (configured(TIPPER_HALL_FRONT)) pinMode(TIPPER_HALL_FRONT, INPUT_PULLUP);
  if (configured(TIPPER_HALL_CLEAR)) pinMode(TIPPER_HALL_CLEAR, INPUT_PULLUP);
  if (configured(TIPPER_ENCODER)) { pinMode(TIPPER_ENCODER, INPUT_PULLUP); attachInterrupt(digitalPinToInterrupt(TIPPER_ENCODER), encoderISR, RISING); }
  Serial.begin(115200); motorOff(); setLockState(true); setDecouplerOff();
  lastControlMs = 0;
}

void loop() {
  handleSerial();
  const unsigned long now = millis();
  if (lockMotionActive && now >= lockDeadline) {
    gripperMotorOff();
    locked = lockTarget;
  }
  // A lost serial heartbeat stops operating outputs; no latched E-stop.
  if (lastControlMs == 0 || now - lastControlMs > WATCHDOG_MS) {
    if (rotationDirection != 0 || lockMotionActive || !decouplerOff) {
      motorOff(); gripperMotorOff(); setDecouplerOff();
      communicationFault = true; state = FAULT;
    }
  }
  if (!decouplerOff && now >= decouplerOffDeadline) setDecouplerOff();
  if (state == JOGGING && now >= rotationDeadline) {
    motorOff(); state = IDLE;
  }
  if (state == ROTATING || state == HOMING) {
    const int32_t position = positionTicks;
    const bool reached = rotationDirection > 0
      ? position >= targetPosition : position <= targetPosition;
    if (reached) {
      motorOff(); state = IDLE;
    } else if (encoderTicks != previousEncoderTicks) {
      previousEncoderTicks = encoderTicks;
      previousEncoderMs = now;
    } else if (now - previousEncoderMs >= ENCODER_STALL_TIMEOUT_MS ||
               now >= rotationDeadline) {
      motorOff(); communicationFault = true; state = FAULT;
    }
  }
}
