/*
 * ============================================================
 *  DROUGHT SENSOR NODE - WITH DS3231 RTC
 *  Board: LaskaKit ESP32-DEVKit
 * ============================================================
 *
 *  Sibling sketch: ../node_no_rtc/node_no_rtc.ino (same role, no RTC
 *  module fitted - times itself off the ESP32's internal clock instead).
 *  Counterpart hub: ../../hub/hub.ino
 *
 *  FEATURES
 *   - Deep sleep at ~12 uA between cycles (I2C-low fix)
 *   - Clock-aligned time slots (collision-free, via DS3231):
 *        NODE_ID 1 -> minute  4   (4, 24, 44 past the hour)
 *        NODE_ID 2 -> minute  8
 *        NODE_ID 3 -> minute 12
 *        NODE_ID 4 -> minute 16
 *        NODE_ID 5 -> minute 20
 *   - Reads RAW moisture + DS3231 temperature + timestamp
 *   - Logs every reading locally to LittleFS (survives power loss,
 *     ~year+ of capacity for the backlog / data-recovery feature)
 *   - Transmits over LoRa 433 MHz each slot
 *   - Every LISTEN_EVERY_N-th transmission (= every 2 h): sets the
 *     listening flag, transmits, then stays in RX for LISTEN_MS and
 *     handles the hub's response (commands joined by ';'):
 *        TIME:<epoch>      -> set the RTC clock
 *        GETDATA:<epoch>   -> resend stored records newer than <epoch>
 *                             (batched ~5 records per LoRa packet)
 *        CFG:<key=value>   -> apply a config / command code
 *   - RAW values only; calibration is done in the cloud app.
 *
 *  RTC TIME SETTING
 *   The clock is set to compile time ONLY when rtc.lostPower() is true
 *   (first use, or a genuinely dead/absent coin cell). With a working
 *   coin cell the time is retained across deep sleep and reflashes and
 *   is never overwritten. To force a one-time set, use FORCE_SET_TIME.
 *
 *  MESSAGE FORMAT (LoRa)
 *     node_id,raw,temperature,epoch,L:<0|1>
 *     backlog packets:  BACKLOG:rec1|rec2|rec3...
 *
 *  WIRING (all peripherals on the IO2-switched 3.3V rail)
 *     LoRa Ra-02: SCK=18 MISO=19 MOSI=23 NSS=5 RST=27 DIO0=26 3.3V GND
 *     Moisture:   AOUT=GPIO34, 3.3V, GND
 *     DS3231:     SDA=21 SCL=22 SQW=33 3.3V GND   (+ backup coin cell!)
 *
 *  LIBRARIES: LoRa (Sandeep Mistry), RTClib (Adafruit)
 * ============================================================
 */

#include <SPI.h>
#include <LoRa.h>
#include <Wire.h>
#include <RTClib.h>
#include <LittleFS.h>

// ==================== CONFIG ====================
#define NODE_ID          2     // <-- unique per node (1..5)
#define SLOT_SPACING     4     // minutes between node slots
#define CYCLE_MINUTES   20     // full cycle length

#define LISTEN_EVERY_N   6     // every Nth TX is a listen cycle (6 * 20min = 2h)
#define LISTEN_MS     3000     // listen window length (ms)

// RTC: 0 = set only if lostPower(); 1 = force one-time set to compile time
#define FORCE_SET_TIME   0

// TEST MODE: 1 = wake every TEST_WAKE_SECONDS (fast bench test, ignores slots)
//            0 = real clock-aligned slot scheduling (deployment)
#define TEST_MODE        0
#define TEST_WAKE_SECONDS  30

// Backlog batching
#define BACKLOG_MAX_RECORDS  5
#define BACKLOG_MAX_BYTES    200
// ================================================

// ---------- Pins ----------
#define PERIPH_POWER   2
#define LORA_SS        5
#define LORA_RST      27
#define LORA_DIO0     26
#define MOISTURE_PIN  34
#define I2C_SDA       21
#define I2C_SCL       22
#define RTC_SQW       33

// ---------- Persists across deep sleep ----------
RTC_DATA_ATTR int txCount = 0;

// ---------- Globals ----------
RTC_DS3231 rtc;
bool rtcOK = false;
const char* LOG_FILE = "/log.csv";

// ============================================================
//  Sensor + storage helpers
// ============================================================
int readMoistureRaw() {
  long sum = 0;
  for (int i = 0; i < 8; i++) { sum += analogRead(MOISTURE_PIN); delay(3); }
  return sum / 8;
}

