/*
 * HO Railroad dual-throttle HID, first-pass firmware.
 * Board: Arduino Nano ESP32, Arduino-ESP32 core 3.x.
 * Libraries: Arduino_GFX_Library, Adafruit ADS1X15, ArduinoJson (v7).
 *
 * SAFETY: Bench UI only. This firmware NEVER drives a locomotive or a turnout.
 * The Pi MUST validate every command and refuse motion without authority.
 * LCD silicon and touch controller are provisionally ST7796 + FT6336;
 * compare with the working laser-controller display before flashing.
 */
#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include <Arduino_GFX_Library.h>
#include <Adafruit_ADS1X15.h>
#include <ArduinoJson.h>

// Unique to THIS console firmware. Change for a second console before flashing.
#ifndef HID_MODULE_ID
#define HID_MODULE_ID 17
#endif
#ifndef HID_LCD_ST7796
#define HID_LCD_ST7796 1
#endif
#ifndef HID_TOUCH_FT6336
#define HID_TOUCH_FT6336 0  // OFF until exact HCM/laser display controller verified
#endif
#ifndef HID_TOUCH_SWAP_XY
#define HID_TOUCH_SWAP_XY 0
#endif
#ifndef HID_TOUCH_INVERT_X
#define HID_TOUCH_INVERT_X 0
#endif
#ifndef HID_TOUCH_INVERT_Y
#define HID_TOUCH_INVERT_Y 0
#endif

constexpr uint8_t BTN_A_LEFT=D7, BTN_A_RIGHT=D6, BTN_B_LEFT=D5, BTN_B_RIGHT=D4;
constexpr uint8_t LCD_CS=D10, LCD_DC=D9, LCD_RST=D8;
constexpr uint8_t LCD_SCK=D13, LCD_MOSI=D11, LCD_MISO=D12;
constexpr uint8_t SDA_PIN=A4, SCL_PIN=A5;
constexpr uint8_t ADS_ADDRESS=0x48, TOUCH_ADDRESS=0x38;
constexpr uint16_t SCREEN_W=480, SCREEN_H=320;
constexpr uint16_t POLL_MS=45, DISPLAY_MS=150, STATUS_TX_MS=500, HELLO_MS=2000;
constexpr uint16_t CONNECTION_TIMEOUT_MS=1500, REPROBE_MS=2000;
constexpr uint16_t BUTTON_DEBOUNCE_MS=35, TOUCH_DEBOUNCE_MS=180;
constexpr int16_t THROTTLE_DEADBAND=650; // ADS raw counts, provisional; measure detents
constexpr int16_t ADS_CENTER=13200;       // at 3.3 V on ADS gain-one range
constexpr int16_t ADS_FULL_SCALE=26400;
constexpr int16_t TAKEOVER_CENTER_TOLERANCE=1100;
constexpr uint16_t C_BG=0x0841,C_PANEL=0x1926,C_FG=0xffff,C_DIM=0xad55;
constexpr uint16_t C_ACCENT=0x3d9c,C_GREEN=0x36c9,C_ORANGE=0xfbc0,C_RED=0xf9a6;

Arduino_ESP32SPI lcdBus(LCD_DC, LCD_CS, LCD_SCK, LCD_MOSI, LCD_MISO);
#if HID_LCD_ST7796
Arduino_ST7796 lcd(&lcdBus, LCD_RST, 1, true);
#else
// No display driver selected: serial protocol, knobs and buttons still function.
#endif
Adafruit_ADS1115 adc;
bool adcPresent=false, lcdPresent=false, linkReady=false;
unsigned long lastRxMs=0, lastHelloMs=0, lastProbeMs=0;
unsigned long lastPollMs=0, lastDisplayMs=0, lastStatusTxMs=0, lastTouchMs=0;
uint32_t sequence=0;
char rxBuf[380]; uint16_t rxLen=0; bool rxDiscard=false;

struct Throttle {
  uint8_t assigned=1;              // UI tentative; Pi confirms authority
  bool manual=false;                // Pi-confirmed mode only
  bool pending=false;               // Pi must send STATE before controls are active
  bool pickup=false;                // require knob to pass CENTER for manual takeover
  int16_t demand=0;                 // last transmitted manual demand
  int16_t knob=0;                   // current signed physical reading
  int16_t confirmedSpeed=0;         // Pi-reported signed command
  char destination[20]="NONE";
  char nextTurnout[8]="-";
  char notice[30]="WAIT FOR PI";
  bool stopped=true;
};
Throttle throttle[2];
bool uiDirty=true;

