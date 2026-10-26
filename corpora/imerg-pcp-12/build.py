import datetime as dt
from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
COLLECTION = "NASA/GPM_L3/IMERG_V07"
BAND = "precipitation"
STEPS = 12
CELL = 0.1
SIZE = 512
SCALE = float(np.float32(0.01))  # IMERG rates are float32 counts times float32 0.01


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for old in b.legacy(CORPUS):
        start = dt.datetime.fromisoformat(old["start_utc"])
        end = start + dt.timedelta(minutes=30 * STEPS)
        found = (
            ee.ImageCollection(COLLECTION)
            .filterDate(start.isoformat(), end.isoformat())
            .sort("system:time_start")
            .aggregate_array("system:index")
            .getInfo()
        )
        if len(found) != STEPS:
            raise ValueError(f"{old['id']}: {len(found)} half-hours found")
        rows.append(
            {
                "id": old["id"],
                "source": f"{COLLECTION} (GPM IMERG Final Run V07, half-hourly)",
                "asset": b.join(f"{COLLECTION}/{index}" for index in found),
                "crs": "EPSG:4326",
                "transform": b.transform_text(
                    float(old["west"]), CELL, float(old["north"]), -CELL
                ),
                "datetime_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "datetime_end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bands": b.join([BAND] * STEPS),
                "shape": f"{STEPS}x{SIZE}x{SIZE}",
                "dtype": "uint16",
                "unit": "mm/hr",
                "scale": repr(SCALE),
                "offset": "0",
                "nodata": "",
                "input_sha256": old["input_sha256"],
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["center_lon"],
                "lat": old["center_lat"],
                "grid_column": old["grid_column"],
                "grid_row": old["grid_row"],
            }
        )
    return rows


def build(row: dict[str, str]):
    ee = src.ee_init()
    transform = b.parse_transform(row["transform"])
    rates = np.stack(
        [
            src.ee_pixels(
                ee.Image(asset).select([BAND]),
                [BAND],
                row["crs"],
                transform,
                (SIZE, SIZE),
            )[0]
            for asset in b.split(row["asset"])
        ]
    ).astype(np.float32)
    if not np.isfinite(rates).all() or rates.min() < 0:
        raise ValueError(f"{row['id']}: the window holds fill values")
    codes = b.cast(np.round(rates.astype(np.float64) / SCALE), row["dtype"])
    if not b.exact(codes, SCALE, 0.0, rates):
        raise ValueError(
            f"{row['id']}: the scale does not reproduce the published rates"
        )
    preview = b.stretch(np.log1p(rates.max(0)))
    return codes, preview


if __name__ == "__main__":
    b.main(CORPUS, select, build)