void logLocally(const String &line) {
  File f = LittleFS.open(LOG_FILE, FILE_APPEND);
  if (f) { f.println(line); f.close(); }
}

// Resend stored records newer than sinceEpoch, batched several per packet
void sendDataSince(uint32_t sinceEpoch) {
  File f = LittleFS.open(LOG_FILE, FILE_READ);
  if (!f) { Serial.println("[BACKLOG] No log file."); return; }

  Serial.print("[BACKLOG] Sending records newer than ");
  Serial.println(sinceEpoch);

  String batch = "";
  int inBatch = 0, totalSent = 0;

  while (f.available()) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    int lastComma = line.lastIndexOf(',');
    if (lastComma < 0) continue;
    uint32_t ep = (uint32_t) line.substring(lastComma + 1).toInt();
    if (ep <= sinceEpoch) continue;

    if (inBatch >= BACKLOG_MAX_RECORDS ||
        batch.length() + line.length() + 1 > BACKLOG_MAX_BYTES) {
      LoRa.beginPacket(); LoRa.print("BACKLOG:"); LoRa.print(batch); LoRa.endPacket();
      delay(120);
      batch = ""; inBatch = 0;
    }
    if (batch.length() > 0) batch += "|";
    batch += line;
    inBatch++; totalSent++;
  }
  if (inBatch > 0) {
    LoRa.beginPacket(); LoRa.print("BACKLOG:"); LoRa.print(batch); LoRa.endPacket();
  }
  f.close();
  Serial.print("[BACKLOG] Sent "); Serial.print(totalSent); Serial.println(" record(s).");
}

// ============================================================
//  Hub response handling
// ============================================================
void handleResponse(String resp) {
  Serial.print("[RESP] "); Serial.println(resp);
  int start = 0;
  while (start < (int)resp.length()) {
    int sep = resp.indexOf(';', start);
    if (sep == -1) sep = resp.length();
    String cmd = resp.substring(start, sep); cmd.trim();

    if (cmd.startsWith("TIME:")) {
      uint32_t e = (uint32_t) cmd.substring(5).toInt();
      if (rtcOK && e > 1700000000UL) {
        rtc.adjust(DateTime(e));
        Serial.print("[CMD] RTC set to "); Serial.println(e);
      }
    }
    else if (cmd.startsWith("GETDATA:")) {
      sendDataSince((uint32_t) cmd.substring(8).toInt());
    }
    else if (cmd.startsWith("CFG:")) {
      Serial.print("[CMD] Config: "); Serial.println(cmd.substring(4));
      // ---- apply config codes here, e.g. parse "interval=30" ----
    }
    else if (cmd.length() > 0) {
      Serial.print("[CMD] Unknown: "); Serial.println(cmd);
    }
    start = sep + 1;
  }
}

// ============================================================
//  Timing
// ============================================================
uint64_t secondsUntilNextSlot() {
  int slotMinute = (NODE_ID * SLOT_SPACING) % CYCLE_MINUTES;

  DateTime now = rtc.now();
  long nowSec = (long)now.minute() * 60 + now.second();   // seconds into the hour

  long target = -1;
  for (long m = slotMinute; m < 60; m += CYCLE_MINUTES) {
    long slotSec = m * 60;
    if (slotSec > nowSec) { target = slotSec; break; }
  }

  long delta;
  if (target >= 0) delta = target - nowSec;
  else             delta = (3600 - nowSec) + (slotMinute * 60);
  if (delta <= 0)  delta = CYCLE_MINUTES * 60;

  Serial.print("[SLOT] slotMin="); Serial.print(slotMinute);
  Serial.print(" now="); Serial.print(now.hour()); Serial.print(":");
  Serial.print(now.minute()); Serial.print(":"); Serial.print(now.second());
  Serial.print(" -> sleep "); Serial.print(delta); Serial.println("s");

  return (uint64_t)delta;
}