struct Button {
  uint8_t pin;
  bool stableHigh=true, prevHigh=true;
  unsigned long changedMs=0;
};
Button buttons[4]={{BTN_A_LEFT},{BTN_A_RIGHT},{BTN_B_LEFT},{BTN_B_RIGHT}};

void transmit(const char* kind, int side=-1, int value=0, const char* direction=nullptr) {
  JsonDocument j;
  j["sof"]="HID1";
  j["module"]=HID_MODULE_ID;
  j["seq"]=++sequence;
  j["type"]=kind;
  if(side>=0) {
    j["side"]=side==0?"A":"B";
    j["train"]=throttle[side].assigned;
  }
  if(!strcmp(kind,"THROTTLE")) j["speed"]=value;
  if(!strcmp(kind,"MODE")) j["mode"]=value?"MANUAL":"AUTO";
  if(!strcmp(kind,"SELECT")) j["train"]=value;
  if(!strcmp(kind,"TURNOUT") && direction) j["path"]=direction;
  Serial.write('\x02');         // STX starts a framed JSON record
  serializeJson(j, Serial);
  Serial.write('\n');           // LF ends the record
}
void setNotice(uint8_t side,const char* message) {
  snprintf(throttle[side].notice,sizeof(throttle[side].notice),"%s",message);
  uiDirty=true;
}
void invalidateLink() {
  if(!linkReady) return;
  linkReady=false;
  for(auto &t:throttle) {
    t.manual=false;t.pending=true;t.pickup=false;t.demand=0;
    snprintf(t.notice,sizeof(t.notice),"PI OFFLINE");
  }
  uiDirty=true;
}
int16_t rawToSpeed(int16_t raw) {
  int32_t offset=(int32_t)raw-ADS_CENTER;
  if(abs(offset)<=THROTTLE_DEADBAND) return 0;
  int32_t span=offset>0?ADS_FULL_SCALE-ADS_CENTER:ADS_CENTER;
  int32_t scale=abs(offset)-THROTTLE_DEADBAND;
  int32_t range=span-THROTTLE_DEADBAND;
  int32_t value=constrain((scale*255)/max(1L,range),0L,255L);
  return offset>0 ? value : -value;
}
bool validTrain(int t){return t>=1&&t<=4;}
uint8_t cycleTrain(uint8_t side,int step) {
  int next=throttle[side].assigned;
  do {
    next=((next-1+step+4)%4)+1;
  } while(next==throttle[1-side].assigned);
  return uint8_t(next);
}
void requestTrain(uint8_t side,int step) {
  if(!linkReady || throttle[side].pending)return;
  uint8_t next=cycleTrain(side,step);
  throttle[side].pending=true;
  setNotice(side,"SELECT PENDING");
  transmit("SELECT",side,next);
}
void requestMode(uint8_t side,bool manual) {
  if(!linkReady || throttle[side].pending)return;
  throttle[side].pending=true;
  throttle[side].pickup=false;
  throttle[side].demand=0;
  setNotice(side,"MODE PENDING");
  transmit("MODE",side,manual?1:0);
}
void requestStop(uint8_t side) {
  if(!linkReady)return;
  throttle[side].demand=0;
  setNotice(side,"STOP REQUEST");
  transmit("STOP",side);
}
void onTurnoutButton(uint8_t button) {
  uint8_t side=button/2;
  if(!linkReady || !throttle[side].manual || throttle[side].pending) {
    setNotice(side,"MANUAL REQUIRED");return;
  }
  transmit("TURNOUT",side,0,(button%2==0)?"LEFT":"RIGHT");
  setNotice(side,"ROUTE REQUESTED");
}
void pollButtons() {
  unsigned long now=millis();
  for(uint8_t i=0;i<4;i++) {
    Button &b=buttons[i];
    bool high=digitalRead(b.pin)==HIGH;
    if(high!=b.prevHigh) b.changedMs=now;
    if(now-b.changedMs>=BUTTON_DEBOUNCE_MS && high!=b.stableHigh) {
      b.stableHigh=high;
      if(!high)onTurnoutButton(i);
    }
    b.prevHigh=high;
  }
}
void readThrottleKnobs() {
  if(!adcPresent)return;
  for(uint8_t side=0;side<2;side++) {
    int16_t raw=adc.readADC_SingleEnded(side);
    throttle[side].knob=rawToSpeed(raw);
    Throttle &t=throttle[side];
    if(!linkReady || !t.manual || t.pending)continue;
    if(!t.pickup) {
      if(abs(int32_t(raw)-ADS_CENTER)>TAKEOVER_CENTER_TOLERANCE) {
        if(strcmp(t.notice,"CENTER THROTTLE"))setNotice(side,"CENTER THROTTLE");
        continue;
      }
      t.pickup=true;
      t.demand=0;
      setNotice(side,"MANUAL READY");
      transmit("THROTTLE",side,0);
    }
    int16_t demanded=t.knob;
    if(demanded!=t.demand) {
      t.demand=demanded;
      transmit("THROTTLE",side,demanded);
      uiDirty=true;
    }
  }
}
void receiveRecord(const char* line) {
  JsonDocument j;
  if(deserializeJson(j,line)!=DeserializationError::Ok)return;
  if(strcmp(j["sof"] | "", "HID1")!=0)return;
  if((j["module"] | -1)!=HID_MODULE_ID)return;
  const char* type=j["type"] | "";
  if(!strcmp(type,"STATE")) {
    JsonArray panels=j["panels"].as<JsonArray>();
    if(panels.size()!=2)return;
    int id0=panels[0]["train"] | 0,id1=panels[1]["train"] | 0;
    if(!validTrain(id0)||!validTrain(id1)||id0==id1)return;
    for(int side=0;side<2;side++) {
      JsonObject p=panels[side];
      Throttle &t=throttle[side];
      bool oldManual=t.manual;
      uint8_t oldAssigned=t.assigned;
      t.assigned=p["train"].as<int>();
      t.manual=strcmp(p["mode"] | "AUTO","MANUAL")==0;
      t.confirmedSpeed=constrain(p["speed"] | 0,-255,255);
      t.stopped=t.confirmedSpeed==0;
      snprintf(t.destination,sizeof(t.destination),"%s",p["destination"] | "NONE");
      snprintf(t.nextTurnout,sizeof(t.nextTurnout),"%s",p["next_turnout"] | "-");
      snprintf(t.notice,sizeof(t.notice),"%s",p["notice"] | "READY");
      t.pending=false;
      if(oldManual!=t.manual || oldAssigned!=t.assigned) {
        t.pickup=false;t.demand=0;
      }
    }
    linkReady=true;
    lastRxMs=millis();
    uiDirty=true;
  } else if(!strcmp(type,"PONG")) {
    lastRxMs=millis();
  } else if(!strcmp(type,"REJECT")) {
    int side=strcmp(j["side"] | "A","B")==0?1:0;
    throttle[side].pending=false;
    setNotice(side,j["reason"] | "REJECTED");
    // Await fresh STATE for confirmed assignment and safe controls.
  }
}
void pollSerial() {
  while(Serial.available()) {
    char c=(char)Serial.read();
    if(c=='\x02') {rxLen=0;rxDiscard=false;continue;}
    if(c=='\n') {
      if(!rxDiscard && rxLen) {
        rxBuf[rxLen]='\0';receiveRecord(rxBuf);
      }
      rxLen=0;rxDiscard=false;
    } else if(!rxDiscard) {
      if(rxLen+1>=sizeof(rxBuf))rxDiscard=true;
      else rxBuf[rxLen++]=c;
    }
  }
}
#if HID_LCD_ST7796
void label(int x,int y,const String &s,uint16_t col,uint8_t size=2) {
  lcd.setCursor(x,y);lcd.setTextColor(col);lcd.setTextSize(size);lcd.print(s);
}
void renderPanel(int side) {
  const int x=side*240;
  Throttle &t=throttle[side];
  lcd.fillRect(x+2,25,236,293,C_PANEL);
  lcd.drawRect(x+2,25,236,293,C_DIM);
  label(x+12,32,side==0?"THROTTLE A":"THROTTLE B",C_DIM,2);
  // Header train picker: touch targets x+5..75 and x+160..235 at y+58..108
  lcd.drawRoundRect(x+9,64,55,42,5,C_ACCENT);
  lcd.drawRoundRect(x+176,64,55,42,5,C_ACCENT);
  label(x+26,74,"-",C_FG,3);
  label(x+195,74,"+",C_FG,3);
  label(x+87,75,"#"+String(t.assigned),C_FG,3);
  label(x+12,119,"SPEED",C_DIM,2);
  String speed=t.confirmedSpeed<0?"REV ":t.confirmedSpeed>0?"FWD ":"STOP ";
  speed+=String(abs(t.confirmedSpeed));
  label(x+12,143,speed,C_FG,3);
  label(x+12,178,"DEST: "+String(t.destination),C_DIM,1);
  label(x+12,195,"NEXT: "+String(t.nextTurnout),C_DIM,1);
  uint16_t autoColor=t.manual?C_DIM:C_GREEN;
  uint16_t manColor=t.manual?C_ORANGE:C_DIM;
  lcd.drawRoundRect(x+10,222,104,42,5,autoColor);
  lcd.drawRoundRect(x+126,222,104,42,5,manColor);
  label(x+27,235,"AUTO",autoColor,2);
  label(x+147,235,"MAN",manColor,2);
  label(x+12,278,String(t.notice),linkReady?C_FG:C_RED,1);
  lcd.drawRoundRect(x+174,274,55,35,5,C_RED);
  label(x+184,284,"STOP",C_RED,1);
}
void renderUi() {
  lcd.fillScreen(C_BG);
  label(12,5,"HO RAILROAD    HID #"+String(HID_MODULE_ID),C_FG,2);
  renderPanel(0);renderPanel(1);
  label(310,5,linkReady?"PI ONLINE":"PI OFFLINE",linkReady?C_GREEN:C_RED,2);
  uiDirty=false;
}
#endif
// FT6336 read is disabled until verified on the physical module.
// FT6336 registers: 0x02 number of touches; 0x03..0x06 first point X/Y.
#if HID_TOUCH_FT6336
bool readTouch(uint16_t &x,uint16_t &y) {
  Wire.beginTransmission(TOUCH_ADDRESS);
  Wire.write(0x02);
  if(Wire.endTransmission(false)!=0)return false;
  if(Wire.requestFrom(TOUCH_ADDRESS,(uint8_t)5)!=(uint8_t)5)return false;
  uint8_t n=Wire.read();
  uint8_t xh=Wire.read(),xl=Wire.read(),yh=Wire.read(),yl=Wire.read();
  if((n&0x0f)==0)return false;
  uint16_t rx=((xh&0x0f)<<8)|xl,ry=((yh&0x0f)<<8)|yl;
  if(HID_TOUCH_SWAP_XY){uint16_t tmp=rx;rx=ry;ry=tmp;}
  if(HID_TOUCH_INVERT_X)rx=SCREEN_W-1-rx;
  if(HID_TOUCH_INVERT_Y)ry=SCREEN_H-1-ry;
  if(rx>=SCREEN_W||ry>=SCREEN_H)return false;
  x=rx;y=ry;return true;
}
void pollTouch() {
  uint16_t x,y;
  if(!readTouch(x,y))return;
  unsigned long now=millis();
  if(now-lastTouchMs<TOUCH_DEBOUNCE_MS)return;
  lastTouchMs=now;
  int side=x<240?0:1, local=x%240;
  if(y>=64&&y<=108) {
    if(local<=75)requestTrain(side,-1);
    else if(local>=160)requestTrain(side,1);
  } else if(y>=222&&y<=264) {
    if(local<=116)requestMode(side,false);
    else requestMode(side,true);
  } else if(y>=274&&y<=315&&local>=172)requestStop(side);
}
#endif
void setup() {
  Serial.begin(115200);
  for(auto &b:buttons) pinMode(b.pin,INPUT_PULLUP);
  Wire.begin(SDA_PIN,SCL_PIN);
  Wire.setClock(400000);
  adcPresent=adc.begin(ADS_ADDRESS,&Wire);
  if(adcPresent)adc.setGain(GAIN_ONE); // +/-4.096V for 0..3.3V wiper
#if HID_LCD_ST7796
  lcdPresent=lcd.begin();
  if(lcdPresent)renderUi();
#endif
  throttle[1].assigned=2;
  throttle[0].pending=throttle[1].pending=true;
  transmit("HELLO");
  lastHelloMs=millis();
}
void loop() {
  unsigned long now=millis();
  pollSerial();
  pollButtons();
#if HID_TOUCH_FT6336
  pollTouch();
#endif
  if(now-lastPollMs>=POLL_MS) {lastPollMs=now;readThrottleKnobs();}
  if(now-lastProbeMs>=REPROBE_MS) {
    lastProbeMs=now;
    if(!adcPresent) {adcPresent=adc.begin(ADS_ADDRESS,&Wire);if(adcPresent)adc.setGain(GAIN_ONE);}
  }
  if(linkReady&&now-lastRxMs>CONNECTION_TIMEOUT_MS)invalidateLink();
  if(now-lastHelloMs>=HELLO_MS&&!linkReady) {
    lastHelloMs=now;transmit("HELLO");
  }
  if(linkReady&&now-lastStatusTxMs>=STATUS_TX_MS) {
    lastStatusTxMs=now;transmit("PING");
  }
#if HID_LCD_ST7796
  if(lcdPresent&&(uiDirty||now-lastDisplayMs>=DISPLAY_MS)) {
    lastDisplayMs=now;renderUi();
  }
#endif
}
