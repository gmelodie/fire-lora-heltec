#!/usr/bin/env python3
"""Compute Brazilian fire-danger indices from each data source.

Sources form a granularity ladder: the deployed node, the INMET A711 station
120 m away, the ERA5 reanalysis grid and the NASA POWER grid. Writes
data/fire_indices.csv.

Index references
  FMA      Soares (1972). FMA = sum(100 / H13) with rainfall restrictions.
  FMA+     Nunes, Soares, Batista (2006). Adds a wind term. PROVISIONAL, see
           FMA_PLUS_NOTE.
  Angstrom Angstrom (1942). I = H/20 + (27 - T)/10, not cumulative.
  Telicyn  I = sum(log10(T13 - Td13)), reset by rain >= 2.5 mm.
  Nesterov G = sum(d * T13), d = E(1 - H/100) in mb, with rainfall restrictions.
"""

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LOCAL = timezone(timedelta(hours=-3))
INDEX_HOUR = 13  # local time at which every index samples its inputs

FMA_PLUS_NOTE = (
    "daily term (100/H) * exp(0.04 * v), v in m/s; confirm against Nunes (2005) "
    "before publication"
)


def saturation_pressure_mb(t_c):
    """Tetens equation, millibars."""
    return 6.1078 * 10 ** (7.5 * t_c / (237.3 + t_c))


def dew_point_c(t_c, rh):
    a, b = 17.62, 243.12
    g = math.log(min(rh, 100.0) / 100.0) + a * t_c / (b + t_c)
    return b * g / (a - g)


# ---------------------------------------------------------------- data loading

def load_inmet():
    """A711 hourly record keyed by UTC epoch."""
    columns = {"prec": 2, "T": 7, "Td": 8, "RH": 15, "wind": 18}
    series = {}
    text = (DATA / "inmet_a711_2026.csv").read_text(encoding="latin-1")
    for line in text.splitlines()[9:]:
        cells = line.split(";")
        if len(cells) < 19:
            continue
        day = datetime.strptime(cells[0].strip(), "%Y/%m/%d").replace(tzinfo=timezone.utc)
        stamp = day + timedelta(hours=int(cells[1].strip()[:2]))
        record = {}
        for name, position in columns.items():
            raw = cells[position].strip().replace(",", ".")
            record[name] = None if raw in ("", "-9999") else float(raw)
        series[int(stamp.timestamp())] = record
    return series


def load_era5():
    """ERA5 at its native 0.25 deg grid, via the Open-Meteo archive.

    The endpoint must be called with models=era5; its default best_match blend
    serves a downscaled product on a different grid. ERA5 publishes with a lag,
    so the final days of the window come back null and are dropped.
    """
    raw = json.loads((DATA / "era5_openmeteo.json").read_text())["hourly"]
    series = {}
    for i, moment in enumerate(raw["time"]):
        wind = raw["wind_speed_10m"][i]
        record = {
            "T": raw["temperature_2m"][i],
            "RH": raw["relative_humidity_2m"][i],
            "Td": raw["dew_point_2m"][i],
            "prec": raw["precipitation"][i],
            "wind": wind / 3.6 if wind is not None else None,  # km/h to m/s
        }
        if record["T"] is None or record["RH"] is None:
            continue
        stamp = datetime.fromisoformat(moment).replace(tzinfo=timezone.utc)
        series[int(stamp.timestamp())] = record
    return series


def load_power():
    """NASA POWER hourly.

    Two traps. The API reports `time_standard: LST`, so the hour field is local
    solar time rather than UTC; at this longitude that is 11 minutes from local
    standard time, so we read it as UTC-3. And PRECTOTCORR is documented in
    mm/day, so each hourly figure is a rate and the daily total is their mean,
    not their sum.
    """
    raw = json.loads((DATA / "nasa_power.json").read_text())["properties"]["parameter"]
    series = {}
    for key in raw["T2M"]:
        stamp = datetime.strptime(key, "%Y%m%d%H").replace(tzinfo=LOCAL)
        series[int(stamp.timestamp())] = {
            "T": raw["T2M"][key],
            "RH": raw["RH2M"][key],
            "Td": raw["T2MDEW"][key],
            "prec": raw["PRECTOTCORR"][key],
            "wind": raw["WS10M"][key],
        }
    return series


def load_node():
    """Node readings per experiment, valid deployment packets only."""
    series = {}
    with (DATA / "readings_labelled.csv").open() as handle:
        for row in csv.DictReader(handle):
            if row["in_run"] != "1" or row["site"] != "field":
                continue
            if not (row["t_valid"] == "1" and row["rh_valid"] == "1"):
                continue
            key = f"node_{row['experiment']}"
            temperature = float(row["temperature_c"])
            humidity = float(row["humidity_pct"])
            series.setdefault(key, {})[int(row["timestamp"])] = {
                "T": temperature,
                "RH": humidity,
                "Td": dew_point_c(temperature, humidity),
                "prec": None,  # the node has no rain gauge
                "wind": None,  # nor an anemometer
            }
    return series


