#!/bin/bash

usage() {
    echo "usage: ./recompile.sh <project> <port> [sensor_id] [--camera]"
    echo "example: ./recompile.sh sensor /dev/ttyUSB0"
    echo "example: ./recompile.sh sensor /dev/ttyUSB0 3"
    echo "example: ./recompile.sh sensor /dev/ttyUSB0 3 --camera"
    echo "example: ./recompile.sh sensor /dev/ttyUSB0 --camera"
    echo "sensor_id must be between 1 and 254"
}

CAMERA=0
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--camera" ]; then
        CAMERA=1
    else
        ARGS+=("$arg")
    fi
done

if [ "${#ARGS[@]}" -lt 2 ] || [ "${#ARGS[@]}" -gt 3 ]; then
    usage
    exit 1
fi

PROJECT=${ARGS[0]}
PORT=${ARGS[1]}
BOARD="esp32:esp32:heltec_wifi_lora_32_V3"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EXTRA_DEFINES=""
if [ "${#ARGS[@]}" -eq 3 ]; then
    SENSOR_ID=${ARGS[2]}
    if ! [[ "$SENSOR_ID" =~ ^[0-9]+$ ]] || [ "$SENSOR_ID" -lt 1 ] || [ "$SENSOR_ID" -gt 254 ]; then
        echo "error: sensor_id must be a number between 1 and 254"
        exit 1
    fi
    EXTRA_DEFINES="-DSENSOR_ID=$SENSOR_ID"
    echo "Sensor ID: $SENSOR_ID"
fi

if [ "$CAMERA" -eq 1 ]; then
    EXTRA_DEFINES="$EXTRA_DEFINES -DCAMERA"
    echo "Camera: enabled"
fi

EXTRA_FLAGS=()
if [ -n "$EXTRA_DEFINES" ]; then
    EXTRA_FLAGS=("--build-property" "compiler.cpp.extra_flags=${EXTRA_DEFINES# }")
fi

echo "Using board: $BOARD"
echo "Port: $PORT"

ln -sf "$REPO_ROOT/secrets.h" "$PROJECT/secrets.h"

arduino-cli compile \
  --fqbn "$BOARD" \
  "${EXTRA_FLAGS[@]}" \
  "$PROJECT" || exit 1

arduino-cli upload -p "$PORT" --fqbn "$BOARD" "$PROJECT" || exit 1
arduino-cli monitor -p "$PORT" -c baudrate=115200