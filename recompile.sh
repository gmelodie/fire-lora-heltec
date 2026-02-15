if [ "$#" -ne 2 ]; then
    echo "usage: ./recompile.sh sensor /dev/ttyUSB0"
    exit 1
fi

arduino-cli compile --fqbn esp32:esp32:heltec_wifi_lora_32_V2 $1

arduino-cli upload -p $2 --fqbn esp32:esp32:heltec_wifi_lora_32_V2 $1

arduino-cli monitor -p $2 -c baudrate=115200
