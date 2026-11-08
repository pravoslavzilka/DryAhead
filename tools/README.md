# tools

Bench tools for getting a node's stored data onto a computer over USB. Each node logs
every reading to LittleFS (`/log.csv`, `node_id,raw,temperature,epoch` per line), so a
node brought in from the field can be backfilled even when the radio missed readings.

## Download mode

Both tools need the ESP32 in download mode. On the LaskaKit ESP32-DEVKit, auto-reset
over USB is unreliable and the board's only button is a user button on **GPIO17**, not
BOOT. Jumper **GPIO0 → GND** (GPIO0 is between GPIO4 and GPIO2), press EN, run the tool,
then remove the jumper and press EN.

## `node_log_dump/` — Arduino IDE sketch

Flash it temporarily onto the node; it prints the filesystem over serial (115200 baud).
Commands: `h` help, `i` info, `l` list, `d` dump `/log.csv`, `a` dump every file. Each
file is printed between `===BEGIN <path> size=N===` and `===END===` markers.

- **Replaces the node firmware.** Upload with the same Partition Scheme the node used
  (normally "Default 4MB with spiffs") or the data won't mount. Reflash the node sketch
  with the right `NODE_ID` afterwards.
- Read-only: mounts with `LittleFS.begin(false)`, so it never formats, and keeps
  `PERIPH_POWER` (GPIO2) low.

## `pull_node_log.py` — read-only, no reflash

```
pip install esptool littlefs-python
python tools/pull_node_log.py --port COM4
```

Reads the partition table and the filesystem partition with `esptool read_flash`, then
unpacks it locally into `node_dump_<timestamp>/`: every file, `log_readable.csv`
(header + UTC times) and `fs_image.bin` (raw backup). Nothing is written to the ESP32,
so the deployed firmware stays as-is.

## After a dump

Dumps go under `node_dumps/`. Before uploading to Supabase, drop what's already there:
nodes log two readings 8–13 s apart in most slots, and `readings` has a unique
`(node_id, recorded_at)` key, so epoch-0 readings can't be uploaded individually.
`node_dumps/node3_20261011_192633/` has the node 3 example: `upload_clean.csv` (the 505
readings uploaded) and `uploaded_ids.json` (their row ids).
