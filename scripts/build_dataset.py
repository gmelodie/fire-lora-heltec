#!/usr/bin/env python3
"""Label every stored reading with its experiment, physical node and position.

Reads data/readings_raw.json (a full dump of the API) and writes
data/readings_labelled.csv plus a per-run summary on stdout.
"""

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LOCAL_OFFSET = timedelta(hours=-3)  # Sao Carlos, no DST
GATEWAY = (-21.979322, -47.883435)

POSITIONS = {
    "A": (-21.9792439, -47.8843463),
    "B": (-21.9793505, -47.8841408),
    "C": (-21.9783096, -47.8844080),
    "D": (-21.9790620, -47.8840620),
    "E": (-21.9793889, -47.8841667),
    "home": None,
}

# One entry per deployment run. `sensor_id` is the byte the node happened to
# report; `node` is the physical board, which outlives any single id.
RUNS = [
    dict(experiment="F1", node="N1", sensor_id="1",   position="B",
         start="2026-04-28 15:41", end="2026-04-30 17:03",
         sf=7,  tx_dbm=14, interval_min=90, enclosure="sealed", site="field"),
    dict(experiment="F1", node="N2", sensor_id="15",  position="A",
         start="2026-04-28 15:34", end="2026-04-30 16:53",
         sf=7,  tx_dbm=14, interval_min=90, enclosure="sealed", site="field"),
    dict(experiment="I1", node="N1", sensor_id="1",   position="home",
         start="2026-05-01 02:11", end="2026-05-03 09:40",
         sf=7,  tx_dbm=14, interval_min=90, enclosure="sealed", site="indoor"),
    dict(experiment="I1", node="N2", sensor_id="2",   position="home",
         start="2026-05-01 02:10", end="2026-05-03 09:39",
         sf=7,  tx_dbm=14, interval_min=90, enclosure="sealed", site="indoor"),
    dict(experiment="I2", node="N3", sensor_id="3",   position="home",
         start="2026-05-15 01:16", end="2026-05-15 16:16",
         sf=10, tx_dbm=16, interval_min=90, enclosure="sealed", site="indoor"),
    dict(experiment="F2", node="N3", sensor_id="3",   position="C",
         start="2026-05-19 12:46", end="2026-05-24 02:53",
         sf=10, tx_dbm=16, interval_min=60, enclosure="sealed", site="field"),
    dict(experiment="F3", node="N4", sensor_id="67",  position="D",
         start="2026-07-08 19:19", end="2026-07-18 01:44",
         sf=11, tx_dbm=16, interval_min=60, enclosure="vented", site="field"),
    dict(experiment="F3", node="N5", sensor_id="222", position="E",
         start="2026-07-08 19:27", end="2026-07-09 23:37",
         sf=11, tx_dbm=16, interval_min=60, enclosure="vented", site="field"),
]

# Calendar span of each campaign, including its bench and deploy-mode packets.
CAMPAIGNS = [
    ("F1", "2026-04-26 00:00", "2026-04-30 23:59"),
    ("I1", "2026-05-01 00:00", "2026-05-03 23:59"),
    ("X", "2026-05-09 00:00", "2026-05-10 23:59"),
    ("I2", "2026-05-15 00:00", "2026-05-15 23:59"),
    ("F2", "2026-05-18 00:00", "2026-05-24 23:59"),
    ("F3", "2026-07-08 00:00", "2026-07-18 23:59"),
]

# Ids the same board reported after an EEPROM read returned a different byte. X is
# dropped from the analysis but its packets still belong to a known board.
ALIASES = {
    ("F1", "2"): "N2",
    ("X", "1"): "N3", ("X", "3"): "N3", ("X", "6"): "N3",
    ("F3", "70"): "N4", ("F3", "224"): "N5",
}


def node_lookup():
    """(experiment, sensor_id) -> physical node, covering bench packets too."""
    table = {(r["experiment"], r["sensor_id"]): r["node"] for r in RUNS}
    table.update(ALIASES)
    return table

FIELDS = [
    "timestamp", "datetime_utc", "datetime_local", "experiment", "node",
    "sensor_id", "position", "distance_m", "site", "enclosure", "sf", "tx_dbm",
    "interval_min", "counter", "rssi", "battery_pct", "temperature_c",
    "humidity_pct", "pressure_hpa", "t_valid", "rh_valid", "p_valid", "in_run",
]


def epoch(text):
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M")
               .replace(tzinfo=timezone.utc).timestamp())


def distance_m(pos):
    coords = POSITIONS.get(pos)
    if coords is None:
        return ""
    radius = 6371000.0
    lat1, lat2 = math.radians(GATEWAY[0]), math.radians(coords[0])
    dlat = lat2 - lat1
    dlon = math.radians(coords[1] - GATEWAY[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(h)), 1)


