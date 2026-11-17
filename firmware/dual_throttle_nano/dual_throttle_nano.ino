/*
 * HO Dual Throttle - Arduino Nano ATmega328P (5V).
 * USB serial protocol v1; PI MUST arbitrate manual ownership and watchdog.
 * WARNING: Commands do not move locomotives unless Pi grants authority.
 * Display: ST7796U SPI 480x320; touch FT6336U I2C 0x38.
 * Logic level shifting REQUIRED: Nano 5V outputs -> 3.3V display/touch.
 * Dependencies: Adafruit GFX Library (lightweight direct draw, no framebuffer).
 */
#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <EEPROM.h>
#include <Adafruit_GFX.h>
#include <string.h>
#include <stdlib.h>

constexpr uint8_t BTN[6]={2,3,4,5,6,7}; // L-left,L-right,R-left,R-right,L-thumb,R-thumb
constexpr uint8_t TFT_RST=8, TFT_DC=9, TFT_CS=10;
constexpr uint8_t POTS[2]={A0,A1};
constexpr uint8_t TOUCH_ADDR=0x38;
constexpr uint32_t BAUD=115200, HOLD_MS=2000, IDLE_MS=5000;
constexpr uint32_t LINK_TIMEOUT_MS=1500, PING_MS=400, MOTION_MS=120, UI_MS=150;
constexpr uint8_t FIRST_TRAIN=1,LAST_TRAIN=4;
constexpr int16_t TFT_W=480,TFT_H=320;
constexpr uint16_t NAVY=0x0843, PANEL=0x10A5, BLUE=0x04DF, WHITE=0xFFFF;
constexpr uint16_t GRAY=0x9CF3, GREEN=0x07E0, AMBER=0xFD20, RED=0xF800;

class ST7796 : public Adafruit_GFX {
 public:
  ST7796():Adafruit_GFX(TFT_W,TFT_H){}
  void command(uint8_t c){digitalWrite(TFT_DC,LOW);digitalWrite(TFT_CS,LOW);SPI.transfer(c);digitalWrite(TFT_CS,HIGH);}
  void data(uint8_t d){digitalWrite(TFT_DC,HIGH);digitalWrite(TFT_CS,LOW);SPI.transfer(d);digitalWrite(TFT_CS,HIGH);}
  void area(int16_t x,int16_t y,int16_t w,int16_t h) {
    command(0x2A);data(x>>8);data(x);data((x+w-1)>>8);data(x+w-1);
    command(0x2B);data(y>>8);data(y);data((y+h-1)>>8);data(y+h-1);
    command(0x2C);
  }
  void begin() {
    pinMode(TFT_CS,OUTPUT);pinMode(TFT_DC,OUTPUT);pinMode(TFT_RST,OUTPUT);
    digitalWrite(TFT_CS,HIGH);SPI.begin();
    digitalWrite(TFT_RST,LOW);delay(20);digitalWrite(TFT_RST,HIGH);delay(130);
    command(0x01);delay(130);command(0x11);delay(130);
    command(0x3A);data(0x55); // RGB565
    command(0x36);data(0x28); // landscape; verify rotation with wired module
    command(0x21); // inversion ON (module dependent)
    command(0x29);delay(20);
    fillScreen(NAVY);
  }
  void drawPixel(int16_t x,int16_t y,uint16_t color) override {
    if(x<0||y<0||x>=TFT_W||y>=TFT_H)return;
    area(x,y,1,1);digitalWrite(TFT_DC,HIGH);digitalWrite(TFT_CS,LOW);
    SPI.transfer(color>>8);SPI.transfer(color);digitalWrite(TFT_CS,HIGH);
  }
  void fillRect(int16_t x,int16_t y,int16_t w,int16_t h,uint16_t c) override {
    if(x<0){w+=x;x=0;}if(y<0){h+=y;y=0;}
    if(x>=TFT_W||y>=TFT_H||w<=0||h<=0)return;
    if(x+w>TFT_W)w=TFT_W-x;if(y+h>TFT_H)h=TFT_H-y;
    area(x,y,w,h);digitalWrite(TFT_DC,HIGH);digitalWrite(TFT_CS,LOW);
    const uint8_t hi=c>>8,lo=c;
    for(int32_t i=(int32_t)w*h;i>0;--i){SPI.transfer(hi);SPI.transfer(lo);}
    digitalWrite(TFT_CS,HIGH);
  }
} lcd;

