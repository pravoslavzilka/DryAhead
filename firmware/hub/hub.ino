/*
 * ============================================================
 *  DROUGHT NETWORK HUB - robust, cloud-driven (+ heartbeat)
 *  Board: LaskaKit ESP32-DEVKit (or any ESP32 + Ra-02)
 *  Mains powered, always awake.
 * ============================================================
 *
 *  PIPELINE
 *   - Receives node packets over LoRa 433 MHz
 *   - Writes EVERY reading to a local buffer FIRST (LittleFS), then
 *     tries to POST it to Supabase. Local copy is only removed once
 *     Supabase CONFIRMS the insert (HTTP 201/200, or 409 = already there).
 *   - If Supabase/WiFi is unreachable, readings accumulate in the local
 *     buffer and are retried on every poll until delivered.
 *   - Idempotency: readings carry a unique (node_id, recorded_at) key
 *     and are upserted, so retries never create duplicates.
 *
 *  INSTRUCTION QUEUE (cloud-driven commands)
 *   - Every POLL_INTERVAL the hub GETs instructions WHERE state='Posted'
 *   - Marks them 'Received', stores them in memory (node + time range)
 *   - When the target node opens a listen window (L:1), the hub sends
 *     GETDATA:<range_start> (+ always TIME sync, + optional CFG)
 *   - When the requested data has arrived, marks the instruction
 *     'Resolved'; on timeout marks 'Failed to resolve' with a message.
 *
 *  HEARTBEAT
 *   - Every HEARTBEAT_INTERVAL the hub POSTs a row to hub_status with:
 *       active, pending_count (buffered/undelivered), last_error,
 *       uptime_seconds, wifi_rssi.
 *   - NOTE: if WiFi/Supabase is totally down, the heartbeat can't be
 *     sent either, so a full outage shows up as the ABSENCE of recent
 *     hub_status rows. Check freshness (latest reported_at), not just
 *     the active flag.
 *
 *  SUPABASE TABLES EXPECTED
 *   readings(id, node_id, raw, temperature, recorded_at, rssi, snr,
 *            is_backlog, received_at)   UNIQUE(node_id, recorded_at)
 *   instructions(id, node_id, command, range_start, range_end,
 *                state, message, created_at, updated_at)
 *   hub_status(id, reported_at, active, pending_count, last_error,
 *              uptime_seconds, wifi_rssi)
 *
 *  Wiring (Ra-02): SCK=18 MISO=19 MOSI=23 NSS=5 RST=27 DIO0=26 3.3V GND
 *  Hub gets true time from NTP (internet); no RTC hardware needed.
 *  It then serves that time to nodes via the TIME sync command.
 *  REMEMBER: GPIO2 HIGH powers the 3.3V peripheral rail.
 *
 *  Libraries: LoRa (Sandeep Mistry), ArduinoJson
 * ============================================================
 */

#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <time.h>      // NTP / network time

// ==================== CONFIG ====================
const char* WIFI_SSID = "*********";
const char* WIFI_PASS = "**********";

const char* SUPABASE_URL = "************";
const char* SUPABASE_KEY = "************";


#define NUM_NODES        5
#define POLL_INTERVAL_MS      600000UL     // poll instructions every 10 min
#define INSTR_TIMEOUT_S       10800UL      // 3 h: fail unresolved instructions
#define HEARTBEAT_INTERVAL_MS 3600000UL    // send hub_status every 1 hour

const char* CFG_CODE = "";             // optional config to push ("" = none)

// NTP (network time) - the hub gets true global time from the internet.
const char* NTP_SERVER1 = "pool.ntp.org";
const char* NTP_SERVER2 = "time.nist.gov";
const long  GMT_OFFSET_SEC      = 0;   // store UTC epoch; convert in the cloud
const int   DAYLIGHT_OFFSET_SEC = 0;
// ================================================

// ---------- Pins ----------
#define PERIPH_POWER   2
#define LORA_SS        5
#define LORA_RST      27
#define LORA_DIO0     26

// ---------- Files ----------
const char* BUFFER_FILE = "/buffer.csv";   // unsent readings

// ---------- Globals ----------
bool timeReady = false;         // true once NTP has synced at least once
unsigned long lastPoll = 0;
unsigned long lastHeartbeat = 0;
String lastError = "";          // reason the last POST failed ("" = ok)

