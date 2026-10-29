"""Steps shared by the use cases in ``usecases/``."""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from .codecs import families
from .codecs.base import CodecConfiguration
from .contract import Budget
from .corpus import DATASET
from .spec import ArraySpec


def fetch(folder: Path, paths: Iterable[str]) -> None:
    """Download the missing samples of the use case in ``folder``.

    They sit on Hugging Face under ``usecases/<use-case>/``, as in the repository.
    """
    from huggingface_hub import snapshot_download

    missing = [path for path in paths if not (folder / path).is_file()]
    if missing:
        snapshot_download(
            DATASET,
            repo_type="dataset",
            allow_patterns=[f"usecases/{folder.name}/{path}" for path in missing],
            local_dir=folder.parent.parent,
        )


def configurations(
    budgets: Iterable[Budget], spec: ArraySpec
) -> list[CodecConfiguration]:
    """Every near-lossless configuration at each budget that accepts ``spec``."""
    found = []
    for budget in budgets:
        for make in families():
            config = make(budget)
            if config.supports(spec):
                found.append(config)
    return found


def compress(
    config: CodecConfiguration, array: np.ndarray, spec: ArraySpec
) -> tuple[np.ndarray, int]:
    """``array`` as ``config`` decodes it, and the size of its encoding in bytes."""
    codec = config.factory(spec)
    encoded = codec.encode(array)
    return codec.decode(encoded), len(encoded)


def roundtrip(
    config: CodecConfiguration, array: np.ndarray, spec: ArraySpec
) -> np.ndarray:
    """``array`` as ``config`` decodes it."""
    return compress(config, array, spec)[0]


def lossy_codecs() -> tuple[Callable[[Budget], CodecConfiguration], ...]:
    """GeoZL with PIVCO and with PFOR behind the lossy quantiser, and JPEG XL with
    its distance searched, all holding the root-mean-square error of each array
    within tau."""
    from .codecs import fixed, jpegxl, quantize

    lossless = {c.id: c for c in fixed()}
    return (
        quantize.rms_family(lossless["geozl-med-pivco"]),
        quantize.rms_family(lossless["geozl-planar-pfor"]),
        jpegxl.distance,
    )


KEPT, LOST, NEW = (245, 158, 11), (56, 189, 248), (244, 63, 94)
"""Orange for what both maps hold, blue for what the decoded map loses, red for
what it adds."""


def shade(values: np.ndarray) -> np.ndarray:
    """``values`` as dark grey RGB, stretched between their 2nd and 99.5th percentiles."""
    low, high = np.nanpercentile(values, (2, 99.5))
    scaled = np.nan_to_num(np.clip((values - low) / max(high - low, 1e-12), 0, 1))
    return np.repeat((40 + 150 * scaled).astype(np.uint8)[..., None], 3, axis=2)


def overlay(
    image: np.ndarray,
    kept: np.ndarray,
    lost: np.ndarray | None = None,
    new: np.ndarray | None = None,
) -> np.ndarray:
    """``image`` with ``kept`` pixels in orange, ``lost`` in blue and ``new`` in red."""
    out = image.copy()
    for mask, colour in ((lost, LOST), (new, NEW), (kept, KEPT)):
        if mask is not None:
            out[mask] = colour
    return out


def enlarged(image: np.ndarray):
    """``image`` as a PIL image, every pixel repeated to about 600 pixels across."""
    from PIL import Image

    factor = max(1, 600 // max(image.shape[:2]))
    return Image.fromarray(image).resize(
        (image.shape[1] * factor, image.shape[0] * factor), Image.NEAREST
    )


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection over union of two masks, 1 when both are empty."""
    union = np.count_nonzero(a | b)
    return 1.0 if union == 0 else np.count_nonzero(a & b) / union


def run(
    task: Callable[[Any], list[dict[str, Any]]],
    items: Sequence[Any],
    path: Path,
) -> list[dict[str, Any]]:
    """``task`` on every item in parallel, its rows written to ``path``."""
    with ProcessPoolExecutor() as pool:
        rows = [row for rows in pool.map(task, items) for row in rows]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows
