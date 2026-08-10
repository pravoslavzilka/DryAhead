// TEST: bare-minimum LoRa receive. Prints anything received with RSSI/SNR.
// No parsing, no protocol - just "can this board hear packets at all".

#include <SPI.h>
#include <LoRa.h>

#define LORA_SS    5
#define LORA_RST   27
#define LORA_DIO0  26

void setup() {
  pinMode(2, OUTPUT);
  digitalWrite(2, HIGH);
  delay(100);
  Serial.begin(115200);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(433E6)) { Serial.println("LoRa init failed!"); while (1); }
  Serial.println("Board 2 - Receiver ready");
}

void loop() {
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String data = "";
    while (LoRa.available()) data += (char)LoRa.read();

    int rssi = LoRa.packetRssi();
    float snr = LoRa.packetSnr();

    Serial.print("RX: ");   Serial.print(data);
    Serial.print("  | RSSI: "); Serial.print(rssi);
    Serial.print(" dBm SNR: ");  Serial.println(snr);
  }
}