// In-memory pending instructions (one per node max for simplicity)
struct Instruction {
  long     id;            // supabase row id (-1 = none active)
  int      nodeId;
  uint32_t rangeStart;
  uint32_t rangeEnd;      // 0 = open-ended
  uint32_t postedAtEpoch; // when we marked Received (for timeout)
  bool     sent;          // GETDATA already transmitted to node?
};
Instruction pending[NUM_NODES + 1];   // indexed by node id

// ============================================================
//  WiFi / time
// ============================================================
bool wifiUp() { return WiFi.status() == WL_CONNECTED; }

// Current UTC epoch from NTP (0 if not yet synced)
uint32_t nowEpoch() {
  time_t t = time(nullptr);
  if (t < 1700000000) return 0;   // not synced yet
  return (uint32_t)t;
}

// Configure NTP and wait briefly for the first sync
void syncTimeNTP() {
  if (!wifiUp()) return;
  configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER1, NTP_SERVER2);
  Serial.print("[NTP] syncing");
  int tries = 0;
  while (time(nullptr) < 1700000000 && tries < 20) {
    delay(500); Serial.print("."); tries++;
  }
  if (nowEpoch() > 0) {
    timeReady = true;
    Serial.print("\n[NTP] time set, epoch = "); Serial.println(nowEpoch());
  } else {
    Serial.println("\n[NTP] sync failed (will retry).");
  }
}

void connectWiFi() {
  if (wifiUp()) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int tries = 0;
  while (!wifiUp() && tries < 20) { delay(500); tries++; }
}

// ============================================================
//  Supabase helpers
// ============================================================

// Upsert one reading. Returns true if Supabase confirmed (201/200) or it
// already existed (409 duplicate) - all mean "safely in the table".
// Records the failure reason in lastError for the heartbeat.
bool supaPostReading(int nodeId, int raw, float temp, uint32_t epoch,
                     int rssi, float snr, bool isBacklog) {
  if (!wifiUp()) connectWiFi();
  if (!wifiUp()) { lastError = "WiFi offline"; return false; }

  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  String url = String(SUPABASE_URL) + "/rest/v1/readings";
  http.begin(client, url);
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
  http.addHeader("Content-Type", "application/json");
  // upsert on the unique (node_id, recorded_at) key -> retries don't duplicate
  http.addHeader("Prefer", "resolution=merge-duplicates,return=minimal");

  String body = "{";
  body += "\"node_id\":"     + String(nodeId) + ",";
  body += "\"raw\":"         + String(raw) + ",";
  body += "\"temperature\":" + String(temp, 2) + ",";
  body += "\"recorded_at\":" + String(epoch) + ",";
  body += "\"rssi\":"        + String(rssi) + ",";
  body += "\"snr\":"         + String(snr, 1) + ",";
  body += "\"is_backlog\":"  + String(isBacklog ? "true" : "false");
  body += "}";

  int code = http.POST(body);
  bool ok = (code == 201 || code == 200 || code == 409);
  if (ok) {
    lastError = "";
  } else {
    lastError = "HTTP " + String(code) + ": " + http.getString();
    if (lastError.length() > 300) lastError = lastError.substring(0, 300);
  }
  http.end();
  return ok;
}

// PATCH an instruction's state (+ optional message)
bool supaUpdateInstruction(long id, const char* state, const char* msg) {
  if (!wifiUp()) connectWiFi();
  if (!wifiUp()) return false;

  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  String url = String(SUPABASE_URL) + "/rest/v1/instructions?id=eq." + String(id);
  http.begin(client, url);
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Prefer", "return=minimal");

  String body = String("{\"state\":\"") + state + "\"";
  if (msg && strlen(msg) > 0) body += String(",\"message\":\"") + msg + "\"";
  body += "}";

  int code = http.sendRequest("PATCH", body);
  http.end();
  return (code == 204 || code == 200);
}

// ============================================================
//  Local buffer (offline storage of unsent readings)
//  Each line: node_id,raw,temp,epoch,rssi,snr,is_backlog
// ============================================================
void bufferAppend(int nodeId, int raw, float temp, uint32_t epoch,
                  int rssi, float snr, bool isBacklog) {
  File f = LittleFS.open(BUFFER_FILE, FILE_APPEND);
  if (!f) { Serial.println("[BUF] open failed!"); return; }
  f.print(nodeId); f.print(",");
  f.print(raw); f.print(",");
  f.print(temp, 2); f.print(",");
  f.print(epoch); f.print(",");
  f.print(rssi); f.print(",");
  f.print(snr, 1); f.print(",");
  f.println(isBacklog ? 1 : 0);
  f.close();
}

