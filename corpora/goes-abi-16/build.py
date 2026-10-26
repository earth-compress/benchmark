"""Build goes-abi-16 from GOES-16 ABI L2 MCMIPF in Earth Engine."""

import math
from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
COLLECTION = "NOAA/GOES/16/MCMIPF"
BANDS = [f"CMI_C{channel:02d}" for channel in range(1, 17)]
SIZE = 512
GAMMA = 2.2


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for old in b.legacy(CORPUS):
        asset = f"{COLLECTION}/{old['asset']}"
        image = ee.Image(asset)
        info = image.select(BANDS[0]).projection().getInfo()
        step, x0, y0 = info["transform"][0], info["transform"][2], info["transform"][5]
        # Earth Engine delivers the fixed grid south up; the window is read north up.
        west = x0 + int(old["grid_column"]) * step
        north = y0 + (int(old["grid_row"]) + SIZE) * step
        keys = ["system:time_start"] + [
            f"{band}_{k}" for band in BANDS for k in ("scale", "offset")
        ]
        props = image.toDictionary(keys).getInfo()
        rows.append(
            {
                "id": old["id"],
                "source": f"{COLLECTION} (GOES-16 ABI L2 Cloud and Moisture Imagery, full disk)",
                "asset": asset,
                "crs": info["wkt"],
                "transform": b.transform_text(west, step, north, -step),
                "datetime_start": src.utc(props["system:time_start"]),
                "datetime_end": src.utc(props["system:time_start"]),
                "bands": b.join(BANDS),
                "shape": f"{len(BANDS)}x{SIZE}x{SIZE}",
                "dtype": "uint16",
                "unit": "reflectance factor (C01-C06); K (C07-C16)",
                "scale": b.join(props[f"{band}_scale"] for band in BANDS),
                "offset": b.join(props[f"{band}_offset"] for band in BANDS),
                "nodata": "",
                "input_sha256": old["input_sha256"],
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
                "grid_column": old["grid_column"],
                "grid_row": old["grid_row"],
                "sun_elevation": old["sun_elevation"],
            }
        )
    return rows


def build(row: dict[str, str]):
    src.ee_init()
    raw = src.ee_row(row)
    if raw.min() < 0:
        raise ValueError(f"{row['id']}: the window holds fill values")
    data = b.cast(raw, row["dtype"])
    scales = [float(v) for v in b.split(row["scale"])]
    offsets = [float(v) for v in b.split(row["offset"])]
    blue, red, veggie = (data[i] * scales[i] + offsets[i] for i in (0, 1, 2))
    green = 0.45 * red + 0.45 * blue + 0.10 * veggie
    light = max(math.sin(math.radians(float(row["sun_elevation"]))), 0.1)
    channels = [np.clip(c / light, 0, 1) ** (1 / GAMMA) for c in (red, green, blue)]
    return data, (np.stack(channels, -1) * 255).astype(np.uint8)


if __name__ == "__main__":
    b.main(CORPUS, select, build)
