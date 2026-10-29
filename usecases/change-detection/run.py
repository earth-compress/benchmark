"""The change detection use case, on the AlphaEarth windows of build.py in 2017 and 2025.

uv run python usecases/change-detection/run.py
"""

import csv
import shutil
from pathlib import Path

import numpy as np

from earthcompress.contract import Budget
from earthcompress.spec import ArraySpec
from earthcompress.usecase import (
    compress,
    fetch,
    iou,
    lossy_codecs,
    overlay,
    run,
    shade,
)

HERE = Path(__file__).resolve().parent
RMS = (1, 2, 4, 8, 16)
"""Root-mean-square errors of the sweep, in codes of the quantised embedding."""
SIMILARITY = 0.8
"""Cosine similarity of the two years below which a pixel has changed."""
PREVIEW = (0, 16, 9)
SHOWN = "gerd"
"""The site of the picture on the use case page."""


def codes(embedding: np.ndarray) -> np.ndarray:
    """The int8 codes as uint8, which JPEG XL takes, with NoData at 0.

    Adding 128 changes no value, it only moves the range.
    """
    return (embedding.astype(np.int16) + 128).astype(np.uint8)


def embedding(stored: np.ndarray) -> np.ndarray:
    values = stored.astype(np.float32) - 128
    return np.sign(values) * np.square(values / 127.5)


def changed(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    a, b = embedding(before), embedding(after)
    with np.errstate(divide="ignore", invalid="ignore"):
        similarity = (a * b).sum(0) / np.sqrt((a * a).sum(0) * (b * b).sum(0))
    valid = (before != 0).all(0) & (after != 0).all(0)
    return valid & (similarity < SIMILARITY)


def maps(background: np.ndarray, original: np.ndarray, decoded=None):
    """The change map over the 2025 embedding in grey.

    With a decoded map, pixels changed on both are orange, pixels the decoded
    map loses are blue, and pixels it adds are red.
    """
    from PIL import Image

    if decoded is None:
        image = overlay(background, original)
    else:
        image = overlay(
            background, original & decoded, original & ~decoded, ~original & decoded
        )
    return Image.fromarray(image)


def years(row: dict[str, str]) -> tuple[np.ndarray, np.ndarray]:
    with np.load(HERE / row["npz_path"]) as archive:
        return codes(archive["before"]), codes(archive["after"])


def task(row: dict[str, str]) -> list[dict]:
    from earthcompress.build import rgb

    before, after = years(row)
    change = changed(before, after)
    background = shade(rgb(embedding(after)[i] for i in PREVIEW).mean(axis=-1))
    figures = HERE / "png" / row["id"]
    shutil.rmtree(figures, ignore_errors=True)
    figures.mkdir(parents=True)
    maps(background, change).save(figures / "original.png", optimize=True)

    spec = ArraySpec(after.shape, after.dtype, sentinel=0)
    rows = []
    for make in lossy_codecs():
        for bound in RMS:
            config = make(Budget(tau=bound))
            if not config.supports(spec):
                continue
            decoded_before, size = compress(config, before, spec)
            decoded_after, n = compress(config, after, spec)
            size += n
            squared = np.sum(np.square(decoded_before - before.astype(np.float64)))
            squared += np.sum(np.square(decoded_after - after.astype(np.float64)))
            found = changed(decoded_before, decoded_after)
            maps(background, change, found).save(
                figures / f"{config.id}.png", optimize=True
            )
            rows.append(
                {
                    "id": row["id"],
                    "site": row["site"],
                    "configuration": config.id,
                    "codec": config.id.split("-tau")[0],
                    "rms_bound": bound,
                    "rmse": float(np.sqrt(squared / (before.size + after.size))),
                    "compression_ratio": (before.nbytes + after.nbytes) / size,
                    "change_iou": iou(change, found),
                }
            )
    return rows


def preview(row: dict[str, str], path: Path) -> None:
    """The 2025 embedding of ``row``, with the pixels that changed since 2017."""
    from PIL import Image

    from earthcompress.build import rgb

    before, after = years(row)
    image = rgb(embedding(after)[i] for i in PREVIEW)
    image[changed(before, after)] = (230, 60, 90)
    Image.fromarray(image).save(path, optimize=True)


def main() -> None:
    with (HERE / "manifest.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    fetch(HERE, [row["npz_path"] for row in rows])
    run(task, rows, HERE / "results.csv")
    preview(next(r for r in rows if r["site"] == SHOWN), HERE / "preview.png")


if __name__ == "__main__":
    main()
