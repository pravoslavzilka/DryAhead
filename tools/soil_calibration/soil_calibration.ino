/*
 * DryAhead - capacitive soil sensor bench calibration rig
 * ======================================================
 * BENCH TOOL ONLY. Not for the field nodes (see firmware/ for those).
 *
 * Hardware : ESP32 dev board, capacitive soil sensor (v1.2 style), signal on
 *            GPIO36 (ADC1_CH0, "VP"). Sensor VCC either on GPIO2 (like the
 *            field nodes' switched rail - see SENSOR_POWER_PIN) or directly on
 *            3V3. It stays powered for the whole session.
 * Arduino IDE: board "ESP32 Dev Module", Serial Monitor 115200 baud,
 *            line ending "Newline". Works with ESP32 Arduino core 2.x and 3.x.
 *
 * ADC setup deliberately mirrors the nodes (12-bit, 11 dB attenuation), so the
 * raw numbers you collect here are directly comparable with node data.
 *
 * COMMANDS (type in Serial Monitor, press Enter)
 *   t        pin test: is the sensor responding at all? (do this first)
 *   l        live stream (Serial Plotter friendly), any key stops
 *   s<1-3>   select which physical sensor is plugged in, e.g. "s2"
 *   w<ml>    CUMULATIVE water added since the dry start, e.g. "w75"
 *   g<grams> total weight of soil+container now (optional), e.g. "g641.3"
 *   m        MEASURE: wait for the reading to settle, then average 10 s
 *   r<n>     override repeat number (auto-increments after every "m")
 *   p        print current settings      H  print CSV header      h  help
 *
 * Each measurement prints one line starting with "CSV," - copy those lines
 * out of the Serial Monitor into a .csv file.
 *
 * PROCEDURE (summary - see notes from Claude for the reasoning)
 *   - At each moisture level measure ALL sensors, in the SAME soil, before
 *     adding the next dose of water.
 *   - After adding water: mix thoroughly, repack to the same 700 ml mark,
 *     insert the sensor to the same depth, press "m".
 *   - Measure each sensor at least twice per level (pull out, reinsert):
 *     the spread between repeats tells you your real-world precision.
 */

#include <Arduino.h>
#include <math.h>
#include <string.h>

// ================================ CONFIG ================================
static const uint8_t  SENSOR_PIN         = 36;      // GPIO36 = ADC1_CH0

// Sensor power: the field nodes feed peripherals from a rail switched by GPIO2.
//   SENSOR_POWER_PIN = 2   -> sensor VCC is wired to GPIO2 (as on the nodes):
//                             this sketch drives it HIGH and keeps it on.
//   SENSOR_POWER_PIN = -1  -> sensor VCC is wired to the 3V3 pin directly.
static const int      SENSOR_POWER_PIN   = 2;
static const uint32_t POWER_WARMUP_MS    = 1500;

// One "reading" = mean of OVERSAMPLE conversions. 16 conversions spaced
// 1.25 ms span 20 ms = exactly one 50 Hz mains cycle, which averages out
// mains pickup. (For 60 Hz mains use SAMPLE_GAP_US = 1040.)
static const int      OVERSAMPLE         = 16;
static const uint32_t SAMPLE_GAP_US      = 1250;
static const uint32_t READING_PERIOD_MS  = 50;      // 20 readings / second

// Final measurement window
static const int      MEASURE_SECONDS    = 10;
static const int      MEASURE_N          = MEASURE_SECONDS * 1000 / READING_PERIOD_MS;  // 200

// "Settled" = over the last SETTLE_WINDOW_S one-second means:
//   (max - min) <= SETTLE_BAND_COUNTS  AND  |slope| <= SETTLE_SLOPE_CPM
// and that has held for SETTLE_HOLD_S consecutive seconds.
// Tune these after you see how noisy your sensors really are.
static const int      SETTLE_WINDOW_S    = 20;
static const float    SETTLE_BAND_COUNTS = 4.0f;    // raw ADC counts
static const float    SETTLE_SLOPE_CPM   = 3.0f;    // raw counts per minute
static const int      SETTLE_HOLD_S      = 10;
static const uint32_t SETTLE_TIMEOUT_S   = 600;     // give up waiting after 10 min

