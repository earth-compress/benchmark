"""Shared single-threaded Zstandard contexts."""

from __future__ import annotations

import zstandard as zstd

SINGLE_THREADED = 0  # python-zstandard reads zero as "no worker threads".
VERSION = (
    f"{'.'.join(str(part) for part in zstd.ZSTD_VERSION)} "
    f"(python-zstandard {zstd.__version__})"
)


def compressor(level: int) -> zstd.ZstdCompressor:
    """A deterministic, single-threaded compressor."""
    return zstd.ZstdCompressor(
        level=level,
        threads=SINGLE_THREADED,
        write_checksum=False,
        write_content_size=True,
    )


def decompressor() -> zstd.ZstdDecompressor:
    return zstd.ZstdDecompressor()
