from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
COLLECTION = "COPERNICUS/S1_GRD_FLOAT"
BANDS = ["VV", "VH"]
SIZE = 512


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for old in b.legacy(CORPUS):
        asset = f"{COLLECTION}/{old['scene_id']}"
        image = ee.Image(asset)
        crs, pixel, x0, y0 = src.ee_centre(
            image.select(BANDS[0]), float(old["lon"]), float(old["lat"]), SIZE
        )
        when = src.utc(image.get("system:time_start").getInfo())
        rows.append(
            {
                "id": old["id"],
                "source": f"{COLLECTION} (Sentinel-1 GRD IW, Earth Engine preprocessing)",
                "asset": asset,
                "crs": crs,
                "transform": b.transform_text(x0, pixel, y0, -pixel),
                "datetime_start": when,
                "datetime_end": when,
                "bands": b.join(BANDS),
                "shape": f"{len(BANDS)}x{SIZE}x{SIZE}",
                "dtype": "float32",
                "unit": "sigma0 (linear)",
                "scale": "1",
                "offset": "0",
                "nodata": "",
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
                "orbit_pass": old["orbit_pass"],
                "relative_orbit": old["relative_orbit"],
            }
        )
    return rows


def build(row: dict[str, str]):
    ee = src.ee_init()
    image = ee.Image(row["asset"]).select(BANDS)
    data = b.cast(src.ee_row(row, image), row["dtype"])
    mask = src.ee_row(row, image.mask().rename(BANDS))
    if not np.isfinite(data).all() or mask.min() == 0:
        raise ValueError(f"{row['id']}: the window holds masked pixels")
    db = 10 * np.log10(np.maximum(data, 1e-6))
    return data, b.rgb((db[0], db[1], db[0] - db[1]))


if __name__ == "__main__":
    b.main(CORPUS, select, build)
