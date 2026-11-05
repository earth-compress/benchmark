"""The Clouds Decoded use case, on the outputs of runs that are already done.

Clouds Decoded takes hours on a GPU, so this does not run it. It downloads what each
compression level produced, about 48 GB, and compares it with what the original data
produced. ``levels.csv`` gives the error and compression ratio of each level, measured
separately.

uv run --extra corpus python usecases/clouds-decoded/run.py
"""

import csv
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

from earthcompress.usecase import fetch, iou, overlay, shade

HERE = Path(__file__).resolve().parent
OUTPUTS = ("cloud_mask", "cloud_height", "properties")
MIN_PIXELS = 1000
"""Fewer ice pixels than this give no radius value, rather than a noisy one."""
WORKERS = 8
"""Each worker holds about 1 GB, so not one per core as in ``usecase.run``."""
CTH_LIMIT = 3000.0
"""Change in cloud top height at the two ends of the colour bar, in metres."""


def read(sample: str, level: str, name: str) -> np.ndarray:
    """All bands of one output, as bands × rows × columns."""
    with rasterio.open(HERE / "tif" / sample / level / f"{name}.tif") as src:
        return src.read().astype(np.float32)


def texture(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> float:
    """The mean step between neighbouring valid pixels, in ``b`` over ``a``."""
    rows, columns = valid[1:] & valid[:-1], valid[:, 1:] & valid[:, :-1]

    def steps(x: np.ndarray) -> float:
        return (
            np.abs(np.diff(x, axis=0))[rows].sum()
            + np.abs(np.diff(x, axis=1))[columns].sum()
        )

    return float(steps(b) / steps(a))


def compare(original: dict, decoded: dict) -> dict:
    """The metrics from compressed data against those from the original."""
    h0, h1 = original["height"], decoded["height"]
    both = np.isfinite(h0) & np.isfinite(h1)
    error = h1[both] - h0[both]

    t0, t1 = original["properties"][0], decoded["properties"][0]
    positive = (t0 > 0) & (t1 > 0)

    # A radius retrieved as the other phase is not comparable, so a pixel counts
    # only when it is ice in the original and stays on the ice side.
    r0, r1 = original["properties"][3], decoded["properties"][3]
    ice = (
        (original["properties"][1] > 0.6)
        & (decoded["properties"][1] > 0.5)
        & np.isfinite(r0)
        & np.isfinite(r1)
    )
    enough = ice.sum() >= MIN_PIXELS

    return {
        "cloud_iou": iou(original["mask"], decoded["mask"]),
        "cth_mae": float(np.abs(error).mean()),
        "cth_bias": float(error.mean()),
        "tau_median_rel_error": float(
            100 * np.median(np.abs(t1[positive] / t0[positive] - 1))
        ),
        "re_ice_mae": float(np.abs(r1[ice] - r0[ice]).mean()) if enough else None,
        "re_ice_texture": texture(r0, r1, ice) if enough else None,
    }


def outputs(sample: str, level: str) -> dict:
    """What Clouds Decoded produced for one product at one level."""
    return {
        "mask": read(sample, level, "cloud_mask")[0] == 1,
        "height": read(sample, level, "cloud_height")[0],
        "properties": read(sample, level, "properties"),
    }


def maps(
    background: np.ndarray, original: np.ndarray, decoded: np.ndarray
) -> Image.Image:
    """The two cloud masks over the scene in grey, every 12th pixel of the 15 m mask.

    Cloud on both is orange, cloud the compressed data loses is blue, and cloud it
    adds is red.
    """
    a, b = original[::12, ::12], decoded[::12, ::12]
    return Image.fromarray(overlay(shade(background), a & b, a & ~b, ~a & b))


def height_change(
    background: np.ndarray, original: np.ndarray, decoded: np.ndarray
) -> Image.Image:
    """The change in cloud top height, every 3rd pixel of the 60 m heights.

    Blue is lower than the original, red higher and white unchanged. A pixel without
    a height in both stays grey.
    """
    from earthcompress.build import colour

    change = (decoded - original)[::3, ::3]
    found = np.isfinite(change)
    image = shade(background)
    scaled = np.clip((change[found] / CTH_LIMIT + 1) / 2, 0, 1)
    image[found] = colour(scaled, "RdBu_r")
    return Image.fromarray(image)


def save(image: Image.Image, path: Path) -> None:
    """``image`` as a PNG of at most 256 colours, which halves its size."""
    image.quantize(256, dither=Image.Dither.NONE).save(path, optimize=True)


def task(item: tuple[str, list[dict]]) -> list[dict]:
    sample, levels = item
    original = outputs(sample, "original")
    figures = HERE / "png" / sample
    with Image.open(figures / "rgb.png") as image:
        background = np.asarray(image.convert("L"), np.float32)

    rows = []
    for row in levels:
        level = row["configuration"]
        codec, setting = level.split("_")
        decoded = outputs(sample, level)
        save(
            maps(background, original["mask"], decoded["mask"]),
            figures / f"{level}.png",
        )
        save(
            height_change(background, original["height"], decoded["height"]),
            figures / f"{level}-cth.png",
        )
        rows.append(
            {
                "id": sample,
                "configuration": level,
                "codec": codec,
                # The number in the level's name: these codecs have no bound on the
                # root-mean-square error, but the results page orders points by it.
                "rms_bound": float(setting.split("-")[-1]),
                "rmse": float(row["rmse"]),
                "compression_ratio": float(row["compression_ratio"]),
                **compare(original, decoded),
            }
        )
    return rows


def main() -> None:
    with (HERE / "manifest.csv").open(newline="") as stream:
        samples = [row["id"] for row in csv.DictReader(stream)]
    with (HERE / "levels.csv").open(newline="") as stream:
        levels = list(csv.DictReader(stream))
    paths = [f"png/{sample}/rgb.png" for sample in samples]
    for sample in samples:
        names = {row["configuration"] for row in levels if row["id"] == sample}
        paths += [
            f"tif/{sample}/{level}/{name}.tif"
            for level in names | {"original"}
            for name in OUTPUTS
        ]
    fetch(HERE, paths)

    items = [(s, [row for row in levels if row["id"] == s]) for s in samples]
    with ProcessPoolExecutor(WORKERS) as pool:
        rows = [row for rows in pool.map(task, items) for row in rows]
    with (HERE / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
