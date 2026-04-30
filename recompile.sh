#!/bin/bash

usage() {
    echo "usage: ./recompile.sh <project> <port> [sensor_id]"
    echo "example: ./recompile.sh sensor /dev/ttyUSB0"
    echo "example: ./recompile.sh sensor /dev/ttyUSB0 3"
    echo "sensor_id must be between 1 and 254"
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    usage
    exit 1
fi

PROJECT=$1
PORT=$2
BOARD="esp32:esp32:heltec_wifi_lora_32_V3"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EXTRA_FLAGS=""
if [ "$#" -eq 3 ]; then
    SENSOR_ID=$3
    if ! [[ "$SENSOR_ID" =~ ^[0-9]+$ ]] || [ "$SENSOR_ID" -lt 1 ] || [ "$SENSOR_ID" -gt 254 ]; then
        echo "error: sensor_id must be a number between 1 and 254"
        exit 1
    fi
    EXTRA_FLAGS="--build-property compiler.cpp.extra_flags=-DSENSOR_ID=$SENSOR_ID"
    echo "Sensor ID: $SENSOR_ID"
fi

echo "Using board: $BOARD"
echo "Port: $PORT"

ln -sf "$REPO_ROOT/secrets.h" "$PROJECT/secrets.h"

arduino-cli compile \
  --fqbn "$BOARD" \
  $EXTRA_FLAGS \
  "$PROJECT" || exit 1

arduino-cli upload -p "$PORT" --fqbn "$BOARD" "$PROJECT" || exit 1
arduino-cli monitor -p "$PORT" -c baudrate=115200