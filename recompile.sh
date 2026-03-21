#!/bin/bash

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "usage: ./recompile.sh <project> <port> [battery_available]"
    echo "example: ./recompile.sh sensor /dev/ttyUSB0 1"
    exit 1
fi

PROJECT=$1
PORT=$2
BATTERY_AVAILABLE=${3:-0}
BOARD="esp32:esp32:heltec_wifi_lora_32_V3"

if [ "$BATTERY_AVAILABLE" != "0" ] && [ "$BATTERY_AVAILABLE" != "1" ]; then
    echo "battery_available must be 0 or 1"
    exit 1
fi

echo "Using board: $BOARD"
echo "Port: $PORT"
echo "BATTERY_AVAILABLE: $BATTERY_AVAILABLE"

arduino-cli compile \
  --fqbn "$BOARD" \
  --build-property "compiler.cpp.extra_flags=-DBATTERY_AVAILABLE=$BATTERY_AVAILABLE" \
  "$PROJECT" || exit 1

arduino-cli upload -p "$PORT" --fqbn "$BOARD" "$PROJECT" || exit 1
arduino-cli monitor -p "$PORT" -c baudrate=115200