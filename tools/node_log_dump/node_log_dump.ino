/*
 *  node_log_dump.ino - read a DryAhead node's stored data over USB serial
 *
 *  Flash this temporarily onto a node (ESP32) to get its LittleFS files
 *  (/log.csv, clock file) onto the computer via Serial Monitor.
 *
 *  !! This REPLACES the node's firmware. The stored data survives only if
 *     you upload with the SAME partition scheme the node firmware used
 *     (Arduino IDE: Tools > Partition Scheme, normally "Default 4MB with
 *     spiffs"). Reflash the node sketch (with the right NODE_ID) afterwards.
 *
 *  Read-only: never formats or writes the filesystem. If mounting fails it
 *  stops and reports, instead of formatting like the node sketches do.
 *
 *  Board: ESP32 Dev Module. Serial Monitor: 115200 baud, newline ending.
 *  Commands:
 *    h  help
 *    i  filesystem info (total / used bytes)
 *    l  list files
 *    d  dump /log.csv
 *    a  dump every file
 */
#include <LittleFS.h>

#define PERIPH_POWER 2   // keep LoRa / sensor / RTC unpowered while dumping

const char* LOG_FILE = "/log.csv";
bool fsOK = false;

void printHelp() {
  Serial.println(F("Commands: h=help  i=info  l=list  d=dump /log.csv  a=dump all files"));
}

void printInfo() {
  Serial.print(F("[FS] total bytes: ")); Serial.println(LittleFS.totalBytes());
  Serial.print(F("[FS] used bytes:  ")); Serial.println(LittleFS.usedBytes());
}

void listFiles() {
  File root = LittleFS.open("/");
  File f = root.openNextFile();
  int count = 0;
  while (f) {
    Serial.print(f.isDirectory() ? F("  [dir] ") : F("  "));
    Serial.print(f.path());
    Serial.print(F("  "));
    Serial.print(f.size());
    Serial.println(F(" bytes"));
    count++;
    f = root.openNextFile();
  }
  Serial.print(F("[FS] ")); Serial.print(count); Serial.println(F(" entr(ies)"));
}

// Markers let a script (or you) cut the file contents out of the serial log.
void dumpFile(const char* path) {
  File f = LittleFS.open(path, FILE_READ);
  if (!f || f.isDirectory()) {
    Serial.print(F("[ERR] cannot open ")); Serial.println(path);
    return;
  }
  Serial.print(F("===BEGIN ")); Serial.print(path);
  Serial.print(F(" size=")); Serial.print(f.size()); Serial.println(F("==="));

  uint8_t buf[256];
  int last = '\n';
  while (f.available()) {
    size_t n = f.read(buf, sizeof(buf));
    Serial.write(buf, n);
    if (n > 0) last = buf[n - 1];
  }
  f.close();
  if (last != '\n') Serial.println();
  Serial.println(F("===END==="));
}

void dumpAll() {
  File root = LittleFS.open("/");
  File f = root.openNextFile();
  while (f) {
    if (!f.isDirectory()) {
      String path = f.path();
      f.close();
      dumpFile(path.c_str());
    }
    f = root.openNextFile();
  }
}

void setup() {
  pinMode(PERIPH_POWER, OUTPUT);
  digitalWrite(PERIPH_POWER, LOW);

  Serial.begin(115200);
  delay(1500);  // give Serial Monitor time to attach
  Serial.println();
  Serial.println(F("=== DryAhead node log dump ==="));

  fsOK = LittleFS.begin(false);  // false = never format
  if (!fsOK) {
    Serial.println(F("[ERR] LittleFS mount failed. Not formatting."));
    Serial.println(F("      Check Tools > Partition Scheme matches the node firmware."));
    return;
  }
  printInfo();
  listFiles();
  printHelp();
}

void loop() {
  if (!fsOK || !Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case 'h': printHelp(); break;
    case 'i': printInfo(); break;
    case 'l': listFiles(); break;
    case 'd': dumpFile(LOG_FILE); break;
    case 'a': dumpAll(); break;
    default: break;  // ignore newlines etc.
  }
}
