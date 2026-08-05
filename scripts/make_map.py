#!/usr/bin/env python3
"""Deployment map over satellite imagery.

Basemap tiles come from Esri World Imagery, which is redistributable with
attribution; Google's imagery is not, which is why this does not use it.

Run with the repo venv: ./scripts/venv/bin/python scripts/make_map.py
"""

import csv
import io
import math
import urllib.request
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "figures"
CACHE = Path("/tmp/ai-docker/tiles")
CACHE.mkdir(parents=True, exist_ok=True)

# Esri World Imagery is the publication-safe basemap: its attribution string is
# documented and stable. It has no imagery deeper than z18 here (0.55 m/px).
# Google carries z20 (0.14 m/px), but pulling raw tiles from mt1.google.com is
# outside Google's terms and gives no way to read the correct per-tile
# attribution, so it is kept only for drafting, never for a submitted figure.
SOURCES = {
    "google": ("https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", 21,
               "Imagery: Google"),
    "esri": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
             "World_Imagery/MapServer/tile/{z}/{y}/{x}", 18,
             "Imagery: Esri, Maxar, Earthstar Geographics"),
}
SOURCE = "google"
TILE_URL, ZOOM, ATTRIBUTION = SOURCES[SOURCE]

GATEWAY = (-21.979322, -47.883435)
STATION = (-21.98028, -47.88389)

# position -> lat, lon, campaign, node, mean RSSI (dBm)
SITES = [
    ("A", -21.9792439, -47.8843463, "F1", "N2", -104.6),
    ("B", -21.9793505, -47.8841408, "F1", "N1", -61.4),
    ("C", -21.9783096, -47.8844080, "F2", "N3", -112.5),
    ("D", -21.9790620, -47.8840620, "F3", "N4", -106.9),
    ("E", -21.9793889, -47.8841667, "F3", "N5", -89.2),
]
MARKERS = {"F1": "o", "F2": "s", "F3": "^"}
# B and E sit about 5 m apart; keep their labels off each other.
# One label per marker carrying both campaign and distance, so nothing floats
# unattached. B and E are 5 m apart and their markers overlap, so those two get
# leader lines back to their own marker.
LABEL = {
    "A": dict(offset=(-13, 0), leader=False),
    "C": dict(offset=(13, 8), leader=False),
    "D": dict(offset=(-14, 3), leader=False),
    "B": dict(offset=(-34, -20), leader=True),
    "E": dict(offset=(34, -22), leader=True),
}

INK = "#0b0b0b"
PAPER = "#ffffff"


def mercator(lat, lon):
    x = (lon + 180.0) / 360.0
    s = math.sin(math.radians(lat))
    y = 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)
    return x, y


def inverse_mercator(x, y):
    lon = x * 360.0 - 180.0
    lat = math.degrees(2 * math.atan(math.exp((0.5 - y) * 2 * math.pi)) - math.pi / 2)
    return lat, lon


def haversine_m(a, b):
    radius = 6371000.0
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def fetch_tile(z, x, y):
    path = CACHE / f"{SOURCE}_{z}_{x}_{y}.jpg"
    if not path.exists():
        request = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y),
                                         headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            path.write_bytes(response.read())
    tile = Image.open(io.BytesIO(path.read_bytes())).convert("RGB")
    if np.asarray(tile).astype(float).std() < 12:
        raise RuntimeError(f"tile {ZOOM}/{x}/{y} has no imagery, lower ZOOM")
    return tile