def validity(reading):
    t, rh, p = reading["temperature"], reading["humidity"], reading["pressure"]
    return (
        t is not None and -10 < t < 55,
        rh is not None and 0 < rh < 100,
        p is not None and 890 < p < 950,
    )


def matching_run(reading):
    for run in RUNS:
        if (reading["sensor_id"] == run["sensor_id"]
                and epoch(run["start"]) <= reading["timestamp"] <= epoch(run["end"])):
            return run
    return None


def campaign_of(reading):
    for name, start, end in CAMPAIGNS:
        if epoch(start) <= reading["timestamp"] <= epoch(end):
            return name
    return ""


def delivery_ratio(counters):
    """Fraction of expected counters that arrived, tolerating reboots."""
    seen = sorted(set(counters))
    segments, current = [], [seen[0]]
    for value in seen[1:]:
        if value > current[-1]:
            current.append(value)
        else:
            segments.append(current)
            current = [value]
    segments.append(current)
    expected = sum(s[-1] - s[0] + 1 for s in segments)
    return len(seen) / expected, expected - len(seen)


def main():
    readings = json.loads((DATA / "readings_raw.json").read_text())
    readings.sort(key=lambda r: r["timestamp"])
    nodes = node_lookup()

    out = []
    for reading in readings:
        run = matching_run(reading)
        in_run = run is not None
        campaign = run["experiment"] if run else campaign_of(reading)
        t_ok, rh_ok, p_ok = validity(reading)
        stamp = datetime.fromtimestamp(reading["timestamp"], timezone.utc)
        position = run["position"] if run else ""
        node = run["node"] if run else nodes.get((campaign, reading["sensor_id"]), "")
        out.append({
            "timestamp": reading["timestamp"],
            "datetime_utc": f"{stamp:%Y-%m-%d %H:%M:%S}",
            "datetime_local": f"{stamp + LOCAL_OFFSET:%Y-%m-%d %H:%M:%S}",
            "experiment": campaign,
            "node": node,
            "sensor_id": reading["sensor_id"],
            "position": position,
            "distance_m": distance_m(position) if position else "",
            "site": run["site"] if run else "bench",
            "enclosure": run["enclosure"] if run else "",
            "sf": run["sf"] if run else "",
            "tx_dbm": run["tx_dbm"] if run else "",
            "interval_min": run["interval_min"] if run else "",
            "counter": reading["counter"],
            "rssi": reading["rssi"],
            "battery_pct": reading["battery"],
            "temperature_c": reading["temperature"],
            "humidity_pct": reading["humidity"],
            "pressure_hpa": reading["pressure"],
            "t_valid": int(t_ok),
            "rh_valid": int(rh_ok),
            "p_valid": int(p_ok),
            "in_run": int(in_run),
        })

    target = DATA / "readings_labelled.csv"
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(out)
    print(f"wrote {target} ({len(out)} rows, {sum(r['in_run'] for r in out)} inside a run)")

    print(f"\n{'exp':<4}{'node':<5}{'id':>4}{'pos':>5}{'dist':>7}{'pkts':>6}"
          f"{'PDR%':>7}{'lost':>5}{'RSSI':>8}{'min':>6}{'bat':>10}{'%/h':>7}"
          f"{'T':>5}{'RH':>5}{'p':>5}")
    for run in RUNS:
        rows = [r for r in out
                if r["experiment"] == run["experiment"] and r["node"] == run["node"]
                and r["in_run"]]
        counters = [r["counter"] for r in rows]
        pdr, lost = delivery_ratio(counters)
        rssi = [r["rssi"] for r in rows]
        battery = [r["battery_pct"] for r in rows if r["battery_pct"] is not None]
        hours = (rows[-1]["timestamp"] - rows[0]["timestamp"]) / 3600
        rate = (battery[0] - battery[-1]) / hours if battery and hours else float("nan")
        print(f"{run['experiment']:<4}{run['node']:<5}{run['sensor_id']:>4}"
              f"{run['position']:>5}{distance_m(run['position']) or '-':>7}{len(rows):>6}"
              f"{100 * pdr:>7.1f}{lost:>5}{sum(rssi) / len(rssi):>8.1f}{min(rssi):>6}"
              f"{f'{battery[0]}->{battery[-1]}':>10}{rate:>7.3f}"
              f"{sum(r['t_valid'] for r in rows):>5}{sum(r['rh_valid'] for r in rows):>5}"
              f"{sum(r['p_valid'] for r in rows):>5}")


if __name__ == "__main__":
    main()
