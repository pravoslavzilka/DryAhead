/*
 * ============================================================
 *  DROUGHT SENSOR NODE - NO EXTERNAL RTC
 *  Board: LaskaKit ESP32-DEVKit
 * ============================================================
 *
 *  Sibling sketch: ../node_with_rtc/node_with_rtc.ino (same role, has
 *  a DS3231 fitted for accurate onboard timekeeping instead).
 *  Counterpart hub: ../../hub/hub.ino
 *
 *  No DS3231. Timekeeping uses the ESP32's internal RTC:
 *   - The chip wakes itself on its internal timer through deep sleep
 *   - An epoch counter lives in RTC memory (survives deep sleep) and
 *     is advanced by the sleep duration + awake time on every cycle
 *   - The hub corrects that counter with TIME:<epoch> in the listen
 *     window, which also cancels accumulated drift
 *
 *  ACCURACY NOTE: the internal RTC uses an RC oscillator, so it drifts
 *  roughly 1-3% (about 1-2 min per hour). The node therefore listens
 *  more often than the DS3231 version, and re-aligns to the slot grid
 *  on every wake. Slots stay usable as long as TIME syncs keep landing.
 *
 *  Slot schedule (same as before):
 *     NODE_ID 1 -> minute  4   (4, 24, 44 past the hour)
 *     NODE_ID 2 -> minute  8
 *     NODE_ID 3 -> minute 12
 *     NODE_ID 4 -> minute 16
 *     NODE_ID 5 -> minute 20
 *
 *  STARTING TIME is taken from the sketch itself: on a fresh flash or a
 *  power-on the node sets its clock to this sketch's COMPILE time (plus a
 *  small upload-lag offset), or to SET_EPOCH if you specify one. It also
 *  saves the clock to flash each cycle, so a brief power loss recovers a
 *  sensible time rather than jumping back to compile time. The hub's
 *  TIME:<epoch> reply then keeps it accurate.
 *
 *  Message: node_id,raw,temperature,epoch,L:<0|1>
 *  Backlog: BACKLOG:rec1|rec2|...
 *
 *  Wiring (all peripherals on the IO2-switched 3.3V rail):
 *     LoRa Ra-02: SCK=18 MISO=19 MOSI=23 NSS=5 RST=27 DIO0=26 3.3V GND
 *     Moisture:   AOUT=GPIO34, 3.3V, GND
 *     (no RTC module, no I2C, no coin cell)
 *
 *  Libraries: LoRa (Sandeep Mistry)
 * ============================================================
 */

#include <SPI.h>
#include <LoRa.h>
#include <LittleFS.h>
#include <time.h>

// ==================== CONFIG ====================
#define NODE_ID          2     // <-- unique per node (1..5)
#define SLOT_SPACING     4     // minutes between node slots
#define CYCLE_MINUTES   20     // full cycle length

#define LISTEN_EVERY_N   3     // listen every Nth TX (3 * 20min = 1 h)
                               // more often than the DS3231 version because
                               // the internal clock drifts and needs syncing
#define LISTEN_MS     3000     // listen window length (ms)

// ---- Starting time ----
// The node sets its clock from the sketch itself on a fresh flash / power-on.
//   SET_EPOCH = 0  -> use the COMPILE time of this sketch (recommended)
//   SET_EPOCH > 0  -> use this exact UTC epoch instead
// UPLOAD_LAG_SECONDS compensates for the compile+upload delay (compile time
// is always a bit in the past by the time the board actually runs).
#define SET_EPOCH            0
#define UPLOAD_LAG_SECONDS   12

// Fallback only: how long to sleep if we somehow have no time at all
#define UNSYNCED_WAKE_SECONDS  120

// Optional crude drift trim, in parts per million.
// Positive = internal clock runs SLOW, so sleep less.
// Leave at 0 until you have measured the drift (see notes at the end).
#define DRIFT_PPM        0

// TEST MODE: 1 = wake every TEST_WAKE_SECONDS, ignore slots
#define TEST_MODE        0
#define TEST_WAKE_SECONDS  30
// ================================================

// ---------- Pins ----------
#define PERIPH_POWER   2
#define LORA_SS        5
#define LORA_RST      27
#define LORA_DIO0     26
#define MOISTURE_PIN  34

// ---------- Persists across deep sleep ----------
RTC_DATA_ATTR int      txCount     = 0;
RTC_DATA_ATTR uint32_t nodeEpoch   = 0;      // our best guess at current time
RTC_DATA_ATTR bool     timeSynced  = false;  // do we have a usable clock?
RTC_DATA_ATTR uint32_t lastSyncAgo = 0;      // seconds since last hub TIME sync
RTC_DATA_ATTR uint32_t bootMagic   = 0;      // detects a cold boot vs sleep wake

#define BOOT_MAGIC  0xD9017E5A

const char* LOG_FILE   = "/log.csv";
const char* CLOCK_FILE = "/clock.txt";   // last known epoch, survives power loss

