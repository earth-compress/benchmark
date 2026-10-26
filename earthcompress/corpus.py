from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import zstandard as zstd

from .build import split
from .spec import ArraySpec


@dataclass(frozen=True)
class Sample:
    id: str
    data: np.ndarray
    unit: str
    scale: tuple[float, ...] = (1.0,)
    offset: tuple[float, ...] = (0.0,)
    sentinel: float | None = None

    @property
    def spec(self) -> ArraySpec:
        return ArraySpec(self.data.shape, self.data.dtype, self.sentinel, self.scale)


def values(text: str, default: float) -> tuple[float, ...]:
    return tuple(float(v) for v in split(text)) or (default,)


def load_samples(corpus: Path, limit: int | None = None) -> list[Sample]:
    with (corpus / "manifest.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))[:limit]

    samples = []
    for row in rows:
        if not row["npz_path"]:
            raise ValueError(f"{row['id']}: not built yet; run its build.py build")
        raw = zstd.ZstdDecompressor().decompress(
            (corpus / row["npz_path"]).read_bytes()
        )
        with np.load(io.BytesIO(raw)) as archive:
            data = np.ascontiguousarray(archive["data"])
        if hashlib.sha256(data.tobytes()).hexdigest() != row["input_sha256"]:
            raise ValueError(f"{row['id']}: input_sha256 mismatch")
        samples.append(
            Sample(
                row["id"],
                data,
                row["unit"],
                values(row["scale"], 1.0),
                values(row["offset"], 0.0),
                float(row["nodata"]) if row["nodata"] else None,
            )
        )
    return samples
