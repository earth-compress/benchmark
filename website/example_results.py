from __future__ import annotations

import csv
import math
import random
from pathlib import Path

import numpy as np

from earthcompress.build import parse_shape, read_manifest
from earthcompress.runner import RESULT_COLUMNS

ROOT = Path(__file__).resolve().parent.parent
MARK = "example"

# Ratio and decode MB/s of each configuration on a typical corpus.
TYPICAL = {
    "zstd-c3": ("zstd", 1.55, 1200),
    "blosc-zstd3-bitshuffle": ("blosc", 1.75, 2400),
    "deflate-c6": ("deflate", 1.45, 350),
    "lzw": ("lzw", 1.25, 180),
    "hdiff-zstd9": ("hdiff+zstd", 1.85, 900),
    "openzl-generic": ("openzl", 2.05, 650),
    "openzl-delta-fieldlz": ("openzl", 1.95, 1100),
    "openzl-delta-pivco": ("openzl", 2.1, 800),
    "geozl-planar-pfor": ("geozl", 2.2, 1700),
    "geozl-planar-pivco": ("geozl", 2.3, 1000),
    "geozl-med-pivco": ("geozl", 2.32, 950),
    "geozl-planar-entropy": ("geozl", 2.28, 1250),
    "geozl-med-entropy": ("geozl", 2.35, 460),
    "geozl-average-entropy": ("geozl", 2.25, 680),
    "geozl-id-pfor": ("geozl", 1.05, 12000),
}


def rows_for(corpus: str, samples: list[dict[str, str]]) -> list[dict]:
    rng = random.Random(corpus)
    gain, fast = rng.uniform(0.7, 1.6), rng.uniform(0.6, 1.4)
    out = []
    for sample in samples:
        size = math.prod(parse_shape(sample["shape"]))
        input_bytes = size * np.dtype(sample["dtype"]).itemsize
        local = random.Random(sample["id"])
        sample_gain = gain * local.uniform(0.85, 1.15)
        for config, (codec, ratio, mb_s) in TYPICAL.items():
            r = max(1.02, 1 + (ratio - 1) * sample_gain * local.uniform(0.9, 1.1))
            compressed = round(input_bytes / r)
            decode_ns = round(
                input_bytes / (mb_s * fast * local.uniform(0.85, 1.15)) * 1000
            )
            encode_ns = round(decode_ns * local.uniform(1.5, 4.0))
            out.append(
                {
                    "sample_id": sample["id"],
                    "codec": codec,
                    "codec_version": MARK,
                    "configuration": config,
                    "mode": "lossless",
                    "tau": "",
                    "budget_level": "",
                    "input_bytes": input_bytes,
                    "compressed_bytes": compressed,
                    "compression_ratio": input_bytes / compressed,
                    "bits_per_value": compressed * 8 / size,
                    "encode_ns": encode_ns,
                    "decode_ns": decode_ns,
                    "decode_ns_min": round(decode_ns * 0.95),
                    "decode_ns_max": round(decode_ns * 1.08),
                    "encode_MB_s": input_bytes / encode_ns * 1000,
                    "decode_MB_s": input_bytes / decode_ns * 1000,
                    "max_abs_error": 0.0,
                    "mae": 0.0,
                    "rmse": 0.0,
                    "mean_error": 0.0,
                    "psnr_dB": "inf",
                    "error_spread": "nan",
                    "error_lag1": "nan",
                    "sentinel_ok": "",
                    "zero_ok": "",
                    "fidelity_ok": True,
                }
            )
    return out


def measured(path: Path) -> bool:
    """Whether ``path`` holds results of a real run, which this script never overwrites."""
    if not path.exists():
        return False
    with path.open(newline="") as stream:
        return any(row["codec_version"] != MARK for row in csv.DictReader(stream))


def main() -> None:
    for folder in sorted((ROOT / "corpora").iterdir()):
        if not (folder / "manifest.csv").exists():
            continue
        samples = [
            s for s in read_manifest(folder) if s.get("shape") and s.get("dtype")
        ]
        if not samples or measured(folder / "results.csv"):
            continue
        with (folder / "results.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=RESULT_COLUMNS, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows_for(folder.name, samples))
        (folder / "environment.json").unlink(missing_ok=True)
        print(f"{folder.name}: {len(samples)} samples")


if __name__ == "__main__":
    main()