// ============================================================
//  Clock helpers
// ============================================================

// Convert this sketch's compile time (__DATE__ / __TIME__) to a UTC epoch.
uint32_t compileEpoch() {
  const char* months = "JanFebMarAprMayJunJulAugSepOctNovDec";
  char monStr[4] = {0};
  int day = 1, year = 2026, hh = 0, mm = 0, ss = 0;

  sscanf(__DATE__, "%3s %d %d", monStr, &day, &year);
  sscanf(__TIME__, "%d:%d:%d", &hh, &mm, &ss);

  const char* pos = strstr(months, monStr);
  int mon = pos ? (int)((pos - months) / 3) : 0;

  struct tm t;
  memset(&t, 0, sizeof(t));
  t.tm_year  = year - 1900;
  t.tm_mon   = mon;
  t.tm_mday  = day;
  t.tm_hour  = hh;
  t.tm_min   = mm;
  t.tm_sec   = ss;
  t.tm_isdst = 0;

  time_t e = mktime(&t);          // TZ defaults to UTC on the ESP32
  return (uint32_t)e;
}

// Remember the clock in flash so a battery swap doesn't lose it entirely
void saveEpoch(uint32_t e) {
  File f = LittleFS.open(CLOCK_FILE, FILE_WRITE);
  if (f) { f.println(e); f.close(); }
}

uint32_t loadSavedEpoch() {
  File f = LittleFS.open(CLOCK_FILE, FILE_READ);
  if (!f) return 0;
  uint32_t e = (uint32_t) f.readStringUntil('\n').toInt();
  f.close();
  return e;
}

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

// Resend stored records newer than sinceEpoch, batched ~5 per packet
void sendDataSince(uint32_t sinceEpoch) {
  File f = LittleFS.open(LOG_FILE, FILE_READ);
  if (!f) { Serial.println("[BACKLOG] No log file."); return; }

  Serial.print("[BACKLOG] Sending records newer than ");
  Serial.println(sinceEpoch);

  String batch = "";
  int inBatch = 0, totalSent = 0;
  const int MAX_RECORDS = 5;
  const int MAX_BYTES   = 200;

  while (f.available()) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    int lastComma = line.lastIndexOf(',');
    if (lastComma < 0) continue;
    uint32_t ep = (uint32_t) line.substring(lastComma + 1).toInt();
    if (ep <= sinceEpoch) continue;

    if (inBatch >= MAX_RECORDS ||
        batch.length() + line.length() + 1 > MAX_BYTES) {
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
      if (e > 1700000000UL) {
        int32_t correction = (int32_t)(e - nodeEpoch);
        nodeEpoch   = e;
        timeSynced  = true;
        lastSyncAgo = 0;
        Serial.print("[CMD] time synced to "); Serial.print(e);
        Serial.print("  (drift correction "); Serial.print(correction);
        Serial.println(" s)");
      }
    }
    else if (cmd.startsWith("GETDATA:")) {
      sendDataSince((uint32_t) cmd.substring(8).toInt());
    }
    else if (cmd.startsWith("CFG:")) {
      Serial.print("[CMD] Config: "); Serial.println(cmd.substring(4));
      // ---- apply config codes here ----
    }
    else if (cmd.length() > 0) {
      Serial.print("[CMD] Unknown: "); Serial.println(cmd);
    }
    start = sep + 1;
  }
}

// ============================================================
//  Timing - all based on nodeEpoch (internal, hub-corrected)
// ============================================================
uint32_t secondsUntilNextSlot() {
  int slotMinute = (NODE_ID * SLOT_SPACING) % CYCLE_MINUTES;

  // Position within the current hour, derived from our epoch counter
  uint32_t secOfHour = nodeEpoch % 3600UL;

  long target = -1;
  for (long m = slotMinute; m < 60; m += CYCLE_MINUTES) {
    long slotSec = m * 60;
    if (slotSec > (long)secOfHour) { target = slotSec; break; }
  }

  long delta;
  if (target >= 0) delta = target - (long)secOfHour;
  else             delta = (3600 - (long)secOfHour) + (slotMinute * 60);
  if (delta <= 0)  delta = CYCLE_MINUTES * 60;

  Serial.print("[SLOT] slotMin="); Serial.print(slotMinute);
  Serial.print("  secOfHour="); Serial.print(secOfHour);
  Serial.print("  -> sleep "); Serial.print(delta); Serial.println(" s");

  return (uint32_t)delta;
}

// Apply the optional drift trim to a requested sleep duration
uint64_t applyDriftTrim(uint32_t seconds) {
  int64_t us = (int64_t)seconds * 1000000LL;
  us -= (us / 1000000LL) * DRIFT_PPM;   // ppm adjustment
  if (us < 1000000LL) us = 1000000LL;
  return (uint64_t)us;
}

