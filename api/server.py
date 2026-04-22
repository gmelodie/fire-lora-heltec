from fastapi import FastAPI, Request, HTTPException
import psycopg2
import psycopg2.extras
import os
import time
import re
from pathlib import Path

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
# Sensor Endpoint
# -------------------------

@app.post("/sensor")
async def receive_sensor(req: Request):
    password = req.headers.get("X-API-Password")
    if password != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

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

@app.get("/readings")
async def get_readings(req: Request):
    password = req.headers.get("X-API-Password")
    if password != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT * FROM readings
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]