// Count how many readings are waiting in the local buffer
int bufferCount() {
  if (!LittleFS.exists(BUFFER_FILE)) return 0;
  File f = LittleFS.open(BUFFER_FILE, FILE_READ);
  if (!f) return -1;
  int n = 0;
  while (f.available()) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) n++;
  }
  f.close();
  return n;
}

// Try to flush the buffer to Supabase. Records that are confirmed are
// dropped; unconfirmed ones are kept (rewritten back). Returns count left.
int bufferFlush() {
  if (!LittleFS.exists(BUFFER_FILE)) return 0;
  if (!wifiUp()) connectWiFi();

  File f = LittleFS.open(BUFFER_FILE, FILE_READ);
  if (!f) return -1;

  String remaining = "";   // lines not yet confirmed
  int delivered = 0, kept = 0;

  while (f.available()) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    // parse: node,raw,temp,epoch,rssi,snr,backlog
    int p[6];
    int from = 0;
    for (int i = 0; i < 6; i++) {
      p[i] = line.indexOf(',', from);
      from = p[i] + 1;
    }
    int      nodeId = line.substring(0, p[0]).toInt();
    int      raw    = line.substring(p[0]+1, p[1]).toInt();
    float    temp   = line.substring(p[1]+1, p[2]).toFloat();
    uint32_t epoch  = (uint32_t) line.substring(p[2]+1, p[3]).toInt();
    int      rssi   = line.substring(p[3]+1, p[4]).toInt();
    float    snr    = line.substring(p[4]+1, p[5]).toFloat();
    bool     bl     = line.substring(p[5]+1).toInt() != 0;

    bool ok = supaPostReading(nodeId, raw, temp, epoch, rssi, snr, bl);
    if (ok) {
      delivered++;
    } else {
      remaining += line + "\n";   // keep for next retry
      kept++;
      // If Supabase is unreachable, stop hammering it this pass -
      // keep the rest of the buffer for the next retry.
      if (!wifiUp()) {
        while (f.available()) {
          String rest = f.readStringUntil('\n');
          rest.trim();
          if (rest.length() > 0) { remaining += rest + "\n"; kept++; }
        }
        break;
      }
    }
  }
  f.close();

  // Rewrite the buffer with only the unconfirmed lines (or delete if empty)
  if (remaining.length() == 0) {
    LittleFS.remove(BUFFER_FILE);
  } else {
    File w = LittleFS.open(BUFFER_FILE, FILE_WRITE);   // overwrite
    if (w) { w.print(remaining); w.close(); }
  }

  if (delivered > 0 || kept > 0) {
    Serial.print("[BUF] flushed: "); Serial.print(delivered);
    Serial.print(" delivered, "); Serial.print(kept); Serial.println(" kept.");
  }
  return kept;
}

// Handle one reading: buffer FIRST, then try immediate delivery.
void ingestReading(int nodeId, int raw, float temp, uint32_t epoch,
                   int rssi, float snr, bool isBacklog) {
  bufferAppend(nodeId, raw, temp, epoch, rssi, snr, isBacklog);  // safety first
  bufferFlush();   // attempt delivery now (also pushes any earlier backlog)
}

// ============================================================
//  Heartbeat -> hub_status
// ============================================================
void sendHeartbeat() {
  if (!wifiUp()) connectWiFi();
  if (!wifiUp()) { Serial.println("[HB] offline, skip heartbeat."); return; }

  int pending = bufferCount();

  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  String url = String(SUPABASE_URL) + "/rest/v1/hub_status";
  http.begin(client, url);
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Prefer", "return=minimal");

  // JSON-escape the error string
  String err = lastError;
  err.replace("\\", "\\\\");
  err.replace("\"", "\\\"");
  err.replace("\n", " ");
  err.replace("\r", " ");

  String body = "{";
  body += "\"active\":true,";
  body += "\"pending_count\":"  + String(pending) + ",";
  body += "\"last_error\":\""   + err + "\",";
  body += "\"uptime_seconds\":" + String((unsigned long)(millis() / 1000)) + ",";
  body += "\"wifi_rssi\":"      + String(WiFi.RSSI());
  body += "}";

  int code = http.POST(body);
  http.end();
  Serial.print("[HB] heartbeat sent (pending "); Serial.print(pending);
  Serial.print(", HTTP "); Serial.print(code); Serial.println(")");
}

