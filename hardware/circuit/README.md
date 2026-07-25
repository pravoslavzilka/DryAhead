# circuit

KiCad schematic and PCB design for the sensor node board: ESP32 (LaskaKit ESP32-DevKit), the
SX127x LoRa radio module, soil moisture sensor input, a DS3231 RTC for timestamping readings, and
the battery/power supply circuit.

Put the KiCad project files here (`.kicad_pro`, `.kicad_sch`, `.kicad_pcb`). These are tracked
with git-lfs (see the root `.gitattributes`) since they're binary and change as a whole on every
edit.

This talks to `firmware/` in one direction (firmware assumes specific pins/peripherals this
circuit provides) and to `hardware/bom.csv` for the parts list.
