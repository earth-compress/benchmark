"""The samples of the change detection use case, AlphaEarth windows where the land
changed between 2017 and 2025.

uv run --extra corpus python usecases/change-detection/build.py
"""

import csv
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

HERE = Path(__file__).resolve().parent
ROOT = "https://storage.googleapis.com/alphaearth_foundations/satellite_embedding/v1/annual"
YEARS = ("2017", "2025")
PIXEL = 10
SIZE = 512
SITES = [
    # site, longitude and latitude of the window centre, what changed
    ("jaci-parana", -64.5745, -9.5784, "forest cleared for pasture"),
    ("apui", -59.6272, -7.3137, "forest cleared"),
    ("dixie-fire", -120.9219, 40.2889, "forest burned in 2021"),
    ("gerd", 35.1445, 11.2471, "reservoir filled from 2020"),
    ("kakhovka", 34.4144, 47.4980, "reservoir drained in 2023"),
    ("la-palma", -17.9003, 28.6216, "lava of 2021"),
    ("grindavik", -22.3496, 63.9150, "lava of 2023 to 2025"),
    ("new-capital", 31.7005, 30.0023, "city built on desert"),
    ("nusantara", 116.6367, -0.9932, "capital built on plantation"),
    ("bulakan", 120.8888, 14.7523, "airport island reclaimed"),
    ("navi-mumbai", 73.0640, 18.9841, "airport built"),
    ("morowali", 122.1600, -2.8069, "nickel industrial park"),
    ("talatan", 100.6281, 36.1232, "solar fields built"),
]
"""Each centre is that of the window of 5 km with about 40% change within 10 km
of the place, picked by eye."""


def index() -> list[dict[str, str]]:
    path = src.CACHE / "aef" / "aef_index.csv"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(f"{ROOT}/aef_index.csv", path)
    csv.field_size_limit(1 << 30)
    with path.open(newline="") as stream:
        return [
            {k: v for k, v in row.items() if k != "WKT"}
            for row in csv.DictReader(stream)
            if row["year"] in YEARS
        ]


def window(files: list[dict[str, str]], lon: float, lat: float) -> dict[str, str]:
    """The window centred on a point in its UTM zone, and the file of each year
    that holds it."""
    from rasterio.warp import transform

    zone = int((lon + 180) // 6) + 1
    crs = f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"
    (x,), (y,) = transform("EPSG:4326", crs, [lon], [lat])
    row = {"crs": crs}
    for year in YEARS:
        found = [
            f
            for f in files
            if f["year"] == year
            and f["crs"] == crs
            and float(f["utm_west"]) <= x <= float(f["utm_east"])
            and float(f["utm_south"]) <= y <= float(f["utm_north"])
        ]
        if not found:
            raise ValueError(f"{lon},{lat}: no {year} file holds the point")
        west, north = float(found[0]["utm_west"]), float(found[0]["utm_north"])
        x0 = west + PIXEL * round((x - west) / PIXEL - SIZE / 2)
        y0 = north - PIXEL * round((north - y) / PIXEL - SIZE / 2)
        row["transform"] = b.transform_text(x0, PIXEL, y0, -PIXEL)
        row[f"asset_{year}"] = found[0]["path"].replace(
            "gs://alphaearth_foundations/satellite_embedding/v1/annual", ROOT
        )
    return row


def fetch(row: dict[str, str]) -> dict[str, str]:
    """Both years of the window of ``row``, saved next to this script."""
    years = [
        b.cast(
            src.cog_window(
                "/vsicurl/" + row[f"asset_{year}"],
                b.parse_transform(row["transform"]),
                (SIZE, SIZE),
            )[0],
            "int8",
        )
        for year in YEARS
    ]
    np.savez_compressed(HERE / row["npz_path"], before=years[0], after=years[1])
    print(row["id"], row["site"], flush=True)
    return row


def main() -> None:
    files = index()
    (HERE / "npz").mkdir(exist_ok=True)
    selected = [
        {
            "id": f"change-{k:02d}",
            "site": site,
            "change": change,
            "lon": lon,
            "lat": lat,
            **window(files, lon, lat),
            "shape": f"64x{SIZE}x{SIZE}",
            "dtype": "int8",
            "nodata": "-128",
            "npz_path": f"npz/change-{k:02d}.npz",
        }
        for k, (site, lon, lat, change) in enumerate(SITES)
    ]
    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(fetch, selected))
    with (HERE / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
