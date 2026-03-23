# Fire LoRa Heltec V3

Using LoRa Heltec V3 boards to detect wildfires in the brazilian Cerrado
Obs: all code works in V3 boards only

## TODO
sensor
- press button to change sensor ID
- show new sensor id on screen
- turn off sensor screen 5s after last button press
- deep sleep mode between transmissions

gateway
- connect to eduroam
    - maybe cable + raspberry pi?
    - maybe a version that doesnt require internet connection?
    - maybe raspberry pi at the same local network as the gateway?

## Setup
1. [Install](https://docs.arduino.cc/arduino-cli/installation/) the Arduino CLI
2. Setup Arduino CLI:
```bash
arduino-cli config init
# add esp32 board repo
arduino-cli config add board_manager.additional_urls \
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32
# install libs
arduino-cli lib install "Adafruit BME280 Library"
arduino-cli lib install "Adafruit Unified Sensor"
arduino-cli lib install "RadioLib"
```
3. Change `./gateway/secrets.example.h` to `./gateway/secrets.h` and fill it with actual values.

**Obs:** The api code fetches the `API_PASSWORD` and `API_URL` string on the `secrets.h` file, so make sure that is set even though you're not compiling the sensor code.
**Obs2:** You'll have to generate the API's `cert.pem` and put that in `secrets.h` too:
```bash
cd api
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```
4. Change API_URL in server.h

## Run the API server
```bash
cd api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

uvicorn server:app \
--host 0.0.0.0 \
--port 8443 \
--ssl-keyfile key.pem \
--ssl-certfile cert.pem
```