// ============================================================
//  Deep sleep (with the 12 uA I2C-low fix)
// ============================================================
void goToSleep() {
  // 1. Calculate the sleep duration FIRST, while the RTC is still powered.
  //    (Reading the RTC after cutting IO2 / driving I2C low would fail and
  //     return 0:0:0 -> wrong sleep interval. This was the 240s bug.)
  uint64_t sleepSec;
#if TEST_MODE
  sleepSec = TEST_WAKE_SECONDS;
#else
  sleepSec = rtcOK ? secondsUntilNextSlot() : (uint64_t)CYCLE_MINUTES * 60;
#endif

  Serial.print("[SLEEP] for "); Serial.print((unsigned long)sleepSec); Serial.println(" s");
  Serial.flush();

  // 2. Now shut everything down for low-power sleep.
  LoRa.sleep();
  digitalWrite(PERIPH_POWER, LOW);                       // cut peripheral 3.3V rail

  // I2C-low fix (keeps ~12uA: prevents RTC back-powering via pull-ups)
  pinMode(I2C_SDA, OUTPUT); digitalWrite(I2C_SDA, LOW);
  pinMode(I2C_SCL, OUTPUT); digitalWrite(I2C_SCL, LOW);
  pinMode(RTC_SQW, OUTPUT); digitalWrite(RTC_SQW, LOW);

  // 3. Sleep until the next slot
  esp_sleep_enable_timer_wakeup(sleepSec * 1000000ULL);
  esp_deep_sleep_start();
}

// ============================================================
//  setup() = one full work cycle (runs fresh on each wake)
// ============================================================
void setup() {
  unsigned long t0 = millis();

  // 1. Power the peripheral rail FIRST
  pinMode(PERIPH_POWER, OUTPUT);
  digitalWrite(PERIPH_POWER, HIGH);
  delay(50);

  Serial.begin(115200);
  delay(300);

  // 2. Decide if this is a listen cycle
  txCount++;
  bool doListen = (txCount % LISTEN_EVERY_N == 0);

  Serial.print("\n=== NODE "); Serial.print(NODE_ID);
  Serial.print(" TX #"); Serial.print(txCount);
  if (doListen) Serial.print("  (LISTEN cycle)");
  Serial.println(" ===");

  analogReadResolution(12);

  // 3. RTC  (set only on genuine power loss -> coin cell preserves time)
  pinMode(I2C_SDA, INPUT); pinMode(I2C_SCL, INPUT);
  Wire.begin(I2C_SDA, I2C_SCL);
  rtcOK = rtc.begin();
  if (rtcOK) {
    if (FORCE_SET_TIME || rtc.lostPower()) {
      Serial.println("[RTC] Setting clock to compile time.");
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    } else {
      Serial.println("[RTC] Time retained from backup cell.");
    }
    DateTime n = rtc.now();
    Serial.printf("[RTC] Now: %04d-%02d-%02d %02d:%02d:%02d\n",
                  n.year(), n.month(), n.day(), n.hour(), n.minute(), n.second());
  } else {
    Serial.println("[RTC] WARNING: DS3231 not found! (fallback timing)");
  }

  // 4. Local storage
  LittleFS.begin(true);

  // 5. Read sensors (RAW only - cloud calibrates)
  int raw = readMoistureRaw();
  uint32_t epoch = 0; float temp = 0.0;
  if (rtcOK) { DateTime n = rtc.now(); epoch = n.unixtime(); temp = rtc.getTemperature(); }

  // 6. Build record (node_id,raw,temp,epoch) and log it locally
  String record = String(NODE_ID) + "," + String(raw) + "," +
                  String(temp, 2) + "," + String(epoch);
  logLocally(record);

  // 7. Transmit (with listening flag)
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (LoRa.begin(433E6)) {
    String msg = record + "," + (doListen ? "L:1" : "L:0");
    LoRa.beginPacket(); LoRa.print(msg); LoRa.endPacket();
    Serial.print("[TX] "); Serial.println(msg);

    // 8. Listen window (only every LISTEN_EVERY_N-th TX = every 2 h)
    if (doListen) {
      Serial.print("[LISTEN] Waiting "); Serial.print(LISTEN_MS); Serial.println(" ms...");
      LoRa.receive();
      unsigned long startT = millis();
      bool got = false;
      while (millis() - startT < LISTEN_MS) {
        if (LoRa.parsePacket()) {
          String resp = "";
          while (LoRa.available()) resp += (char)LoRa.read();
          handleResponse(resp);
          got = true; break;
        }
      }
      if (!got) Serial.println("[LISTEN] No response.");
    }
  } else {
    Serial.println("[LoRa] init failed - skipping TX.");
  }

  // 9. Awake-time metric (for battery calculations)
  Serial.print("[TIMING] Awake "); Serial.print(millis() - t0); Serial.println(" ms");

  // 10. Deep sleep until the next slot
  goToSleep();
}

void loop() {
  // never reached - all work is in setup(), then deep sleep
}