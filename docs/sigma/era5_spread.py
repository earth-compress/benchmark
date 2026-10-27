"""Median ERA5 ensemble spread over the days of the ERA5 corpora.

Downloads the `ensemble_spread` product of the Climate Data Store for each day
of the corpora, eight fields a day, and prints the median spread of each
variable weighted by the area of its cells. The download needs a Climate Data
Store account and its key in `~/.cdsapirc`. Run from the repository root:

    uv run --extra corpus python docs/sigma/era5_spread.py <directory>
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import cdsapi
import eccodes
import numpy as np

MANIFEST = Path("corpora/era5-t2m-1h/manifest.csv")
VARIABLES = [
    "2m_temperature",
    "10m_u_component_of_wind",
    "mean_sea_level_pressure",
    "total_cloud_cover",
    "total_precipitation",
]


def days() -> list[str]:
    with MANIFEST.open(newline="") as stream:
        return [row["datetime_start"][:10] for row in csv.DictReader(stream)]


def download(directory: Path) -> None:
    client = cdsapi.Client(quiet=True)
    for day in days():
        path = directory / f"{day}.grib"
        if path.exists():
            continue
        year, month, dd = day.split("-")
        client.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": ["ensemble_spread"],
                "variable": VARIABLES,
                "year": [year],
                "month": [month],
                "day": [dd],
                "time": [f"{hour:02d}:00" for hour in range(0, 24, 3)],
                "data_format": "grib",
            },
            str(path.with_suffix(".part")),
        )
        path.with_suffix(".part").rename(path)


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cumulative, cumulative[-1] / 2)])


def main(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    download(directory)
    fields, latitudes = defaultdict(list), None
    for path in sorted(directory.glob("*.grib")):
        with path.open("rb") as stream:
            while (handle := eccodes.codes_grib_new_from_file(stream)) is not None:
                rows, columns = (eccodes.codes_get(handle, key) for key in ("Nj", "Ni"))
                latitudes = eccodes.codes_get_array(handle, "distinctLatitudes")
                fields[eccodes.codes_get(handle, "shortName")].append(
                    eccodes.codes_get_values(handle).reshape(rows, columns)
                )
                eccodes.codes_release(handle)
    for name, stack in fields.items():
        spread = np.stack(stack)
        area = np.broadcast_to(
            np.cos(np.radians(latitudes))[None, :, None], spread.shape
        )
        print(
            f"{name:4} {len(stack):3} fields  median {weighted_median(spread.ravel(), area.ravel()):.4g}"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
