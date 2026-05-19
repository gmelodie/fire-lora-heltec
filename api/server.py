from fastapi import FastAPI, Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from scalar_fastapi import get_scalar_api_reference
import psycopg2
import psycopg2.extras
import os
import time
import re
from pathlib import Path
from typing import Optional, List

# secrets.h is mounted at /secrets.h in Docker; fall back to ../secrets.h for local dev
_SECRETS_CANDIDATES = ["/secrets.h", "../secrets.h"]

def _find_secrets():
    for p in _SECRETS_CANDIDATES:
        path = Path(p)
        if path.exists():
            return path
    raise RuntimeError(f"secrets.h not found (tried: {_SECRETS_CANDIDATES})")

def _parse_define(content, name):
    match = re.search(rf'#define\s+{name}\s+"([^"]+)"', content)
    if not match:
        raise RuntimeError(f"{name} not found in secrets.h")
    return match.group(1)

_secrets_content = _find_secrets().read_text()
API_PASSWORD = os.getenv("API_PASSWORD") or _parse_define(_secrets_content, "API_PASSWORD")
_DB_PASSWORD  = os.getenv("DB_PASSWORD")  or _parse_define(_secrets_content, "DB_PASSWORD")

# -------------------------
# App / OpenAPI metadata
# -------------------------

tags_metadata = [
    {"name": "Readings", "description": "Query stored sensor readings."},
    {"name": "Sensors",  "description": "Discover known sensor IDs."},
    {"name": "Ingest",   "description": "Gateway-only endpoint that stores new readings."},
]

app = FastAPI(
    title="Fire LoRa Sensor API",
    description=(
        "REST API for the Fire LoRa Heltec V3 wildfire-detection network.\n\n"
        "All endpoints require the `X-API-Password` header. "
        "Interactive docs: [`/scalar`](/scalar) (Scalar) · [`/docs`](/docs) (Swagger UI) · "
        "[`/redoc`](/redoc) (ReDoc) · raw spec: [`/openapi.json`](/openapi.json) (OpenAPI 3.1)."
    ),
    version="1.0.0",
    openapi_tags=tags_metadata,
    license_info={"name": "MIT", "identifier": "MIT"},
    contact={"name": "fire-lora-heltec", "url": "https://github.com/gmelodie/fire-lora-heltec"},
)

# -------------------------
# Auth
# -------------------------

_api_key_header = APIKeyHeader(
    name="X-API-Password",
    description="Shared secret from `secrets.h`.",
    auto_error=False,
)

def require_auth(api_key: Optional[str] = Security(_api_key_header)):
    if api_key != API_PASSWORD:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")

# -------------------------
# Schemas
# -------------------------

class Reading(BaseModel):
    id: int = Field(..., description="Row ID (database-assigned).")
    sensor_id: str = Field(..., description="Sensor identifier.", examples=["1"])
    temperature: Optional[float] = Field(None, description="Air temperature (°C).")
    humidity: Optional[float] = Field(None, description="Relative humidity (%).")
    pressure: Optional[float] = Field(None, description="Atmospheric pressure (hPa).")
    battery: Optional[int] = Field(None, description="Sensor battery (mV).")
    camera_battery: Optional[int] = Field(None, description="Camera battery (mV), if equipped.")
    counter: int = Field(..., description="Monotonic packet counter from the sensor.")
    rssi: int = Field(..., description="Received signal strength at the gateway (dBm).")
    timestamp: int = Field(..., description="Unix epoch seconds when the gateway received the reading.")

class SensorsList(BaseModel):
    sensors: List[str] = Field(..., description="Distinct sensor IDs seen so far.")

class IngestPayload(BaseModel):
    sensor_id: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    battery: Optional[int] = None
    camera_battery: Optional[int] = None
    counter: int
    rssi: int

class StatusOk(BaseModel):
    status: str = Field("ok", examples=["ok"])

