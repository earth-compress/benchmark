"""The drainage network use case, on ten samples of cop-dem-glo30.

uv run --extra corpus python usecases/drainage/run.py
"""

import csv
import heapq
import math
import shutil
from pathlib import Path

import numpy as np

from earthcompress.contract import Budget
from earthcompress.corpus import Sample, load_samples
from earthcompress.spec import ArraySpec
from earthcompress.usecase import compress, lossy_codecs, overlay, run

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent.parent / "corpora" / "cop-dem-glo30"
SAMPLES = [0, 1, 10, 11, 20, 21, 30, 31, 40, 41]
"""The first two samples of each regime."""
STREAM = 1000
"""Upstream cells from which a cell is part of the stream network."""
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
STEP = 0.1
"""Height of one stored code, in metres."""
RMS = (0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4)
"""Root-mean-square errors of the sweep, in metres."""


def codes(dem: np.ndarray) -> tuple[np.ndarray, int]:
    """``dem`` as uint16 decimetres above its lowest whole metre, which JPEG XL
    takes and which moves no height by more than 5 cm, and that metre."""
    base = math.floor(float(np.min(dem)))
    stored = np.rint((dem.astype(np.float64) - base) / STEP)
    if stored.max() > np.iinfo(np.uint16).max:
        raise ValueError("the relief does not fit in uint16 decimetres")
    return stored.astype(np.uint16), base


def upstream(dem: np.ndarray) -> np.ndarray:
    """Cells draining through each cell.

    A priority flood from the edges reaches every cell from the lowest cell
    around it, and each cell drains to the cell that reached it, so pits and
    flats drain too. Ties go to the cell reached first.
    """
    rows, cols = dem.shape
    z = dem.ravel().tolist()
    receiver = [-1] * len(z)
    seen = bytearray(len(z))
    edge = sorted(
        {r * cols + c for r in (0, rows - 1) for c in range(cols)}
        | {r * cols + c for r in range(rows) for c in (0, cols - 1)}
    )
    heap = []
    for i in edge:
        seen[i] = 1
        heap.append((z[i], len(heap), i))
    heapq.heapify(heap)
    count = len(heap)
    order = []
    while heap:
        level, _, i = heapq.heappop(heap)
        order.append(i)
        r, c = divmod(i, cols)
        for dr, dc in NEIGHBOURS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols:
                j = rr * cols + cc
                if not seen[j]:
                    seen[j] = 1
                    receiver[j] = i
                    heapq.heappush(heap, (max(z[j], level), count, j))
                    count += 1
    cells = [1] * len(z)
    for i in reversed(order):
        if receiver[i] >= 0:
            cells[receiver[i]] += cells[i]
    return np.array(cells).reshape(rows, cols)


def near(mask: np.ndarray) -> np.ndarray:
    """Cells within one cell of ``mask``."""
    rows, cols = mask.shape
    padded = np.pad(mask, 1)
    out = np.zeros_like(mask)
    for dr in range(3):
        for dc in range(3):
            out |= padded[dr : dr + rows, dc : dc + cols]
    return out


def stream_f1(original: np.ndarray, decoded: np.ndarray) -> float:
    """F1 of the decoded network, a stream cell matching within one cell."""
    if not original.any() and not decoded.any():
        return 1.0
    precision = np.count_nonzero(decoded & near(original)) / max(
        np.count_nonzero(decoded), 1
    )
    recall = np.count_nonzero(original & near(decoded)) / max(
        np.count_nonzero(original), 1
    )
    total = precision + recall
    return 0.0 if total == 0 else 2 * precision * recall / total


def hillshade(dem: np.ndarray) -> np.ndarray:
    """The relief of ``dem`` in dark grey."""
    from earthcompress.build import relief

    grey = relief(dem, 30.0).mean(axis=-1)
    return np.repeat((30 + 0.6 * grey).astype(np.uint8)[..., None], 3, axis=2)


def networks(background: np.ndarray, original: np.ndarray, decoded=None):
    """The stream network over the relief, drawn three cells wide.

    With a decoded network, streams on both within one cell are orange, original
    streams the decoded one misses are blue, and streams it adds are red.
    """
    from PIL import Image

    if decoded is None:
        image = overlay(background, near(original))
    else:
        image = overlay(
            background,
            near((original & near(decoded)) | (decoded & near(original))),
            near(original & ~near(decoded)),
            near(decoded & ~near(original)),
        )
    return Image.fromarray(image)


def task(item: tuple[Sample, str]) -> list[dict]:
    sample, regime = item
    dem, _ = codes(sample.data)
    spec = ArraySpec(dem.shape, dem.dtype)
    streams = upstream(dem) >= STREAM
    background = hillshade(sample.data)
    figures = HERE / "png" / sample.id
    shutil.rmtree(figures, ignore_errors=True)
    figures.mkdir(parents=True)
    networks(background, streams).save(figures / "original.png", optimize=True)

    rows = []
    for make in lossy_codecs():
        for bound in RMS:
            config = make(Budget(tau=bound / STEP))
            if not config.supports(spec):
                continue
            decoded, size = compress(config, dem, spec)
            found = upstream(decoded) >= STREAM
            image = networks(background, streams, found)
            image.save(figures / f"{config.id}.png", optimize=True)
            error = decoded.astype(np.float64) - dem
            rows.append(
                {
                    "id": sample.id,
                    "regime": regime,
                    "configuration": config.id,
                    "codec": config.id.split("-tau")[0],
                    "rms_bound": bound,
                    "rmse": float(np.sqrt(np.mean(np.square(error)))) * STEP,
                    "compression_ratio": dem.nbytes / size,
                    "stream_f1": stream_f1(streams, found),
                }
            )
    return rows


def preview(path: Path) -> None:
    """The relief of the first sample with its stream network."""
    from PIL import Image

    from earthcompress.build import relief

    dem = load_samples(CORPUS, limit=1)[0].data
    image = relief(dem, 30.0)
    image[near(upstream(dem) >= STREAM)] = (24, 92, 196)
    Image.fromarray(image).save(path, optimize=True)


def main() -> None:
    with (CORPUS / "manifest.csv").open(newline="") as stream:
        corpus = {row["id"]: row for row in csv.DictReader(stream)}
    samples = [load_samples(CORPUS)[i] for i in SAMPLES]
    rows = []
    for sample in samples:
        dem, base = codes(sample.data)
        rows.append(
            {
                "id": sample.id,
                "site": corpus[sample.id]["site"],
                "regime": corpus[sample.id]["regime"],
                "shape": "x".join(str(n) for n in dem.shape),
                "dtype": str(dem.dtype),
                "base_m": base,
            }
        )
    with (HERE / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    run(task, [(s, corpus[s.id]["regime"]) for s in samples], HERE / "results.csv")
    preview(HERE / "preview.png")


if __name__ == "__main__":
    main()
