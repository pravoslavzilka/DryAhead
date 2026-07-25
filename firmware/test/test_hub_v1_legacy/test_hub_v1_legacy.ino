/*
 * LEGACY REFERENCE - superseded by ../../hub/hub.ino
 *
 * NOT compatible with the current nodes: this only listens and prints,
 * it never replies, so it won't serve TIME/GETDATA/CFG to
 * ../../nodes/node_with_rtc/ or ../../nodes/node_no_rtc/. Its counterpart
 * is ../test_node_with_rtc_v1_legacy/.
 *
 * BASE RECEIVER (Hub)
 * Listens on LoRa 433 MHz and prints all received messages to serial.
 *
 * Board: LaskaKit ESP32-DEVKit (or any ESP32 + Ra-02)
 * REMEMBER: GPIO2 HIGH powers the 3.3V peripheral rail
 *
 * Wiring (Ra-02):
 *   SCK=18, MISO=19, MOSI=23, NSS=5, RST=27, DIO0=26, 3.3V, GND
 *
 * Expects sensor packets in CSV format:
 *   id,moisture%,raw,temperatureC,epoch
 */

#include <SPI.h>
#include <LoRa.h>

#define PERIPH_POWER  2
#define LORA_SS    5
#define LORA_RST   27
#define LORA_DIO0  26

unsigned long packetCount = 0;

void setup() {
  pinMode(PERIPH_POWER, OUTPUT);
  digitalWrite(PERIPH_POWER, HIGH);   // power the Ra-02
  delay(200);

  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== LoRa Base Receiver ===");
  Serial.println("Listening on 433 MHz...\n");

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(433E6)) {
    Serial.println("ERROR: LoRa init failed! Check wiring/antenna.");
    while (1);
  }
  Serial.println("Receiver ready.\n");
}

void loop() {
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    // Read the raw message
    String data = "";
    while (LoRa.available()) {
      data += (char)LoRa.read();
    }

    int rssi = LoRa.packetRssi();
    float snr = LoRa.packetSnr();
    packetCount++;

    // --- Print the raw packet + signal info ---
    Serial.println("----------------------------------------");
    Serial.print("Packet #");
    Serial.print(packetCount);
    Serial.print("  | RSSI: ");
    Serial.print(rssi);
    Serial.print(" dBm | SNR: ");
    Serial.print(snr);
    Serial.println(" dB");
    Serial.print("Raw: ");
    Serial.println(data);

    // --- Try to parse the CSV: id,moisture,raw,temp,epoch ---
    parseAndPrint(data);

    Serial.println();
  }
}

// Splits the CSV message and prints each field nicely.
// Falls back to raw display if the format doesn't match.
void parseAndPrint(String data) {
  // Count commas to check it looks like our format
  int commas = 0;
  for (unsigned int i = 0; i < data.length(); i++) {
    if (data.charAt(i) == ',') commas++;
  }

  if (commas != 4) {
    Serial.println("(unrecognized format - shown raw above)");
    return;
  }

  // Extract the 5 fields
  int i1 = data.indexOf(',');
  int i2 = data.indexOf(',', i1 + 1);
  int i3 = data.indexOf(',', i2 + 1);
  int i4 = data.indexOf(',', i3 + 1);

  String nodeId   = data.substring(0, i1);
  String moisture = data.substring(i1 + 1, i2);
  String raw      = data.substring(i2 + 1, i3);
  String temp     = data.substring(i3 + 1, i4);
  String epoch    = data.substring(i4 + 1);

  Serial.print("  Node ID:    "); Serial.println(nodeId);
  Serial.print("  Moisture:   "); Serial.print(moisture); Serial.println(" %");
  Serial.print("  Raw ADC:    "); Serial.println(raw);
  Serial.print("  Temp:       "); Serial.print(temp); Serial.println(" C");
  Serial.print("  Timestamp:  "); Serial.print(epoch); Serial.println(" (unix epoch)");
}