# ------------------------------------------------------------ daily extraction

def local_day(epoch_seconds):
    return datetime.fromtimestamp(epoch_seconds, LOCAL).date()


def sample_at_index_hour(series, day, tolerance_minutes=30):
    """Reading closest to 13:00 local on `day`, or None."""
    target = datetime.combine(day, datetime.min.time(), LOCAL).replace(hour=INDEX_HOUR)
    target_epoch = int(target.timestamp())
    window = tolerance_minutes * 60
    best, best_gap = None, window + 1
    for stamp, record in series.items():
        gap = abs(stamp - target_epoch)
        if gap <= window and gap < best_gap:
            best, best_gap = record, gap
    return best


def daily_rain(series, day, mode="sum"):
    """Daily total in mm. `mode` is "mean" when the source reports a rate."""
    values = [record["prec"] for stamp, record in series.items()
              if local_day(stamp) == day and record.get("prec") is not None]
    if not values:
        return None
    return sum(values) / len(values) if mode == "mean" else sum(values)


def daily_frame(series, days, rain_source=None, wind_source=None, rain_mode="sum"):
    """One row per day: the 13:00 sample plus rain, borrowing where needed."""
    frame = []
    for day in days:
        sample = sample_at_index_hour(series, day)
        if sample is None:
            frame.append(None)
            continue
        rain = daily_rain(series, day, rain_mode)
        if rain is None and rain_source is not None:
            rain = daily_rain(rain_source, day)
        wind = sample.get("wind")
        if wind is None and wind_source is not None:
            borrowed = sample_at_index_hour(wind_source, day)
            wind = borrowed["wind"] if borrowed else None
        frame.append({
            "day": day, "T": sample["T"], "RH": sample["RH"],
            "Td": sample.get("Td"), "rain": rain, "wind": wind,
        })
    return frame


# -------------------------------------------------------------------- indices

def fma_carry(rain):
    """Multiplier applied to yesterday's accumulation (Soares 1972)."""
    if rain is None or rain <= 2.4:
        return 1.0
    if rain <= 4.9:
        return 0.7
    if rain <= 9.9:
        return 0.4
    if rain <= 12.9:
        return 0.2
    return None  # >12.9 mm: stop the sum, today contributes nothing


def nesterov_carry(rain):
    if rain is None or rain <= 2.0:
        return 1.0
    if rain <= 5.0:
        return 0.75
    if rain <= 8.0:
        return 0.5
    if rain <= 10.0:
        return 0.0  # restart from today's term alone
    return None


def accumulate(frame, term, carry, seed=0.0):
    """Walk the days applying a cumulative index with rainfall restrictions.

    `seed` carries the accumulation a node inherits from the dry spell that ran
    before it was installed. Without it a node that joins an ongoing dry spell
    starts from zero and reads far lower than a station that has been counting
    for weeks.
    """
    values, total = [], seed
    for row in frame:
        if row is None:
            values.append(None)
            continue
        factor = carry(row["rain"])
        if factor is None:
            total = 0.0
            values.append(0.0)
            continue
        today = term(row)
        total = total * factor + (today if today is not None else 0.0)
        values.append(total)
    return values


def fma(frame, seed=0.0):
    return accumulate(frame, lambda r: 100.0 / r["RH"] if r["RH"] else None,
                      fma_carry, seed)


def fma_plus(frame, seed=0.0):
    def term(row):
        if row["RH"] is None or row["wind"] is None:
            return None
        return (100.0 / row["RH"]) * math.exp(0.04 * row["wind"])
    return accumulate(frame, term, fma_carry, seed)


def angstrom(frame, seed=0.0):
    """Not cumulative, so the seed is ignored. Lower values mean higher danger."""
    return [None if r is None else r["RH"] / 20.0 + (27.0 - r["T"]) / 10.0 for r in frame]


def telicyn(frame, seed=0.0):
    def term(row):
        spread = row["T"] - row["Td"]
        return math.log10(spread) if spread > 1.0 else 0.0
    return accumulate(frame, term,
                      lambda rain: None if (rain or 0) >= 2.5 else 1.0, seed)


def nesterov(frame, seed=0.0):
    def term(row):
        deficit = saturation_pressure_mb(row["T"]) * (1.0 - row["RH"] / 100.0)
        return deficit * row["T"]
    return accumulate(frame, term, nesterov_carry, seed)


