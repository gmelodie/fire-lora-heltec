#!/usr/bin/env python3
"""Render the paper figures into figures/ as vector PDFs.

Run with the repo venv: ./scripts/venv/bin/python scripts/make_figures.py
"""

import csv
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)

# Validated categorical slots (light mode, all-pairs clean). Colour follows the
# entity: a calibrated node keeps the node's hue and changes line style.
NODE = "#2a78d6"
INMET = "#eb6834"
ERA5 = "#1baf7a"
POWER = "#4a3aa7"

INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#dcdcd8"
BAND = "#f0ece6"

SOURCE_STYLE = {
    "node": (NODE, "-", "Sensor node"),
    "node_cal": (NODE, "--", "Sensor node, calibrated"),
    "inmet": (INMET, "-", "INMET A711 (120 m)"),
    "era5": (ERA5, "-", "ERA5 (0.25°, ~28 km)"),
    "power": (POWER, "-", "NASA POWER (~50 km)"),
}

COLUMN, FULL = 3.5, 7.16
LOCAL = timezone(timedelta(hours=-3))

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 7.5,
    "axes.labelsize": 8,
    "axes.titlesize": 8.5,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK,
    "axes.linewidth": 0.7,
    "xtick.color": INK2, "ytick.color": INK2,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "grid.color": GRID, "grid.linewidth": 0.6,
    "figure.dpi": 200,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


def save(fig, name):
    """Vector PDF for LaTeX, PNG alongside for visual inspection."""
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png", dpi=220)


