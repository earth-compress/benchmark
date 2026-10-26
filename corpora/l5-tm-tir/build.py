from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
DTYPE = "uint8"
SIZE = 512
PREVIEW = None


def asset_of(old: dict[str, str]) -> str:
    return f"LANDSAT/{old['scene_id'][:4]}/C02/{old['tier']}/{old['scene_id']}"


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for old in b.legacy(CORPUS):
        asset = asset_of(old)
        bands = old["band_order"].split("|")
        when = src.utc(ee.Image(asset).get("system:time_start").getInfo())
        pixel = float(old["grid_m"])
        rows.append(
            {
                "id": old["id"],
                "source": f"{asset.rsplit('/', 1)[0]} (Landsat Collection 2 Level-1)",
                "asset": asset,
                "crs": old["crs"],
                "transform": b.transform_text(
                    float(old["translate_x"]), pixel, float(old["translate_y"]), -pixel
                ),
                "datetime_start": when,
                "datetime_end": when,
                "bands": b.join(bands),
                "shape": "x".join(map(str, (SIZE, SIZE))),
                "dtype": DTYPE,
                "unit": "DN",
                "scale": "1",
                "offset": "0",
                "nodata": "0",
                "input_sha256": old["input_sha256"],
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
                "spacecraft": old["spacecraft"],
                "sensor": old["sensor"],
                "product_id": old["product_id"],
                "wrs_path": old["wrs_path"],
                "wrs_row": old["wrs_row"],
                "acquired_m": old["acquired_m"],
            }
        )
    return rows


def preview(data: np.ndarray, row: dict[str, str]) -> np.ndarray:
    return b.stretch(data if data.ndim == 2 else data[0], cmap="inferno")


def build(row: dict[str, str]):
    src.ee_init()
    data = b.cast(src.ee_row(row), row["dtype"])
    return data, preview(data, row)


if __name__ == "__main__":
    b.main(CORPUS, select, build, preview)