// ================================ STATE =================================
// (types must be declared up here: the Arduino IDE auto-generates function
//  prototypes before any later struct definition)
struct Stats { float mean, sd, mn, mx; };

static int   gSensor  = 1;
static int   gRep     = 1;
static float gWaterMl = 0.0f;
static float gMassG   = NAN;

static float gRaw[MEASURE_N];
static float gMv[MEASURE_N];
static float gSorted[MEASURE_N];

// ============================== PRIMITIVES ==============================
static void waitUntil(uint32_t tMs) {
  while ((int32_t)(millis() - tMs) < 0) delay(1);
}

static void drainSerial() {
  while (Serial.available()) Serial.read();
}

// One oversampled reading: mean raw counts and mean millivolts.
static void readOnce(float &raw, float &mv) {
  uint32_t sr = 0, sm = 0;
  uint32_t next = micros();
  for (int i = 0; i < OVERSAMPLE; i++) {
    sr += analogRead(SENSOR_PIN);
    sm += analogReadMilliVolts(SENSOR_PIN);
    next += SAMPLE_GAP_US;
    while ((int32_t)(micros() - next) < 0) { }
  }
  raw = (float)sr / OVERSAMPLE;
  mv  = (float)sm / OVERSAMPLE;
}

// Least-squares slope of y[0..n-1], samples dt seconds apart (units: y per s).
static float slopePerSec(const float *y, int n, float dt) {
  if (n < 2) return 0.0f;
  double sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (int i = 0; i < n; i++) {
    double x = i * (double)dt;
    sx += x; sy += y[i]; sxx += x * x; sxy += x * y[i];
  }
  double den = n * sxx - sx * sx;
  return den == 0 ? 0.0f : (float)((n * sxy - sx * sy) / den);
}

// ============================== PIN TEST ================================
static void captureStats(uint32_t ms, Stats &s, bool echo) {
  double sum = 0, sum2 = 0;
  int n = 0;
  s.mn = 1e9f; s.mx = -1e9f;
  uint32_t t0 = millis(), next = t0, lastPrint = t0;
  while (millis() - t0 < ms) {
    float r, m;
    readOnce(r, m);
    sum += r; sum2 += (double)r * r; n++;
    if (r < s.mn) s.mn = r;
    if (r > s.mx) s.mx = r;
    if (echo && millis() - lastPrint >= 500) {
      Serial.printf("    raw %7.1f   %5.0f mV\n", r, m);
      lastPrint = millis();
    }
    next += 100;
    waitUntil(next);
  }
  s.mean = (float)(sum / n);
  double var = n > 1 ? (sum2 - n * (double)s.mean * s.mean) / (n - 1) : 0;
  s.sd = var > 0 ? (float)sqrt(var) : 0.0f;
}

static void waitForKey() {
  drainSerial();
  while (!Serial.available()) delay(10);
  drainSerial();
}

