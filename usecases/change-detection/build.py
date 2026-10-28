"""The 2017 embeddings of the change detection use case, on the windows of alphaearth-v1-64.

uv run python usecases/change-detection/build.py
"""

import csv
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent.parent / "corpora" / "alphaearth-v1-64"
ROOT = "https://storage.googleapis.com/alphaearth_foundations/satellite_embedding/v1/annual"
YEAR = "2017"


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
            if row["year"] == YEAR
        ]


def fetch(row: dict[str, str]) -> dict[str, str]:
    """The window of ``row`` in its file of YEAR, saved next to this script."""
    data, _ = src.cog_window(
        "/vsicurl/" + row["asset"],
        b.parse_transform(row["transform"]),
        b.parse_shape(row["shape"])[1:],
    )
    np.savez_compressed(HERE / row["npz_path"], data=b.cast(data, row["dtype"]))
    print(row["id"], row["site"], row["asset"], flush=True)
    return {k: row[k] for k in ("id", "site", "year", "asset", "npz_path")}


def main() -> None:
    files = index()
    (HERE / "npz").mkdir(exist_ok=True)
    selected = []
    for row in b.read_manifest(CORPUS):
        transform = b.parse_transform(row["transform"])
        shape = b.parse_shape(row["shape"])[1:]
        x0, dx, _, y0, _, dy = transform
        x1, y1 = x0 + shape[1] * dx, y0 + shape[0] * dy
        found = sorted(
            f["path"]
            for f in files
            if f["crs"] == row["crs"]
            and float(f["utm_west"]) <= x0
            and x1 <= float(f["utm_east"])
            and float(f["utm_south"]) <= y1
            and y0 <= float(f["utm_north"])
        )
        if not found:
            raise ValueError(f"{row['id']}: no {YEAR} file holds the window")
        asset = found[0].replace(
            "gs://alphaearth_foundations/satellite_embedding/v1/annual", ROOT
        )
        selected.append(
            {**row, "year": YEAR, "asset": asset, "npz_path": f"npz/{row['id']}.npz"}
        )
    # Each window spans whole 1024 x 1024 blocks of 64 bands, so they are read
    # side by side.
    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(fetch, selected))
    with (HERE / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
