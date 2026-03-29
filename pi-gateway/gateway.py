#!/usr/bin/env python3
"""
Orange Pi Zero 2W gateway: reads JSON sensor payloads from the Heltec
gateway over UART2 (rx_2) and forwards them to the API via HTTPS POST.

Configuration is read from ../gateway/secrets.h and ../settings.h.
"""

import json
import logging
import re
import time
from pathlib import Path

import requests
import serial

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

REQUIRED_FIELDS = {"sensor_id", "temperature", "humidity", "pressure", "battery", "counter", "rssi"}

_HERE = Path(__file__).parent


def _parse_h_defines(path: Path) -> dict[str, str]:
    """Parse simple '#define KEY "value"' entries from a C header file."""
    defines: dict[str, str] = {}
    text = path.read_text()

    # Single-line string defines
    for m in re.finditer(r'#define\s+(\w+)\s+"([^"]*)"', text):
        defines[m.group(1)] = m.group(2)

    # Multi-line R"EOF(...)EOF" defines
    for m in re.finditer(r'(?:static\s+\S+\s+\*?)(\w+)\s*=\s*R"EOF\(([\s\S]*?)\)EOF"', text):
        defines[m.group(1)] = m.group(2)

    return defines


def _load_config() -> dict[str, str]:
    return _parse_h_defines(_HERE / "../gateway/secrets.h")


_CFG = _load_config()

API_URL      = _CFG.get("API_URL", "")
API_PASSWORD = _CFG.get("API_PASSWORD", "")
UART_DEV     = "/dev/ttyS2"
BAUD_RATE    = int(_CFG.get("UART_BAUD", "115200"))


def is_valid(data: dict) -> bool:
    return REQUIRED_FIELDS.issubset(data.keys())


def post_reading(payload: str) -> None:
    try:
        resp = requests.post(
            f"{API_URL}/sensor",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Password": API_PASSWORD,
            },
            verify=False,
            timeout=10,
        )
        log.info("POST %s -> %d", f"{API_URL}/sensor", resp.status_code)
    except requests.RequestException as exc:
        log.error("POST failed: %s", exc)


def main() -> None:
    log.info("Config: API_URL=%s UART=%s BAUD=%d", API_URL, UART_DEV, BAUD_RATE)
    with serial.Serial(UART_DEV, BAUD_RATE, timeout=1) as ser:
        log.info("Listening for sensor data...")
        while True:
            try:
                raw = ser.readline()
            except serial.SerialException as exc:
                log.error("Serial read error: %s", exc)
                time.sleep(1)
                continue

            if not raw:
                continue

            line = raw.decode("utf-8", errors="ignore").strip()
            line = line.replace(":nil", ":null")
            log.debug("UART raw: %s", line)
            if not line.startswith("{"):
                continue  # skip debug / non-JSON lines

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                log.warning("Corrupted JSON: %s", line)
                continue

            if not is_valid(data):
                log.warning("Missing fields, skipping: %s", data)
                continue

            log.info("Received: sensor=%s temp=%s hum=%s batt=%s rssi=%s",
                     data["sensor_id"], data["temperature"],
                     data["humidity"], data["battery"], data["rssi"])
            post_reading(line)


if __name__ == "__main__":
    main()
