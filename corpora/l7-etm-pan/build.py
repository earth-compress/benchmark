from pathlib import Path

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
DTYPE = "uint8"
SIZE = 1024
PREVIEW = None


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for sample in b.read_manifest(CORPUS):
        asset = sample["asset"]
        when = src.utc(ee.Image(asset).get("system:time_start").getInfo())
        rows.append(
            {
                "id": sample["id"],
                "source": f"{asset.rsplit('/', 1)[0]} (Landsat Collection 2 Level-1)",
                "asset": asset,
                "crs": sample["crs"],
                "transform": sample["transform"],
                "datetime_start": when,
                "datetime_end": when,
                "bands": sample["bands"],
                "shape": "x".join(map(str, (SIZE, SIZE))),
                "dtype": DTYPE,
                "unit": "DN",
                "scale": "1",
                "offset": "0",
                "nodata": "0",
                "input_sha256": sample["input_sha256"],
                "site": sample["site"],
                "regime": sample["regime"],
                "lon": sample["lon"],
                "lat": sample["lat"],
                "spacecraft": sample["spacecraft"],
                "sensor": sample["sensor"],
                "product_id": sample["product_id"],
                "wrs_path": sample["wrs_path"],
                "wrs_row": sample["wrs_row"],
                "acquired_m": sample["acquired_m"],
            }
        )
    return rows


def build(row: dict[str, str]):
    src.ee_init()
    data = b.cast(src.ee_row(row), row["dtype"])
    preview = b.stretch(data if data.ndim == 2 else data[0])
    return data, preview


if __name__ == "__main__":
    b.main(CORPUS, select, build)
