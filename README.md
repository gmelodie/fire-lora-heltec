# Fire LoRa Heltec V3

Using LoRa Heltec V3 boards to detect wildfires in the Brazilian Cerrado.

> **Note:** All Arduino code targets Heltec V3 boards only.

## Architecture

```
[Sensor nodes]  --LoRa-->  [Heltec V3 gateway]  --HTTPS POST-->  [FastAPI + PostgreSQL]
                                                                          |
                                                               http://host:8000  (dashboard)
```

The gateway board posts sensor readings directly to the API over HTTPS — no intermediate Pi needed.

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
arduino-cli lib install "ESP8266 and ESP32 OLED driver for SSD1306 displays"
```

### 3. Configure secrets

Copy `gateway/secrets.example.h` to `gateway/secrets.h` and fill in your values:

```c
// ── Regular WPA2 (home / office router) ───────────────────────────────────
#define WIFI_SSID "your_wifi"
#define WIFI_PASS "your_password"

// ── Eduroam / WPA2-Enterprise ──────────────────────────────────────────────
// Uncomment USE_EAP and fill in the three EAP fields instead.
// #define USE_EAP
// #define EAP_IDENTITY "user@university.edu"
// #define EAP_USERNAME "user@university.edu"
// #define EAP_PASSWORD "your_eap_password"

// ── API ────────────────────────────────────────────────────────────────────
#define API_PASSWORD "your_password"   // must match API_PASSWORD in .env
#define API_URL "https://192.168.x.x:8443"

/* Root certificate for the API server (PEM format) */
static const char *API_CERT PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
...your cert here...
-----END CERTIFICATE-----
)EOF";
```

### 4. Compile and upload

Use `recompile.sh` to compile and flash a sketch:

```bash
./recompile.sh <project> <port>
```

| Argument | Description |
|---|---|
| `project` | `sensor` or `gateway` |
| `port` | Serial port, e.g. `/dev/ttyUSB0` |

Examples:

```bash
./recompile.sh gateway /dev/ttyUSB0
./recompile.sh sensor /dev/ttyUSB0
```

After flashing, `recompile.sh` opens a serial monitor at 115200 baud automatically.

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

## API Endpoints

All endpoints require the `X-API-Password` header.

| Method | Path | Description |
|---|---|---|
| `POST` | `/sensor` | Ingest a sensor reading |
| `GET` | `/sensors` | List distinct sensor IDs |
| `GET` | `/readings/latest` | Latest reading per sensor |
| `GET` | `/readings` | Historical readings — supports `sensor_id`, `from_ts`, `to_ts`, `limit` query params |

## Utilities

### Measure sensor awake time

`sensor/collect_samples.py` reads `AWAKE_MS` lines from the sensor over USB serial and computes the average awake duration (useful for tuning deep-sleep power budgets):

```bash
python3 sensor/collect_samples.py [port] [output_file]
# default port: /dev/ttyUSB0
# default output: samples.txt
```

It collects 30 samples and prints the average awake time in milliseconds.

## Orange Pi Gateway (legacy)

`pi-gateway/gateway.py` is retained for reference. It was the original bridge between the Heltec gateway board (via UART) and the API, superseded by direct HTTPS posting from the gateway board itself.
