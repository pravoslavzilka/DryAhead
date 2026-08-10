// TEST: field range check. Flash to a portable receiver, walk around the
// planned node locations, and watch for RSSI/SNR + "no signal" warnings to
// find dead zones before a node is permanently deployed there.

#include <SPI.h>
#include <LoRa.h>

#define LORA_SS    5
#define LORA_RST   27
#define LORA_DIO0  26

unsigned long lastRx = 0;

void setup() {
  pinMode(2, OUTPUT);
  digitalWrite(2, HIGH);
  delay(100);
  Serial.begin(115200);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(433E6)) { Serial.println("LoRa init failed!"); while(1); }
  Serial.println("FIELD RECEIVER - walk to each node location...");
}

void loop() {
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String data = "";
    while (LoRa.available()) data += (char)LoRa.read();
    lastRx = millis();
    Serial.print("GOT: "); Serial.print(data);
    Serial.print("  | RSSI: "); Serial.print(LoRa.packetRssi());
    Serial.print(" dBm | SNR: "); Serial.println(LoRa.packetSnr());
  }

  // Warn if no signal for 5 seconds (you've gone out of range)
  if (millis() - lastRx > 5000) {
    Serial.println("... no signal (out of range or blocked) ...");
    lastRx = millis();   // reset so it warns every 5s
  }
}