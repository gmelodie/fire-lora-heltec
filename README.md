# Fire LoRa Heltec V3

Using LoRa Heltec V3 boards to detect wildfires in the Brazilian Cerrado.

> **Note:** All Arduino code targets Heltec V3 boards only.

## Architecture

```
[Sensor nodes]  --LoRa-->  [Heltec V3 gateway]  --HTTPS POST-->  [FastAPI + PostgreSQL]
                                                                          |
                                                     https://cerrado.gmelodie.com  (public site)
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

All secrets live in a single file at the repo root. Copy the example and fill in your values:

```bash
cp secrets.example.h secrets.h
```

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
#define API_PASSWORD "your_api_password"
#define API_URL "https://192.168.x.x:8443"

// ── Database ───────────────────────────────────────────────────────────────
#define DB_PASSWORD "your_db_password"

/* Root certificate for the API server (PEM format) */
static const char *API_CERT PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
...your cert here...
-----END CERTIFICATE-----
)EOF";
```

The firmware, API server, and startup script all read from this one file.

### 4. Compile and upload

Use `recompile.sh` to compile and flash a sketch:

```bash
./recompile.sh <project> <port> [sensor_id] [--camera]
```

| Argument | Description |
|---|---|
| `project` | `sensor` or `gateway` |
| `port` | Serial port, e.g. `/dev/ttyUSB0` |
| `sensor_id` | Optional. Integer 1–254, sets `SENSOR_ID` at build time |
| `--camera` | Optional. Enables camera support (`-DCAMERA`) |

Examples:

```bash
./recompile.sh gateway /dev/ttyUSB0
./recompile.sh sensor /dev/ttyUSB0
./recompile.sh sensor /dev/ttyUSB0 3
./recompile.sh sensor /dev/ttyUSB0 3 --camera
./recompile.sh sensor /dev/ttyUSB0 --camera
```

After flashing, `recompile.sh` opens a serial monitor at 115200 baud automatically.

## Server Setup (Docker)

The API and database run as Docker containers managed by `docker compose`.

### 1. Install Docker

