from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import numpy as np
import pytest
import zstandard as zstd

COLUMNS = (
    "id",
    "shape",
    "dtype",
    "grid",
    "grid_unit",
    "exact",
    "input_sha256",
    "npz_path",
    "png_path",
)


def write_corpus(
    root: Path,
    arrays: dict[str, np.ndarray],
    *,
    grid: float = 1.0,
    grid_unit: str = "DN",
    extra: dict[str, np.ndarray] | None = None,
) -> Path:
    """Write a minimal protocol-shaped corpus."""
    (root / "npz").mkdir(parents=True, exist_ok=True)
    compressor = zstd.ZstdCompressor(level=1)
    rows = []
    for sample_id, array in arrays.items():
        array = np.ascontiguousarray(array)
        buffer = io.BytesIO()
        np.savez(buffer, data=array, **(extra or {}))
        path = f"npz/{sample_id}.npz.zst"
        (root / path).write_bytes(compressor.compress(buffer.getvalue()))
        rows.append(
            {
                "id": sample_id,
                "shape": "x".join(str(size) for size in array.shape),
                "dtype": array.dtype.name,
                "grid": grid,
                "grid_unit": grid_unit,
                "exact": "True",
                "input_sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
                "npz_path": path,
                "png_path": f"png/{sample_id}.png",
            }
        )
    with (root / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return root


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    generator = np.random.default_rng(0)
    # No zeros: the zero promise gets its own corpus, so near-lossless tests
    # here measure the bound rather than tripping over zero preservation.
    return write_corpus(
        tmp_path / "demo",
        {
            "demo-00": generator.integers(1, 4000, size=(2, 32, 32), dtype=np.int16),
            "demo-01": generator.integers(1, 4000, size=(2, 32, 32), dtype=np.int16),
        },
    )
