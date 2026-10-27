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
    mean_error: float
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


def identical(reference: np.ndarray, decoded: np.ndarray) -> np.ndarray:
    """Where an element decoded to its input value, NaN to NaN included."""
    same = reference == decoded
    if reference.dtype.kind == "f":
        same |= np.isnan(reference) & np.isnan(decoded)
    return same


def _rows(array: np.ndarray) -> np.ndarray:
    """View the array as rows of its last axis."""
    flat = np.ascontiguousarray(array)
    return flat.reshape(-1, flat.shape[-1]) if flat.ndim > 1 else flat.reshape(1, -1)


def _per_row(values, shape: tuple[int, ...], nrows: int) -> np.ndarray:
    """One value per row of ``_rows``, from one value or one per plane."""
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    if values.size == 1:
        return np.full(nrows, values[0])
    if len(shape) < 2 or values.size != shape[0]:
        raise ValueError(f"{values.size} plane values for shape {shape}")
    return np.repeat(values, nrows // shape[0])


def _error(reference: np.ndarray, decoded: np.ndarray, scale) -> np.ndarray:
    """``x - x̂`` in native units, by rows.

    An element decoded to itself has no error, infinities and NaN included;
    any other element that is not finite has an infinite error.
    """
    with np.errstate(invalid="ignore"):
        error = (reference.astype(np.float64) - decoded.astype(np.float64)) * scale
    error[identical(reference, decoded)] = 0.0
    error[~np.isfinite(error)] = np.inf
    return error


def _valid(rows: np.ndarray, nodata: float | None) -> np.ndarray:
    if nodata is None:
        return np.ones(rows.shape, bool)
    if math.isnan(nodata):
        return ~np.isnan(rows) if rows.dtype.kind == "f" else np.ones(rows.shape, bool)
    return rows != nodata


def distortion(
    reference: np.ndarray,
    decoded: np.ndarray,
    scale=1.0,
    offset=0.0,
    nodata: float | None = None,
) -> Distortion:
    """The error of ``decoded`` against ``reference`` over valid elements, in native units."""
    check_structure(reference, decoded)
    ref_rows, dec_rows = _rows(reference), _rows(decoded)
    nrows, width = ref_rows.shape
    row_scale = _per_row(scale, reference.shape, nrows)
    row_offset = _per_row(offset, reference.shape, nrows)

    size = 0
    worst = 0.0
    abs_sum = sq_sum = signed_sum = 0.0
    low, high = math.inf, -math.inf
    # Lag-1 accumulators over adjacent valid pairs within a row.
    n = sx = sy = sxx = syy = sxy = 0.0

    for start in range(0, nrows, _ROWS):
        block = slice(start, start + _ROWS)
        valid = _valid(ref_rows[block], nodata)
        k = row_scale[block, None]
        ref = ref_rows[block].astype(np.float64)
        err = _error(ref_rows[block], dec_rows[block], k)
        native = (ref * k + row_offset[block, None])[valid]
        native = native[np.isfinite(native)]
        absolute = np.abs(err[valid])
        if not absolute.size:
            continue

        size += absolute.size
        worst = max(worst, float(absolute.max()))
        abs_sum += float(absolute.sum())
        sq_sum += float(np.square(absolute).sum())
        signed_sum -= float(err[valid].sum())
        if native.size:
            low = min(low, float(native.min()))
            high = max(high, float(native.max()))

        if width > 1:
            pair = valid[:, :-1] & valid[:, 1:]
            x, y = err[:, :-1][pair], err[:, 1:][pair]
            n += x.size
            sx += float(x.sum())
            sy += float(y.sum())
            sxx += float(np.square(x).sum())
            syy += float(np.square(y).sum())
            sxy += float((x * y).sum())

    if size == 0:
        return Distortion(0.0, 0.0, 0.0, 0.0, math.inf, math.nan, math.nan)
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
        mean_error=signed_sum / size,
        psnr_db=psnr_db,
        error_spread=_spread(ref_rows, dec_rows, row_scale, worst, nodata),
        error_lag1=_pearson(n, sx, sy, sxx, syy, sxy),
    )


def _spread(
    ref_rows: np.ndarray,
    dec_rows: np.ndarray,
    row_scale: np.ndarray,
    worst: float,
    nodata: float | None,
) -> float:
    """``p99(|error|) / max(|error|)``. Exact decodes have no spread to report,
    and neither do decodes with an infinite error."""
    if worst == 0.0 or not math.isfinite(worst):
        return math.nan

    counts = np.zeros(_BINS, dtype=np.int64)
    for start in range(0, ref_rows.shape[0], _ROWS):
        block = slice(start, start + _ROWS)
        valid = _valid(ref_rows[block], nodata)
        absolute = np.abs(
            _error(ref_rows[block], dec_rows[block], row_scale[block, None])
        )[valid]
        index = np.minimum((absolute / worst * (_BINS - 1)).astype(np.int64), _BINS - 1)
        counts += np.bincount(index, minlength=_BINS)

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