// ============================================================
//  Deep sleep
// ============================================================
void goToSleep(unsigned long awakeMs) {
  // 1. Decide how long to sleep
  uint32_t sleepSec;
#if TEST_MODE
  sleepSec = TEST_WAKE_SECONDS;
#else
  sleepSec = timeSynced ? secondsUntilNextSlot() : UNSYNCED_WAKE_SECONDS;
#endif

  // 2. Advance our epoch counter by this cycle's awake time + the sleep
  //    we are about to perform. This is what keeps "time" moving.
  uint32_t awakeSec = (awakeMs + 500) / 1000;
  nodeEpoch   += awakeSec + sleepSec;
  lastSyncAgo += awakeSec + sleepSec;

  Serial.print("[SLEEP] for "); Serial.print(sleepSec);
  Serial.print(" s   (epoch now "); Serial.print(nodeEpoch);
  Serial.print(", last sync "); Serial.print(lastSyncAgo); Serial.println(" s ago)");
  Serial.flush();

  // 3. Persist the clock so a power cycle can pick up roughly where we left off
  saveEpoch(nodeEpoch);

  // 4. Shut down and sleep
  LoRa.sleep();
  digitalWrite(PERIPH_POWER, LOW);      // cut the peripheral 3.3V rail

  esp_sleep_enable_timer_wakeup(applyDriftTrim(sleepSec));
  esp_deep_sleep_start();
}

// ============================================================
//  setup() = one full work cycle
// ============================================================
void setup() {
  unsigned long t0 = millis();

  pinMode(PERIPH_POWER, OUTPUT);
  digitalWrite(PERIPH_POWER, HIGH);
  delay(50);

  Serial.begin(115200);
  delay(300);

  LittleFS.begin(true);

  // ---- Cold boot (fresh flash or power-on)? Set the clock from the sketch ----
  if (bootMagic != BOOT_MAGIC) {
    uint32_t startEpoch = (SET_EPOCH > 0)
                            ? (uint32_t)SET_EPOCH
                            : compileEpoch() + UPLOAD_LAG_SECONDS;

    // If flash holds a LATER time than the sketch's, trust that instead:
    // it means we already ran and only lost power briefly.
    uint32_t saved = loadSavedEpoch();
    if (saved > startEpoch) {
      Serial.print("[CLOCK] restoring saved epoch "); Serial.println(saved);
      startEpoch = saved;
    } else {
      Serial.print("[CLOCK] set from sketch, epoch "); Serial.println(startEpoch);
    }

    nodeEpoch   = startEpoch;
    timeSynced  = true;
    lastSyncAgo = 0;
    txCount     = 0;
    bootMagic   = BOOT_MAGIC;
  }

  txCount++;

  // Listen every LISTEN_EVERY_N-th transmission (or every one if the
  // clock somehow got lost, so the hub can re-sync us quickly).
  bool doListen = (!timeSynced) || (txCount % LISTEN_EVERY_N == 0);

  Serial.print("\n=== NODE "); Serial.print(NODE_ID);
  Serial.print(" TX #"); Serial.print(txCount);
  if (!timeSynced) Serial.print("  (UNSYNCED)");
  else if (doListen) Serial.print("  (LISTEN cycle)");
  Serial.println(" ===");

  analogReadResolution(12);

  // Read sensors (RAW only - cloud calibrates)
  int   raw  = readMoistureRaw();
  float temp = temperatureRead();   // ESP32 die temperature, see note below

  // Build & log record: node_id,raw,temp,epoch
  // epoch is 0 while unsynced, so the hub/cloud can tell it apart.
  uint32_t stamp = timeSynced ? nodeEpoch : 0;
  String record = String(NODE_ID) + "," + String(raw) + "," +
                  String(temp, 2) + "," + String(stamp);
  logLocally(record);

  // Transmit (with listening flag)
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (LoRa.begin(433E6)) {
    String msg = record + "," + (doListen ? "L:1" : "L:0");
    LoRa.beginPacket(); LoRa.print(msg); LoRa.endPacket();
    Serial.print("[TX] "); Serial.println(msg);

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

  unsigned long awakeMs = millis() - t0;
  Serial.print("[TIMING] Awake "); Serial.print(awakeMs); Serial.println(" ms");

  goToSleep(awakeMs);
}

void loop() {
  // never reached - all work is in setup(), then deep sleep
}

/*
 * ------------------------------------------------------------
 *  MEASURING DRIFT (optional, to set DRIFT_PPM)
 *
 *  1. Flash with DRIFT_PPM = 0 and TEST_MODE = 0.
 *  2. Let the node run for a few hours WITHOUT the hub answering
 *     (so no TIME syncs correct it).
 *  3. Compare the node's reported epoch against real time.
 *       drift_ppm = (node_seconds - real_seconds) / real_seconds * 1e6
 *  4. Put that number in DRIFT_PPM. Positive if the node's clock is
 *     ahead of real time.
 *
 *  In practice the hourly TIME sync makes this unnecessary unless the
 *  node goes a long time without hearing from the hub.
 * ------------------------------------------------------------
 */
