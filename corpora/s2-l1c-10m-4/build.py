from pathlib import Path

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
BANDS = ["B2", "B3", "B4", "B8"]
SIZE = 512
PREVIEW = (2, 1, 0)


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for sample in b.read_manifest(CORPUS):
        asset = sample["asset"]
        image = ee.Image(asset)
        keys = [
            "system:time_start",
            "MGRS_TILE",
            "PROCESSING_BASELINE",
            "SPACECRAFT_NAME",
        ]
        keys += [f"RADIO_ADD_OFFSET_{band}" for band in BANDS]
        props = image.toDictionary(keys).getInfo()
        when = src.utc(props["system:time_start"])
        rows.append(
            {
                "id": sample["id"],
                "source": "COPERNICUS/S2 (Sentinel-2 MSI Level-1C)",
                "asset": asset,
                "crs": sample["crs"],
                "transform": sample["transform"],
                "datetime_start": when,
                "datetime_end": when,
                "bands": b.join(BANDS),
                "shape": f"{len(BANDS)}x{SIZE}x{SIZE}",
                "dtype": "uint16",
                "unit": "DN",
                "scale": "1",
                "offset": "0",
                "nodata": "0",
                "site": sample["site"],
                "regime": sample["regime"],
                "lon": sample["lon"],
                "lat": sample["lat"],
                "spacecraft": props.get("SPACECRAFT_NAME", ""),
                "mgrs_tile": props.get("MGRS_TILE", ""),
                "processing_baseline": props.get("PROCESSING_BASELINE", ""),
                "radio_add_offset": b.join(
                    int(props.get(f"RADIO_ADD_OFFSET_{band}", 0)) for band in BANDS
                ),
            }
        )
    return rows


def build(row: dict[str, str]):
    src.ee_init()
    data = b.cast(src.ee_row(row), row["dtype"])
    return data, b.rgb(data[i] for i in PREVIEW)


if __name__ == "__main__":
    b.main(CORPUS, select, build)
