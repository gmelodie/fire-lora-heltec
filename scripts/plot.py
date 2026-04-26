#!/usr/bin/env python3
"""Query the fire-sensor API and plot time-series graphs."""

import argparse
import os
import sys
import warnings
from datetime import datetime, timezone
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import urllib3  # noqa: F401 (imported for disable_warnings)

METRICS = ["temperature", "humidity", "pressure", "battery", "rssi"]
UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "pressure": "hPa",
    "battery": "%",
    "rssi": "dBm",
}


def parse_ts(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Unrecognised date/time: {s!r}  (use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")


def api_get(host, password, path, params=None, verify=True):
    url = host + path
    try:
        r = requests.get(url, headers={"X-API-Password": password}, params=params,
                         timeout=15, verify=verify)
    except requests.exceptions.SSLError:
        sys.exit(
            f"SSL certificate verification failed for {host}.\n"
            "If the server uses a self-signed cert, add --no-verify to skip verification."
        )
    except requests.ConnectionError:
        sys.exit(f"Cannot connect to {host}")
    if r.status_code == 401:
        sys.exit("Unauthorized — check your password")
    r.raise_for_status()
    return r.json()


def fetch_readings(host, password, sensor_id, from_ts, to_ts, limit, verify):
    params = {"sensor_id": sensor_id, "limit": limit}
    if from_ts:
        params["from_ts"] = from_ts
    if to_ts:
        params["to_ts"] = to_ts
    return api_get(host, password, "/readings", params, verify=verify)


def main():
    parser = argparse.ArgumentParser(description="Plot sensor readings from the API")
    parser.add_argument("--host", default=os.getenv("API_URL"), help="API base URL (or set API_URL)")
    parser.add_argument("--password", default=os.getenv("API_PASSWORD"), help="API password (or set API_PASSWORD)")
    parser.add_argument("--sensor", help="Sensor ID (default: all sensors)")
    parser.add_argument("--metric", choices=METRICS, help="Metric to plot (default: all)")
    parser.add_argument("--from", dest="from_ts", type=parse_ts, metavar="DATE", help="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
    parser.add_argument("--to", dest="to_ts", type=parse_ts, metavar="DATE", help="End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
    parser.add_argument("--limit", type=int, default=2000, help="Max readings per sensor (default: 2000)")
    parser.add_argument("--no-verify", dest="no_verify", action="store_true", help="Skip SSL certificate verification (for self-signed certs)")
    parser.add_argument("--out", metavar="FILE", help="Save to file instead of showing interactively")
    args = parser.parse_args()

    if not args.host:
        sys.exit("Provide --host or set API_URL")
    if not args.password:
        sys.exit("Provide --password or set API_PASSWORD")

    host = args.host.rstrip("/")
    verify = not args.no_verify

    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    metrics = [args.metric] if args.metric else METRICS

    if args.sensor:
        sensor_ids = [args.sensor]
    else:
        data = api_get(host, args.password, "/sensor", verify=verify)
        sensor_ids = data.get("sensors", [])
        if not sensor_ids:
            sys.exit("No sensors found")

    all_readings = {}
    for sid in sensor_ids:
        rows = fetch_readings(host, args.password, sid, args.from_ts, args.to_ts, args.limit, verify)
        if rows:
            all_readings[sid] = rows

    if not all_readings:
        sys.exit("No readings returned for the given filters")

    fig, axes = plt.subplots(len(metrics), 1, figsize=(12, 3 * len(metrics)), sharex=True)
    if len(metrics) == 1:
        axes = [axes]

    fig.suptitle("Sensor readings", fontsize=13)

    for ax, metric in zip(axes, metrics):
        for sid, rows in all_readings.items():
            times = []
            values = []
            for r in rows:
                if r.get(metric) is not None:
                    times.append(datetime.fromtimestamp(r["timestamp"]))
                    values.append(r[metric])
            if times:
                ax.plot(times, values, marker=".", markersize=3, linewidth=1, label=f"Sensor {sid}")

        ax.set_ylabel(f"{metric}\n({UNITS[metric]})", fontsize=9)
        ax.grid(True, alpha=0.3)
        if all_readings:
            ax.legend(fontsize=8)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate()
    plt.tight_layout()

    if args.out:
        plt.savefig(args.out, dpi=150)
        print(f"Saved to {args.out}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
