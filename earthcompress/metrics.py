"""Distortion metrics, including the shape of the error.

Protocol section 7. Everything is computed in float64 over the whole sample, in
the native unit of the data, in row blocks so that a global hourly field does
not materialise a second copy of itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_ROWS = 1 << 12  # rows of the last axis per block
_BINS = 1 << 16  # histogram resolution for the p99 of |error|


@dataclass(frozen=True)
class Distortion:
    """The error of a decoded array against its reference."""

    max_abs_error: float
    mae: float
    rmse: float
    psnr_db: float
    error_spread: float
    error_lag1: float

    @property
    def exact(self) -> bool:
        """Whether every element decoded to its reference value."""
        return self.max_abs_error == 0.0


def check_structure(reference: np.ndarray, decoded: np.ndarray) -> None:
    """Raise unless ``decoded`` has the shape and dtype of ``reference``."""
    if decoded.shape != reference.shape:
        raise ValueError(
            f"decoded shape {decoded.shape}, reference shape {reference.shape}"
        )
    if decoded.dtype != reference.dtype:
        raise ValueError(
            f"decoded dtype {decoded.dtype}, reference dtype {reference.dtype}"
        )


def same_bytes(left: np.ndarray, right: np.ndarray) -> bool:
    """Whether two arrays hold identical shape, dtype and bytes in C order."""
    return (
        left.shape == right.shape
        and left.dtype == right.dtype
        and np.ascontiguousarray(left).tobytes(order="C")
        == np.ascontiguousarray(right).tobytes(order="C")
    )


def _rows(array: np.ndarray) -> np.ndarray:
    """View the array as rows of its last axis."""
    flat = np.ascontiguousarray(array)
    return flat.reshape(-1, flat.shape[-1]) if flat.ndim > 1 else flat.reshape(1, -1)


def distortion(reference: np.ndarray, decoded: np.ndarray) -> Distortion:
    """Measure the error of ``decoded`` against ``reference``."""
    check_structure(reference, decoded)
    ref_rows, dec_rows = _rows(reference), _rows(decoded)
    nrows, width = ref_rows.shape
    size = nrows * width
    if size == 0:
        raise ValueError("cannot measure distortion on an empty array")

    worst = 0.0
    abs_sum = sq_sum = 0.0
    low, high = math.inf, -math.inf
    # Lag-1 accumulators over adjacent pairs within a row.
    n = sx = sy = sxx = syy = sxy = 0.0

    for start in range(0, nrows, _ROWS):
        block = slice(start, start + _ROWS)
        ref = ref_rows[block].astype(np.float64)
        err = ref - dec_rows[block].astype(np.float64)
        absolute = np.abs(err)

        worst = max(worst, float(absolute.max()))
        abs_sum += float(absolute.sum())
        sq_sum += float(np.square(err).sum())
        low = min(low, float(ref.min()))
        high = max(high, float(ref.max()))

        if width > 1:
            x, y = err[:, :-1], err[:, 1:]
            n += x.size
            sx += float(x.sum())
            sy += float(y.sum())
            sxx += float(np.square(x).sum())
            syy += float(np.square(y).sum())
            sxy += float((x * y).sum())

    mae = abs_sum / size
    rmse = math.sqrt(sq_sum / size)
    peak = high - low

    if rmse == 0.0:
        psnr_db = math.inf
    elif peak == 0.0:
        psnr_db = math.nan
    else:
        psnr_db = 20.0 * math.log10(peak / rmse)

    return Distortion(
        max_abs_error=worst,
        mae=mae,
        rmse=rmse,
        psnr_db=psnr_db,
        error_spread=_spread(ref_rows, dec_rows, nrows, worst),
        error_lag1=_pearson(n, sx, sy, sxx, syy, sxy),
    )


def _spread(
    ref_rows: np.ndarray, dec_rows: np.ndarray, nrows: int, worst: float
) -> float:
    """``p99(|error|) / max(|error|)``: does the codec fill its budget?

    Near 1 means the error is spread through the budget, which buys ratio. Well
    below 1 means it sits near zero and ratio is left unclaimed. Exact decodes
    have no spread to report.
    """
    if worst == 0.0:
        return math.nan

    counts = np.zeros(_BINS, dtype=np.int64)
    for start in range(0, nrows, _ROWS):
        block = slice(start, start + _ROWS)
        absolute = np.abs(
            ref_rows[block].astype(np.float64) - dec_rows[block].astype(np.float64)
        )
        index = np.minimum((absolute / worst * (_BINS - 1)).astype(np.int64), _BINS - 1)
        counts += np.bincount(index.reshape(-1), minlength=_BINS)

    cumulative = np.cumsum(counts)
    target = 0.99 * float(cumulative[-1])
    bin_index = int(np.searchsorted(cumulative, target, side="left"))
    return min(bin_index / (_BINS - 1), 1.0)


def _pearson(
    n: float, sx: float, sy: float, sxx: float, syy: float, sxy: float
) -> float:
    """Pearson correlation from accumulated sums."""
    if n < 2:
        return math.nan
    cov = sxy - sx * sy / n
    vx = sxx - sx * sx / n
    vy = syy - sy * sy / n
    if vx <= 0.0 or vy <= 0.0:
        return math.nan
    return cov / math.sqrt(vx * vy)
