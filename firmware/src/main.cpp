#include <Arduino.h>

// Packet layout (what goes into the LoRa payload below) is defined in
// contracts/telemetry.md — read it before changing anything here, and keep
// backend/ in sync with any change to the layout.

void setup() {
  Serial.begin(115200);

  // TODO: init RTC (DS3231)
  // TODO: init LoRa radio (SX127x)
  // TODO: init soil moisture sensor ADC input
}

void loop() {
  // TODO: read soil moisture + RTC timestamp
  // TODO: pack reading per contracts/telemetry.md
  // TODO: send over LoRa
  // TODO: sleep until next reading interval
}
