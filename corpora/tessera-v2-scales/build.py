from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
ROOT = "https://data.source.coop/tessera/tessera"
MODEL = "TESSERA-V-2.0-2B-L"
VARIANT = "v2-2B-L~beta1"
PIXEL = 10
SIZE = 512


def select() -> list[dict[str, str]]:
    import rasterio

    rows = []
    for sample in b.read_manifest(CORPUS):
        tile, year = sample["source_tile"], sample["datetime_start"][:4]
        with rasterio.open(f"/vsicurl/{ROOT}/landmasks/v2/{tile}.tiff") as mask:
            t, crs = mask.transform, mask.crs.to_string()
        if (abs(t.a) != PIXEL) or t.b or t.d:
            raise ValueError(f"{tile}: unexpected landmask grid")
        top, left = int(sample["crop_row"]), int(sample["crop_col"])
        rows.append(
            {
                "id": sample["id"],
                "source": f"TESSERA {MODEL} embeddings, {VARIANT}",
                "asset": f"{ROOT}/npy/{VARIANT}/{year}/{tile}/{tile}_scales.npy",
                "crs": crs,
                "transform": b.transform_text(
                    t.c + left * t.a, t.a, t.f + top * t.e, t.e
                ),
                "datetime_start": f"{year}-01-01T00:00:00Z",
                "datetime_end": f"{year}-12-31T23:59:59Z",
                "bands": "scale",
                "shape": "512x512",
                "dtype": "float32",
                "unit": "scale of the codes",
                "scale": "1",
                "offset": "0",
                "nodata": "",
                "input_sha256": sample["input_sha256"],
                "site": sample["site"],
                "regime": sample["regime"],
                "lon": sample["lon"],
                "lat": sample["lat"],
                "source_tile": tile,
                "crop_row": sample["crop_row"],
                "crop_col": sample["crop_col"],
            }
        )
    return rows


def preview(data: np.ndarray, row: dict[str, str]) -> np.ndarray:
    return b.stretch(data, cmap="viridis")


def build(row: dict[str, str]):
    block = src.npy_window(
        row["asset"], int(row["crop_row"]), int(row["crop_col"]), SIZE, SIZE
    )
    data = b.cast(block, row["dtype"])
    return data, preview(data, row)


if __name__ == "__main__":
    b.main(CORPUS, select, build, preview)
