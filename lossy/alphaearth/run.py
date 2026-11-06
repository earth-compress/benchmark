"""Rate against error on the AlphaEarth embeddings, for georvq and the lossy
configurations of the benchmark.

The 15 samples of alphaearth-v1-64 are 64 int8 dimensions of 512 x 512 pixels,
64 georvq windows of 64 px each. The error is the cosine distance of each
pixel's dequantised embedding to the original, and the root-mean-square error
of the int8 codes.

uv run --extra learned python lossy/alphaearth/run.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from earthcompress.codecs import fixed, lossy, quantize
from earthcompress.contract import Budget
from earthcompress.corpus import load_samples
from earthcompress.spec import ArraySpec

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CORPUS = ROOT / "corpora" / "alphaearth-v1-64"
NODATA = -128
TAUS = (1, 2, 4, 8, 16, 32)
"""Root-mean-square errors of the sweep, in int8 codes."""
BUNDLE = ("earth-compress/georvq-ae-v2", "a32fac9c601ee5f58d185afc527eaf61b77a5574")
WINDOW = 64
WORKERS = 8


def embedding(codes: np.ndarray) -> np.ndarray:
    """int8 codes as the published embedding, ``(v / 127.5)² · sign(v)``."""
    v = codes.astype(np.float64) / 127.5
    return v * np.abs(v)


def errors(codes: np.ndarray, decoded: np.ndarray) -> dict:
    valid = (codes != NODATA).all(0)
    a, b = embedding(codes)[:, valid], embedding(decoded)[:, valid]
    cos = (a * b).sum(0) / np.maximum(np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0), 1e-12)
    distance = 1 - cos
    e = codes[:, valid].astype(np.float64) - decoded[:, valid].astype(np.float64)
    return {
        "cos_mean": float(distance.mean()),
        "cos_p99": float(np.percentile(distance, 99)),
        "rmse_codes": float(np.sqrt(np.mean(e**2))),
        "max_codes": float(np.abs(e).max()),
    }


def classical():
    by_id = {config.id: config for config in fixed()}
    return lossy() + (quantize.rms_family(by_id["geozl-med-entropy"]),)


def measure_classical(sample: str, codes: np.ndarray) -> list[dict]:
    """The codes are shifted by 128 to uint8, which every codec takes. The
    shift changes no value and puts NoData at 0."""
    shifted = (codes.astype(np.int16) + 128).astype(np.uint8)
    spec = ArraySpec(shifted.shape, shifted.dtype)
    rows = []
    for make in classical():
        for tau in TAUS:
            config = make(Budget(float(tau)))
            if not config.supports(spec):
                continue
            codec = config.factory(spec)
            t = time.perf_counter()
            data = codec.encode(shifted)
            enc = time.perf_counter() - t
            t = time.perf_counter()
            decoded = codec.decode(data)
            dec = time.perf_counter() - t
            back = (decoded.astype(np.int16) - 128).astype(np.int8)
            rows.append(
                {
                    "sample_id": sample,
                    "codec": config.id.rsplit("-tau", 1)[0],
                    "setting": f"tau={tau}",
                    "bytes": len(data),
                    "bits_per_pixel": len(data) * 8 / (codes.shape[1] * codes.shape[2]),
                    **errors(codes, back),
                    "encode_s": enc,
                    "decode_s": dec,
                }
            )
    return rows


_CODEC = None


def georvq():
    global _CODEC
    if _CODEC is None:
        import torch
        from huggingface_hub import snapshot_download
        from georvq.ae.v2 import AE_V2
        from georvq.inference.bundle import load_bundle

        torch.set_num_threads(1)
        folder = snapshot_download(BUNDLE[0], revision=BUNDLE[1], ignore_patterns=["onnx/*"])
        _CODEC = load_bundle(folder, AE_V2, "cpu", None, True)
        _CODEC.rung_bits = {
            tuple(r["tuple"]): r["bits_window"]
            for r in json.loads((Path(folder) / "bundle.json").read_text())["rungs"]
        }
    return _CODEC


def georvq_decodes(codes: np.ndarray):
    """Every rung of one georvq encode, as (rung, bits, decoded codes, seconds)."""
    codec = georvq()
    c, h, w = codes.shape
    n = h // WINDOW
    wins = np.ascontiguousarray(
        codes.reshape(c, n, WINDOW, n, WINDOW).transpose(1, 3, 0, 2, 4).reshape(n * n, c, WINDOW, WINDOW)
    )
    t = time.perf_counter()
    rec, _, valid = codec.encode_windows(wins, stats=False)
    enc = time.perf_counter() - t
    valid = valid.cpu().numpy()
    base = rec["base"][0]
    for rung in codec.rungs:
        t = time.perf_counter()
        tiers = [
            rec[name][:depth].transpose(1, 0, 2) if depth else None
            for name, depth in zip(codec.names[1:], rung[1:])
        ]
        out = codec.decode_records(base, tiers, rung, valid)
        decoded = out.reshape(n, n, c, WINDOW, WINDOW).transpose(2, 0, 3, 1, 4).reshape(c, h, w)
        dec = time.perf_counter() - t
        yield rung, codec.rung_bits[tuple(rung)] * n * n, decoded, enc, dec


def measure_georvq(sample: str, codes: np.ndarray) -> list[dict]:
    rows = []
    for rung, bits, decoded, enc, dec in georvq_decodes(codes):
        rows.append(
            {
                "sample_id": sample,
                "codec": "georvq-ae-v2",
                "setting": "rung=" + "-".join(map(str, rung)),
                "bytes": bits / 8,
                "bits_per_pixel": bits / (codes.shape[1] * codes.shape[2]),
                **errors(codes, decoded),
                "encode_s": enc,
                "decode_s": dec,
            }
        )
    return rows


def task(item) -> list[dict]:
    sample, codes = item
    rows = measure_georvq(sample, codes) + measure_classical(sample, codes)
    print(f"{sample}: {len(rows)} rows", flush=True)
    return rows


def main() -> None:
    items = [(s.id, s.data) for s in load_samples(CORPUS)]
    if len(sys.argv) > 1:
        items = items[: int(sys.argv[1])]
    with ProcessPoolExecutor(WORKERS) as pool:
        rows = [row for rows in pool.map(task, items) for row in rows]
    with (HERE / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows for {len(items)} samples")


if __name__ == "__main__":
    main()
