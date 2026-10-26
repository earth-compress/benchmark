import csv
import urllib.request
from pathlib import Path

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
ROOT = "https://storage.googleapis.com/alphaearth_foundations/satellite_embedding/v1/annual"
BANDS = [f"A{i:02d}" for i in range(64)]
PIXEL = 10
SIZE = 512
PREVIEW = (0, 16, 9)


def index() -> list[dict[str, str]]:
    path = src.CACHE / "aef" / "aef_index.csv"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(f"{ROOT}/aef_index.csv", path)
    csv.field_size_limit(1 << 30)
    with path.open(newline="") as stream:
        return [
            {k: v for k, v in row.items() if k != "WKT"}
            for row in csv.DictReader(stream)
        ]


def select() -> list[dict[str, str]]:
    files = index()
    rows = []
    for old in b.legacy(CORPUS):
        x0, y0 = float(old["translate_x"]), float(old["translate_y"])
        x1, y1 = x0 + SIZE * PIXEL, y0 - SIZE * PIXEL
        found = [
            f
            for f in files
            if old["image_id"] in f["path"]
            and f["year"] == old["year"]
            and float(f["utm_west"]) <= x0
            and x1 <= float(f["utm_east"])
            and float(f["utm_south"]) <= y1
            and y0 <= float(f["utm_north"])
        ]
        if len(found) != 1:
            raise ValueError(f"{old['id']}: {len(found)} files hold the window")
        asset = found[0]["path"].replace(
            "gs://alphaearth_foundations/satellite_embedding/v1/annual", ROOT
        )
        rows.append(
            {
                "id": old["id"],
                "source": "AlphaEarth Foundations Satellite Embedding V1 annual, int8 COGs",
                "asset": asset,
                "crs": found[0]["crs"],
                "transform": b.transform_text(x0, PIXEL, y0, -PIXEL),
                "datetime_start": f"{old['year']}-01-01T00:00:00Z",
                "datetime_end": f"{old['year']}-12-31T23:59:59Z",
                "bands": b.join(BANDS),
                "shape": f"{len(BANDS)}x{SIZE}x{SIZE}",
                "dtype": "int8",
                "unit": "quantised embedding",
                "scale": "1",
                "offset": "0",
                "nodata": "-128",
                "input_sha256": old["input_sha256"],
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
                "year": old["year"],
            }
        )
    return rows


def build(row: dict[str, str]):
    data, _ = src.cog_window(
        "/vsicurl/" + row["asset"],
        b.parse_transform(row["transform"]),
        b.parse_shape(row["shape"])[1:],
    )
    data = b.cast(data, row["dtype"])
    return data, b.rgb(data[i] for i in PREVIEW)


if __name__ == "__main__":
    b.main(CORPUS, select, build)
