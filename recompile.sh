#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "usage: ./recompile.sh sensor /dev/ttyUSBX"
    exit 1
fi

PROJECT=$1
PORT=$2

if [ "$PORT" = "/dev/ttyUSB0" ]; then
    BOARD="esp32:esp32:heltec_wifi_lora_32_V2"
elif [ "$PORT" = "/dev/ttyUSB1" ]; then
    BOARD="esp32:esp32:heltec_wifi_lora_32_V3"
else
    echo "Unknown port: $PORT"
    exit 1
fi

echo "Using board: $BOARD"
echo "Port: $PORT"

arduino-cli compile --fqbn $BOARD $PROJECT || exit 1
arduino-cli upload -p $PORT --fqbn $BOARD $PROJECT || exit 1
arduino-cli monitor -p $PORT -c baudrate=115200
