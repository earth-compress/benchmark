import datetime as dt
from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
COLLECTION = "NASA/GPM_L3/IMERG_V07"
BAND = "precipitation"
STEPS = 12
SIZE = 512
SCALE = float(np.float32(0.01))  # IMERG rates are float32 counts times float32 0.01


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for sample in b.read_manifest(CORPUS):
        start = dt.datetime.fromisoformat(sample["datetime_start"])
        end = start + dt.timedelta(minutes=30 * STEPS)
        found = (
            ee.ImageCollection(COLLECTION)
            .filterDate(start.isoformat(), end.isoformat())
            .sort("system:time_start")
            .aggregate_array("system:index")
            .getInfo()
        )
        if len(found) != STEPS:
            raise ValueError(f"{sample['id']}: {len(found)} half-hours found")
        rows.append(
            {
                "id": sample["id"],
                "source": f"{COLLECTION} (GPM IMERG Final Run V07, half-hourly)",
                "asset": b.join(f"{COLLECTION}/{index}" for index in found),
                "crs": "EPSG:4326",
                "transform": sample["transform"],
                "datetime_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "datetime_end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bands": b.join([BAND] * STEPS),
                "shape": f"{STEPS}x{SIZE}x{SIZE}",
                "dtype": "uint16",
                "unit": "mm/hr",
                "scale": repr(SCALE),
                "offset": "0",
                "nodata": "",
                "input_sha256": sample["input_sha256"],
                "site": sample["site"],
                "regime": sample["regime"],
                "lon": sample["lon"],
                "lat": sample["lat"],
                "grid_column": sample["grid_column"],
                "grid_row": sample["grid_row"],
            }
        )
    return rows


def preview(codes: np.ndarray, row: dict[str, str]) -> np.ndarray:
    """The highest rate of each pixel over the half hours."""
    return b.stretch(np.log1p(codes.max(0) * SCALE), cmap="YlGnBu")


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
    return codes, preview(codes, row)


if __name__ == "__main__":
    b.main(CORPUS, select, build, preview)
