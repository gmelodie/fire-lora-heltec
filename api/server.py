from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import psycopg2
import psycopg2.extras
import os
import time
import re
from pathlib import Path
from typing import Optional

app = FastAPI()

SECRETS_FILE = "../gateway/secrets.h"

# -------------------------
# Load password from env or secrets.h
# -------------------------

def load_password():
    env_pw = os.getenv("API_PASSWORD")
    if env_pw:
        return env_pw
    path = Path(SECRETS_FILE)
    if not path.exists():
        raise RuntimeError(f"API_PASSWORD env var not set and secrets file not found: {SECRETS_FILE}")
    content = path.read_text()
    match = re.search(r'#define\s+API_PASSWORD\s+"([^"]+)"', content)
    if not match:
        raise RuntimeError("API_PASSWORD not found in secrets.h")
    return match.group(1)

API_PASSWORD = load_password()

# -------------------------
# Database
# -------------------------

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "sensor_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
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
            id          SERIAL PRIMARY KEY,
            sensor_id   TEXT,
            temperature REAL,
            humidity    REAL,
            pressure    REAL,
            battery     INTEGER,
            counter     INTEGER,
            rssi        INTEGER,
            timestamp   INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

def insert_reading(data):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO readings (
            sensor_id,
            temperature,
            humidity,
            pressure,
            battery,
            counter,
            rssi,
            timestamp
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data["sensor_id"],
        float(data["temperature"]) if data["temperature"] is not None else None,
        float(data["humidity"])    if data["humidity"]    is not None else None,
        float(data["pressure"])    if data["pressure"]    is not None else None,
        int(data["battery"])       if data["battery"]     is not None else None,
        int(data["counter"]),
        int(data["rssi"]),
        int(time.time())
    ))
    conn.commit()
    conn.close()

# -------------------------
# Auth helper
# -------------------------

def require_auth(req: Request):
    if req.headers.get("X-API-Password") != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

# -------------------------
# Sensor Endpoint
# -------------------------

@app.post("/sensor")
async def receive_sensor(req: Request):
    require_auth(req)

    try:
        payload = await req.json()
    except:
        raise HTTPException(400, "Invalid JSON")

    required = ["sensor_id", "temperature", "humidity", "pressure", "battery", "counter", "rssi"]
    for f in required:
        if f not in payload:
            raise HTTPException(400, f"Missing {f}")

    insert_reading(payload)
    print("Sensor:", payload)
    return {"status": "ok"}

@app.get("/sensors")
async def get_sensors(req: Request):
    require_auth(req)

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT sensor_id FROM readings ORDER BY sensor_id")
    rows = cur.fetchall()
    conn.close()

    return {"sensors": [row[0] for row in rows]}

@app.get("/readings/latest")
async def get_latest_readings(req: Request):
    require_auth(req)

    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT DISTINCT ON (sensor_id)
            id, sensor_id, temperature, humidity, pressure,
            battery, counter, rssi, timestamp
        FROM readings
        ORDER BY sensor_id, timestamp DESC
    """)
    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]

@app.get("/readings")
async def get_readings(
    req: Request,
    sensor_id: Optional[str] = None,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    limit: int = 500,
):
    require_auth(req)

    conditions = []
    params = []
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
    params.append(min(limit, 2000))

    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"""
        SELECT id, sensor_id, temperature, humidity, pressure,
               battery, counter, rssi, timestamp
        FROM readings
        {where}
        ORDER BY timestamp ASC
        LIMIT %s
    """, params)
    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]

# -------------------------
# Dashboard
# -------------------------

@app.get("/")
async def dashboard():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