static void pinTest() {
  Stats a, b, junk;
  Serial.println();
  Serial.println("=== PIN TEST (GPIO36) ===");
  Serial.println("Phase A: sensor in AIR, hands off. Capturing 5 s ...");
  captureStats(5000, a, true);
  Serial.printf("  A: mean %.1f  sd %.2f  min %.0f  max %.0f\n", a.mean, a.sd, a.mn, a.mx);

  Serial.println("Phase B: put the sensing part into WATER or MOIST SOIL (up to the line),");
  Serial.println("         then press Enter ...");
  waitForKey();
  Serial.println("  letting it settle 3 s, then capturing 4 s ...");
  captureStats(3000, junk, true);
  captureStats(4000, b, true);
  Serial.printf("  B: mean %.1f  sd %.2f  min %.0f  max %.0f\n", b.mean, b.sd, b.mn, b.mx);

  float delta = b.mean - a.mean;
  Serial.printf("  change A->B: %+.1f counts\n", delta);

  Serial.println("VERDICT:");
  if (a.mean < 100 && b.mean < 100) {
    Serial.println("  STUCK AT ~0. Signal wire not on GPIO36, sensor unpowered, or GND/signal swapped.");
  } else if (a.mean > 3900 && b.mean > 3900) {
    Serial.println("  STUCK AT FULL SCALE. Signal wire floating/disconnected, or AOUT tied to 3V3.");
  } else if (fabsf(delta) >= 300.0f) {
    if (delta < 0) Serial.println("  RESPONDING. Value dropped when wet - correct for a capacitive v1.2 sensor.");
    else           Serial.println("  RESPONDING, but value ROSE when wet. Unusual for v1.2 - check sensor type/wiring.");
  } else if (fabsf(delta) >= 80.0f) {
    Serial.println("  WEAK RESPONSE. Check the sensor went deep enough / water touched the sensing area.");
  } else {
    Serial.println("  NO RESPONSE. Readings did not change. Check 3V3 + GND power, the signal wire, and that");
    Serial.println("  the sensor was really in water. Try another sensor.");
  }
  if (a.sd > 40.0f) Serial.println("  NOTE: very noisy in air (sd > 40) - suspicious wiring or a loose connection.");
  Serial.println();
}

// =============================== LIVE MODE ==============================
static void liveMode() {
  Serial.println("Live mode - send any key to stop.");
  drainSerial();
  uint32_t next = millis();
  while (!Serial.available()) {
    float r, m;
    readOnce(r, m);
    Serial.printf("raw:%.1f,mV:%.0f\n", r, m);   // Serial Plotter format
    next += 100;
    waitUntil(next);
  }
  drainSerial();
  Serial.println("Live mode stopped.");
}

// ============================ SETTLE + MEASURE ==========================
static bool waitForSettle(uint32_t &settleSecs) {
  float win[SETTLE_WINDOW_S];
  int cnt = 0, stable = 0;
  uint32_t sec = 0;
  drainSerial();
  Serial.printf("  waiting for the reading to settle (max %us, send any key to skip) ...\n",
                (unsigned)SETTLE_TIMEOUT_S);

  while (true) {
    // one-second mean of readings
    double acc = 0;
    int k = 0;
    uint32_t next = millis();
    for (uint32_t i = 0; i < 1000 / READING_PERIOD_MS; i++) {
      float r, m;
      readOnce(r, m);
      acc += r; k++;
      next += READING_PERIOD_MS;
      waitUntil(next);
    }
    float mean = (float)(acc / k);
    sec++;

    if (cnt < SETTLE_WINDOW_S) {
      win[cnt++] = mean;
    } else {
      memmove(win, win + 1, (SETTLE_WINDOW_S - 1) * sizeof(float));
      win[SETTLE_WINDOW_S - 1] = mean;
    }

    float range = NAN, slopeCpm = NAN;
    if (cnt == SETTLE_WINDOW_S) {
      float mn = win[0], mx = win[0];
      for (int i = 1; i < cnt; i++) { if (win[i] < mn) mn = win[i]; if (win[i] > mx) mx = win[i]; }
      range = mx - mn;
      slopeCpm = slopePerSec(win, cnt, 1.0f) * 60.0f;
      bool ok = range <= SETTLE_BAND_COUNTS && fabsf(slopeCpm) <= SETTLE_SLOPE_CPM;
      stable = ok ? stable + 1 : 0;
    }

    if (sec % 5 == 0) {
      if (cnt < SETTLE_WINDOW_S)
        Serial.printf("    t=%3us  now=%7.1f  (collecting window %d/%d)\n", (unsigned)sec, mean, cnt, SETTLE_WINDOW_S);
      else
        Serial.printf("    t=%3us  now=%7.1f  range%d=%5.1f  slope=%+6.1f/min  stable=%d/%d\n",
                      (unsigned)sec, mean, SETTLE_WINDOW_S, range, slopeCpm, stable, SETTLE_HOLD_S);
    }

    if (stable >= SETTLE_HOLD_S) {
      settleSecs = sec;
      Serial.printf("  settled after %us.\n", (unsigned)sec);
      return true;
    }
    if (sec >= SETTLE_TIMEOUT_S) {
      settleSecs = sec;
      Serial.println("  TIMEOUT - not settled; measuring anyway (flagged settled=0).");
      return false;
    }
    if (Serial.available()) {
      drainSerial();
      settleSecs = sec;
      Serial.println("  skipped by user; measuring now (flagged settled=0).");
      return false;
    }
  }
}

