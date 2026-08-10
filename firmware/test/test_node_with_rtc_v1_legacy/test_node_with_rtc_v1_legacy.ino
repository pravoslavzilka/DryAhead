/*
 * LEGACY REFERENCE - superseded by ../../nodes/node_with_rtc/node_with_rtc.ino
 *
 * NOT compatible with the current hub protocol: this sketch calibrates
 * moisture to a percentage on-device and sends a one-way message
 * (id,percent,raw,temp,epoch) with no listen window, so it won't talk to
 * ../../hub/hub.ino. Its counterpart is ../test_hub_v1_legacy/. Kept for
 * comparison against the current RAW-only, backend-calibrated approach.
 *
 * NODE 1 - DEEP SLEEP + LoRa transmission (battery-optimized)
 * Board: LaskaKit ESP32-DEVKit
 *
 * Cycle: wake -> IO2 HIGH (power peripherals) -> read moisture + RTC time/temp
 *        -> transmit over LoRa 433MHz -> IO2 LOW + I2C lines LOW -> deep sleep (~12uA)
 *
 * Incorporates all discovered fixes:
 *   - GPIO2 HIGH powers the 3.3V peripheral rail
 *   - SDA/SCL/SQW driven LOW before sleep (stops RTC back-powering via pull-ups)
 *   - Timer-based wake (reliable, low-power)
 *   - LoRa put to sleep before power-down
 *   - Minimal awake time
 *
 * Wiring:
 *   LoRa Ra-02: SCK=18, MISO=19, MOSI=23, NSS=5, RST=27, DIO0=26, 3.3V(IO2 rail), GND
 *   Moisture:   AOUT=GPIO34, 3.3V(IO2 rail), GND
 *   DS3231:     SDA=21, SCL=22, SQW=33, 3.3V(IO2 rail), GND  (+ coin cell installed)
 *
 * Libraries: LoRa (Sandeep Mistry), RTClib (Adafruit)
 */

#include <SPI.h>
#include <LoRa.h>
#include <Wire.h>
#include <RTClib.h>

// ---------- Node identity & schedule ----------
#define NODE_ID         1
#define SLEEP_MINUTES   10        // deployment interval (use 1-2 for testing)

// ---------- Debug ----------
#define DEBUG_SERIAL    1         // 1 = print to serial (testing); 0 = silent (saves a bit of awake time)

// ---------- Pins ----------
#define PERIPH_POWER  2
#define LORA_SS    5
#define LORA_RST   27
#define LORA_DIO0  26
#define MOISTURE_PIN  34
#define I2C_SDA   21
#define I2C_SCL   22
#define RTC_SQW   33

// ---------- Moisture calibration (REPLACE with your measured values) ----------
const int DRY_VALUE = 3200;
const int WET_VALUE = 1400;

RTC_DS3231 rtc;

#if DEBUG_SERIAL
  #define DBG(x)    Serial.print(x)
  #define DBGLN(x)  Serial.println(x)
#else
  #define DBG(x)
  #define DBGLN(x)
#endif

int readMoistureRaw() {
  long sum = 0;
  for (int i = 0; i < 8; i++) { sum += analogRead(MOISTURE_PIN); delay(3); }
  return sum / 8;
}

void goToSleep() {
  // 1. Put LoRa to sleep (clean shutdown before cutting power)
  LoRa.sleep();

  // 2. Cut the peripheral 3.3V rail
  digitalWrite(PERIPH_POWER, LOW);

  // 3. Drive I2C + SQW lines LOW so they don't back-power the RTC
  //    through its pull-up resistors (this was the 82uA drain fix!)
  pinMode(I2C_SDA, OUTPUT); digitalWrite(I2C_SDA, LOW);
  pinMode(I2C_SCL, OUTPUT); digitalWrite(I2C_SCL, LOW);
  pinMode(RTC_SQW, OUTPUT); digitalWrite(RTC_SQW, LOW);

  // 4. Set the wake timer
  uint64_t sleep_us = (uint64_t)SLEEP_MINUTES * 60ULL * 1000000ULL;
  esp_sleep_enable_timer_wakeup(sleep_us);

  DBG("[SLEEP] Deep sleep for ");
  DBG(SLEEP_MINUTES);
  DBGLN(" min...");
#if DEBUG_SERIAL
  Serial.flush();
#endif

  esp_deep_sleep_start();   // chip resets on wake; setup() runs again
}

void setup() {
  unsigned long wakeStart = millis();   // measure awake time

  // 1. Power the peripheral rail FIRST
  pinMode(PERIPH_POWER, OUTPUT);
  digitalWrite(PERIPH_POWER, HIGH);
  delay(50);    // brief settle (kept short to minimize awake time)

#if DEBUG_SERIAL
  Serial.begin(115200);
  delay(300);   // shorter than 1000 to save awake time; enough to see output
  DBGLN("");
  DBG("=== NODE "); DBG(NODE_ID); DBGLN(" wake ===");
#endif

  analogReadResolution(12);

  // 2. RTC (I2C) - re-init each wake since pins were driven low during sleep
  pinMode(I2C_SDA, INPUT);   // release the lines we drove low
  pinMode(I2C_SCL, INPUT);
  Wire.begin(I2C_SDA, I2C_SCL);
  bool rtcOK = rtc.begin();
  if (rtcOK && rtc.lostPower()) {
    DBGLN("[RTC] Lost power - setting to compile time.");
    // First run only: comment out & re-flash after first successful set.
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  }

  // 3. Read sensors
  int raw = readMoistureRaw();
  int percent = constrain(map(raw, DRY_VALUE, WET_VALUE, 0, 100), 0, 100);

  uint32_t epoch = 0;
  float temp = 0.0;
  if (rtcOK) {
    DateTime now = rtc.now();
    epoch = now.unixtime();
    temp  = rtc.getTemperature();
  }

  // 4. Build message: id,moisture,raw,temp,epoch
  String msg = String(NODE_ID) + "," + String(percent) + "," +
               String(raw) + "," + String(temp, 2) + "," + String(epoch);

  // 5. Initialize LoRa and transmit
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (LoRa.begin(433E6)) {
    LoRa.beginPacket();
    LoRa.print(msg);
    LoRa.endPacket();      // blocks until sent
    DBG("[TX] Sent: "); DBGLN(msg);
  } else {
    DBGLN("[LoRa] init failed - skipping TX this cycle.");
  }

  // 6. Report awake time (this is your battery-cost metric)
  DBG("[TIMING] Awake: "); DBG(millis() - wakeStart); DBGLN(" ms");

  // 7. Sleep
  goToSleep();
}

void loop() {
  // never reached - all work is in setup(), then deep sleep
}