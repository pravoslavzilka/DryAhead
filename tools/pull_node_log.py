#!/usr/bin/env python3
"""Pull the LittleFS log off a DryAhead node connected over USB.

Read-only: uses esptool `read_flash` to copy the node's filesystem partition
to the computer, then unpacks it locally. Nothing is written to the ESP32 and
the deployed firmware stays as-is. The board is reset afterwards and resumes
its normal cycle.

Setup:   pip install esptool littlefs-python
Usage:   python tools/pull_node_log.py --port COM5
         python tools/pull_node_log.py --port COM5 --out node4_dump

Output folder gets every file from the node's filesystem (log.csv, and the
clock file on node_no_rtc), plus log_readable.csv with a header row and
human-readable UTC timestamps.
"""
import argparse
import csv
import datetime as dt
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from littlefs import LittleFS

PARTITION_TABLE_OFFSET = 0x8000
PARTITION_TABLE_SIZE = 0xC00
BLOCK_SIZE = 4096
DATA_TYPE = 0x01
FS_SUBTYPES = (0x82, 0x83)  # spiffs (Arduino's LittleFS label), littlefs


def read_flash(port: str, baud: int, offset: int, size: int, dest: Path) -> bytes:
    cmd = [sys.executable, "-m", "esptool", "--port", port, "--baud", str(baud),
           "read_flash", hex(offset), hex(size), str(dest)]
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)
    return dest.read_bytes()


def find_fs_partition(table: bytes) -> tuple[int, int, str]:
    for i in range(0, len(table), 32):
        entry = table[i:i + 32]
        magic, ptype, subtype, offset, size, label = struct.unpack("<HBBII16s", entry[:28])
        if magic != 0x50AA:
            break
        if ptype == DATA_TYPE and subtype in FS_SUBTYPES:
            return offset, size, label.rstrip(b"\x00").decode(errors="replace")
    raise SystemExit("No spiffs/littlefs data partition found in the partition table.")


def extract(image: bytes, out_dir: Path) -> list[Path]:
    fs = LittleFS(block_size=BLOCK_SIZE, block_count=len(image) // BLOCK_SIZE, mount=False)
    fs.context.buffer = bytearray(image)
    fs.mount()
    written = []
    for root, _dirs, files in fs.walk("/"):
        for name in files:
            src = f"{root.rstrip('/')}/{name}"
            dest = out_dir / src.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with fs.open(src, "rb") as f:
                dest.write_bytes(f.read())
            written.append(dest)
    return written


def write_readable(log_path: Path, out_path: Path) -> int:
    rows = 0
    with log_path.open(newline="") as src, out_path.open("w", newline="") as dst:
        w = csv.writer(dst)
        w.writerow(["node_id", "moisture_raw", "temperature_c", "epoch", "time_utc"])
        for line in csv.reader(src):
            if len(line) < 4:
                continue
            try:
                ts = dt.datetime.fromtimestamp(int(line[3]), dt.timezone.utc).isoformat()
            except ValueError:
                ts = ""
            w.writerow(line[:4] + [ts])
            rows += 1
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True, help="Serial port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--out", type=Path, default=None, help="Output folder (default: node_dump_<timestamp>)")
    args = ap.parse_args()

    out_dir = args.out or Path(f"node_dump_{dt.datetime.now():%Y%m%d_%H%M%S}")
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        table = read_flash(args.port, args.baud, PARTITION_TABLE_OFFSET, PARTITION_TABLE_SIZE, tmp / "pt.bin")
        offset, size, label = find_fs_partition(table)
        print(f"Filesystem partition '{label}' at {offset:#x}, {size // 1024} KB")
        image = read_flash(args.port, args.baud, offset, size, tmp / "fs.bin")

    (out_dir / "fs_image.bin").write_bytes(image)  # raw backup of the partition
    files = extract(image, out_dir)
    for f in files:
        print(f"  extracted {f} ({f.stat().st_size} bytes)")

    log = out_dir / "log.csv"
    if log.exists():
        n = write_readable(log, out_dir / "log_readable.csv")
        print(f"{n} readings -> {out_dir / 'log_readable.csv'}")
    else:
        print("No /log.csv on this node.")


if __name__ == "__main__":
    main()
