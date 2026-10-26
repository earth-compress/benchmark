"""Building of benchmark corpora. Protocol section 4.

Each corpus folder has a ``build.py`` with two steps. ``select`` chooses the
samples and writes ``manifest.csv``; it runs once. ``build`` reads only
``manifest.csv``, fetches every sample, writes it, and checks ``input_sha256``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
import zstandard as zstd

COLUMNS = [
    "id",
    "source",
    "asset",
    "crs",
    "transform",
    "datetime_start",
    "datetime_end",
    "bands",
    "shape",
    "dtype",
    "unit",
    "scale",
    "offset",
    "nodata",
    "input_sha256",
    "npz_path",
    "png_path",
]

ZSTD_LEVEL = 19


def join(values: Iterable) -> str:
    """Join per-plane values with ``|``."""
    return "|".join(str(value) for value in values)


def split(value: str) -> list[str]:
    return value.split("|") if value else []


def transform_text(x0: float, dx: float, y0: float, dy: float) -> str:
    """Six values of a north-up affine geotransform, in GDAL order."""
    return " ".join(repr(float(v)) for v in (x0, dx, 0.0, y0, 0.0, dy))


def parse_transform(value: str) -> tuple[float, ...]:
    values = tuple(float(v) for v in value.split())
    if len(values) != 6:
        raise ValueError(f"a transform needs six values: {value!r}")
    return values


def parse_shape(value: str) -> tuple[int, ...]:
    return tuple(int(v) for v in value.split("x"))


def legacy(corpus: Path, name: str | None = None) -> list[dict[str, str]]:
    """Rows of the prototype manifest, so that ``select`` keeps the same samples.

    The prototype corpora live in ``EC_LEGACY``, by default ``../ec-benchmark/corpora``
    next to this repository.
    """
    import os

    root = Path(
        os.environ.get("EC_LEGACY", corpus.parents[2] / "ec-benchmark" / "corpora")
    )
    with (root / (name or corpus.name) / "manifest.csv").open(newline="") as stream:
        return list(csv.DictReader(stream))


def cast(data: np.ndarray, dtype: str) -> np.ndarray:
    """Cast to the manifest dtype, refusing any change of value."""
    out = data.astype(dtype)
    if not np.array_equal(out.astype(data.dtype), data):
        raise ValueError(f"values of {data.dtype} do not fit in {dtype}")
    return out


def read_manifest(corpus: Path) -> list[dict[str, str]]:
    with (corpus / "manifest.csv").open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_manifest(corpus: Path, rows: list[dict[str, str]]) -> None:
    extra: list[str] = []
    for row in rows:
        extra += [key for key in row if key not in COLUMNS and key not in extra]
    with (corpus / "manifest.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS + extra, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in COLUMNS + extra})


def exact(codes: np.ndarray, scale, offset, published: np.ndarray) -> bool:
    """The exactness test of protocol section 1, one scale and offset per plane."""
    scale = np.asarray(scale, dtype=np.float64)
    offset = np.asarray(offset, dtype=np.float64)
    shape = (-1,) + (1,) * (codes.ndim - 1)
    if scale.ndim:
        scale = scale.reshape(shape)
    if offset.ndim:
        offset = offset.reshape(shape)
    back = (codes.astype(np.float64) * scale + offset).astype(published.dtype)
    return back.shape == published.shape and back.tobytes(
        order="C"
    ) == published.tobytes(order="C")


def sha256(data: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(data).tobytes(order="C")).hexdigest()


def save(
    corpus: Path,
    row: dict[str, str],
    data: np.ndarray,
    preview: np.ndarray | None = None,
) -> None:
    """Write one sample and its preview, and check it against ``row``."""
    data = np.ascontiguousarray(data)
    shape = "x".join(str(n) for n in data.shape)
    if row.get("shape") and row["shape"] != shape:
        raise ValueError(f"{row['id']}: shape {shape}, manifest {row['shape']}")
    if row.get("dtype") and row["dtype"] != str(data.dtype):
        raise ValueError(f"{row['id']}: dtype {data.dtype}, manifest {row['dtype']}")
    digest = sha256(data)
    if row.get("input_sha256") and row["input_sha256"] != digest:
        raise ValueError(f"{row['id']}: input_sha256 does not match the manifest")
    row.update(shape=shape, dtype=str(data.dtype), input_sha256=digest)

    arrays = {"data": data}
    scale = [float(v) for v in split(row.get("scale", ""))]
    offset = [float(v) for v in split(row.get("offset", ""))]
    if scale and any(v != 1 for v in scale):
        arrays["scale"] = np.array(scale if len(scale) > 1 else scale[0])
    if offset and any(v != 0 for v in offset):
        arrays["offset"] = np.array(offset if len(offset) > 1 else offset[0])
    if row.get("nodata"):
        arrays["sentinel"] = np.array(row["nodata"], dtype=np.float64).astype(
            data.dtype
        )

    buffer = io.BytesIO()
    np.savez(buffer, **arrays)
    path = corpus / "npz" / f"{row['id']}.npz.zst"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zstd.ZstdCompressor(level=ZSTD_LEVEL).compress(buffer.getvalue()))
    row["npz_path"] = path.relative_to(corpus).as_posix()

    if preview is not None:
        from PIL import Image

        png = corpus / "png" / f"{row['id']}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(preview).save(png, optimize=True)
        row["png_path"] = png.relative_to(corpus).as_posix()


def stretch(plane: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Percentile stretch of one plane to 8 bits."""
    values = plane.astype(np.float64)
    valid = values[np.isfinite(values) if mask is None else mask & np.isfinite(values)]
    if valid.size == 0:
        return np.zeros(plane.shape, np.uint8)
    low, high = np.percentile(valid, (2, 98))
    scaled = np.clip((values - low) / max(high - low, 1e-12), 0, 1)
    return (np.nan_to_num(scaled) * 255).astype(np.uint8)


def rgb(planes: Iterable[np.ndarray]) -> np.ndarray:
    return np.stack([stretch(p) for p in planes], -1)


def main(
    corpus: Path,
    select: Callable[[], list[dict[str, str]]],
    build: Callable[[dict[str, str]], tuple[np.ndarray, np.ndarray | None]],
) -> None:
    """Command line of a corpus ``build.py``."""
    parser = argparse.ArgumentParser(prog=f"{corpus.name}/build.py")
    sub = parser.add_subparsers(dest="step", required=True)
    sub.add_parser("select", help="choose the samples and write manifest.csv")
    run = sub.add_parser("build", help="fetch every sample listed in manifest.csv")
    run.add_argument("--only", nargs="*", help="sample ids to build")
    args = parser.parse_args()

    if args.step == "select":
        rows = select()
        write_manifest(corpus, rows)
        print(f"{corpus.name}: {len(rows)} samples selected")
        return

    rows = read_manifest(corpus)
    failed = []
    for row in rows:
        if args.only and row["id"] not in args.only:
            continue
        try:
            data, preview = build(row)
            save(corpus, row, data, preview)
        except Exception as error:  # noqa: BLE001 - report every failing sample
            failed.append(row["id"])
            print(f"{row['id']}: FAILED {error}", flush=True)
            continue
        print(
            f"{row['id']}: {row['shape']} {row['dtype']} {row['input_sha256'][:12]}",
            flush=True,
        )
    write_manifest(corpus, rows)
    if failed:
        raise SystemExit(
            f"{corpus.name}: {len(failed)} samples failed: {' '.join(failed)}"
        )
