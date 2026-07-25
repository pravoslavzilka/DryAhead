// TEST: WiFi-only, no LoRa. Posts a synthetic fake reading to Supabase every
// 30s, to exercise the ingestion path without needing real sensor hardware.
// See also ../test_supabase_insert_debug/ for lower-level insert/upsert/read checks.
// NOTE: WiFi password and Supabase key below are hardcoded plaintext - fine for
// a bench test, pull into a gitignored config before this repo goes anywhere less trusted.

#include <WiFi.h>
#include <HTTPClient.h>

// ---------- WiFi credentials ----------
const char* WIFI_SSID = "OSK_9731_EXT";
const char* WIFI_PASS = "WO6Q86X3KB";
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>


// ---------- Supabase ----------
const char* SUPABASE_URL = "https://gdqedzibkfthdmuozpvg.supabase.co";
const char* SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdkcWVkemlia2Z0aGRtdW96cHZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIxMzIxMzUsImV4cCI6MjA5NzcwODEzNX0.yHEHCj82NZXV2nAMtdyOgCdspDSfsAlEmoGhxQ8ENyA";   // the long anon public key (eyJ...)

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting WiFi");
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 30) {
    delay(500); Serial.print("."); tries++;
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi OK, IP: "); Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi FAILED");
  }
}

void postReading(int nodeId, int moisture, int raw, float temp, uint32_t recordedAt, int rssi) {
  if (WiFi.status() != WL_CONNECTED) { connectWiFi(); }

  WiFiClientSecure client;
  client.setInsecure();   // Option A: skip cert verification (PoC)

  HTTPClient http;
  String url = String(SUPABASE_URL) + "/rest/v1/readings";
  http.begin(client, url);

  // Required Supabase headers
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Prefer", "return=minimal");

  // Build JSON body
  String body = "{";
  body += "\"node_id\":"     + String(nodeId)     + ",";
  body += "\"moisture\":"    + String(moisture)   + ",";
  body += "\"raw\":"         + String(raw)        + ",";
  body += "\"temperature\":" + String(temp, 2)    + ",";
  body += "\"recorded_at\":" + String(recordedAt) + ",";
  body += "\"rssi\":"        + String(rssi);
  body += "}";

  Serial.print("POST body: "); Serial.println(body);

  int code = http.POST(body);
  Serial.print("HTTP response: "); Serial.println(code);

  if (code == 201) {
    Serial.println(">>> SUCCESS: row inserted into Supabase!");
  } else {
    Serial.print(">>> Response body: ");
    Serial.println(http.getString());   // shows the error if it failed
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== Supabase POST Test ===");
  connectWiFi();
}

void loop() {
  // Send a fake sample reading every 30 seconds
  static int counter = 0;
  Serial.println("\n--- Sending test reading ---");
  postReading(
    1,                    // node_id
    30 + counter,         // moisture (varying so you see changes)
    2800,                 // raw
    24.5,                 // temperature
    1781900000 + counter, // recorded_at (fake epoch)
    -55                   // rssi
  );
  counter++;
  delay(30000);   // every 30 seconds
}