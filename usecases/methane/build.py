"""The twenty patches of the methane use case, from MethaneSET on their native grid.

uv run --with tacoreader --with pandas --with "duckdb<1.5" python usecases/methane/build.py
"""

import csv
import os
from pathlib import Path

import numpy as np

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

import rasterio  # noqa: E402
import tacoreader  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = "https://huggingface.co/datasets/tacofoundation/methaneset/resolve/main"
SENSORS = {
    "s2": dict(
        collection="methaneset-s2-finetune",
        bands=[11, 12],
        backgrounds=["bg0", "bg1", "bg2", "bg3"],
        block=2,
        pixel=20,
    ),
    "l89": dict(
        collection="methaneset-l89-finetune",
        bands=[5, 6],
        backgrounds=["bg0"],
        block=3,
        pixel=30,
    ),
}
PATCHES = {
    "s2": [
        "b615fcc6-7589-405e-9048-1ff06c587746",
        "f4bb9caf-6538-4180-94d2-371556b5622a",
        "c05c3b35-e370-434e-b63a-941b292c9d05",
        "4be2300a-3b72-4741-85a8-e51201277b2b",
        "563a9025-917f-4cfb-bf08-a2ff880a038d",
        "34f5931e-b55e-4684-b81d-82e693ce5b32",
        "92010314-21bc-4330-94cb-6a4a058f3f81",
        "e0507c84-8413-469c-8add-0b878c80baa2",
        "a5c82654-2d3a-45db-a480-cdbdd1497f8a",
        "c54b3e35-4dad-4eaa-8dd4-4b432e72661e",
    ],
    "l89": [
        "7dc92434-bfca-4201-98b1-81cfa0691633",
        "5c214d71-ffe7-4b2f-b291-f0f88367dfb3",
        "e4f42b60-0ccf-49d3-8c6b-7a66e35e99db",
        "08f43b29-b354-4256-83a0-3a663eaa1234",
        "7f376ed2-b346-4cba-bfb7-ae95ada7d7f2",
        "77732c17-89ce-46d0-88ba-acfec3e1343e",
        "f0d14542-b785-4dbe-bd8c-6aff3a9d50d0",
        "8feb1956-b9f7-4bad-9e2b-aa51dc755801",
        "6d5784e3-1265-4c5a-b054-ffab64feb2e5",
        "08b4aec1-6fb0-4cf8-88a7-8c8b18da4cb6",
    ],
}


def read(scene, layer: str) -> tuple[np.ndarray, float | None]:
    with rasterio.open(scene.read(layer)) as src:
        return src.read(), src.nodata


REFLECTANCE = 2e-5
"""Reflectance of one DN of Landsat Collection 2, as in l8-oli-8."""


def dn(reflectance: np.ndarray) -> np.ndarray:
    codes = np.rint(reflectance.astype(np.float64) / REFLECTANCE)
    return np.clip(codes, 0, np.iinfo(np.uint16).max).astype(np.uint16)


def blocks(array: np.ndarray, block: int, oy: int, ox: int) -> np.ndarray:
    """The whole ``block`` × ``block`` cells of the last two axes, from (oy, ox)."""
    h = (array.shape[-2] - oy) // block * block
    w = (array.shape[-1] - ox) // block * block
    cut = array[..., oy : oy + h, ox : ox + w]
    return cut.reshape(*cut.shape[:-2], h // block, block, w // block, block)


def origin(target: np.ndarray, block: int) -> tuple[int, int]:
    """Where the blocks MethaneSET repeats each native pixel over start."""
    for oy in range(block):
        for ox in range(block):
            cells = blocks(target, block, oy, ox)
            if np.array_equal(
                cells, np.broadcast_to(cells[..., :1, :, :1], cells.shape)
            ):
                return oy, ox
    raise ValueError(f"the target is not repeated over {block} × {block} blocks")


def main() -> None:
    tacoreader.use("pandas")
    (HERE / "npz").mkdir(exist_ok=True)
    rows = []
    for sensor, s in SENSORS.items():
        dataset = tacoreader.load(f"{ROOT}/{s['collection']}/")
        ids = list(dataset.data.to_pandas()["id"])
        for k, patch in enumerate(PATCHES[sensor]):
            scene = dataset.read(ids.index(patch))
            target, nodata = read(scene, "target")
            target = target[s["bands"]]
            bg = np.stack(
                [read(scene, name)[0][s["bands"]] for name in s["backgrounds"]]
            )
            if bg.dtype != target.dtype:
                raise ValueError(
                    f"{patch}: backgrounds are {bg.dtype}, target {target.dtype}"
                )
            if target.dtype.kind == "f":
                # Landsat reflectance as uint16 DN, which moves no value by more
                # than half a DN.
                target, bg, nodata = dn(target), dn(bg), None
            plume = read(scene, "plume")[0][0] > 0

            # Back to the native grid, one value per repeated block. The mask is
            # drawn at 10 m, so a native pixel is plume where most of it is.
            oy, ox = origin(target, s["block"])
            target = blocks(target, s["block"], oy, ox)[..., 0, :, 0]
            bg = blocks(bg, s["block"], oy, ox)[..., 0, :, 0]
            plume = blocks(plume, s["block"], oy, ox).mean(axis=(-3, -1)) > 0.5
            name = f"methane-{sensor}-{k:02d}"
            np.savez_compressed(
                HERE / "npz" / f"{name}.npz", target=target, bg=bg, plume=plume
            )
            rows.append(
                {
                    "id": name,
                    "sensor": sensor,
                    "methaneset_id": patch,
                    "pixel_m": s["pixel"],
                    "shape": "x".join(str(n) for n in target.shape),
                    "dtype": str(target.dtype),
                    "nodata": "" if nodata is None else nodata,
                    "plume_pixels": int(plume.sum()),
                    "npz_path": f"npz/{name}.npz",
                }
            )
            print(name, target.shape, target.dtype, int(plume.sum()), flush=True)
    with (HERE / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
