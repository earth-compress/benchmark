import csv
import math
import re
import urllib.request
from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src

CORPUS = Path(__file__).resolve().parent
BUCKET = "https://s3.us-west-2.amazonaws.com/us-west-2.opendata.source.coop"
PREFIX = "clay/lgnd-clay-v1-5-sentinel-2-l2a/aggregated"
HTTPS = "https://data.source.coop"
YEAR, MONTH = 2024, 6
CELLS = 32
DIMENSIONS = 1024
CELL_KM = 2.56
BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
CELL_COLUMNS = [
    "row",
    "col",
    "cell_id",
    "chips_id",
    "stac_item_id",
    "datetime",
    "xmin",
    "ymin",
    "xmax",
    "ymax",
]


def geohash(lon: float, lat: float, length: int = 2) -> str:
    lo, la = [-180.0, 180.0], [-90.0, 90.0]
    bits, text, even, value = 0, "", True, 0
    while len(text) < length:
        span = lo if even else la
        mid = (span[0] + span[1]) / 2
        coordinate = lon if even else lat
        value = value * 2 + (coordinate >= mid)
        span[0 if coordinate >= mid else 1] = mid
        even, bits = not even, bits + 1
        if bits == 5:
            text, bits, value = text + BASE32[value], 0, 0
    return text


def files(partition: str) -> list[str]:
    url = f"{BUCKET}?list-type=2&prefix={PREFIX}/geohash_l2={partition}/year={YEAR}/month={MONTH:02d}/"
    with urllib.request.urlopen(url, timeout=120) as response:
        listing = response.read().decode()
    return [
        f"{HTTPS}/{key}" for key in re.findall(r"<Key>([^<]+\.parquet)</Key>", listing)
    ]


def local(url: str) -> Path:
    path = src.CACHE / "clay" / url.split(f"{PREFIX}/", 1)[1]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            url, headers={"User-Agent": "EarthCompress/0.1"}
        )
        with urllib.request.urlopen(request, timeout=600) as response:
            path.with_suffix(".part").write_bytes(response.read())
        path.with_suffix(".part").rename(path)
    return path


def read(urls: list[str], columns: list[str]):
    import pyarrow as pa
    import pyarrow.parquet as pq

    return pa.concat_tables(
        [pq.read_table(local(url), columns=columns) for url in urls]
    )


