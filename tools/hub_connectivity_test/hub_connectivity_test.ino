/*
 * DryAhead hub - Wi-Fi + Supabase connectivity test (bench tool, READ-ONLY)
 * =========================================================================
 * Runs on the hub's ESP32. Uses the same stack the hub firmware uses
 * (WiFiClientSecure + HTTPClient, setInsecure(), apikey + Bearer headers) so a
 * PASS here means the hub's network path really works. It only does GETs; it
 * never writes to the database.
 *
 * Setup:
 *   1. python tools/hub_connectivity_test/make_secrets_h.py   (creates secrets.h)
 *   2. Open this sketch in Arduino IDE, board "ESP32 Dev Module", upload.
 *   3. Serial Monitor 115200 baud. Results print automatically; send "r" to rerun.
 *
 * NOTE: uploading replaces whatever is on the board (e.g. the hub firmware).
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "secrets.h"      // WIFI_SSID, WIFI_PASS, SUPABASE_URL, SUPABASE_KEY (git-ignored)

static const char* TABLES[] = { "readings", "instructions", "hub_status" };
static const uint32_t WIFI_TIMEOUT_MS = 20000;

static const char* wifiStatusText(wl_status_t s) {
  switch (s) {
    case WL_NO_SSID_AVAIL:   return "SSID not found (wrong name, out of range, or 5 GHz-only network)";
    case WL_CONNECT_FAILED:  return "connect failed (usually WRONG PASSWORD)";
    case WL_CONNECTION_LOST: return "connection lost";
    case WL_DISCONNECTED:    return "disconnected / still trying";
    case WL_IDLE_STATUS:     return "idle";
    case WL_CONNECTED:       return "connected";
    default:                 return "unknown";
  }
}

static String hostOf(const String& url) {
  String h = url;
  int p = h.indexOf("://");
  if (p >= 0) h = h.substring(p + 3);
  int slash = h.indexOf('/');
  if (slash >= 0) h = h.substring(0, slash);
  return h;
}

static bool testWifi() {
  Serial.println("\n[1/3] Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(200);

  int n = WiFi.scanNetworks();
  bool seen = false;
  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i) == WIFI_SSID) {
      seen = true;
      Serial.printf("  SSID visible: yes (RSSI %d dBm, channel %d)\n", WiFi.RSSI(i), WiFi.channel(i));
      break;
    }
  }
  if (!seen) Serial.printf("  SSID visible: NO (%d networks seen) - check the name / range / 2.4 GHz\n", n);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_TIMEOUT_MS) delay(250);

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("  PASS  connected in %lu ms, IP %s, RSSI %d dBm\n",
                  (unsigned long)(millis() - t0), WiFi.localIP().toString().c_str(), WiFi.RSSI());
    return true;
  }
  Serial.printf("  FAIL  %s (status %d)\n", wifiStatusText(WiFi.status()), (int)WiFi.status());
  return false;
}

static bool testDns() {
  Serial.println("\n[2/3] DNS");
  String host = hostOf(SUPABASE_URL);
  IPAddress ip;
  if (WiFi.hostByName(host.c_str(), ip)) {
    Serial.printf("  PASS  %s -> %s\n", host.c_str(), ip.toString().c_str());
    return true;
  }
  Serial.printf("  FAIL  cannot resolve %s (no internet, or wrong SUPABASE_URL)\n", host.c_str());
  return false;
}

static bool testSupabase() {
  Serial.println("\n[3/3] Supabase (read-only GET, same client as hub firmware)");
  bool all = true;
  for (const char* t : TABLES) {
    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;
    http.setTimeout(15000);
    String url = String(SUPABASE_URL) + "/rest/v1/" + t + "?select=*&limit=1";
    http.begin(client, url);
    http.addHeader("apikey", SUPABASE_KEY);
    http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);

    uint32_t t0 = millis();
    int code = http.GET();
    uint32_t ms = millis() - t0;

    if (code == 200) {
      String body = http.getString();
      Serial.printf("  PASS  %-13s HTTP 200  %lu ms  %s\n", t, (unsigned long)ms,
                    body.length() <= 4 ? "empty result (no rows, or RLS hides them)" : "row(s) returned");
    } else if (code > 0) {
      const char* hint = code == 401 ? "key rejected" : code == 403 ? "blocked by row-level security"
                       : code == 404 ? "table not found / not exposed" : "";
      Serial.printf("  FAIL  %-13s HTTP %d  %s\n", t, code, hint);
      all = false;
    } else {
      Serial.printf("  FAIL  %-13s %s (%d)\n", t, HTTPClient::errorToString(code).c_str(), code);
      all = false;
    }
    http.end();
  }
  return all;
}

static void runAll() {
  Serial.println("\n===== DryAhead hub connectivity test =====");
  bool w = testWifi();
  bool d = w && testDns();
  bool s = d && testSupabase();
  Serial.println("\n----- SUMMARY -----");
  Serial.printf("Wi-Fi: %s | DNS: %s | Supabase: %s\n",
                w ? "PASS" : "FAIL", w ? (d ? "PASS" : "FAIL") : "skipped", d ? (s ? "PASS" : "FAIL") : "skipped");
  Serial.println("Send \"r\" to run again.");
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  runAll();
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'r' || c == 'R') runAll();
  }
  delay(20);
}