Install [Docker Engine](https://docs.docker.com/engine/install/) with the Compose plugin.

### 2. Build and start

Ensure `secrets.h` exists at the repo root (see Firmware Setup step 3), then:

```bash
./start.sh
```

The public site is available at `http://localhost:8000` and the dashboard at
`http://localhost:8000/dashboard` (or replace `localhost` with the server's IP).

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

## Web pages

| URL | Access | Content |
|---|---|---|
| `/` | public | Site map over satellite imagery: live node state, plus a time scrubber that replays each field campaign |
| `/dashboard` | API password | Live card per sensor and time-series charts of every metric, refreshed every 30 s |

The public page reads `static/deployments.json`, which holds the node positions, the campaign
windows and the per-field validity flags. Update that file when a node moves or a new sensor id
appears.

## API Endpoints

Every read endpoint is public. `POST /sensor` and `GET /auth/check` require the
`X-API-Password` header.

| Method | Path | Description |
|---|---|---|
| `POST` | `/sensor` | Ingest a sensor reading |
| `GET` | `/auth/check` | Validate the API password (used by the dashboard login) |
| `GET` | `/sensors` | List distinct sensor IDs |
| `GET` | `/readings/latest` | Latest reading per sensor |
| `GET` | `/readings` | Historical readings — supports `sensor_id`, `from_ts`, `to_ts`, `limit` query params |

### Interactive docs

The API publishes an **OpenAPI 3.1** spec, with two built-in UIs:

| URL | Description |
|---|---|
| `/scalar` | Scalar — modern UI with a built-in API client (recommended) |
| `/docs` | Swagger UI — click *Authorize* and paste the API password |
| `/redoc` | ReDoc — read-only, prints nicely |
| `/openapi.json` | Raw OpenAPI 3.1 spec (machine-readable; feed it to a client generator) |

## Utilities

### Firmware unit tests

The pure helpers in `sensor/sensor_math.h` (gateway-lost backoff, battery OCV curve) run on the
host, with no board attached:

```bash
./tests/run.sh
```

### Plot sensor data

`scripts/plot.py` queries the API and produces time-series charts for any sensor/metric combination.

```bash
cd scripts
pip install -r requirements.txt

# All sensors, all metrics, interactive window
python3 plot.py --host https://192.168.x.x:8443 --password yourpassword --no-verify

# One sensor, one metric, saved to file
python3 plot.py --host https://192.168.x.x:8443 --password yourpassword --no-verify \
  --sensor 1 --metric temperature \
  --from 2024-01-01 --to 2024-01-07 \
  --out week.png
```

| Flag | Default | Description |
|---|---|---|
| `--host` | `$API_URL` | API base URL |
| `--password` | `$API_PASSWORD` | API password |
| `--sensor` | all sensors | Filter to one sensor ID |
| `--metric` | all metrics | One of `temperature`, `humidity`, `pressure`, `battery`, `rssi` |
| `--from` | — | Start date `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS` |
| `--to` | — | End date (same format) |
| `--limit` | 2000 | Max readings per sensor |
| `--no-verify` | off | Skip SSL certificate verification (use with self-signed certs) |
| `--out` | — | Save to file instead of opening interactively |

`--host` and `--password` can also be set via the `API_URL` and `API_PASSWORD` environment variables.

### Measure sensor awake time

`sensor/collect_samples.py` reads `AWAKE_MS` lines from the sensor over USB serial and computes the average awake duration (useful for tuning deep-sleep power budgets):

```bash
python3 sensor/collect_samples.py [port] [output_file]
# default port: /dev/ttyUSB0
# default output: samples.txt
```

It collects 30 samples and prints the average awake time in milliseconds.

## Public HTTPS (Let's Encrypt)

The public server answers on port 443 with a certificate from Let's Encrypt. uvicorn terminates
TLS itself, so there is no reverse proxy. Port 8443 keeps its own listener on the same
certificate, which lets the gateway boards keep their current `API_URL` with no re-flash.

A `certbot` container issues the certificate and renews it twice a day, sharing the
`letsencrypt` volume with the API container. It holds port 80 for the ACME challenge, so nothing
else on the host may listen there.

### 1. Point DNS at the server

Create an `A` record for `cerrado.gmelodie.com`, then open both ports:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### 2. Switch compose to the production overlay

```bash
cp .env.example .env      # then set LETSENCRYPT_EMAIL
./restart.sh
```

`.env` sets `COMPOSE_FILE` to `docker-compose.yml:docker-compose.prod.yml`, plus `DOMAIN` and
`LETSENCRYPT_EMAIL`. Every `docker compose` command in this README then picks the overlay up on
its own, including `./start.sh` and `./restart.sh`. A machine without `.env` keeps the
self-signed certificate on 8443, which is what a laptop wants.

The overlay adds the certbot container, publishes port 443, and points uvicorn at
`/etc/letsencrypt/live/$DOMAIN/`. The database volume is untouched: only the API container is
recreated.

### 3. Watch the first issuance

```bash
docker compose logs -f certbot
curl https://cerrado.gmelodie.com/readings/latest
```

The API starts before the certificate exists. It waits up to five minutes for the file, and
serves the self-signed pair if certbot is still failing, so the site stays reachable on 8443
while you fix DNS. When certbot writes or renews the certificate, `api/entrypoint.sh` notices the
change within an hour and exits, and the restart policy brings uvicorn back on the new file.

Renewal failures repeat every 10 minutes rather than in a tight loop, because Let's Encrypt
counts failures per hour. Check with:

```bash
docker compose exec certbot certbot certificates
```

## Self-signed certificate (LAN only)

On a server with no domain name, uvicorn falls back to a self-signed pair. Generate it:

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem \
  -days 3650 -nodes \
  -subj "/CN=fire-sensor-api" \
  -addext "subjectAltName=IP:<your-server-ip>"
```

Then paste the contents of `cert.pem` into the `API_CERT` field in `secrets.h`. The gateway board uses it to verify the server's identity.

`cert.pem` and `key.pem` must be present at the repo root when starting the server. They are mounted into the API container automatically, and both are gitignored (`*.pem`). Keep them even on the public server: the base compose file mounts them, and uvicorn ignores them once `SSL_CERTFILE` points at the Let's Encrypt copy.

## Orange Pi Gateway (legacy)

`pi-gateway/gateway.py` is retained for reference. It was the original bridge between the Heltec gateway board (via UART) and the API, superseded by direct HTTPS posting from the gateway board itself.
