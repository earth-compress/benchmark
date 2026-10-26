"""Build esa-wc-v200 from the ESA WorldCover 2021 v200 COGs on AWS."""

from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
SIZE = 512
COLOURS = {
    10: (0, 100, 0),
    20: (255, 187, 34),
    30: (255, 255, 76),
    40: (240, 150, 255),
    50: (250, 0, 0),
    60: (180, 180, 180),
    70: (240, 240, 240),
    80: (0, 100, 200),
    90: (0, 150, 160),
    95: (0, 207, 117),
    100: (250, 230, 160),
}


def select() -> list[dict[str, str]]:
    rows = []
    for old in b.legacy(CORPUS):
        asset = f"{BASE}/{old['tile']}.tif"
        crs, transform = src.cog_centre(
            "/vsicurl/" + asset, float(old["lon"]), float(old["lat"]), SIZE
        )
        rows.append(
            {
                "id": old["id"],
                "source": "ESA WorldCover 10 m 2021 v200, AWS open data",
                "asset": asset,
                "crs": crs,
                "transform": " ".join(repr(float(v)) for v in transform),
                "datetime_start": "2021-01-01T00:00:00Z",
                "datetime_end": "2021-12-31T23:59:59Z",
                "bands": "Map",
                "shape": f"{SIZE}x{SIZE}",
                "dtype": "uint8",
                "unit": "class code",
                "scale": "1",
                "offset": "0",
                "nodata": "0",
                "input_sha256": old["input_sha256"],
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
                "tile": old["tile"],
            }
        )
    return rows


def build(row: dict[str, str]):
    data, _ = src.cog_window(
        "/vsicurl/" + row["asset"],
        b.parse_transform(row["transform"]),
        b.parse_shape(row["shape"]),
    )
    data = b.cast(data[0], row["dtype"])
    preview = np.zeros(data.shape + (3,), np.uint8)
    for code, colour in COLOURS.items():
        preview[data == code] = colour
    return data, preview


if __name__ == "__main__":
    b.main(CORPUS, select, build)
