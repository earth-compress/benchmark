"""The crops of the Clouds Decoded use case, cut from their Sentinel-2 L1C products.

Each crop is 2520 × 2520 pixels at 10 m, 70 georvq windows of 36 pixels across,
with the matching 1260 and 420 pixels at 20 and 60 m. ``crops/<id>.zip`` holds a
``.SAFE`` directory with what Clouds Decoded reads besides the band images, the
13 bands of the crop as uint16 DN in ``bands.npz``, and a ``COMPRESSED.json``
that sends Clouds Decoded to them through ``run.py``.

uv run --extra corpus python usecases/clouds-decoded/build.py /data/s2get/Sentinel-2/MSI/L1C
"""

import csv
import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

HERE = Path(__file__).resolve().parent
SIZE = 2520
"""Pixels of a crop at 10 m."""
BANDS = {
    "B01": 60,
    "B02": 10,
    "B03": 10,
    "B04": 10,
    "B05": 20,
    "B06": 20,
    "B07": 20,
    "B08": 10,
    "B8A": 20,
    "B09": 60,
    "B10": 60,
    "B11": 20,
    "B12": 20,
}
"""The 13 bands and their pixel size in metres."""
KEPT = ("MTD_TL.xml", "QI_DATA/MSK_DETFOO_", "AUX_DATA/AUX_ECMWFT")
"""What Clouds Decoded reads in a granule besides the band images."""


def product(root: Path, name: str) -> Path:
    date = name.split("_")[2]
    path = root / date[:4] / date[4:6] / date[6:8] / f"{name}.SAFE"
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def band(safe: Path, name: str, col: int, row: int) -> tuple[np.ndarray, dict]:
    """The crop of one band on its native grid, and the band's full grid."""
    (path,) = safe.glob(f"GRANULE/*/IMG_DATA/*_{name}.jp2")
    step = BANDS[name] // 10
    with rasterio.open(path) as src:
        window = Window(col // step, row // step, SIZE // step, SIZE // step)
        data = src.read(1, window=window, boundless=False)
        grid = {"shape": [src.height, src.width], "res": BANDS[name]}
        if name == "B02":
            grid["georef"] = {
                "crs": src.crs.to_wkt(),
                "transform": list(src.transform)[:6],
                "width": src.width,
                "height": src.height,
            }
    if data.shape != (SIZE // step, SIZE // step):
        raise ValueError(f"{safe.name} {name}: the crop leaves the product")
    return data, grid


def crop(safe: Path, row: dict) -> bytes:
    col, line = int(row["col_off"]), int(row["row_off"])
    if col % 6 or line % 6:
        raise ValueError(f"{row['id']}: the crop must start on a 60 m pixel")
    with ThreadPoolExecutor(len(BANDS)) as pool:
        read = dict(
            zip(BANDS, pool.map(lambda b: band(safe, b, col, line), BANDS), strict=True)
        )
    arrays = {b: data for b, (data, _) in read.items()}
    grids = {b: grid for b, (_, grid) in read.items()}
    manifest = {
        "format": "clouds-decoded-compressed",
        "version": 2,
        "reader": "crop",
        "georef": grids["B02"].pop("georef"),
        "window": [col, line, SIZE, SIZE],
        "bands": grids,
    }
    npz = io.BytesIO()
    np.savez_compressed(npz, **arrays)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(safe / "MTD_MSIL1C.xml", f"{safe.name}/MTD_MSIL1C.xml")
        for path in sorted(safe.glob("GRANULE/*/**/*")):
            relative = path.relative_to(safe).as_posix()
            if path.is_file() and any(k in relative for k in KEPT):
                z.write(path, f"{safe.name}/{relative}")
        z.writestr(f"{safe.name}/COMPRESSED.json", json.dumps(manifest, indent=1))
        z.writestr(f"{safe.name}/bands.npz", npz.getvalue(), zipfile.ZIP_STORED)
    return out.getvalue()


def main() -> None:
    root = Path(sys.argv[1])
    with (HERE / "manifest.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    (HERE / "crops").mkdir(exist_ok=True)
    for row in rows:
        data = crop(product(root, row["product"]), row)
        (HERE / "crops" / f"{row['id']}.zip").write_bytes(data)
        print(f"{row['id']}: {len(data) / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