def block(table, lon: float, lat: float) -> list[dict]:
    """The 32 by 32 cells nearest a point, as contiguous rows."""
    bbox = table.column("bbox").to_pylist()
    ids = table.column("cell_id").to_pylist()
    rows: dict[float, list[int]] = {}
    for i, box in enumerate(bbox):
        rows.setdefault(round(box["ymin"], 6), []).append(i)
    keys = sorted(rows, reverse=True)
    centre = min(range(len(keys)), key=lambda k: abs(keys[k] - lat))
    chosen = keys[centre - CELLS // 2 : centre + CELLS // 2]
    if len(chosen) != CELLS:
        raise ValueError(f"only {len(chosen)} rows near {lon},{lat}")
    cells = []
    for r, key in enumerate(chosen):
        members = sorted(set(rows[key]), key=lambda i: bbox[i]["xmin"])
        members = list({ids[i]: i for i in members}.values())
        nearest = min(
            range(len(members)), key=lambda k: abs(bbox[members[k]]["xmin"] - lon)
        )
        run = members[nearest - CELLS // 2 : nearest + CELLS // 2]
        if len(run) != CELLS:
            raise ValueError(f"row {r}: only {len(run)} cells near {lon},{lat}")
        width = bbox[run[0]]["xmax"] - bbox[run[0]]["xmin"]
        for a, c in zip(run, run[1:], strict=False):
            if abs(bbox[c]["xmin"] - bbox[a]["xmax"]) > 0.05 * width:
                raise ValueError(f"row {r}: a gap in the cells near {lon},{lat}")
        cells += [(r, col, i) for col, i in enumerate(run)]
    return cells


def nearest_block(table, lon: float, lat: float, step_lon: float, step_lat: float):
    """The complete block nearest the site, moving the centre by up to 16 cells.

    Clay has no cells over open water, so a block centred on a coast can have gaps.
    """
    shifts = sorted(
        ((dx, dy) for dx in range(-16, 17, 4) for dy in range(-16, 17, 4)),
        key=lambda d: (d[0] ** 2 + d[1] ** 2, d),
    )
    for dx, dy in shifts:
        centre = (lon + dx * step_lon, lat + dy * step_lat)
        try:
            return block(table, *centre), centre
        except ValueError:
            continue
    raise ValueError(f"no complete block within 16 cells of {lon},{lat}")


def select() -> list[dict[str, str]]:
    rows = []
    (CORPUS / "cells").mkdir(exist_ok=True)
    for old in b.legacy(CORPUS, "alphaearth-v1-64"):
        lon, lat = float(old["lon"]), float(old["lat"])
        dlat = CELLS * CELL_KM / 111.0
        dlon = dlat / math.cos(math.radians(lat))
        partitions = sorted(
            {
                geohash(lon + sx * dlon, lat + sy * dlat)
                for sx in (-1, 0, 1)
                for sy in (-1, 0, 1)
            }
        )
        urls = [url for p in partitions for url in files(p)]
        table = read(urls, ["cell_id", "chips_id", "stac_item_id", "datetime", "bbox"])
        sid = old["id"].replace("alphaearth-v1-64", CORPUS.name)
        cells, centre = nearest_block(table, lon, lat, dlon / CELLS, dlat / CELLS)
        bbox = table.column("bbox").to_pylist()
        records = []
        for r, col, i in cells:
            records.append(
                {
                    "row": r,
                    "col": col,
                    "cell_id": table.column("cell_id")[i].as_py(),
                    "chips_id": table.column("chips_id")[i].as_py(),
                    "stac_item_id": table.column("stac_item_id")[i].as_py(),
                    "datetime": table.column("datetime")[i]
                    .as_py()
                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    **{k: repr(bbox[i][k]) for k in ("xmin", "ymin", "xmax", "ymax")},
                }
            )
        with (CORPUS / "cells" / f"{sid}.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=CELL_COLUMNS, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(records)
        widths = [float(c["xmax"]) - float(c["xmin"]) for c in records]
        heights = [float(c["ymax"]) - float(c["ymin"]) for c in records]
        times = sorted(c["datetime"] for c in records)
        rows.append(
            {
                "id": sid,
                "source": "LGND Clay v1.5 Sentinel-2 L2A embeddings, monthly aggregated, 2560 m MajorTOM cells",
                "asset": b.join(urls),
                "crs": "EPSG:4326",
                "transform": b.transform_text(
                    float(records[0]["xmin"]),
                    float(np.mean(widths)),
                    float(records[0]["ymax"]),
                    -float(np.mean(heights)),
                ),
                "datetime_start": times[0],
                "datetime_end": times[-1],
                "bands": b.join(f"E{i:04d}" for i in range(DIMENSIONS)),
                "shape": f"{DIMENSIONS}x{CELLS}x{CELLS}",
                "dtype": "float32",
                "unit": "embedding",
                "scale": "1",
                "offset": "0",
                "nodata": "",
                "site": old["site"],
                "regime": old["regime"],
                "lon": old["lon"],
                "lat": old["lat"],
                "centre_lon": repr(centre[0]),
                "centre_lat": repr(centre[1]),
                "cells_path": f"cells/{sid}.csv",
            }
        )
        print(f"{sid}: {len(urls)} files", flush=True)
    return rows


def build(row: dict[str, str]):
    with (CORPUS / row["cells_path"]).open(newline="") as stream:
        cells = list(csv.DictReader(stream))
    table = read(b.split(row["asset"]), ["cell_id", "embedding"])
    index = {cell: i for i, cell in enumerate(table.column("cell_id").to_pylist())}
    embedding = table.column("embedding")
    data = np.empty((DIMENSIONS, CELLS, CELLS), np.float32)
    for cell in cells:
        vector = np.asarray(embedding[index[cell["cell_id"]]].as_py(), np.float32)
        data[:, int(cell["row"]), int(cell["col"])] = vector
    return data, b.rgb(data[i] for i in (0, 1, 2))


if __name__ == "__main__":
    b.main(CORPUS, select, build)
