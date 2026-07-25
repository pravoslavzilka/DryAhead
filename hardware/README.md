# hardware

The physical design of a field sensor node: the electronics circuit and the enclosure it lives
in. This is the domain that `firmware/` runs on top of.

- **`circuit/`** — the KiCad schematic and PCB layout: ESP32 module, LoRa (SX127x) radio, soil
  moisture sensor interface, DS3231 RTC, and power/battery circuitry.
- **`enclosure/`** — CAD/STL files for the physical housing that protects the electronics in the
  field (e.g. mounted on/near an irrigation pipe) and the antenna mount.
- **`bom.csv`** — the bill of materials: every part used, so a node can be built or re-ordered.

Design files here are binary (KiCad project files, STEP/STL exports) and tracked with git-lfs —
see `.gitattributes` at the repo root.