struct Calibration {uint16_t reverse,center,forward;};
struct Stored {uint16_t magic;Calibration c[2];uint16_t crc;};
Stored saved;
constexpr uint16_t MAGIC=0x48A3;
enum Mode:uint8_t{STANDBY,REQUESTED,ACTIVE,RELEASING};
struct Side {
  int8_t train; int8_t requestedTrain;
  Mode mode;int16_t speed;int16_t raw;
  uint32_t holdStart,idleSince,lastMotion;
  bool waitingAssignment,neutralArmed;
};
Side side[2]={{1,-1,STANDBY,0,512,0,0,0,false,false},
              {2,-1,STANDBY,0,512,0,0,0,false,false}};
struct Key {bool stable,prior;uint32_t changed,down;};
Key key[6];
uint32_t lastLink=0,lastPing=0,lastUI=0;
bool online=false, uiDirty=true;
char rx[80];uint8_t rxPos=0;
uint32_t touchLast=0;bool touchWasDown=false;

uint16_t checksum(const Stored &v){
  const uint8_t *p=(const uint8_t*)&v;uint16_t c=0xA55A;
  for(size_t i=0;i<sizeof(Stored)-2;i++)c=(uint16_t)((c<<5)|(c>>11))^p[i];
  return c;
}
void loadCal(){
  EEPROM.get(0,saved);
  bool ok=saved.magic==MAGIC&&saved.crc==checksum(saved);
  for(uint8_t s=0;s<2&&ok;s++)
    ok=saved.c[s].reverse+30<saved.c[s].center &&
       saved.c[s].center+30<saved.c[s].forward && saved.c[s].forward<=1023;
  if(!ok){
    saved.magic=MAGIC;
    for(uint8_t s=0;s<2;s++)saved.c[s]={0,512,1023};
    saved.crc=checksum(saved);
  }
}
void saveCal(){saved.crc=checksum(saved);EEPROM.put(0,saved);}
char name(uint8_t s){return s?'R':'L';}
void sendSimple(const __FlashStringHelper* kind,uint8_t s){
  Serial.print(kind);Serial.print(' ');Serial.print(name(s));Serial.print(' ');Serial.println(side[s].train);
}
void sendMotion(uint8_t s,int16_t speed){
  if(!online||side[s].mode!=ACTIVE)return;
  Serial.print(F("MOTION "));Serial.print(name(s));Serial.print(' ');
  Serial.print(side[s].train);Serial.print(' ');Serial.println(speed);
}
void zeroAndRelease(uint8_t s){
  if(side[s].mode==ACTIVE)sendMotion(s,0);
  if(side[s].mode==ACTIVE||side[s].mode==REQUESTED)
    sendSimple(F("RELEASE"),s);
  side[s].mode=RELEASING;side[s].speed=0;uiDirty=true;
}
bool neutral(uint8_t s){
  uint16_t center=saved.c[s].center;
  return abs(side[s].raw-(int16_t)center)<=16; // ~1.6% full ADC, calibrated
}
int16_t speedFor(uint8_t s){
  Calibration &c=saved.c[s];
  int32_t v=side[s].raw;
  if(abs((int16_t)v-(int16_t)c.center)<=16)return 0;
  if(v<c.center) return -(int16_t)constrain((c.center-v)*100L/max(1,(int)c.center-(int)c.reverse),0,100);
  return (int16_t)constrain((v-c.center)*100L/max(1,(int)c.forward-(int)c.center),0,100);
}
bool reserved(uint8_t s,int train){return side[1-s].train==train ||
  (side[1-s].waitingAssignment&&side[1-s].requestedTrain==train);}
