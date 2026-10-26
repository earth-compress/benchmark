from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
SIZE = 512


def url(tile: str) -> str:
    return f"/vsicurl/{BUCKET}/{tile}/{tile}.tif"


def select() -> list[dict[str, str]]:
    rows = []
    for old in b.legacy(CORPUS):
        crs, transform = src.cog_centre(
            url(old["tile"]), float(old["lon"]), float(old["lat"]), SIZE
        )
        rows.append(
            {
                "id": old["id"],
                "source": "Copernicus DEM GLO-30 (2021 release), AWS open data",
                "asset": f"{BUCKET}/{old['tile']}/{old['tile']}.tif",
                "crs": crs,
                "transform": " ".join(repr(float(v)) for v in transform),
                "datetime_start": "2011-01-01T00:00:00Z",
                "datetime_end": "2015-12-31T23:59:59Z",
                "bands": "elevation",
                "shape": f"{SIZE}x{SIZE}",
                "dtype": "float32",
                "unit": "m",
                "scale": "1",
                "offset": "0",
                "nodata": "",
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
                "tile": old["tile"],
            }
        )
    return rows


def preview(data: np.ndarray, row: dict[str, str]) -> np.ndarray:
    return b.relief(data, 30.0)


def build(row: dict[str, str]):
    data, _ = src.cog_window(
        "/vsicurl/" + row["asset"],
        b.parse_transform(row["transform"]),
        b.parse_shape(row["shape"]),
    )
    data = b.cast(data[0], row["dtype"])
    if not np.isfinite(data).all():
        raise ValueError(f"{row['id']}: the window holds fill values")
    return data, preview(data, row)


if __name__ == "__main__":
    b.main(CORPUS, select, build, preview)
