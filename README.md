# Fire LoRa Heltec V3

Using LoRa Heltec V3 boards to detect wildfires in the Brazilian Cerrado.

> **Note:** All Arduino code targets Heltec V3 boards only.

## Architecture

```
[Sensor nodes]  --LoRa-->  [Heltec V3 gateway]  --UART-->  [Orange Pi Zero 2W]
                                                                     |
                                                              HTTP POST /sensor
                                                                     |
                                                            [FastAPI + PostgreSQL]
                                                                     |
                                                           http://host:8000  (dashboard)
```

## Firmware Setup (Arduino)

### 1. Install Arduino CLI

Follow the [official installation guide](https://docs.arduino.cc/arduino-cli/installation/).

### 2. Configure Arduino CLI

```bash
arduino-cli config init

# Add ESP32 board support
arduino-cli config add board_manager.additional_urls \
  https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32

# Install required libraries
arduino-cli lib install "Adafruit BME280 Library"
arduino-cli lib install "Adafruit Unified Sensor"
arduino-cli lib install "RadioLib"
```

### 3. Configure secrets

Copy `gateway/secrets.example.h` to `gateway/secrets.h` and fill in your values:

```c
#define WIFI_SSID     "your_wifi"
#define WIFI_PASS     "your_password"
#define API_PASSWORD  "your_api_password"   // must match API_PASSWORD in .env
#define API_URL       "http://192.168.x.x:8000"
```

## Server Setup (Docker)

The API and database run as Docker containers managed by `docker compose`.

### 1. Install Docker

Install [Docker Engine](https://docs.docker.com/engine/install/) with the Compose plugin.

### 2. Create the environment file

```bash
cp .env.example .env
```

Edit `.env` and set the two required values:

```
API_PASSWORD=your-api-password-here   # same value as in secrets.h
DB_PASSWORD=your-db-password-here

# Optional — defaults shown
# DB_NAME=sensor_db
# DB_USER=postgres
# API_PORT=8000
```

### 3. Build and start

```bash
docker compose up -d --build
```

The dashboard is available at `http://localhost:8000` (or replace `localhost` with the server's IP).

### Stop

```bash
docker compose down
```

### Update and restart (production)

```bash
./restart.sh
```

This pulls the latest code, rebuilds the API image, and restarts the containers with no downtime for the database.

### View logs

```bash
# All services
docker compose logs -f

# API only
docker compose logs -f api
```

## Dashboard

Navigate to `http://<host>:8000` and enter the API password.

| Section | Description |
|---|---|
| Current State | Live card per sensor — temperature, humidity, pressure, battery, RSSI, last seen. Refreshes every 30 s. |
| History | Select sensor, metric, and a time range to plot a time-series chart. |

## Orange Pi Gateway

The gateway script bridges the Heltec gateway board (UART) to the API.

```bash
cd pi-gateway
pip install -r requirements.txt
python3 gateway.py
```

## API Endpoints

All endpoints require the `X-API-Password` header.

| Method | Path | Description |
|---|---|---|
| `POST` | `/sensor` | Ingest a sensor reading |
| `GET` | `/sensors` | List distinct sensor IDs |
| `GET` | `/readings/latest` | Latest reading per sensor |
| `GET` | `/readings` | Historical readings — supports `sensor_id`, `from_ts`, `to_ts`, `limit` query params |