// ============================================================
//  Instruction queue
// ============================================================
void pollInstructions() {
  if (!wifiUp()) connectWiFi();
  if (!wifiUp()) { Serial.println("[INSTR] offline, skip poll."); return; }

  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  String url = String(SUPABASE_URL) +
    "/rest/v1/instructions?state=eq.Posted&select=id,node_id,range_start,range_end";
  http.begin(client, url);
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);

  int code = http.GET();
  if (code != 200) { Serial.print("[INSTR] poll code "); Serial.println(code); http.end(); return; }
  String payload = http.getString();
  http.end();

  StaticJsonDocument<2048> doc;
  if (deserializeJson(doc, payload)) { Serial.println("[INSTR] JSON parse error"); return; }

  for (JsonObject o : doc.as<JsonArray>()) {
    long id   = o["id"];
    int  node = o["node_id"];
    uint32_t rs = o["range_start"] | 0;
    uint32_t re = o["range_end"] | 0;

    if (node >= 1 && node <= NUM_NODES) {
      pending[node].id            = id;
      pending[node].nodeId        = node;
      pending[node].rangeStart    = rs;
      pending[node].rangeEnd      = re;
      pending[node].postedAtEpoch = nowEpoch();
      pending[node].sent          = false;
      supaUpdateInstruction(id, "Received", nullptr);
      Serial.print("[INSTR] node "); Serial.print(node);
      Serial.print(" -> Received (since "); Serial.print(rs); Serial.println(")");
    }
  }
}

// Time out instructions that have not been resolved in INSTR_TIMEOUT_S
void checkInstructionTimeouts() {
  if (!timeReady) return;
  uint32_t now = nowEpoch();
  if (now == 0) return;
  for (int n = 1; n <= NUM_NODES; n++) {
    if (pending[n].id >= 0 && pending[n].postedAtEpoch > 0 &&
        (now - pending[n].postedAtEpoch) > INSTR_TIMEOUT_S) {
      supaUpdateInstruction(pending[n].id, "Failed to resolve",
                            "node did not deliver within timeout");
      Serial.print("[INSTR] node "); Serial.print(n); Serial.println(" -> Failed (timeout)");
      pending[n].id = -1;
    }
  }
}

// ============================================================
//  Build command for a listening node
// ============================================================
String buildCommand(int nodeId) {
  String cmd = "";
  uint32_t epoch = nowEpoch();
  if (epoch > 1700000000UL) cmd += "TIME:" + String(epoch);

  if (nodeId >= 1 && nodeId <= NUM_NODES && pending[nodeId].id >= 0) {
    if (cmd.length() > 0) cmd += ";";
    cmd += "GETDATA:" + String(pending[nodeId].rangeStart);
    pending[nodeId].sent = true;
    Serial.print("[INSTR] sending GETDATA to node "); Serial.println(nodeId);
  }
  if (strlen(CFG_CODE) > 0) {
    if (cmd.length() > 0) cmd += ";";
    cmd += "CFG:" + String(CFG_CODE);
  }
  return cmd;
}

// ============================================================
//  Parse a node record "node_id,raw,temp,epoch" -> ingest
//  Returns the node id (or -1).
// ============================================================
int parseRecord(const String &rec, int rssi, float snr, bool isBacklog) {
  int i1 = rec.indexOf(',');
  int i2 = rec.indexOf(',', i1 + 1);
  int i3 = rec.indexOf(',', i2 + 1);
  if (i1 < 0 || i2 < 0 || i3 < 0) return -1;

  int      nodeId = rec.substring(0, i1).toInt();
  int      raw    = rec.substring(i1 + 1, i2).toInt();
  float    temp   = rec.substring(i2 + 1, i3).toFloat();
  uint32_t epoch  = (uint32_t) rec.substring(i3 + 1).toInt();

  ingestReading(nodeId, raw, temp, epoch, rssi, snr, isBacklog);
  return nodeId;
}

