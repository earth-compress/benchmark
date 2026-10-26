from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from earthcompress import build


def write_corpus(
    root: Path,
    arrays: dict[str, np.ndarray],
    *,
    scale: str = "1",
    offset: str = "0",
    nodata: str = "",
    unit: str = "DN",
) -> Path:
    """Write a protocol-shaped corpus with the writer the corpus builders use."""
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for sample_id, array in arrays.items():
        row = {
            "id": sample_id,
            "source": "test",
            "asset": "test",
            "crs": "EPSG:4326",
            "transform": build.transform_text(0.0, 1.0, 0.0, -1.0),
            "datetime_start": "2023-01-01T00:00:00Z",
            "datetime_end": "2023-01-01T00:00:00Z",
            "bands": "b",
            "unit": unit,
            "scale": scale,
            "offset": offset,
            "nodata": nodata,
        }
        build.save(root, row, array)
        rows.append(row)
    build.write_manifest(root, rows)
    return root


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    generator = np.random.default_rng(0)
    # No zeros: the zero promise gets its own corpus, so near-lossless tests
    # here measure the bound rather than tripping over zero preservation.
    return write_corpus(
        tmp_path / "demo",
        {
            f"demo-{i:02d}": generator.integers(
                1, 4000, size=(2, 32, 32), dtype=np.int16
            )
            for i in range(4)
        },
    )
