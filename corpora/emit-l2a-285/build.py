from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
COLLECTION = "NASA/EMIT/L2A/RFL"
BANDS = [f"reflectance_{i}" for i in range(285)]
SIZE = 128
PREVIEW = (35, 23, 12)  # near 640, 550 and 470 nm


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for sample in b.read_manifest(CORPUS):
        asset = sample["asset"]
        image = ee.Image(asset)
        crs, pixel, x0, y0 = src.ee_centre(
            image.select(BANDS[0]), float(sample["lon"]), float(sample["lat"]), SIZE
        )
        when = src.utc(image.get("system:time_start").getInfo())
        rows.append(
            {
                "id": sample["id"],
                "source": f"{COLLECTION} (EMIT L2A Estimated Surface Reflectance V001)",
                "asset": asset,
                "crs": crs,
                "transform": b.transform_text(x0, pixel, y0, -pixel),
                "datetime_start": when,
                "datetime_end": when,
                "bands": b.join(BANDS),
                "shape": f"{len(BANDS)}x{SIZE}x{SIZE}",
                "dtype": "float32",
                "unit": "reflectance",
                "scale": "1",
                "offset": "0",
                "nodata": "",
                "input_sha256": sample["input_sha256"],
                "site": sample["site"],
                "regime": sample["regime"],
                "lon": sample["lon"],
                "lat": sample["lat"],
            }
        )
    return rows


def build(row: dict[str, str]):
    src.ee_init()
    data = b.cast(src.ee_row(row), row["dtype"])
    if not np.isfinite(data).all() or (data == -9999).any():
        raise ValueError(f"{row['id']}: the window holds fill values")
    return data, b.rgb(data[i] for i in PREVIEW)


if __name__ == "__main__":
    b.main(CORPUS, select, build)
