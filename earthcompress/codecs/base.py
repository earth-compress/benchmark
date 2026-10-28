from __future__ import annotations

import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np

from ..contract import Budget, Mode
from ..spec import ArraySpec


class Family(StrEnum):
    """How a near-lossless or lossy configuration meets its bound."""

    NATIVE = "native"
    """The codec's own bounded mode, run as published."""
    QUANTIZED = "quantized"
    """The shared quantiser of this benchmark, then a lossless codec."""
    SAFEGUARDED = "safeguarded"
    """A native configuration wrapped in Compression Safeguards."""
    SEARCHED = "searched"
    """A codec with no error target, its setting searched on each sample."""


class Codec(Protocol):
    def encode(self, array: np.ndarray) -> bytes: ...

    def decode(self, compressed: bytes) -> np.ndarray: ...


@dataclass(frozen=True)
class CodecConfiguration:
    id: str
    codec: str
    version: str
    mode: Mode
    parameters: Mapping[str, object]
    factory: Callable[[ArraySpec], Codec]
    budget: Budget | None = None
    supports: Callable[[ArraySpec], bool] = lambda spec: True
    family: Family | None = None

    def __post_init__(self) -> None:
        bounded = self.mode is not Mode.LOSSLESS
        if bounded != (self.budget is not None):
            raise ValueError(f"{self.id}: only near-lossless and lossy carry a budget")
        if bounded != (self.family is not None):
            raise ValueError(
                f"{self.id}: only near-lossless and lossy belong to a family"
            )


def lossless(
    id: str, codec: str, version: str, factory, **parameters
) -> CodecConfiguration:
    supports = parameters.pop("supports", lambda spec: True)
    return CodecConfiguration(
        id, codec, version, Mode.LOSSLESS, parameters, factory, supports=supports
    )


def _bounded(
    mode: Mode,
    name: str,
    codec: str,
    version: str,
    factory,
    budget: Budget,
    family: Family,
    supports: Callable[[ArraySpec], bool],
    parameters: Mapping[str, object],
) -> CodecConfiguration:
    suffix = budget.level if budget.level is not None else f"tau{budget.tau:g}"
    return CodecConfiguration(
        id=f"{name}-{suffix}",
        codec=codec,
        version=version,
        mode=mode,
        parameters=parameters,
        factory=factory,
        budget=budget,
        supports=supports,
        family=family,
    )


def near_lossless(
    name: str,
    codec: str,
    version: str,
    factory,
    budget: Budget,
    family: Family,
    supports: Callable[[ArraySpec], bool] = lambda spec: True,
    **parameters,
) -> CodecConfiguration:
    """A configuration at ``budget``, named after its level or its tau."""
    return _bounded(
        Mode.NEAR_LOSSLESS,
        name,
        codec,
        version,
        factory,
        budget,
        family,
        supports,
        parameters,
    )


def lossy(
    name: str,
    codec: str,
    version: str,
    factory,
    budget: Budget,
    family: Family,
    supports: Callable[[ArraySpec], bool] = lambda spec: True,
    **parameters,
) -> CodecConfiguration:
    """A configuration whose root-mean-square error is held within ``budget``."""
    return _bounded(
        Mode.LOSSY, name, codec, version, factory, budget, family, supports, parameters
    )


def code_bound(spec: ArraySpec, budget: Budget) -> float:
    """The budget in the units of the stored values.

    Integers count whole steps of the largest scale; floats use tau as stated.
    """
    return float(spec.steps(budget.tau)) if spec.is_integer else budget.tau


def working_float(dtype: np.dtype) -> np.dtype:
    """The float type that holds every value of ``dtype`` exactly."""
    if dtype.kind == "f":
        return dtype
    return np.dtype(np.float32 if dtype.itemsize <= 2 else np.float64)


def code_rms(array: np.ndarray, decoded: np.ndarray) -> float:
    """The root-mean-square difference of two arrays, in stored units."""
    error = array.astype(np.float64) - decoded.astype(np.float64)
    return float(np.sqrt(np.mean(np.square(error)))) if error.size else 0.0


def to_stored(values: np.ndarray, spec: ArraySpec) -> np.ndarray:
    """Float output of a codec back in the stored type of the sample.

    Integers round to the nearest code and clip to the type, which can only
    move a value towards an integer input, so a bound in whole codes holds.
    """
    if not spec.is_integer:
        return np.ascontiguousarray(values, dtype=spec.dtype).reshape(spec.shape)
    limits = np.iinfo(spec.dtype)
    codes = np.clip(np.rint(values), limits.min, limits.max)
    return codes.astype(spec.dtype).reshape(spec.shape)


def unpack(raw, spec: ArraySpec) -> np.ndarray:
    return np.frombuffer(raw, dtype=spec.dtype).reshape(spec.shape)


def as_bits(array: np.ndarray) -> np.ndarray:
    """Floating-point values as unsigned integers of the same width."""
    if array.dtype.kind == "f":
        return array.view(f"u{array.dtype.itemsize}")
    return array


_COUNT = struct.Struct("<I")


def pack_frames(frames: list[bytes]) -> bytes:
    """Frames behind a header of their count and sizes."""
    header = _COUNT.pack(len(frames)) + b"".join(
        _COUNT.pack(len(frame)) for frame in frames
    )
    return header + b"".join(frames)


def unpack_frames(data: bytes) -> list[bytes]:
    """The frames of ``pack_frames``, in order."""
    (count,) = _COUNT.unpack_from(data)
    start = _COUNT.size * (1 + count)
    frames = []
    for i in range(count):
        (size,) = _COUNT.unpack_from(data, _COUNT.size * (1 + i))
        frames.append(data[start : start + size])
        start += size
    return frames
