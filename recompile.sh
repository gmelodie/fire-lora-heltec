#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "usage: ./recompile.sh <project> <port>"
    echo "example: ./recompile.sh sensor /dev/ttyUSB0"
    exit 1
fi

PROJECT=$1
PORT=$2
BOARD="esp32:esp32:heltec_wifi_lora_32_V3"

echo "Using board: $BOARD"
echo "Port: $PORT"

arduino-cli compile \
  --fqbn "$BOARD" \
  "$PROJECT" || exit 1

arduino-cli upload -p "$PORT" --fqbn "$BOARD" "$PROJECT" || exit 1
arduino-cli monitor -p "$PORT" -c baudrate=115200