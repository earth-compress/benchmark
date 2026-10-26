"""Loading of benchmark samples. Protocol section 4."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import zstandard as zstd

from .build import COLUMNS, parse_shape, split
from .spec import ArraySpec

MANIFEST_FILENAME = "manifest.csv"


@dataclass(frozen=True)
class Sample:
    """One reference array from a corpus, verified against its manifest row."""

    id: str
    data: np.ndarray
    unit: str
    scale: tuple[float, ...] = (1.0,)
    offset: tuple[float, ...] = (0.0,)
    sentinel: float | None = None

    @property
    def spec(self) -> ArraySpec:
        return ArraySpec(self.data.shape, self.data.dtype, self.sentinel, self.scale)


def _resolve(corpus: Path, value: str) -> Path:
    path = (corpus / value).resolve()
    try:
        path.relative_to(corpus.resolve())
    except ValueError as error:
        raise ValueError(f"sample path escapes the corpus: {value}") from error
    return path


def _values(text: str, default: float) -> tuple[float, ...]:
    values = tuple(float(v) for v in split(text))
    return values or (default,)


def _matches(archive, name: str, values: tuple[float, ...], default: float) -> bool:
    if name not in archive.files:
        return all(v == default for v in values)
    stored = np.asarray(archive[name], dtype=np.float64).reshape(-1)
    return stored.size == len(values) and bool(np.all(stored == np.array(values)))


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
    missing = set(COLUMNS) - set(rows[0])
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
        if not row["npz_path"] or not row["input_sha256"]:
            raise ValueError(f"{sample_id}: not built yet; run its build.py build")
        scale = _values(row["scale"], 1.0)
        offset = _values(row["offset"], 0.0)
        raw = decompressor.decompress(_resolve(corpus, row["npz_path"]).read_bytes())
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            if "data" not in archive.files:
                raise ValueError(f"{sample_id}: the archive has no 'data' array")
            data = np.ascontiguousarray(archive["data"])
            if not _matches(archive, "scale", scale, 1.0) or not _matches(
                archive, "offset", offset, 0.0
            ):
                raise ValueError(
                    f"{sample_id}: scale or offset differs from the manifest"
                )
            sentinel = (
                float(np.asarray(archive["sentinel"]).reshape(-1)[0])
                if "sentinel" in archive.files
                else None
            )

        if data.shape != parse_shape(row["shape"]):
            raise ValueError(
                f"{sample_id}: manifest shape {row['shape']}, file {data.shape}"
            )
        if data.dtype != np.dtype(row["dtype"]):
            raise ValueError(
                f"{sample_id}: manifest dtype {row['dtype']}, file {data.dtype}"
            )
        if (row["nodata"] != "") != (sentinel is not None):
            raise ValueError(f"{sample_id}: nodata differs from the manifest")
        digest = hashlib.sha256(data.tobytes(order="C")).hexdigest()
        if digest != row["input_sha256"]:
            raise ValueError(f"{sample_id}: input_sha256 mismatch")

        samples.append(Sample(sample_id, data, row["unit"], scale, offset, sentinel))

    return samples
