/*
 * ============================================================
 *  BASE STATION HUB
 *  Board: LaskaKit ESP32-DEVKit (or any ESP32 + Ra-02)
 * ============================================================
 *
 *  Counterpart to ../nodes/node_with_rtc/ and ../nodes/node_no_rtc/ -
 *  this is what nodes expect to hear back from during their listen
 *  window. Implements the full bidirectional protocol:
 *
 *   - Receives every node packet and prints it (raw,temp,epoch,L flag)
 *   - Receives BACKLOG: packets (resent stored records)
 *   - When a packet has L:1 (node is listening), it IMMEDIATELY
 *     replies within the node's 3 s window with a command built from
 *     whatever test scenarios you enable below.
 *
 *  Scenarios you can toggle (see CONFIG section):
 *     1) TIME    -> sends current epoch so the node sets its RTC
 *     2) GETDATA -> asks the node to resend records since an epoch
 *     3) CFG     -> sends a config/command code
 *     4) any combination (commands are joined with ';')
 *
 *  You can also trigger scenarios live by typing in the Serial
 *  Monitor:  t = time, g = getdata, c = cfg, a = all, n = none
 *
 *  Wiring (Ra-02): SCK=18 MISO=19 MOSI=23 NSS=5 RST=27 DIO0=26 3.3V GND
 *  REMEMBER: GPIO2 HIGH powers the 3.3V peripheral rail.
 * ============================================================
 */

#include <SPI.h>
#include <LoRa.h>
#include <Wire.h>
#include <RTClib.h>

// ---------- Pins ----------
#define PERIPH_POWER   2
#define LORA_SS        5
#define LORA_RST      27
#define LORA_DIO0     26
#define I2C_SDA       21
#define I2C_SCL       22

// ==================== TEST CONFIG ====================
// Which commands to send when a node reports L:1.
// Toggle these true/false, or change live via Serial (t/g/c/a/n).
bool SEND_TIME    = true;    // scenario 1: set the node's RTC
bool SEND_GETDATA = true;    // scenario 2: ask for stored data
bool SEND_CFG     = false;   // scenario 3: send a config code

// For GETDATA: ask for everything newer than this epoch.
// 0 = ask for ALL stored records (good for testing the backlog).
uint32_t GETDATA_SINCE = 0;

// For CFG: the config string to send (node prints/applies it).
const char* CFG_STRING = "interval=30";
// ====================================================

RTC_DS3231 rtc;
bool rtcOK = false;
unsigned long packetCount = 0;

// ------------------------------------------------------------
// Build the command string from the enabled scenarios
// ------------------------------------------------------------
String buildCommand() {
  String cmd = "";

  if (SEND_TIME) {
    uint32_t epoch;
    if (rtcOK) {
      epoch = rtc.now().unixtime();
    } else {
      epoch = 1781900000UL;   // fallback fixed time if hub has no RTC
    }
    cmd += "TIME:" + String(epoch);
  }

  if (SEND_GETDATA) {
    if (cmd.length() > 0) cmd += ";";
    cmd += "GETDATA:" + String(GETDATA_SINCE);
  }

  if (SEND_CFG) {
    if (cmd.length() > 0) cmd += ";";
    cmd += "CFG:" + String(CFG_STRING);
  }

  return cmd;   // empty string = nothing to send
}

// ------------------------------------------------------------
// Print which scenarios are currently armed
// ------------------------------------------------------------
void printArmed() {
  Serial.print(">> Armed responses: ");
  Serial.print(SEND_TIME    ? "TIME "    : "");
  Serial.print(SEND_GETDATA ? "GETDATA " : "");
  Serial.print(SEND_CFG     ? "CFG "     : "");
  if (!SEND_TIME && !SEND_GETDATA && !SEND_CFG) Serial.print("(none)");
  Serial.println();
}

// ------------------------------------------------------------
// Handle live keyboard control from the Serial Monitor
// ------------------------------------------------------------
void handleSerialInput() {
  if (!Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case 't': SEND_TIME = !SEND_TIME;       break;
    case 'g': SEND_GETDATA = !SEND_GETDATA; break;
    case 'c': SEND_CFG = !SEND_CFG;         break;
    case 'a': SEND_TIME = SEND_GETDATA = SEND_CFG = true;  break;
    case 'n': SEND_TIME = SEND_GETDATA = SEND_CFG = false; break;
    default: return;   // ignore newlines etc.
  }
  printArmed();
}

void setup() {
  pinMode(PERIPH_POWER, OUTPUT);
  digitalWrite(PERIPH_POWER, HIGH);   // power the LoRa module
  delay(100);

  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== TEST HUB / RECEIVER ===");
  Serial.println("Keyboard: t=TIME  g=GETDATA  c=CFG  a=ALL  n=NONE");

  // Optional RTC on the hub (used to send the real time to nodes).
  Wire.begin(I2C_SDA, I2C_SCL);
  rtcOK = rtc.begin();
  if (rtcOK) {
    if (rtc.lostPower()) {
      // Set the hub clock once so it can serve correct time to nodes.
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    }
    Serial.println("[RTC] Hub RTC present - will serve real time.");
  } else {
    Serial.println("[RTC] No hub RTC - TIME will use a fixed fallback value.");
  }

  // LoRa
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(433E6)) {
    Serial.println("[LoRa] init failed!");
    while (1);
  }
  Serial.println("[LoRa] Listening on 433 MHz.");
  printArmed();
  Serial.println("---------------------------------------------");

  LoRa.receive();   // start in receive mode
}

void loop() {
  handleSerialInput();   // allow live toggling of scenarios

  int packetSize = LoRa.parsePacket();
  if (!packetSize) return;

  // Read the packet
  String data = "";
  while (LoRa.available()) data += (char)LoRa.read();
  int rssi = LoRa.packetRssi();
  float snr = LoRa.packetSnr();
  packetCount++;

  Serial.println("---------------------------------------------");
  Serial.print("RX #"); Serial.print(packetCount);
  Serial.print("  RSSI "); Serial.print(rssi);
  Serial.print(" dBm  SNR "); Serial.println(snr, 1);

  // --- Is this a resent backlog record? ---
  if (data.startsWith("BACKLOG:")) {
    Serial.print("[BACKLOG RX] ");
    Serial.println(data.substring(8));
    LoRa.receive();   // keep listening for more backlog
    return;
  }

  // --- Normal node packet: node_id,raw,temp,epoch,L:x ---
  Serial.print("[DATA] ");
  Serial.println(data);

  // Does the node say it is listening?  (look for "L:1")
  bool nodeListening = (data.indexOf("L:1") >= 0);

  if (nodeListening) {
    Serial.println("[LISTEN] Node is listening - sending response NOW.");
    String cmd = buildCommand();

    if (cmd.length() > 0) {
      // Reply immediately so it lands inside the node's 3 s window
      LoRa.beginPacket();
      LoRa.print(cmd);
      LoRa.endPacket();
      Serial.print("[TX->NODE] ");
      Serial.println(cmd);
    } else {
      Serial.println("[LISTEN] No scenarios armed - sending nothing.");
    }
  }

  LoRa.receive();   // back to listening
}