def tidy(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(True, axis="y", alpha=0.7)
    ax.set_axisbelow(True)


def load_indices():
    rows = list(csv.DictReader((DATA / "fire_indices.csv").open()))
    for row in rows:
        row["date"] = date.fromisoformat(row["day"])
    return rows


def load_readings():
    rows = list(csv.DictReader((DATA / "readings_labelled.csv").open()))
    return [r for r in rows if r["in_run"] == "1"]


def number(text):
    return float(text) if text not in ("", None) else None


# --------------------------------------------------------------- figure 1

FMA_BANDS = [(0, 1.0, "None"), (1.0, 3.0, "Low"), (3.0, 8.0, "Medium"),
             (8.0, 20.0, "High"), (20.0, 60.0, "Very high")]


# (campaign span, span with a working environmental sensor). In F3 only node
# N5 carried a BME280 and it lasted 28 h, so the index can only be evaluated
# on one day even though the campaign ran for nine.
DEPLOYMENTS = [(date(2026, 5, 19), date(2026, 5, 24),
                date(2026, 5, 19), date(2026, 5, 23), "F2"),
               (date(2026, 7, 8), date(2026, 7, 18),
                date(2026, 7, 8), date(2026, 7, 9), "F3")]


def figure_season(rows):
    """FMA across the whole record, from each public source, node days marked.

    No danger-class bands here: FMA reaches 94 while the top class starts at 20,
    so banding would paint most of the panel one colour. Classes are compared in
    the Angstrom figure instead.
    """
    fig, ax = plt.subplots(figsize=(FULL, 1.95))

    for start, end, sens_start, sens_end, label in DEPLOYMENTS:
        ax.axvspan(start, end, color=BAND, alpha=0.55, lw=0, zorder=0)
        ax.axvspan(sens_start, sens_end, color=BAND, alpha=1.0, lw=0, zorder=0)
        ax.text(start + (end - start) / 2, 93, label, ha="center", va="top",
                fontsize=6.6, color=INK2, zorder=3)

    for key in ("inmet", "era5", "power"):
        colour, style, label = SOURCE_STYLE[key]
        series = sorted((r for r in rows if r["source"] == key), key=lambda r: r["date"])
        xs = [r["date"] for r in series]
        ys = [number(r["FMA"]) for r in series]
        ax.plot(xs, ys, color=colour, ls=style, lw=1.0, label=label, zorder=4,
                solid_capstyle="round")

    node = sorted((r for r in rows if r["source"].startswith("node")
                   and not r["source"].endswith("_cal")), key=lambda r: r["date"])
    ax.plot([r["date"] for r in node], [number(r["FMA"]) for r in node],
            ls="none", marker="o", ms=4.6, mfc=NODE, mec="white", mew=0.9,
            zorder=6, label=SOURCE_STYLE["node"][2])

    # The 18 May divergence is explained in the caption rather than on the panel;
    # every in-figure position for that much text collides with a series.
    ax.annotate("", xy=(date(2026, 5, 18), 5.85), xytext=(date(2026, 5, 18), 0.1),
                arrowprops=dict(arrowstyle="<->", lw=0.7, color=INK, shrinkA=0,
                                shrinkB=0), zorder=7)
    ax.annotate("18 May: 13.8 mm at A711 resets FMA to 0;\n"
                "ERA5 records 5.5 mm and holds at 5.9",
                xy=(date(2026, 5, 20), 7), xytext=(date(2026, 5, 25), 76),
                fontsize=6.4, color=INK, va="center", ha="left",
                linespacing=1.35, zorder=8,
                arrowprops=dict(arrowstyle="-", lw=0.6, color=INK2,
                                connectionstyle="arc3,rad=0.10"))

    ax.set_ylabel("Monte Alegre Formula (FMA)")
    ax.set_xlim(date(2026, 4, 1), date(2026, 7, 31))
    ax.set_ylim(0, 96)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    tidy(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=False,
              ncol=4, handlelength=1.8, columnspacing=1.8)
    save(fig, "fma_season")
    plt.close(fig)


# --------------------------------------------------------------- figure 2

ANG_BANDS = [(0, 2.5, "High"), (2.5, 3.0, "Moderate"), (3.0, 7.0, "Low")]


def figure_ladder(rows):
    """Angstrom by source on every day the node reported. Not cumulative, so
    the sources are directly comparable without a shared history."""
    days = sorted({r["date"] for r in rows if r["source"].startswith("node")})
    wet = [d for d in days if d.month == 5]
    dry = [d for d in days if d.month == 7]

    fig, axes = plt.subplots(
        1, 2, figsize=(FULL, 2.05), sharey=True,
        gridspec_kw={"width_ratios": [len(wet), max(len(dry), 1) + 0.6], "wspace": 0.06})

    lookup = {(r["source"], r["date"]): r for r in rows}
    order = ["node", "node_cal", "inmet", "era5", "power"]

    for ax, block, title in ((axes[0], wet, "F2 · wet season · sealed enclosure"),
                             (axes[1], dry, "F3 · dry season · vented enclosure")):
        for lower, upper, label in ANG_BANDS:
            shade = {"High": 0.55, "Moderate": 0.3, "Low": 0.12}[label]
            ax.axhspan(lower, upper, color=BAND, alpha=shade, lw=0, zorder=0)
        for position, day in enumerate(block):
            experiment = "F2" if day.month == 5 else "F3"
            for offset, key in enumerate(order):
                name = (f"node_{experiment}" if key == "node"
                        else f"node_{experiment}_cal" if key == "node_cal" else key)
                row = lookup.get((name, day))
                if not row:
                    continue
                colour, style, _ = SOURCE_STYLE[key]
                x = position + (offset - 2) * 0.15
                ax.plot([x], [number(row["Angstrom"])], marker="o", ms=6,
                        mfc="white" if key == "node_cal" else colour,
                        mec=colour, mew=1.6, zorder=5)
        ax.set_xticks(range(len(block)))
        ax.set_xticklabels([f"{d:%d %b}" for d in block])
        ax.set_title(title, color=INK2, pad=6)
        tidy(ax)
        ax.grid(False, axis="x")

    axes[0].set_ylabel("Ångström index")
    low, high = 1.2, 6.4
    axes[0].set_ylim(low, high)
    axes[1].set_xlim(-0.5, len(dry) + 0.2)
    right = axes[1].get_xlim()[1] - 0.06
    for lower, upper, label in ANG_BANDS:
        # clamp each band to the visible range, or "High" is centred off-panel
        centre = (max(lower, low) + min(upper, high)) / 2
        axes[1].text(right, centre, label, va="center", ha="right",
                     fontsize=6.4, color=INK2)

    # Direction of danger shown on the axis instead of stated in the label.
    axes[0].annotate("", xy=(-0.155, 0.18), xytext=(-0.155, 0.72),
                     xycoords="axes fraction", textcoords="axes fraction",
                     arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1.0))
    axes[0].text(-0.185, 0.45, "more dangerous", transform=axes[0].transAxes,
                 rotation=90, va="center", ha="center", fontsize=6.4, color=INK2)

    handles = [Line2D([], [], marker="o", ls="none", ms=6,
                      mfc="white" if key == "node_cal" else SOURCE_STYLE[key][0],
                      mec=SOURCE_STYLE[key][0], mew=1.6, label=SOURCE_STYLE[key][2])
               for key in order]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.09),
               frameon=False, ncol=5, handletextpad=0.4, columnspacing=1.6)
    save(fig, "index_ladder")
    plt.close(fig)


