"""Rate against error on the 13 Sentinel-2 L1C bands, for georvq and the lossy
configurations of the benchmark.

The three S2 corpora hold the same 50 scenes, centred on the same point, at 10,
20 and 60 m. Their common footprint is cut to 504 px at 10 m, 14 georvq
windows of 36 px, and the matching 252 and 84 px at 20 and 60 m.

uv run --extra learned python lossy/s2/run.py
"""

from __future__ import annotations

import csv
import json
import os
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
GRIDS = (
    ("10m", "s2-l1c-10m-4", 10),
    ("20m", "s2-l1c-20m-6", 20),
    ("60m", "s2-l1c-60m-3", 60),
)
SIDE = 504
"""Pixels of the common footprint at 10 m."""
TAUS = (2, 5, 10, 20, 40, 80, 160, 320)
"""Root-mean-square errors of the sweep, in DN."""
BUNDLE = ("earth-compress/georvq-s2-v1", "a01551cbf956b6dd34f2a1fd6e3227906f6d965f")
WORKERS = 8


def origin(row: dict) -> tuple[float, float]:
    values = [float(v) for v in row["transform"].split()]
    return values[0], values[3]


def scenes() -> list[tuple[str, tuple[np.ndarray, ...]]]:
    """Each scene as its three grids cut to the common footprint."""
    loaded = {}
    for name, corpus, _ in GRIDS:
        folder = ROOT / "corpora" / corpus
        with (folder / "manifest.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        loaded[name] = list(zip(rows, load_samples(folder), strict=False))
    out = []
    for i, (row10, _) in enumerate(loaded["10m"]):
        x10, y10 = origin(row10)
        rows = [loaded[name][i][0] for name, _, _ in GRIDS]
        if any(row["asset"] != row10["asset"] for row in rows):
            raise ValueError(f"{row10['id']}: the three grids are not one scene")
        # the first 10 m pixel at which every coarser grid has a pixel edge
        shift = []
        for axis, sign in ((0, 1), (1, -1)):
            for k in range(6):
                edge = (x10, y10)[axis] + sign * 10 * k
                if all(
                    (sign * (edge - origin(row)[axis]) / m).is_integer()
                    for row, (_, _, m) in zip(rows, GRIDS, strict=False)
                ):
                    shift.append(k)
                    break
            else:
                raise ValueError(f"{row10['id']}: the grids share no pixel edge")
        col, line = shift
        x0, y0 = x10 + 10 * col, y10 - 10 * line
        arrays = []
        for (name, _, metres), row in zip(GRIDS, rows, strict=False):
            x, y = origin(row)
            c, r = int((x0 - x) / metres), int((y - y0) / metres)
            side = SIDE * 10 // metres
            data = loaded[name][i][1].data[:, r : r + side, c : c + side]
            if data.shape[1:] != (side, side):
                raise ValueError(f"{row['id']}: the footprint leaves the sample")
            arrays.append(data)
        out.append((row10["id"].replace("s2-l1c-10m-4", "s2-l1c"), tuple(arrays)))
    return out


def classical():
    by_id = {config.id: config for config in fixed()}
    return lossy() + (quantize.rms_family(by_id["geozl-med-entropy"]),)


def errors(arrays, decoded) -> dict:
    row = {}
    squares, count = 0.0, 0
    for (name, _, _), a, d in zip(GRIDS, arrays, decoded, strict=False):
        e = a.astype(np.float64) - d.astype(np.float64)
        row[f"rmse_{name}"] = float(np.sqrt(np.mean(e**2)))
        row[f"max_{name}"] = float(np.abs(e).max())
        squares, count = squares + float(np.sum(e**2)), count + e.size
    row["rmse_all"] = float(np.sqrt(squares / count))
    return row


def measure_classical(sample: str, arrays) -> list[dict]:
    rows = []
    for make in classical():
        for tau in TAUS:
            configs = [make(Budget(float(tau))) for _ in arrays]
            specs = [ArraySpec(a.shape, a.dtype) for a in arrays]
            if not all(c.supports(s) for c, s in zip(configs, specs, strict=False)):
                continue
            size, decoded, enc, dec = 0, [], 0.0, 0.0
            for config, spec, array in zip(configs, specs, arrays, strict=False):
                codec = config.factory(spec)
                t = time.perf_counter()
                data = codec.encode(np.ascontiguousarray(array))
                enc += time.perf_counter() - t
                t = time.perf_counter()
                decoded.append(codec.decode(data))
                dec += time.perf_counter() - t
                size += len(data)
            rows.append(
                {
                    "sample_id": sample,
                    "codec": configs[0].id.rsplit("-tau", 1)[0],
                    "setting": f"tau={tau}",
                    "bytes": size,
                    "bits_per_pixel": size * 8 / SIDE**2,
                    **errors(arrays, decoded),
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
        from georvq.s2.v1 import load_bundle
        from huggingface_hub import snapshot_download

        torch.set_num_threads(1)
        folder = snapshot_download(
            BUNDLE[0], revision=BUNDLE[1], ignore_patterns=["onnx/*"]
        )
        _CODEC = load_bundle(folder, device="cpu")
        _CODEC.rung_bits = {
            tuple(r["tuple"]): r["bits_window"]
            for r in json.loads((Path(folder) / "bundle.json").read_text())["rungs"]
        }
    return _CODEC


def windows(arrays) -> tuple[np.ndarray, ...]:
    out = []
    for array, (_, _, metres) in zip(arrays, GRIDS, strict=False):
        w = 360 // metres
        n = array.shape[1] // w
        out.append(
            np.ascontiguousarray(
                array.reshape(array.shape[0], n, w, n, w)
                .transpose(1, 3, 0, 2, 4)
                .reshape(n * n, array.shape[0], w, w)
            )
        )
    return tuple(out)


def unwindow(blocks: np.ndarray, side: int) -> np.ndarray:
    n = side // blocks.shape[-1]
    c, w = blocks.shape[1], blocks.shape[-1]
    return blocks.reshape(n, n, c, w, w).transpose(2, 0, 3, 1, 4).reshape(c, side, side)


def georvq_decodes(arrays):
    """Every rung of one georvq encode, as (rung, bits, decoded grids, seconds)."""
    import torch
    from georvq.inference.store_codec import cumulative
    from georvq.s2.v1 import GRIDS as RVQ_GRIDS
    from georvq.s2.v1 import stats_vector

    codec = georvq()
    wins = windows(arrays)
    with torch.no_grad():
        t = time.perf_counter()
        x, valid = codec.spec.prep(codec.model, wins, codec.device)
        fields = codec.channel.encode(stats_vector(codec.model.source.last_stats()))
        stacked, _, _ = codec.codec.encode_batch(x, valid=valid)
        enc = time.perf_counter() - t
        stats = torch.from_numpy(codec.channel.decode(fields))
        cums = [
            cumulative(rvq, torch.from_numpy(s), sp.depth)
            for rvq, s, sp in zip(codec.model.rvqs, stacked, codec.specs, strict=False)
        ]
        for rung in codec.rungs:
            t = time.perf_counter()
            out = codec._forward(
                [c[L] for c, L in zip(cums, rung, strict=False)], rung, stats, valid
            )
            decoded = [
                unwindow(
                    out[g].float().round().clamp(1, 65535).numpy().astype(np.uint16),
                    a.shape[1],
                )
                for (g, _, _), a in zip(RVQ_GRIDS, arrays, strict=False)
            ]
            dec = time.perf_counter() - t
            yield rung, codec.rung_bits[tuple(rung)] * len(wins[0]), decoded, enc, dec


def measure_georvq(sample: str, arrays) -> list[dict]:
    rows = []
    for rung, bits, decoded, enc, dec in georvq_decodes(arrays):
        rows.append(
            {
                "sample_id": sample,
                "codec": "georvq-s2-v1",
                "setting": "rung=" + "-".join(map(str, rung)),
                "bytes": bits / 8,
                "bits_per_pixel": bits / SIDE**2,
                **errors(arrays, decoded),
                "encode_s": enc,
                "decode_s": dec,
            }
        )
    return rows


def task(item) -> list[dict]:
    sample, arrays = item
    rows = measure_georvq(sample, arrays) + measure_classical(sample, arrays)
    print(f"{sample}: {len(rows)} rows", flush=True)
    return rows


def main() -> None:
    items = scenes()
    if len(sys.argv) > 1:
        items = items[: int(sys.argv[1])]
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    with ProcessPoolExecutor(WORKERS) as pool:
        rows = [row for rows in pool.map(task, items) for row in rows]
    with (HERE / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows for {len(items)} scenes")


if __name__ == "__main__":
    main()
