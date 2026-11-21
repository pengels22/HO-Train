/* HO Railroad receive-only 14-channel Arduino Nano ESP32 IR decoder. */
#include <Arduino.h>

constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t FRAME_WINDOW_MS = 500;
constexpr uint32_t EMPTY_REPORT_MS = 500;
constexpr uint32_t MIN_FLASH_GAP_US = 3000;
constexpr uint32_t MAX_FLASH_GAP_US = 320000;
constexpr uint8_t CHANNEL_COUNT = 14;
constexpr uint8_t SAMPLE_COUNT = 3;

struct Channel { uint8_t pin; const char *pinName; const char *stationId; };
// Physical channel order mirrors config/ir_receivers.yaml. Verify wiring at
// commissioning; this sketch never drives an output.
const Channel channels[CHANNEL_COUNT] = {
  {D2,"D2","tunnel_entrance"},{D3,"D3","yard_entrance"},
  {D4,"D4","ski_entrance"},{D5,"D5","tunnel_exit_east"},
  {D6,"D6","tunnel_exit_west"},{D7,"D7","underground_entrance"},
  {D8,"D8","tipper_entrance"},{D9,"D9","stall_1a"},
  {D10,"D10","stall_1b"},{D11,"D11","stall_2"},
  {D12,"D12","stall_3"},{A0,"A0","mine_station"},
  {A1,"A1","farm_station"},{A2,"A2","town_station"},
};

struct Decoder { bool active=false, previous=false; uint8_t flashes=0, samples[SAMPLE_COUNT]={}, sampleCount=0, lastTrain=0; uint32_t frameStart=0,lastFlash=0,lastEmpty=0; };
Decoder decoders[CHANNEL_COUNT];

void emit(uint8_t i, const char *train, bool numeric=false) {
  Serial.print(F("{\"channel\":")); Serial.print(i+1);
  Serial.print(F(",\"pin\":\"")); Serial.print(channels[i].pinName);
  Serial.print(F("\",\"station_id\":\"")); Serial.print(channels[i].stationId);
  Serial.print(F("\",\"train_id\":"));
  if (numeric) Serial.print(train); else { Serial.print('"'); Serial.print(train); Serial.print('"'); }
  Serial.println('}');
}

uint8_t majority(const Decoder &d) {
  uint8_t best=1, votesBest=0;
  for (uint8_t id=1; id<=4; ++id) { uint8_t votes=0; for (uint8_t n=0;n<SAMPLE_COUNT;++n) if(d.samples[n]==id) ++votes; if(votes>votesBest){best=id;votesBest=votes;} }
  return best;
}

void finish(uint8_t i) {
  Decoder &d=decoders[i];
  if (d.flashes>=1 && d.flashes<=4) {
    d.samples[d.sampleCount++]=d.flashes;
    if (d.sampleCount==SAMPLE_COUNT) { d.lastTrain=majority(d); d.sampleCount=0; char id[2]={char('0'+d.lastTrain),0}; emit(i,id,true); }
  }
  d.flashes=0; d.frameStart=0; d.lastFlash=0;
}

void sample(uint8_t i, uint32_t ms, uint32_t us) {
  Decoder &d=decoders[i]; bool active=digitalRead(channels[i].pin)==LOW; d.active=active;
  if (d.frameStart && ms-d.frameStart>=FRAME_WINDOW_MS) finish(i);
  if (!active) { d.previous=false; if(d.frameStart && ms-d.frameStart>=150) finish(i); return; }
  if (d.previous) return; d.previous=true; if(!d.frameStart)d.frameStart=ms;
  uint32_t gap=d.lastFlash?us-d.lastFlash:0;
  if(!d.lastFlash || (gap>=MIN_FLASH_GAP_US && gap<=MAX_FLASH_GAP_US)){++d.flashes;d.lastFlash=us;}
}

void setup() { Serial.begin(SERIAL_BAUD); for(uint8_t i=0;i<CHANNEL_COUNT;++i)pinMode(channels[i].pin,INPUT_PULLUP); Serial.println(F("{\"ready\":true,\"controller\":\"nano_esp32_ir\",\"channels\":14,\"outputs_disabled\":true}")); }
void loop() { uint32_t ms=millis(),us=micros(); for(uint8_t i=0;i<CHANNEL_COUNT;++i){sample(i,ms,us);Decoder &d=decoders[i];if(!d.active&&!d.frameStart&&ms-d.lastEmpty>=EMPTY_REPORT_MS){d.lastEmpty=ms;emit(i,"no_train");}} }
