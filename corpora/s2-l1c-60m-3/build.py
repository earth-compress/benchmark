from pathlib import Path

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
COLLECTION = "COPERNICUS/S2"
BANDS = ["B1", "B9", "B10"]
PIXEL = 60
SIZE = 512
PREVIEW = (0, 1, 2)


def select() -> list[dict[str, str]]:
    ee = src.ee_init()
    rows = []
    for old in b.legacy(CORPUS):
        asset = f"{COLLECTION}/{old['image_id']}"
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
                "id": old["id"],
                "source": "COPERNICUS/S2 (Sentinel-2 MSI Level-1C)",
                "asset": asset,
                "crs": old["crs"],
                "transform": b.transform_text(
                    float(old["translate_x"]), PIXEL, float(old["translate_y"]), -PIXEL
                ),
                "datetime_start": when,
                "datetime_end": when,
                "bands": b.join(BANDS),
                "shape": f"{len(BANDS)}x{SIZE}x{SIZE}",
                "dtype": "uint16",
                "unit": "DN",
                "scale": "1",
                "offset": "0",
                "nodata": "0",
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
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