void selectTrain(uint8_t s,int dir){
  if(!online||side[s].mode!=STANDBY||!neutral(s)||side[s].waitingAssignment)return;
  int candidate=side[s].train;
  for(uint8_t i=0;i<LAST_TRAIN;i++){
    candidate+=dir;
    if(candidate>LAST_TRAIN)candidate=FIRST_TRAIN;
    if(candidate<FIRST_TRAIN)candidate=LAST_TRAIN;
    if(!reserved(s,candidate))break;
  }
  if(reserved(s,candidate)||candidate==side[s].train)return;
  side[s].requestedTrain=candidate;side[s].waitingAssignment=true;
  Serial.print(F("SELECT "));Serial.print(name(s));Serial.print(' ');Serial.println(candidate);
  uiDirty=true;
}
void turnout(uint8_t s,bool left){
  if(!online||side[s].mode!=ACTIVE)return;
  Serial.print(F("TURNOUT "));Serial.print(name(s));Serial.print(' ');
  Serial.print(side[s].train);Serial.println(left?F(" LEFT"):F(" RIGHT"));
  side[s].idleSince=0;
}
void onPress(uint8_t n){
  if(n<4){turnout(n<2,n%2==0);return;}
  uint8_t s=n-4;
  key[n].down=millis();
  side[s].holdStart=millis();
}
void onRelease(uint8_t n){
  if(n>=4)side[n-4].holdStart=0;
}
void buttons(){
  uint32_t now=millis();
  for(uint8_t i=0;i<6;i++){
    bool v=digitalRead(BTN[i])==LOW;
    if(v!=key[i].prior){key[i].prior=v;key[i].changed=now;}
    if(v!=key[i].stable&&now-key[i].changed>=30){
      key[i].stable=v;if(v)onPress(i);else onRelease(i);
    }
  }
}
void failLink(){
  online=false;
  for(uint8_t s=0;s<2;s++){
    side[s].mode=STANDBY;side[s].waitingAssignment=false;
    side[s].holdStart=0;side[s].idleSince=0;side[s].neutralArmed=false;
    side[s].speed=0;
  }
  uiDirty=true;
}
void handle(char *line){
  // Parse bounded, line-oriented replies. Pi must validate all commands.
  char *op=strtok(line," ");
  if(!op)return;
  if(!strcmp(op,"READY")||!strcmp(op,"PONG")){
    lastLink=millis();online=true;uiDirty=true;return;
  }
  if(!online)return;
  char *p=strtok(nullptr," ");
  if(!p||(p[0]!='L'&&p[0]!='R')||p[1])return;
  uint8_t s=p[0]=='R';
  char *n=strtok(nullptr," ");
  if(!n)return;
  int train=atoi(n);
  if(train<FIRST_TRAIN||train>LAST_TRAIN)return;
  if(!strcmp(op,"ASSIGN")){
    if(side[s].waitingAssignment&&side[s].requestedTrain==train &&
       !reserved(s,train)&&side[s].mode==STANDBY&&neutral(s)){
      side[s].train=train;
    }
    side[s].waitingAssignment=false;uiDirty=true;return;
  }
  if(train!=side[s].train)return;
  if(!strcmp(op,"GRANT")){
    if(side[s].mode==REQUESTED && neutral(s) && !reserved(s,train)){
      side[s].mode=ACTIVE;side[s].lastMotion=0;side[s].idleSince=millis();
    }
  }else if(!strcmp(op,"RELEASED")||!strcmp(op,"DENY")){
    side[s].mode=STANDBY;side[s].holdStart=0;side[s].neutralArmed=false;
  }
  uiDirty=true;
}
void serialIn(){
  while(Serial.available()){
    char c=(char)Serial.read();
    if(c=='\n'){
      rx[rxPos]=0;if(rxPos)handle(rx);rxPos=0;
    }else if(c!='\r'){
      if(rxPos<sizeof(rx)-1)rx[rxPos++]=c;
      else rxPos=0;
    }
  }
}
void updateThrottle(){
  uint32_t now=millis();
  for(uint8_t s=0;s<2;s++){
    // Discard first conversion after ADC mux change; pot wipers have 100nF to GND.
    analogRead(POTS[s]);int32_t sum=0;
    for(uint8_t i=0;i<4;i++)sum+=analogRead(POTS[s]);
    side[s].raw=(int16_t)(sum/4);
    int16_t cmd=speedFor(s);
    bool inNeutral=neutral(s);
    if(inNeutral)side[s].neutralArmed=true;
    if(side[s].mode==STANDBY&&online&&inNeutral&&side[s].holdStart &&
       key[s+4].stable&&now-side[s].holdStart>=HOLD_MS &&
       !side[s].waitingAssignment&&!reserved(s,side[s].train)){
      side[s].mode=REQUESTED;side[s].holdStart=0;
      sendSimple(F("ACQUIRE"),s);uiDirty=true;
    }
    if(side[s].mode==ACTIVE){
      // The physical stick must have been neutral at grant.
      if(!side[s].neutralArmed)cmd=0;
      if(cmd!=side[s].speed){side[s].speed=cmd;uiDirty=true;}
      if(cmd!=0)side[s].idleSince=0;
      else if(side[s].idleSince==0)side[s].idleSince=now;
      if(cmd==0&&side[s].idleSince&&now-side[s].idleSince>=IDLE_MS){
        zeroAndRelease(s);continue;
      }
      if(now-side[s].lastMotion>=MOTION_MS){
        sendMotion(s,cmd);side[s].lastMotion=now;
      }
    }else if(side[s].speed!=0){side[s].speed=0;uiDirty=true;}
  }
}
bool readTouch(uint16_t &x,uint16_t &y){
  Wire.beginTransmission(TOUCH_ADDR);Wire.write(0x02);
  if(Wire.endTransmission(false)!=0)return false;
  if(Wire.requestFrom(TOUCH_ADDR,(uint8_t)5)!=(uint8_t)5)return false;
  uint8_t count=Wire.read()&0x0F;
  uint8_t xh=Wire.read(),xl=Wire.read(),yh=Wire.read(),yl=Wire.read();
  if(count==0)return false;
  x=((xh&0x0F)<<8)|xl;y=((yh&0x0F)<<8)|yl;
  return x<TFT_W&&y<TFT_H;
}
void touch(){
  if(millis()-touchLast<40)return;
  touchLast=millis();
  uint16_t x,y;bool down=readTouch(x,y);
  if(down&&!touchWasDown){
    uint8_t s=x>=240;
    uint16_t localX=x%240;
    // Large selection buttons in top row only: minus 12..75, plus 165..228.
    if(y>=34&&y<101){
      if(localX<80)selectTrain(s,-1);
      else if(localX>=160)selectTrain(s,1);
    }
  }
  touchWasDown=down;
}
void centerText(int x,int y,const __FlashStringHelper* t,uint8_t size,uint16_t color){
  lcd.setTextSize(size);lcd.setTextColor(color,PANEL);
  // Fixed-width subset: caller uses known labels, center approx.
  lcd.setCursor(x,y);lcd.print(t);
}
void drawSide(uint8_t s){
  int x=s*240;
  lcd.fillRect(x+3,3,234,314,PANEL);
  lcd.drawRect(x+3,3,234,314,BLUE);
  lcd.fillRoundRect(x+12,34,64,64,8,NAVY);
  lcd.fillRoundRect(x+164,34,64,64,8,NAVY);
  lcd.setTextSize(4);lcd.setTextColor(WHITE,NAVY);
  lcd.setCursor(x+32,49);lcd.print('-');
  lcd.setCursor(x+184,49);lcd.print('+');
  lcd.setTextColor(WHITE,PANEL);lcd.setTextSize(2);
  lcd.setCursor(x+82,40);lcd.print(F("TRAIN"));
  lcd.setTextSize(4);lcd.setCursor(x+109,64);lcd.print(side[s].train);
  lcd.setTextSize(5);lcd.setCursor(x+52,115);
  int16_t v=side[s].speed;
  lcd.print(abs(v));lcd.print('%');
  lcd.setTextSize(2);lcd.setCursor(x+75,166);
  lcd.print(v<0?F("REV"):v>0?F("FWD"):F("STOP"));
  lcd.fillRect(x+16,196,208,11,NAVY);
  lcd.fillRect(x+120,196,(int)(104L*abs(v)/100),11,v<0?RED:GREEN);
  lcd.drawFastVLine(x+120,192,20,WHITE);
  lcd.setTextColor(GRAY,PANEL);lcd.setTextSize(1);
  lcd.setCursor(x+15,218);lcd.print(F("MODE"));
  lcd.setCursor(x+15,238);lcd.print(F("LINK"));
  lcd.setCursor(x+15,258);lcd.print(F("ENABLE"));
  lcd.setTextColor(WHITE,PANEL);
  lcd.setCursor(x+110,218);lcd.print(side[s].mode==ACTIVE?F("MANUAL"):F("STANDBY"));
  lcd.setCursor(x+110,238);lcd.print(online?F("ONLINE"):F("OFFLINE"));
  lcd.setCursor(x+110,258);
  switch(side[s].mode){
    case ACTIVE:lcd.print(F("ON"));break;
    case REQUESTED:lcd.print(F("WAITING"));break;
    case RELEASING:lcd.print(F("RELEASE"));break;
    default:lcd.print(F("STANDBY"));
  }
  lcd.setCursor(x+18,289);
  if(side[s].waitingAssignment)lcd.print(F("SELECTING..."));
  else if(side[s].holdStart&&key[s+4].stable)lcd.print(F("HOLD 2 SEC"));
  else lcd.print(F("USB / DISPATCHER"));
}
void display(){
  if(!uiDirty&&millis()-lastUI<UI_MS)return;
  if(millis()-lastUI<UI_MS)return;
  lastUI=millis();uiDirty=false;
  drawSide(0);drawSide(1);
}
void setup(){
  for(uint8_t i=0;i<6;i++)pinMode(BTN[i],INPUT_PULLUP);
  Serial.begin(BAUD);Wire.begin();Wire.setClock(100000);
  loadCal();lcd.begin();
  Serial.println(F("HELLO NANO_DUAL_THROTTLE 1"));
  lastUI=0;uiDirty=true;
}
void loop(){
  serialIn();
  if(online&&millis()-lastLink>LINK_TIMEOUT_MS)failLink();
  if(millis()-lastPing>=PING_MS){
    Serial.println(F("PING"));lastPing=millis();
  }
  buttons();updateThrottle();touch();display();
  // Calibration command over serial is deliberately NOT available during use.
  // Calibrate on a separate bench sketch / enter EEPROM validated values.
}
