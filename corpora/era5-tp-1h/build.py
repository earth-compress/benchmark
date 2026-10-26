import datetime as dt
from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
DATASET = "reanalysis-era5-single-levels"
VARIABLE = "total_precipitation"
SHORT = "tp"
UNIT = "m"
HOURS = 24


def fields(day: str) -> list[dict]:
    found = src.grib_fields(src.era5_grib(day), SHORT)
    if len(found) != HOURS:
        raise ValueError(f"{day}: {len(found)} hourly fields of {SHORT}")
    return found


def select() -> list[dict[str, str]]:
    rows = []
    for old in b.legacy(CORPUS):
        day = old["date"]
        found = fields(day)
        first = found[0]
        if (
            first["lon0"] != 0
            or first["lat0"] != 90
            or first["dlon"] != 0.25
            or first["dlat"] != 0.25
        ):
            raise ValueError(f"{day}: unexpected grid")
        start = dt.datetime.fromisoformat(day).replace(tzinfo=dt.UTC)
        rows.append(
            {
                "id": old["id"],
                "source": "ERA5 hourly data on single levels, Copernicus Climate Data Store, GRIB",
                "asset": f"{DATASET}?variable={VARIABLE}&date={day}&time=00:00/23:00&format=grib",
                "crs": "EPSG:4326",
                "transform": b.transform_text(-0.125, 0.25, 90.125, -0.25),
                "datetime_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "datetime_end": (start + dt.timedelta(hours=HOURS - 1)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "bands": b.join(f"{SHORT}@{h:02d}:00" for h in range(HOURS)),
                "shape": f"{HOURS}x721x1440",
                "dtype": "uint16",
                "unit": UNIT,
                "scale": b.join(repr(f["scale"]) for f in found),
                "offset": b.join(repr(f["offset"]) for f in found),
                "nodata": "",
                "variable": VARIABLE,
                "grib_short_name": SHORT,
                "bits_per_value": b.join(sorted({f["bits"] for f in found})),
            }
        )
    return rows


def build(row: dict[str, str]):
    day = row["datetime_start"][:10]
    found = fields(day)
    scale = [f["scale"] for f in found]
    offset = [f["offset"] for f in found]
    if (
        b.join(repr(v) for v in scale) != row["scale"]
        or b.join(repr(v) for v in offset) != row["offset"]
    ):
        raise ValueError(f"{row['id']}: the packing differs from the manifest")
    codes = b.cast(np.stack([f["codes"] for f in found]), row["dtype"])
    values = np.stack([f["values"] for f in found])
    if not b.exact(codes, scale, offset, values):
        raise ValueError(
            f"{row['id']}: the codes do not reproduce the published values"
        )
    first = np.log1p(values[0] * 1e4) if SHORT == "tp" else values[0]
    return codes, b.stretch(first)


if __name__ == "__main__":
    b.main(CORPUS, select, build)