# -------------------------
# Database
# -------------------------

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname="sensor_db",
        user="postgres",
        password=_DB_PASSWORD,
    )

def init_db():
    for attempt in range(10):
        try:
            conn = get_db_conn()
            break
        except psycopg2.OperationalError:
            if attempt == 9:
                raise
            time.sleep(2)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id              SERIAL PRIMARY KEY,
            sensor_id       TEXT,
            temperature     REAL,
            humidity        REAL,
            pressure        REAL,
            battery         INTEGER,
            camera_battery  INTEGER,
            counter         INTEGER,
            rssi            INTEGER,
            timestamp       INTEGER
        )
    """)
    cur.execute("""
        ALTER TABLE readings
        ADD COLUMN IF NOT EXISTS camera_battery INTEGER
    """)
    conn.commit()
    conn.close()

init_db()

def insert_reading(data: IngestPayload):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO readings (
            sensor_id, temperature, humidity, pressure,
            battery, camera_battery, counter, rssi, timestamp
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data.sensor_id,
        data.temperature,
        data.humidity,
        data.pressure,
        data.battery,
        data.camera_battery,
        data.counter,
        data.rssi,
        int(time.time()),
    ))
    conn.commit()
    conn.close()

# -------------------------
# Endpoints
# -------------------------

@app.post(
    "/sensor",
    tags=["Ingest"],
    summary="Ingest a sensor reading",
    description="Called by the LoRa gateway each time it receives a packet from a sensor node.",
    response_model=StatusOk,
    dependencies=[Depends(require_auth)],
)
async def receive_sensor(payload: IngestPayload):
    insert_reading(payload)
    return StatusOk()

@app.get(
    "/sensors",
    tags=["Sensors"],
    summary="List sensor IDs",
    description="Returns every distinct `sensor_id` that has ever reported a reading.",
    response_model=SensorsList,
    dependencies=[Depends(require_auth)],
)
async def get_sensors():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT sensor_id FROM readings ORDER BY sensor_id")
    rows = cur.fetchall()
    conn.close()
    return SensorsList(sensors=[row[0] for row in rows])

@app.get(
    "/readings/latest",
    tags=["Readings"],
    summary="Latest reading per sensor",
    description="One row per sensor, picking the most recent reading by `timestamp`.",
    response_model=List[Reading],
    dependencies=[Depends(require_auth)],
)
async def get_latest_readings():
    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DISTINCT ON (sensor_id)
            id, sensor_id, temperature, humidity, pressure,
            battery, camera_battery, counter, rssi, timestamp
        FROM readings
        ORDER BY sensor_id, timestamp DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get(
    "/readings",
    tags=["Readings"],
    summary="Historical readings",
    description="Returns readings ordered oldest → newest. Filter by sensor and/or time window.",
    response_model=List[Reading],
    dependencies=[Depends(require_auth)],
)
async def get_readings(
    sensor_id: Optional[str] = Query(None, description="Restrict to one sensor."),
    from_ts: Optional[int]   = Query(None, description="Inclusive lower bound on `timestamp` (epoch seconds)."),
    to_ts:   Optional[int]   = Query(None, description="Inclusive upper bound on `timestamp` (epoch seconds)."),
    limit:   int             = Query(500, ge=1, le=2000, description="Max rows to return (hard cap 2000)."),
):
    conditions = []
    params: list = []
    if sensor_id is not None:
        conditions.append("sensor_id = %s")
        params.append(sensor_id)
    if from_ts is not None:
        conditions.append("timestamp >= %s")
        params.append(from_ts)
    if to_ts is not None:
        conditions.append("timestamp <= %s")
        params.append(to_ts)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"""
        SELECT id, sensor_id, temperature, humidity, pressure,
               battery, camera_battery, counter, rssi, timestamp
        FROM readings
        {where}
        ORDER BY timestamp ASC
        LIMIT %s
    """, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# -------------------------
# Dashboard (HTML — excluded from API docs)
# -------------------------

@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)

@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
