#!/usr/bin/env python3
"""
Collects AWAKE_MS samples from the sensor over USB serial.
Usage: python3 collect_samples.py [port] [output_file]
  port:        serial port (default: /dev/ttyUSB0)
  output_file: where to save results (default: samples.txt)
"""

import sys
import serial

PORT       = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
OUTPUT     = sys.argv[2] if len(sys.argv) > 2 else "samples.txt"
NUM_SAMPLES = 30

samples = []

print(f"Listening on {PORT}, collecting {NUM_SAMPLES} samples → {OUTPUT}")
print("All serial output is shown. Waiting for AWAKE_MS lines...\n")

with serial.Serial(PORT, 115200, timeout=5) as ser:
    while len(samples) < NUM_SAMPLES:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="ignore").strip()
        print(line)
        if line.startswith("AWAKE_MS:"):
            ms = int(line.split(":")[1])
            samples.append(ms)
            print(f"  → sample {len(samples)}/{NUM_SAMPLES}: {ms} ms")

with open(OUTPUT, "w") as f:
    for ms in samples:
        f.write(f"{ms}\n")

avg = sum(samples) / len(samples)
print(f"\nDone. Average awake time: {avg:.0f} ms")
print(f"Results saved to {OUTPUT}")
