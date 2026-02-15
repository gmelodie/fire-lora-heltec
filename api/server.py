from fastapi import FastAPI, Request, HTTPException
import sqlite3
import time
import re
from pathlib import Path

app = FastAPI()
DB_FILE = "sensor_data.db"
SECRETS_FILE = "../gateway/secrets.h"

# -------------------------
# Load password from secrets.h
# -------------------------
def load_password():
    path = Path(SECRETS_FILE)

    if not path.exists():
        raise RuntimeError(f"Secrets file not found: {SECRETS_FILE}")

    content = path.read_text()

    match = re.search(r'#define\s+API_PASSWORD\s+"([^"]+)"', content)

    if not match:
        raise RuntimeError("API_PASSWORD not found in secrets.h")

    return match.group(1)


API_PASSWORD = load_password()

# -------------------------
# Database
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT,
            temperature REAL,
            humidity REAL,
            pressure REAL,
            counter INTEGER,
            rssi INTEGER,
            timestamp INTEGER
        )
    """)

    conn.commit()
    conn.close()


init_db()


def insert_reading(data):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO readings (
            sensor_id,
            temperature,
            humidity,
            pressure,
            counter,
            rssi,
            timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data["sensor_id"],
        float(data["temperature"]),
        float(data["humidity"]),
        float(data["pressure"]),
        int(data["counter"]),
        int(data["rssi"]),
        int(time.time())
    ))

    conn.commit()
    conn.close()


# -------------------------
# Endpoint
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

    required = [
        "sensor_id",
        "temperature",
        "humidity",
        "pressure",
        "counter",
        "rssi"
    ]

    for f in required:
        if f not in payload:
            raise HTTPException(400, f"Missing {f}")

    insert_reading(payload)

    print("Received:", payload)

    return {"status": "ok"}

