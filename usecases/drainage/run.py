"""The drainage network use case, on ten samples of cop-dem-glo30.

uv run python usecases/drainage/run.py
"""

import heapq
from pathlib import Path

import numpy as np

from earthcompress.budgets import budgets_for
from earthcompress.corpus import Sample, load_samples
from earthcompress.usecase import configurations, roundtrip, run

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent.parent / "corpora" / "cop-dem-glo30"
SAMPLES = [0, 1, 10, 11, 20, 21, 30, 31, 40, 41]
"""The first two samples of each regime."""
STREAM = 1000
"""Upstream cells from which a cell is part of the stream network."""
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


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


def task(sample: Sample) -> list[dict]:
    streams = upstream(sample.data) >= STREAM
    rows = []
    for config in configurations(budgets_for(CORPUS.name).values(), sample.spec):
        decoded = roundtrip(config, sample.data, sample.spec)
        rows.append(
            {
                "id": sample.id,
                "configuration": config.id,
                "family": config.family,
                "budget_level": config.budget.level,
                "tau": config.budget.tau,
                "stream_f1": stream_f1(streams, upstream(decoded) >= STREAM),
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
    samples = load_samples(CORPUS)
    run(task, [samples[i] for i in SAMPLES], HERE / "results.csv")
    preview(HERE / "preview.png")


if __name__ == "__main__":
    main()
