"""Loading of benchmark samples. Protocol section 4."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import zstandard as zstd

from .spec import ArraySpec

MANIFEST_FILENAME = "manifest.csv"
MANIFEST_COLUMNS = frozenset(
    {"id", "shape", "dtype", "grid", "grid_unit", "exact", "input_sha256", "npz_path"}
)


@dataclass(frozen=True)
class Sample:
    """One reference array from a corpus, verified against its manifest row."""

    id: str
    data: np.ndarray
    grid: float
    grid_unit: str
    exact: bool
    scale: np.ndarray | None = None
    offset: np.ndarray | None = None
    symbols: np.ndarray | None = None
    sentinel: float | None = None

    @property
    def spec(self) -> ArraySpec:
        return ArraySpec(self.data.shape, self.data.dtype, self.sentinel, self.grid)


def _parse_shape(value: str) -> tuple[int, ...]:
    try:
        shape = tuple(int(part) for part in value.lower().split("x"))
    except ValueError as error:
        raise ValueError(f"invalid shape {value!r}") from error
    if not shape or any(size < 1 for size in shape):
        raise ValueError(f"invalid shape {value!r}")
    return shape


def _resolve(corpus: Path, value: str) -> Path:
    path = (corpus / value).resolve()
    try:
        path.relative_to(corpus.resolve())
    except ValueError as error:
        raise ValueError(f"sample path escapes the corpus: {value}") from error
    return path


def _optional(archive, name: str) -> np.ndarray | None:
    return np.ascontiguousarray(archive[name]) if name in archive.files else None


def load_samples(corpus: Path, limit: int | None = None) -> list[Sample]:
    """Read every sample of ``corpus``, or the first ``limit`` of them."""
    corpus = corpus.resolve()
    manifest_path = corpus / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing corpus manifest: {manifest_path}")

    with manifest_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"{MANIFEST_FILENAME} contains no samples")
    missing = MANIFEST_COLUMNS - set(rows[0])
    if missing:
        raise ValueError(
            f"{MANIFEST_FILENAME} is missing: {', '.join(sorted(missing))}"
        )
    if limit is not None:
        rows = rows[:limit]

    decompressor = zstd.ZstdDecompressor()
    samples: list[Sample] = []
    for row in rows:
        sample_id = row["id"]
        raw = decompressor.decompress(_resolve(corpus, row["npz_path"]).read_bytes())
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            if "data" not in archive.files:
                raise ValueError(f"{sample_id}: the archive has no 'data' array")
            data = np.ascontiguousarray(archive["data"])
            scale = _optional(archive, "scale")
            offset = _optional(archive, "offset")
            symbols = _optional(archive, "symbols")
            sentinel_array = _optional(archive, "sentinel")

        expected_shape = _parse_shape(row["shape"])
        expected_dtype = np.dtype(row["dtype"])
        if data.shape != expected_shape:
            raise ValueError(
                f"{sample_id}: manifest shape {expected_shape}, file {data.shape}"
            )
        if data.dtype != expected_dtype:
            raise ValueError(
                f"{sample_id}: manifest dtype {expected_dtype}, file {data.dtype}"
            )

        digest = hashlib.sha256(data.tobytes(order="C")).hexdigest()
        if digest != row["input_sha256"]:
            raise ValueError(f"{sample_id}: input_sha256 mismatch")

        samples.append(
            Sample(
                id=sample_id,
                data=data,
                grid=float(row["grid"]),
                grid_unit=row["grid_unit"],
                exact=row["exact"].strip().lower() in {"true", "1", "yes"},
                scale=scale,
                offset=offset,
                symbols=symbols,
                sentinel=None
                if sentinel_array is None
                else float(sentinel_array.reshape(-1)[0]),
            )
        )

    return samples