// ============================================================
//  Setup
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== DROUGHT NETWORK HUB (robust + heartbeat) ===");

  for (int n = 0; n <= NUM_NODES; n++) pending[n].id = -1;

  // IMPORTANT: start WiFi FIRST. WiFi init disturbs GPIO2 (the pin that
  // gates the 3.3V peripheral rail on the LaskaKit DEVKit), so we assert
  // the rail AFTER WiFi is up, and keep re-asserting it in loop().
  LittleFS.begin(true);
  connectWiFi();
  Serial.println(wifiUp() ? "WiFi OK" : "WiFi offline (will retry)");

  syncTimeNTP();   // get true global time from the internet

  // Now power the peripheral rail (after WiFi has grabbed its resources)
  pinMode(PERIPH_POWER, OUTPUT);
  digitalWrite(PERIPH_POWER, HIGH);
  delay(100);

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(433E6)) { Serial.println("[LoRa] init failed!"); while (1); }
  Serial.println("[LoRa] listening on 433 MHz.");
  LoRa.receive();

  // Flush any buffer left from a previous session
  bufferFlush();
  pollInstructions();
  lastPoll = millis();

  // Send an initial heartbeat so we know the hub just (re)started
  sendHeartbeat();
  lastHeartbeat = millis();
}

// ============================================================
//  Main loop
// ============================================================
void loop() {
  // Keep the peripheral rail asserted (WiFi activity can disturb GPIO2)
  digitalWrite(PERIPH_POWER, HIGH);

  // Periodic: poll instructions, retry buffer, check timeouts
  if (millis() - lastPoll >= POLL_INTERVAL_MS) {
    Serial.println("--- periodic poll ---");
    if (!timeReady) syncTimeNTP();  // ensure we have time
    bufferFlush();              // retry any undelivered readings
    pollInstructions();         // pick up new Posted instructions
    checkInstructionTimeouts(); // fail stale ones
    lastPoll = millis();
  }

  // Periodic: hourly heartbeat
  if (millis() - lastHeartbeat >= HEARTBEAT_INTERVAL_MS) {
    sendHeartbeat();
    lastHeartbeat = millis();
  }

  int packetSize = LoRa.parsePacket();
  if (!packetSize) return;

  String data = "";
  while (LoRa.available()) data += (char)LoRa.read();
  int rssi = LoRa.packetRssi();
  float snr = LoRa.packetSnr();

  Serial.println("---------------------------------------------");
  Serial.print("RX  RSSI "); Serial.print(rssi);
  Serial.print("  SNR "); Serial.print(snr, 1);
  Serial.print("  : "); Serial.println(data);

  // --- Batched backlog: BACKLOG:rec1|rec2|... ---
  if (data.startsWith("BACKLOG:")) {
    String payload = data.substring(8);
    int start = 0;
    int firstNode = -1;
    while (start < (int)payload.length()) {
      int sep = payload.indexOf('|', start);
      if (sep == -1) sep = payload.length();
      String rec = payload.substring(start, sep); rec.trim();
      if (rec.length() > 0) {
        int nid = parseRecord(rec, rssi, snr, true);
        if (firstNode < 0) firstNode = nid;
      }
      start = sep + 1;
    }
    // Backlog arrived -> the instruction for that node is fulfilled
    if (firstNode >= 1 && firstNode <= NUM_NODES && pending[firstNode].id >= 0) {
      supaUpdateInstruction(pending[firstNode].id, "Resolved", nullptr);
      Serial.print("[INSTR] node "); Serial.print(firstNode); Serial.println(" -> Resolved");
      pending[firstNode].id = -1;
    }
    LoRa.receive();
    return;
  }

  // --- Normal node packet: node_id,raw,temp,epoch,L:x ---
  bool nodeListening = (data.indexOf("L:1") >= 0);
  int lpos = data.lastIndexOf(",L:");
  String record = (lpos >= 0) ? data.substring(0, lpos) : data;

  int nodeId = parseRecord(record, rssi, snr, false);

  // --- If listening, reply with commands now ---
  if (nodeListening && nodeId >= 1) {
    String cmd = buildCommand(nodeId);
    if (cmd.length() > 0) {
      LoRa.beginPacket(); LoRa.print(cmd); LoRa.endPacket();
      Serial.print("[TX->NODE "); Serial.print(nodeId); Serial.print("] ");
      Serial.println(cmd);
    }
  }

  LoRa.receive();
}