static void printHeader() {
  Serial.println("CSV,sensor,rep,water_ml,mass_g,settled,settle_s,mean_raw,median_raw,std_raw,min_raw,max_raw,slope_raw_per_min,mean_mV,n");
}

static void doMeasure() {
  Serial.println();
  Serial.printf("[sensor %d | rep %d | water %.1f ml | mass %s]\n", gSensor, gRep, gWaterMl,
                isnan(gMassG) ? "-" : String(gMassG, 1).c_str());

  uint32_t settleS = 0;
  bool settled = waitForSettle(settleS);

  Serial.printf("  measuring for %d s (%d readings x %d conversions) ...\n",
                MEASURE_SECONDS, MEASURE_N, OVERSAMPLE);
  uint32_t next = millis();
  for (int i = 0; i < MEASURE_N; i++) {
    readOnce(gRaw[i], gMv[i]);
    next += READING_PERIOD_MS;
    waitUntil(next);
  }

  double sum = 0, sum2 = 0, sumMv = 0;
  float mn = gRaw[0], mx = gRaw[0];
  for (int i = 0; i < MEASURE_N; i++) {
    sum += gRaw[i]; sum2 += (double)gRaw[i] * gRaw[i]; sumMv += gMv[i];
    if (gRaw[i] < mn) mn = gRaw[i];
    if (gRaw[i] > mx) mx = gRaw[i];
    gSorted[i] = gRaw[i];
  }
  float mean = (float)(sum / MEASURE_N);
  double var = (sum2 - MEASURE_N * (double)mean * mean) / (MEASURE_N - 1);
  float sd = var > 0 ? (float)sqrt(var) : 0.0f;

  for (int i = 1; i < MEASURE_N; i++) {            // insertion sort for the median
    float v = gSorted[i];
    int j = i - 1;
    while (j >= 0 && gSorted[j] > v) { gSorted[j + 1] = gSorted[j]; j--; }
    gSorted[j + 1] = v;
  }
  float median = (MEASURE_N % 2) ? gSorted[MEASURE_N / 2]
                                 : 0.5f * (gSorted[MEASURE_N / 2 - 1] + gSorted[MEASURE_N / 2]);
  float slopeCpm = slopePerSec(gRaw, MEASURE_N, READING_PERIOD_MS / 1000.0f) * 60.0f;
  float meanMv = (float)(sumMv / MEASURE_N);

  Serial.printf("  RESULT: mean %.2f  median %.2f  sd %.2f  range %.1f..%.1f  drift %+.2f/min  (%.0f mV)\n",
                mean, median, sd, mn, mx, slopeCpm, meanMv);

  Serial.printf("CSV,%d,%d,%.1f,", gSensor, gRep, gWaterMl);
  if (!isnan(gMassG)) Serial.printf("%.1f", gMassG);
  Serial.printf(",%d,%u,%.3f,%.3f,%.3f,%.1f,%.1f,%.3f,%.1f,%d\n",
                settled ? 1 : 0, (unsigned)settleS, mean, median, sd, mn, mx, slopeCpm, meanMv, MEASURE_N);

  gRep++;
  Serial.printf("(next rep number: %d - pull the sensor out and reinsert for a repeat, or change s/w)\n", gRep);
}