INDICES = {
    "FMA": fma, "FMA+": fma_plus, "Angstrom": angstrom,
    "Telicyn": telicyn, "Nesterov": nesterov,
}

CLASSES = {
    "FMA": [(1.0, "None"), (3.0, "Low"), (8.0, "Medium"), (20.0, "High"),
            (math.inf, "Very high")],
    "Telicyn": [(2.0, "None"), (3.5, "Low"), (5.0, "Medium"), (math.inf, "High")],
    "Nesterov": [(300.0, "None"), (500.0, "Low"), (1000.0, "Medium"),
                 (4000.0, "High"), (math.inf, "Very high")],
    # Angstrom runs the other way: smaller means more dangerous.
    "Angstrom": [(2.5, "High"), (3.0, "Moderate"), (math.inf, "Low")],
}


def danger_class(index, value):
    if value is None or index not in CLASSES:
        return ""
    for bound, label in CLASSES[index]:
        if value <= bound:
            return label
    return ""


# ----------------------------------------------------------------- calibration

def hourly_dew_offset(node_series, reference, hour):
    """Mean (node dew point - reference dew point) at one local hour.

    Derived against A711, so a calibrated node is not an independent check on
    A711. It stays informative against the reanalysis grids.
    """
    gaps = []
    for stamp, record in node_series.items():
        if datetime.fromtimestamp(stamp, LOCAL).hour != hour:
            continue
        match = reference.get(round(stamp / 3600) * 3600)
        if match and match.get("Td") is not None and record.get("Td") is not None:
            gaps.append(record["Td"] - match["Td"])
    return sum(gaps) / len(gaps) if gaps else None


def calibrated(node_series, offset):
    """Remove the enclosure moisture bias, keeping the node's own temperature."""
    out = {}
    for stamp, record in node_series.items():
        dew = record["Td"] - offset
        dew = min(dew, record["T"])
        humidity = 100.0 * saturation_pressure_mb(dew) / saturation_pressure_mb(record["T"])
        out[stamp] = dict(record, Td=dew, RH=max(1.0, min(100.0, humidity)))
    return out


# ------------------------------------------------------------------- pipeline

def main():
    inmet, era5, power = load_inmet(), load_era5(), load_power()
    nodes = load_node()

    calibrations = {}
    for name, series in list(nodes.items()):
        offset = hourly_dew_offset(series, inmet, INDEX_HOUR)
        if offset is None:
            continue
        calibrations[f"{name}_cal"] = offset
        nodes[f"{name}_cal"] = calibrated(series, offset)

    sources = {"inmet": inmet, "era5": era5, "power": power}
    sources.update(nodes)
    rain_modes = {"power": "mean"}

    start, end = datetime(2026, 4, 1).date(), datetime(2026, 7, 31).date()
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    baseline = daily_frame(inmet, days)
    seeds = {index: function(baseline) for index, function in INDICES.items()}

    rows = []
    for name, series in sources.items():
        is_node = name.startswith("node_")
        frame = daily_frame(
            series, days,
            rain_source=inmet if is_node else None,
            wind_source=inmet if is_node else None,
            rain_mode=rain_modes.get(name, "sum"),
        )
        seed = {index: 0.0 for index in INDICES}
        if is_node:
            first = next((i for i, row in enumerate(frame) if row is not None), None)
            if first:
                for index in INDICES:
                    prior = seeds[index][first - 1]
                    seed[index] = prior if prior is not None else 0.0
        computed = {index: function(frame, seed[index])
                    for index, function in INDICES.items()}
        for position, row in enumerate(frame):
            if row is None:
                continue
            record = {
                "source": name, "day": row["day"].isoformat(),
                "is_node": int(is_node),
                "T13": round(row["T"], 2), "RH13": round(row["RH"], 2),
                "Td13": round(row["Td"], 2) if row["Td"] is not None else "",
                "wind13": round(row["wind"], 2) if row["wind"] is not None else "",
                "rain": round(row["rain"], 1) if row["rain"] is not None else "",
            }
            for index in INDICES:
                value = computed[index][position]
                record[index] = round(value, 3) if value is not None else ""
                record[f"{index}_class"] = danger_class(index, value)
            rows.append(record)

    rows.sort(key=lambda r: (r["day"], r["source"]))
    target = DATA / "fire_indices.csv"
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {target} ({len(rows)} rows)")
    print(f"FMA+ note: {FMA_PLUS_NOTE}")
    for name, offset in calibrations.items():
        print(f"calibration {name}: dew point at {INDEX_HOUR}:00 local "
              f"reduced by {offset:.2f} C")

    for name in sources:
        count = sum(1 for r in rows if r["source"] == name)
        print(f"  {name:<16} {count:>3} days")


if __name__ == "__main__":
    main()
