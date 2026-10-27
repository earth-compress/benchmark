from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .contract import PROMISES, Budget, Mode, Promise
from .metrics import identical, same_bytes

_ROWS = 1 << 12


@dataclass(frozen=True)
class Verdict:
    """The outcome of one check. ``ok`` is None when the check did not apply."""

    promise: Promise
    ok: bool | None
    detail: str = ""
    count: int = 0
    """Elements that broke the promise."""

    @property
    def failed(self) -> bool:
        return self.ok is False


@dataclass(frozen=True)
class Report:
    """Every verdict for one sample and configuration."""

    verdicts: tuple[Verdict, ...]

    @property
    def ok(self) -> bool:
        """Whether no promise the configuration made was broken."""
        return not any(verdict.failed for verdict in self.verdicts)

    def of(self, promise: Promise) -> bool | None:
        for verdict in self.verdicts:
            if verdict.promise is promise:
                return verdict.ok
        return None

    def count(self, promise: Promise) -> int | None:
        """Elements that broke ``promise``, or None when it was not checked."""
        for verdict in self.verdicts:
            if verdict.promise is promise:
                return None if verdict.ok is None else verdict.count
        return None

    @property
    def failures(self) -> tuple[Verdict, ...]:
        return tuple(verdict for verdict in self.verdicts if verdict.failed)


def _rows(array: np.ndarray) -> np.ndarray:
    flat = np.ascontiguousarray(array)
    return flat.reshape(-1, flat.shape[-1]) if flat.ndim > 1 else flat.reshape(1, -1)


def _is(array: np.ndarray, sentinel: float) -> np.ndarray:
    """Where ``array`` holds the sentinel, NaN included."""
    if isinstance(sentinel, float) and math.isnan(sentinel):
        return (
            np.isnan(array)
            if np.issubdtype(array.dtype, np.floating)
            else np.zeros(array.shape, bool)
        )
    return array == sentinel


def _check_structure(reference: np.ndarray, decoded: np.ndarray) -> Verdict:
    if decoded.shape != reference.shape:
        return Verdict(
            Promise.STRUCTURE, False, f"shape {decoded.shape} != {reference.shape}"
        )
    if decoded.dtype != reference.dtype:
        return Verdict(
            Promise.STRUCTURE, False, f"dtype {decoded.dtype} != {reference.dtype}"
        )
    return Verdict(Promise.STRUCTURE, True)


def _check_exactness(reference: np.ndarray, decoded: np.ndarray) -> Verdict:
    if same_bytes(reference, decoded):
        return Verdict(Promise.EXACTNESS, True)
    return Verdict(Promise.EXACTNESS, False, "decoded bytes differ from the input")


def _check_bound(
    reference: np.ndarray,
    decoded: np.ndarray,
    budget: Budget,
    scale: np.ndarray,
    sentinel: float | None,
) -> Verdict:
    """``|x - x̂| <= tau`` on every valid element, in native units."""
    ref_rows, dec_rows = _rows(reference), _rows(decoded)
    scale = np.asarray(scale, dtype=np.float64).reshape(-1)
    per_row = (
        np.full(ref_rows.shape[0], scale[0])
        if scale.size == 1
        else np.repeat(scale, ref_rows.shape[0] // scale.size)
    )
    worst = 0.0
    offenders = 0
    for start in range(0, ref_rows.shape[0], _ROWS):
        block = slice(start, start + _ROWS)
        ref = ref_rows[block]
        dec = dec_rows[block]
        with np.errstate(invalid="ignore"):
            error = np.abs(ref.astype(np.float64) - dec.astype(np.float64))
            error *= per_row[block, None]
        same = identical(ref, dec)
        bad = ~same & ~(error <= budget.tau)
        if sentinel is not None:
            bad &= ~_is(ref, sentinel)
        offenders += int(bad.sum())
        finite = error[np.isfinite(error) & ~same]
        if finite.size:
            worst = max(worst, float(finite.max()))
    if offenders:
        return Verdict(
            Promise.BOUND,
            False,
            f"{offenders} element(s) outside tau={budget.tau:g}, worst error {worst:g}",
            offenders,
        )
    return Verdict(Promise.BOUND, True, f"worst error {worst:g}")


def _check_sentinel(
    reference: np.ndarray, decoded: np.ndarray, sentinel: float | None
) -> Verdict:
    """Sentinels decode to themselves, and appear nowhere else."""
    if sentinel is None:
        return Verdict(Promise.SENTINEL, None, "no sentinel declared")
    was = _is(reference, sentinel)
    now = _is(decoded, sentinel)
    lost = int((was & ~now).sum())
    invented = int((~was & now).sum())
    if lost or invented:
        return Verdict(
            Promise.SENTINEL,
            False,
            f"{lost} sentinel(s) lost, {invented} invented in valid data",
            lost + invented,
        )
    return Verdict(Promise.SENTINEL, True, f"{int(was.sum())} preserved")


def _native(array: np.ndarray, scale, offset) -> np.ndarray:
    shape = (-1,) + (1,) * (array.ndim - 1)
    scale = np.asarray(scale, dtype=np.float64).reshape(-1)
    offset = np.asarray(offset, dtype=np.float64).reshape(-1)
    k = scale[0] if scale.size == 1 else scale.reshape(shape)
    b = offset[0] if offset.size == 1 else offset.reshape(shape)
    return array.astype(np.float64) * k + b


def _check_zero(reference: np.ndarray, decoded: np.ndarray, scale, offset) -> Verdict:
    """Exact zeros, in native units, survive. A respected bound does not imply this."""
    was = _native(reference, scale, offset) == 0
    count = int(was.sum())
    if count == 0:
        return Verdict(Promise.ZERO, None, "no exact zeros in the input")
    lost = int((was & (_native(decoded, scale, offset) != 0)).sum())
    if lost:
        return Verdict(
            Promise.ZERO, False, f"{lost} of {count} exact zeros changed", lost
        )
    return Verdict(Promise.ZERO, True, f"{count} preserved")


def verify(
    mode: Mode,
    budget: Budget | None,
    reference: np.ndarray,
    decoded: np.ndarray,
    sentinel: float | None = None,
    scale=1.0,
    offset=0.0,
) -> Report:
    """Check every promise ``mode`` makes, except determinism."""
    promises = PROMISES[mode]
    verdicts = [_check_structure(reference, decoded)]

    if verdicts[0].failed:
        # Nothing else can be measured against a mismatched array.
        return Report(tuple(verdicts))

    if Promise.EXACTNESS in promises:
        verdicts.append(_check_exactness(reference, decoded))
    if Promise.BOUND in promises:
        if budget is None:
            raise ValueError(f"{mode} requires a budget")
        verdicts.append(_check_bound(reference, decoded, budget, scale, sentinel))
    if Promise.SENTINEL in promises:
        verdicts.append(_check_sentinel(reference, decoded, sentinel))
    if Promise.ZERO in promises:
        verdicts.append(_check_zero(reference, decoded, scale, offset))

    return Report(tuple(verdicts))