// =============================== COMMANDS ===============================
static void printSettings() {
  Serial.printf("Settings: sensor=%d  rep=%d  water=%.1f ml (cumulative)  mass=%s g\n",
                gSensor, gRep, gWaterMl, isnan(gMassG) ? "-" : String(gMassG, 1).c_str());
}

static void printHelp() {
  Serial.println();
  Serial.println("Commands: t=pin test | l=live | s<1-3>=sensor | w<ml>=cumulative water | g<grams>=mass");
  Serial.println("          m=measure | r<n>=rep number | p=settings | H=CSV header | h=help");
  printSettings();
}

static void handleLine(String line) {
  line.trim();
  if (line.length() == 0) return;
  char c = line[0];
  String arg = line.substring(1);
  arg.trim();

  switch (c) {
    case 't': pinTest(); break;
    case 'l': liveMode(); break;
    case 'm': doMeasure(); break;
    case 'p': printSettings(); break;
    case 'H': printHeader(); break;
    case 'h': case '?': printHelp(); break;
    case 's': {
      int v = arg.toInt();
      if (v < 1 || v > 3) { Serial.println("Sensor must be 1, 2 or 3."); break; }
      gSensor = v; gRep = 1;
      Serial.printf("Sensor %d selected. Swap the wiring now; give it ~30-60 s to warm up before \"m\".\n", gSensor);
      break;
    }
    case 'w':
      gWaterMl = arg.toFloat(); gRep = 1;
      Serial.printf("Cumulative water set to %.1f ml (rep reset to 1).\n", gWaterMl);
      break;
    case 'g':
      gMassG = arg.length() ? arg.toFloat() : NAN;
      Serial.println(arg.length() ? "Mass recorded." : "Mass cleared.");
      break;
    case 'r':
      gRep = max(1, (int)arg.toInt());
      Serial.printf("Rep number set to %d.\n", gRep);
      break;
    default:
      Serial.println("Unknown command. Type h for help.");
  }
}

// ================================ ARDUINO ===============================
void setup() {
  Serial.begin(115200);
  delay(500);
  if (SENSOR_POWER_PIN >= 0) {
    pinMode(SENSOR_POWER_PIN, OUTPUT);
    digitalWrite(SENSOR_POWER_PIN, HIGH);          // power the sensor, stays on all session
    Serial.printf("Sensor power: GPIO%d HIGH, warming up %u ms ...\n", SENSOR_POWER_PIN, (unsigned)POWER_WARMUP_MS);
    delay(POWER_WARMUP_MS);
  } else {
    Serial.println("Sensor power: expecting sensor VCC on the 3V3 pin (no power pin driven).");
  }
  analogReadResolution(12);
  analogSetPinAttenuation(SENSOR_PIN, ADC_11db);   // same as the field nodes

  Serial.println();
  Serial.println("DryAhead soil calibration rig  (sensor on GPIO36, 12-bit, 11 dB)");
  Serial.printf("Per reading: %d conversions over %.0f ms | measure window: %d s | settle band: %.1f counts, %.1f counts/min\n",
                OVERSAMPLE, OVERSAMPLE * SAMPLE_GAP_US / 1000.0, MEASURE_SECONDS, SETTLE_BAND_COUNTS, SETTLE_SLOPE_CPM);
  Serial.println("First run \"t\" to check the sensor responds.");
  printHeader();
  printHelp();
}

void loop() {
  if (Serial.available()) {
    handleLine(Serial.readStringUntil('\n'));
  }
  delay(5);
}
