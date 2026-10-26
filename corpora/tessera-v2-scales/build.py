from pathlib import Path

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
ROOT = "https://data.source.coop/tessera/tessera"
VARIANT = "v2-2B-L~beta1"
PIXEL = 10
SIZE = 512


def select() -> list[dict[str, str]]:
    import rasterio

    rows = []
    for old in b.legacy(CORPUS, "tessera-v2-128"):
        tile, year = old["source_tile"], old["year"]
        with rasterio.open(f"/vsicurl/{ROOT}/landmasks/v2/{tile}.tiff") as mask:
            t, crs = mask.transform, mask.crs.to_string()
        if (abs(t.a) != PIXEL) or t.b or t.d:
            raise ValueError(f"{tile}: unexpected landmask grid")
        top, left = int(old["crop_row"]), int(old["crop_col"])
        rows.append(
            {
                "id": old["id"].replace("tessera-v2-128", CORPUS.name),
                "source": f"TESSERA {old['model']} embeddings, {VARIANT}",
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
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
                "source_tile": tile,
                "crop_row": old["crop_row"],
                "crop_col": old["crop_col"],
            }
        )
    return rows


def build(row: dict[str, str]):
    block = src.npy_window(
        row["asset"], int(row["crop_row"]), int(row["crop_col"]), SIZE, SIZE
    )
    data = b.cast(block, row["dtype"])
    return data, b.stretch(data)


if __name__ == "__main__":
    b.main(CORPUS, select, build)