# --------------------------------------------------------------- figure 3

def figure_condensation():
    """Dew point excess over A711 by local hour: the enclosure water cycle."""
    profiles = {
        "F3 · vented (N5)": (INMET, {
            0: -5.32, 1: -4.15, 2: -4.30, 3: -4.75, 4: -4.31, 5: -3.99, 6: -4.06,
            7: -4.79, 8: -1.28, 9: 13.89, 12: 4.75, 13: 6.49, 14: 8.88, 15: 7.37,
            16: 8.74, 17: 1.77, 18: -2.06, 19: -3.14, 20: -4.58, 21: -4.46,
            22: -3.68, 23: -5.25}),
        "F2 · sealed (N3)": (NODE, {
            0: -0.75, 1: -0.74, 2: -0.72, 3: -0.67, 4: -0.58, 5: -0.48, 6: -0.94,
            7: -0.56, 8: -0.10, 9: 0.24, 10: 0.59, 11: 1.61, 12: 2.13, 13: 2.39,
            14: 2.42, 15: 3.18, 16: 1.07, 17: 0.77, 18: 0.28, 19: 0.20, 20: -0.12,
            21: -0.32, 22: -0.62, 23: -0.59}),
    }
    fig, ax = plt.subplots(figsize=(COLUMN, 2.15))
    ax.axhline(0, color=INK2, lw=0.8, zorder=2)
    ax.axvspan(9, 17, color=BAND, alpha=0.55, lw=0, zorder=0)
    ax.text(16.4, 11.9, "condensate\nevaporates", ha="center", va="center",
            fontsize=6.2, color=INK2, linespacing=1.3)
    ax.text(3.5, -7.6, "water condenses\non cold walls", ha="center", va="center",
            fontsize=6.2, color=INK2, linespacing=1.3)

    for label, (colour, profile) in profiles.items():
        hours = sorted(profile)
        ax.plot(hours, [profile[h] for h in hours], color=colour, lw=1.8,
                marker="o", ms=3.4, mec="white", mew=0.7, zorder=5, label=label)

    ax.axvline(13, color=INK, lw=0.9, ls=(0, (3, 2)), zorder=4)
    ax.annotate("13:00, the hour\nFMA samples", xy=(13, -6.5), xytext=(15.4, -8.6),
                fontsize=6.2, color=INK, ha="left",
                arrowprops=dict(arrowstyle="-", lw=0.7, color=INK))

    ax.set_xlabel("Local hour")
    ax.set_ylabel("Dew point excess (°C)")
    ax.set_xlim(0, 23.5)
    ax.set_ylim(-9.5, 16.2)
    ax.set_xticks(range(0, 24, 4))
    tidy(ax)
    ax.legend(loc="upper left", frameon=False, handlelength=1.5)
    save(fig, "condensation_cycle")
    plt.close(fig)


# --------------------------------------------------------------- figure 4

