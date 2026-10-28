"""The change detection use case, on alphaearth-v1-64 and the 2017 embeddings of build.py.

uv run python usecases/change-detection/run.py
"""

import csv
from pathlib import Path

import numpy as np

from earthcompress.contract import Budget
from earthcompress.corpus import Sample, load_samples
from earthcompress.usecase import configurations, fetch, iou, roundtrip, run

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent.parent / "corpora" / "alphaearth-v1-64"
BUDGETS = [Budget(tau=codes) for codes in (1.0, 4.0, 16.0)]
"""Bounds in int8 codes. The corpus has no budget of its own."""
SIMILARITY = 0.8
"""Cosine similarity of the two years below which a pixel has changed."""
CHANGED = 0.005
"""Smallest changed fraction of a sample on the original.

With less change, a single changed pixel on the decoded copy moves the IoU
between 1 and 0.
"""


def embedding(codes: np.ndarray) -> np.ndarray:
    values = codes.astype(np.float32)
    return np.sign(values) * np.square(values / 127.5)


def changed(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    a, b = embedding(before), embedding(after)
    with np.errstate(divide="ignore", invalid="ignore"):
        similarity = (a * b).sum(0) / np.sqrt((a * a).sum(0) * (b * b).sum(0))
    valid = (before != -128).all(0) & (after != -128).all(0)
    return valid & (similarity < SIMILARITY)


def task(item: tuple[Sample, str]) -> list[dict]:
    sample, path = item
    with np.load(HERE / path) as archive:
        before = archive["data"]
    after = sample.data
    change = changed(before, after)
    if change.mean() < CHANGED:
        return []
    rows = []
    for config in configurations(BUDGETS, sample.spec):
        decoded = changed(
            roundtrip(config, before, sample.spec),
            roundtrip(config, after, sample.spec),
        )
        rows.append(
            {
                "id": sample.id,
                "configuration": config.id,
                "family": config.family,
                "tau": config.budget.tau,
                "change_iou": iou(change, decoded),
            }
        )
    return rows


def preview(path: Path) -> None:
    """Iowa in 2025, with the pixels that changed since 2017."""
    from PIL import Image

    from earthcompress.build import rgb

    after = load_samples(CORPUS, limit=4)[3].data
    with np.load(HERE / "npz" / "alphaearth-v1-64-03.npz") as archive:
        before = archive["data"]
    image = rgb(embedding(after)[i] for i in (0, 16, 9))
    image[changed(before, after)] = (230, 60, 90)
    Image.fromarray(image).save(path, optimize=True)


def main() -> None:
    with (HERE / "manifest.csv").open(newline="") as stream:
        paths = {row["id"]: row["npz_path"] for row in csv.DictReader(stream)}
    fetch(HERE, paths.values())
    samples = load_samples(CORPUS)
    run(task, [(s, paths[s.id]) for s in samples], HERE / "results.csv")
    preview(HERE / "preview.png")


if __name__ == "__main__":
    main()
