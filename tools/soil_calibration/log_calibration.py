#!/usr/bin/env python3
"""Serial logger for the soil calibration rig (tools/soil_calibration).

Replaces the Arduino Serial Monitor: shows everything the board prints, lets you
type commands (t, s2, w75, g641.3, m, ...), and automatically appends every
"CSV," line to a .csv file, so there is nothing to copy by hand.

    python tools/soil_calibration/log_calibration.py --port COM4

Close the Arduino Serial Monitor first - only one program can hold the port.
Files (default folder tools/soil_calibration/data/):
    soil_cal_<date>.csv   one row per measurement (appended, survives restarts)
    soil_cal_<date>.log   full timestamped transcript (settling info etc.)
Stop with Ctrl+C.
"""
import argparse
import datetime as dt
import pathlib
import sys
import threading

import serial
import serial.tools.list_ports

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_HEADER = ("sensor,rep,water_ml,mass_g,settled,settle_s,mean_raw,median_raw,"
                  "std_raw,min_raw,max_raw,slope_raw_per_min,mean_mV,n")


class Recorder:
    """Turns lines from the board into CSV rows + a transcript."""

    def __init__(self, csv_path: pathlib.Path, log_path: pathlib.Path):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path, self.log_path = csv_path, log_path
        self.header_written = csv_path.exists() and csv_path.stat().st_size > 0
        self.rows = 0

    def _append(self, path: pathlib.Path, text: str) -> None:
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write(text)  # open/close per write: nothing lost if the PC crashes

    def handle(self, line: str) -> None:
        now = dt.datetime.now().isoformat(timespec="seconds")
        self._append(self.log_path, f"{now}  {line}\n")
        if not line.startswith("CSV,"):
            return
        body = line[4:].strip()
        if body.startswith("sensor,"):            # the board's header line
            if not self.header_written:
                self._append(self.csv_path, f"logged_at,{body}\n")
                self.header_written = True
            return
        if not body or not body[0].isdigit():
            return
        if not self.header_written:
            self._append(self.csv_path, f"logged_at,{DEFAULT_HEADER}\n")
            self.header_written = True
        self._append(self.csv_path, f"{now},{body}\n")
        self.rows += 1
        print(f"      >>> saved row #{self.rows} to {self.csv_path.name}")


def pick_port(requested):
    if requested:
        return requested
    ports = list(serial.tools.list_ports.comports())
    if len(ports) == 1:
        return ports[0].device
    print("Specify --port. Available ports:")
    for p in ports:
        print(f"  {p.device}  {p.description}")
    sys.exit(2)


def main() -> None:
    today = dt.date.today().isoformat()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", help="serial port, e.g. COM4")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", type=pathlib.Path,
                    default=HERE / "data" / f"soil_cal_{today}.csv", help="output CSV path")
    args = ap.parse_args()

    rec = Recorder(args.out, args.out.with_suffix(".log"))
    port = pick_port(args.port)

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, args.baud, 0.2
    ser.dtr = False   # keep these low BEFORE opening, so connecting does not
    ser.rts = False   # reset the board (that would wipe sensor/water settings)
    ser.open()

    print(f"Connected to {port}. CSV -> {args.out}")
    print("Type commands and press Enter (h = help). Ctrl+C to quit.\n")

    def send_typed():
        for typed in sys.stdin:
            ser.write((typed.strip() + "\n").encode())

    threading.Thread(target=send_typed, daemon=True).start()

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            print(line)
            rec.handle(line)
    except KeyboardInterrupt:
        print(f"\nStopped. {rec.rows} rows saved this session -> {args.out}")
    except serial.SerialException as e:
        print(f"\nSerial connection lost: {e}\n{rec.rows} rows saved -> {args.out}")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
