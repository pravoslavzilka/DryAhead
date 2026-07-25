/*
 * ============================================================
 *  SUPABASE INSERT TEST - with detailed debugging
 *  Board: LaskaKit ESP32-DEVKit
 * ============================================================
 *
 *  Isolates the hub -> Supabase path and prints exactly what
 *  happens at each step, so we can see WHERE and WHY it fails.
 *
 *  It runs three tests, 10 s apart, repeatedly:
 *    TEST A: plain INSERT  (no upsert header)   -> isolates the insert
 *    TEST B: UPSERT insert (merge-duplicates)   -> tests the constraint
 *    TEST C: GET back the latest rows           -> confirms read access
 *
 *  Watch the serial monitor: each prints the HTTP code and the full
 *  Supabase response body, which tells us the exact problem.
 *
 *  No LoRa, no GPIO2 rail needed (we don't use peripherals here),
 *  but we still set GPIO2 high in case the board needs it.
 *
 *  NOTE: WiFi password and Supabase key below are hardcoded plaintext -
 *  fine for a bench test, pull into a gitignored config before this repo
 *  goes anywhere less trusted.
 * ============================================================
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// ==================== CONFIG ====================
const char* WIFI_SSID = "OSK_9731_EXT";
const char* WIFI_PASS = "WO6Q86X3KB";

const char* SUPABASE_URL = "https://gdqedzibkfthdmuozpvg.supabase.co";
const char* SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdkcWVkemlia2Z0aGRtdW96cHZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIxMzIxMzUsImV4cCI6MjA5NzcwODEzNX0.yHEHCj82NZXV2nAMtdyOgCdspDSfsAlEmoGhxQ8ENyA";
      // anon public key (eyJ...)
const char* TABLE        = "readings";
// ================================================

#define PERIPH_POWER 2

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[WiFi] connecting");
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 30) { delay(500); Serial.print("."); tries++; }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("\n[WiFi] OK, IP "); Serial.print(WiFi.localIP());
    Serial.print("  RSSI "); Serial.println(WiFi.RSSI());
  } else {
    Serial.println("\n[WiFi] FAILED");
  }
}

// Print the result of any HTTP request in full
void report(const char* label, int code, HTTPClient &http) {
  Serial.print("  ["); Serial.print(label); Serial.print("] HTTP code: ");
  Serial.println(code);
  if (code > 0) {
    String body = http.getString();
    Serial.print("  Response body: ");
    Serial.println(body.length() ? body : "(empty)");
  } else {
    Serial.print("  Transport error: ");
    Serial.println(http.errorToString(code));  // negative = connection/TLS issue
  }
}

// TEST A: plain insert (no upsert)
void testPlainInsert() {
  Serial.println("\n--- TEST A: plain INSERT ---");
  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  String url = String(SUPABASE_URL) + "/rest/v1/" + TABLE;
  Serial.print("  URL: "); Serial.println(url);

  http.begin(client, url);
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Prefer", "return=representation");   // ask Supabase to echo the row

  String body = "{";
  body += "\"node_id\":99,";
  body += "\"raw\":1234,";
  body += "\"temperature\":21.5,";
  body += "\"recorded_at\":" + String((unsigned long)(1782740000 + millis()/1000)) + ",";
  body += "\"rssi\":-50,";
  body += "\"snr\":9.0,";
  body += "\"is_backlog\":false";
  body += "}";
  Serial.print("  Body: "); Serial.println(body);

  int code = http.POST(body);
  report("INSERT", code, http);
  http.end();

  if (code == 201) Serial.println("  >>> SUCCESS: plain insert works!");
}

// TEST B: upsert insert (needs the unique constraint)
void testUpsert() {
  Serial.println("\n--- TEST B: UPSERT (merge-duplicates) ---");
  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  String url = String(SUPABASE_URL) + "/rest/v1/" + TABLE;

  http.begin(client, url);
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Prefer", "resolution=merge-duplicates,return=minimal");

  String body = "{";
  body += "\"node_id\":99,";
  body += "\"raw\":5678,";
  body += "\"temperature\":22.0,";
  body += "\"recorded_at\":1782740001,";   // fixed -> tests duplicate handling
  body += "\"rssi\":-55,";
  body += "\"snr\":8.5,";
  body += "\"is_backlog\":false";
  body += "}";

  int code = http.POST(body);
  report("UPSERT", code, http);
  http.end();

  if (code == 201 || code == 200) Serial.println("  >>> SUCCESS: upsert works (constraint present).");
  else if (code == 400) Serial.println("  >>> Likely MISSING unique constraint on (node_id, recorded_at).");
}

// TEST C: read rows back
void testRead() {
  Serial.println("\n--- TEST C: GET rows ---");
  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  String url = String(SUPABASE_URL) + "/rest/v1/" + TABLE +
               "?select=node_id,raw,recorded_at&order=id.desc&limit=3";

  http.begin(client, url);
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);

  int code = http.GET();
  report("GET", code, http);
  http.end();

  if (code == 200) Serial.println("  >>> SUCCESS: read works.");
}

void setup() {
  pinMode(PERIPH_POWER, OUTPUT);
  digitalWrite(PERIPH_POWER, HIGH);

  Serial.begin(115200);
  delay(1000);
  Serial.println("\n========================================");
  Serial.println("   SUPABASE INSERT DEBUG TEST");
  Serial.println("========================================");

  connectWiFi();

  Serial.print("URL configured: "); Serial.println(SUPABASE_URL);
  Serial.print("Table: "); Serial.println(TABLE);
  Serial.print("Key length: "); Serial.print(strlen(SUPABASE_KEY));
  Serial.println(" chars (anon keys are ~200+ chars)");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) { connectWiFi(); }

  testPlainInsert();
  delay(2000);
  testUpsert();
  delay(2000);
  testRead();

  Serial.println("\n================ cycle done, waiting 10s ================\n");
  delay(10000);
}