def figure_link(readings):
    """RSSI against distance, with the near-field controls and a free-space line."""
    runs = {}
    for row in readings:
        key = (row["experiment"], row["node"])
        runs.setdefault(key, []).append(row)

    fig, ax = plt.subplots(figsize=(COLUMN, 2.0))

    distances = [d / 100 for d in range(100, 30000)]
    for power_dbm, colour in ((16, INK2),):
        free = [power_dbm + 4 - (20 * math.log10(d / 1000) + 20 * math.log10(915) + 32.44)
                for d in distances]
        ax.plot(distances, free, color=colour, lw=0.9, ls=(0, (4, 3)), zorder=2)
    ax.text(150, -52, "free space,\n16 dBm", fontsize=6.2, color=INK2, ha="center")

    # Runs cluster between 70 and 95 m, and each run also draws a vertical
    # range bar. Horizontal offsets clear both the marker and its own bar.
    label_offsets = {("I2", "N3"): (0, 10), ("I1", "N1"): (0, 10),
                     ("I1", "N2"): (0, -14), ("F1", "N1"): (-11, 0),
                     ("F3", "N5"): (11, 3), ("F1", "N2"): (-11, 0),
                     ("F3", "N4"): (0, -13), ("F2", "N3"): (11, 0)}

    styles = {7: (NODE, "SF7, 14 dBm"), 10: (ERA5, "SF10, 16 dBm"),
              11: (INMET, "SF11, 16 dBm")}
    seen = set()
    for (experiment, node), rows in sorted(runs.items()):
        spreading = int(rows[0]["sf"])
        colour, label = styles[spreading]
        indoor = rows[0]["site"] == "indoor"
        distance = float(rows[0]["distance_m"]) if rows[0]["distance_m"] else (
            4.0 if experiment == "I1" else 2.0)
        values = [int(r["rssi"]) for r in rows]
        mean = sum(values) / len(values)
        ax.plot([distance, distance], [min(values), max(values)], color=colour,
                lw=1.4, alpha=0.5, solid_capstyle="round", zorder=3)
        ax.plot([distance], [mean], marker="s" if indoor else "o", ms=7,
                mfc="white" if indoor else colour, mec=colour, mew=1.6, zorder=5,
                label=label if label not in seen else None)
        seen.add(label)
        dx, dy = label_offsets.get((experiment, node), (0, 9))
        ax.annotate(f"{experiment}·{node}", xy=(distance, mean), xytext=(dx, dy),
                    textcoords="offset points", fontsize=6, color=INK2,
                    ha="center" if dx == 0 else ("right" if dx < 0 else "left"),
                    va="center" if dx else ("top" if dy < 0 else "bottom"),
                    zorder=10)  # above the markers, which sit at zorder 5

    ax.set_xscale("log")
    ax.set_xlabel("Distance to gateway (m)")
    ax.set_ylabel("RSSI (dBm)")
    ax.set_xlim(1.4, 260)
    ax.set_ylim(-135, -5)
    ax.set_xticks([2, 5, 10, 25, 50, 100, 200])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    tidy(ax)
    handles = [Line2D([], [], marker="o", ls="none", ms=6, mfc=c, mec=c,
                      label=l) for c, l in styles.values()]
    handles.append(Line2D([], [], marker="s", ls="none", ms=6, mfc="white",
                          mec=INK2, mew=1.4, label="indoor control"))
    ax.legend(handles=handles, loc="lower left", frameon=False, handletextpad=0.4)
    save(fig, "link_budget")
    plt.close(fig)


# --------------------------------------------------------------- figure 5

def figure_battery(readings):
    """The 9.2-day discharge that replaces the 28 h estimate."""
    fig, ax = plt.subplots(figsize=(COLUMN, 2.0))

    for node, colour, label in (("N4", INMET, "F3 · N4, 9.2 days"),
                                ("N5", NODE, "F3 · N5, 28 h")):
        rows = sorted((r for r in readings if r["node"] == node and r["experiment"] == "F3"),
                      key=lambda r: int(r["timestamp"]))
        start = int(rows[0]["timestamp"])
        hours = [(int(r["timestamp"]) - start) / 3600 for r in rows]
        level = [int(r["battery_pct"]) for r in rows]
        ax.plot(hours, level, color=colour, lw=1.8, zorder=5, label=label,
                solid_capstyle="round")

    rate = (69 - 2) / 221.4
    ax.plot([0, 100 / rate], [100, 0], color=INMET, lw=1.0, ls=(0, (3, 2)),
            alpha=0.75, zorder=3)
    ax.text(232, 46, f"same rate from a full charge:\n{100 / rate:.0f} h "
                     f"({100 / rate / 24:.1f} days), {rate * 500 / 100:.2f} mA mean",
            fontsize=6.4, color=INK2, ha="center", va="center", linespacing=1.4)

    ax.set_xlabel("Hours since deployment")
    ax.set_ylabel("Reported battery (%)")
    ax.set_xlim(0, 345)
    ax.set_ylim(0, 105)
    tidy(ax)
    ax.legend(loc="upper right", frameon=False, handlelength=1.5)
    save(fig, "battery_discharge")
    plt.close(fig)


def main():
    rows = load_indices()
    readings = load_readings()
    figure_season(rows)
    figure_ladder(rows)
    figure_condensation()
    figure_link(readings)
    figure_battery(readings)
    for path in sorted(OUT.glob("*.pdf")):
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