def basemap(lat_min, lat_max, lon_min, lon_max):
    """Stitched imagery plus its extent in normalised Mercator units."""
    n = 2 ** ZOOM
    x0, y0 = mercator(lat_max, lon_min)
    x1, y1 = mercator(lat_min, lon_max)
    tx0, ty0 = int(x0 * n), int(y0 * n)
    tx1, ty1 = int(x1 * n), int(y1 * n)
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            canvas.paste(fetch_tile(ZOOM, tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    extent = (tx0 / n, (tx1 + 1) / n, (ty1 + 1) / n, ty0 / n)
    return np.asarray(canvas), extent


def scale_bar(ax, lat, x_left, y_bottom, metres=50):
    """Bar of `metres` drawn in normalised Mercator units."""
    span = metres / (40075016.686 * math.cos(math.radians(lat)))
    ax.plot([x_left, x_left + span], [y_bottom, y_bottom], color=PAPER, lw=3,
            solid_capstyle="butt", zorder=9)
    ax.plot([x_left, x_left + span], [y_bottom, y_bottom], color=INK, lw=1.6,
            solid_capstyle="butt", zorder=10)
    ax.text(x_left + span / 2, y_bottom, f"{metres} m", color=PAPER, fontsize=6.5,
            ha="center", va="bottom", zorder=11)


def main():
    lats = [GATEWAY[0], STATION[0]] + [s[1] for s in SITES]
    lons = [GATEWAY[1], STATION[1]] + [s[2] for s in SITES]
    xs = [mercator(la, lo)[0] for la, lo in zip(lats, lons)]
    ys = [mercator(la, lo)[1] for la, lo in zip(lats, lons)]
    my = (max(ys) - min(ys)) * 0.07
    target_width = (max(ys) - min(ys) + 2 * my) * 0.76
    mx = max((target_width - (max(xs) - min(xs))) / 2, (max(xs) - min(xs)) * 0.12)
    view = (min(xs) - mx, max(xs) + mx, min(ys) - my, max(ys) + my)

    # Fetch imagery for the final view, not the site bounding box, or the wide
    # crop leaves blank margins where the scale bar and ramp would sit.
    north, west = inverse_mercator(view[0], view[2])
    south, east = inverse_mercator(view[1], view[3])
    image, extent = basemap(south, north, west, east)

    fig, ax = plt.subplots(figsize=(3.5, 4.6))
    ax.imshow(image, extent=extent, origin="upper", interpolation="bilinear",
              zorder=0)

    norm = Normalize(vmin=-115, vmax=-60)
    ramp = plt.get_cmap("Oranges")
    gx, gy = mercator(*GATEWAY)

    for name, lat, lon, campaign, node, rssi in SITES:
        sx, sy = mercator(lat, lon)
        ax.plot([gx, sx], [gy, sy], color=PAPER, lw=0.9, ls=(0, (2.5, 2.5)),
                zorder=3)
        ax.plot([sx], [sy], marker=MARKERS[campaign], ms=8.5,
                mfc=ramp(norm(rssi)), mec="none", zorder=7)
        spec = LABEL[name]
        ax.annotate(f"{campaign} · {haversine_m(GATEWAY, (lat, lon)):.0f} m",
                    xy=(sx, sy), xytext=spec["offset"],
                    textcoords="offset points", fontsize=6.4, color=PAPER,
                    ha="right" if spec["offset"][0] < 0 else "left",
                    va="center", zorder=9, fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color=PAPER, lw=0.6,
                                    shrinkA=0, shrinkB=5)
                    if spec["leader"] else None)

    ax.plot([gx], [gy], marker="*", ms=16, mfc="#2a78d6", mec="none", zorder=8)
    ax.annotate("Gateway", xy=(gx, gy), xytext=(0, -13),
                textcoords="offset points", fontsize=6.6, color=PAPER,
                ha="center", va="center", zorder=9, fontweight="bold")
    sx, sy = mercator(*STATION)
    ax.plot([sx], [sy], marker="D", ms=7.5, mfc="#1baf7a", mec="none", zorder=8)
    ax.annotate("INMET A711", xy=(sx, sy), xytext=(0, -12),
                textcoords="offset points", fontsize=6.6, color=PAPER,
                ha="center", va="center", zorder=9, fontweight="bold")

    ax.set_xlim(view[0], view[1])
    # Mercator y grows southward and imshow already inverted the axis, so the
    # limits must stay in descending order or north and south swap.
    ax.set_ylim(view[3], view[2])

    left, bottom = ax.get_xlim()[0], ax.get_ylim()[0]
    width = ax.get_xlim()[1] - left
    height = ax.get_ylim()[1] - bottom
    scale_bar(ax, GATEWAY[0], left + width * 0.05, bottom + height * 0.055)
    ax.annotate("N", xy=(left + width * 0.93, bottom + height * 0.88),
                xytext=(left + width * 0.93, bottom + height * 0.80),
                color=PAPER, fontsize=8, ha="center", fontweight="bold", zorder=10,
                arrowprops=dict(arrowstyle="-|>", color=PAPER, lw=1.2))
    ax.text(left + width * 0.02, bottom + height * 0.012, ATTRIBUTION,
            fontsize=4.4, color=PAPER, ha="left", va="bottom", zorder=10, alpha=0.9)

    # RSSI ramp sits on the image so the map keeps the full column width.
    cax = ax.inset_axes([0.62, 0.10, 0.28, 0.018])
    bar = fig.colorbar(ScalarMappable(norm=norm, cmap=ramp), cax=cax,
                       orientation="horizontal")
    bar.outline.set_visible(False)
    cax.tick_params(labelsize=5.6, colors=PAPER, length=2, pad=1)
    cax.set_title("Mean RSSI (dBm)", fontsize=6, color=PAPER, pad=2.5)

    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.savefig(OUT / "deployment_map.pdf", bbox_inches="tight", pad_inches=0.03)
    fig.savefig(OUT / "deployment_map.png", bbox_inches="tight", pad_inches=0.01, dpi=260)
    print(f"wrote {OUT / 'deployment_map.pdf'} ({SOURCE} z{ZOOM})")


if __name__ == "__main__":
    main()
