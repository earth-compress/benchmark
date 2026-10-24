"""Verification of the promises a configuration made. Protocol section 6.

Every check here exists because a published compressor failed it. A check that
cannot be run is reported as not run, never as passed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contract import PROMISES, BoundKind, Budget, Mode, Promise
from .metrics import same_bytes

_ROWS = 1 << 12


@dataclass(frozen=True)
class Verdict:
    """The outcome of one check. ``ok`` is None when the check did not apply."""

    promise: Promise
    ok: bool | None
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.ok is False


@dataclass(frozen=True)
class Report:
    """Every verdict for one sample and configuration."""

    verdicts: tuple[Verdict, ...]
    subnormals_ok: bool | None

    @property
    def ok(self) -> bool:
        """Whether no promise the configuration made was broken."""
        return not any(verdict.failed for verdict in self.verdicts)

    def of(self, promise: Promise) -> bool | None:
        for verdict in self.verdicts:
            if verdict.promise is promise:
                return verdict.ok
        return None

    @property
    def failures(self) -> tuple[Verdict, ...]:
        return tuple(verdict for verdict in self.verdicts if verdict.failed)


def _rows(array: np.ndarray) -> np.ndarray:
    flat = np.ascontiguousarray(array)
    return flat.reshape(-1, flat.shape[-1]) if flat.ndim > 1 else flat.reshape(1, -1)


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
    reference: np.ndarray, decoded: np.ndarray, budget: Budget, grid: float
) -> Verdict:
    """The declared bound, with the equivalence clause of protocol 2.1.

    A budget is declared in native units and the array is stored in grid steps,
    so an absolute allowance converts with ``grid``. A relative one does not:
    the scale cancels on both sides of ``|x - x̂| <= tau · |x|``.
    """
    ref_rows, dec_rows = _rows(reference), _rows(decoded)
    worst_ratio = 0.0
    offenders = 0
    for start in range(0, ref_rows.shape[0], _ROWS):
        block = slice(start, start + _ROWS)
        ref = ref_rows[block].astype(np.float64)
        dec = dec_rows[block].astype(np.float64)
        with np.errstate(invalid="ignore"):
            error = np.abs(ref - dec)
        # The equivalence clause: equal values never violate a bound, which is
        # what keeps a correctly preserved infinity from failing (inf - inf is NaN).
        equal = ref == dec
        if budget.kind is BoundKind.RELATIVE:
            allowance = budget.tau * np.abs(ref)
        else:
            allowance = np.full_like(error, budget.tau / grid)
        bad = ~equal & ~(error <= allowance)
        offenders += int(bad.sum())
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(
                allowance > 0, error / allowance, np.where(equal, 0.0, np.inf)
            )
        finite = ratio[np.isfinite(ratio)]
        if finite.size:
            worst_ratio = max(worst_ratio, float(finite.max()))
        if np.isinf(ratio).any():
            worst_ratio = float("inf")
    if offenders:
        return Verdict(
            Promise.BOUND,
            False,
            f"{offenders} element(s) outside the {budget.kind} bound "
            f"tau={budget.tau:g}, worst {worst_ratio:.4g}x the allowance",
        )
    return Verdict(Promise.BOUND, True, f"worst {worst_ratio:.4g}x of the allowance")


def _check_sentinel(
    reference: np.ndarray, decoded: np.ndarray, sentinel: float | None
) -> Verdict:
    """Sentinels decode to themselves, and appear nowhere else."""
    if sentinel is None:
        return Verdict(Promise.SENTINEL, None, "no sentinel declared")
    was = reference == sentinel
    now = decoded == sentinel
    lost = int((was & ~now).sum())
    invented = int((~was & now).sum())
    if lost or invented:
        return Verdict(
            Promise.SENTINEL,
            False,
            f"{lost} sentinel(s) lost, {invented} invented in valid data",
        )
    return Verdict(Promise.SENTINEL, True, f"{int(was.sum())} preserved")


def _check_zero(reference: np.ndarray, decoded: np.ndarray) -> Verdict:
    """Exact zeros survive. A respected bound does not imply this."""
    was = reference == 0
    count = int(was.sum())
    if count == 0:
        return Verdict(Promise.ZERO, None, "no exact zeros in the input")
    lost = int((was & (decoded != 0)).sum())
    if lost:
        return Verdict(Promise.ZERO, False, f"{lost} of {count} exact zeros changed")
    return Verdict(Promise.ZERO, True, f"{count} preserved")


def _check_subnormals(reference: np.ndarray, decoded: np.ndarray) -> bool | None:
    """Recorded, not enforced.

    Rounding subnormals away changes no useful statistic, and also removes the
    only evidence that the producer emits them. A codec must not hide that.
    """
    if not np.issubdtype(reference.dtype, np.floating):
        return None
    tiny = np.finfo(reference.dtype).tiny
    was = (reference != 0) & (np.abs(reference) < tiny)
    if not was.any():
        return None
    return bool(np.all(decoded[was] != 0))


def verify(
    mode: Mode,
    budget: Budget | None,
    reference: np.ndarray,
    decoded: np.ndarray,
    sentinel: float | None = None,
    grid: float = 1.0,
) -> Report:
    """Check every promise ``mode`` makes, and record the rest."""
    promises = PROMISES[mode]
    verdicts = [_check_structure(reference, decoded)]

    if verdicts[0].failed:
        # Nothing else can be measured against a mismatched array.
        return Report(tuple(verdicts), None)

    if Promise.EXACTNESS in promises:
        verdicts.append(_check_exactness(reference, decoded))
    if Promise.BOUND in promises:
        if budget is None:
            raise ValueError(f"{mode} requires a budget")
        verdicts.append(_check_bound(reference, decoded, budget, grid))
    if Promise.SENTINEL in promises:
        verdicts.append(_check_sentinel(reference, decoded, sentinel))
    if Promise.ZERO in promises:
        verdicts.append(_check_zero(reference, decoded))

    return Report(tuple(verdicts), _check_subnormals(reference, decoded))
