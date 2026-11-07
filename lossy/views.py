"""The pictures of the lossy page: every sample of each dataset decoded by every
codec near each rate of the page's slider.

For each rate and codec it keeps the setting whose rate on that sample is
nearest, and writes

- Sentinel-2: true colour and the error of the 10 m bands, and the power
  spectrum of the decode against the original;
- AlphaEarth: the first three principal components of the embedding as colour,
  the cosine distance to the original, and the decoded int8 codes of the central 128 px, which the page reads to draw similarity maps.

uv run --extra learned python lossy/views.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from earthcompress.contract import Budget
from earthcompress.spec import ArraySpec

HERE = Path(__file__).resolve().parent
S2_SAMPLES = tuple(f"s2-l1c-{i:02d}" for i in range(50))
AE_SAMPLES = tuple(f"alphaearth-v1-64-{i:02d}" for i in range(15))
S2_STOPS = (0.3, 0.5, 1, 2, 3, 6)
AE_STOPS = (0.2, 0.5, 1, 2, 4, 8)
"""Rates of the slider, in bits per pixel."""
CROP = 128
"""Side of the AlphaEarth crop, in pixels."""
S2_ERROR = 250.0
AE_ERROR = 0.05
"""Top of the colour scale of the error maps, in DN and in cosine distance."""
RAMP = np.array(
    [(0, 0, 4), (59, 15, 112), (140, 41, 129), (222, 73, 104), (254, 159, 109), (252, 253, 191)],
    dtype=np.float64,
)


def module(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / name / "run.py")
    found = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(found)
    return found


def ramp(values: np.ndarray) -> np.ndarray:
    """``values`` from 0 to 1 as RGB on the colour ramp."""
    v = np.clip(values, 0, 1) * (len(RAMP) - 1)
    low = np.floor(v).astype(int).clip(0, len(RAMP) - 2)
    t = (v - low)[..., None]
    return (RAMP[low] * (1 - t) + RAMP[low + 1] * t).round().astype(np.uint8)


def save(rgb: np.ndarray, path: Path, lossless: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path, "WEBP", quality=88, lossless=lossless, method=6)


def matched(views: list[dict], stops) -> dict:
    """For each stop and codec, the view nearest that rate."""
    out: dict[str, dict] = {}
    for stop in stops:
        for codec in dict.fromkeys(v["codec"] for v in views):
            mine = [v for v in views if v["codec"] == codec]
            best = min(mine, key=lambda v: abs(np.log(v["bits_per_pixel"] / stop)))
            out.setdefault(f"{stop:g}", {})[codec] = best
    return out


# Sentinel-2


def s2_rgb(bands: np.ndarray, low: float, high: float) -> np.ndarray:
    rgb = bands[[2, 1, 0]].astype(np.float64).transpose(1, 2, 0)
    return (np.clip((rgb - low) / (high - low), 0, 1) ** (1 / 1.6) * 255).round().astype(np.uint8)


def spectrum(bands: np.ndarray) -> np.ndarray:
    """Radially averaged power of each 10 m band, summed, in log-spaced bins."""
    side = bands.shape[-1]
    window = np.outer(np.hanning(side), np.hanning(side))
    f = np.fft.fftfreq(side)
    radius = np.hypot(*np.meshgrid(f, f, indexing="ij"))
    edges = np.geomspace(2 / side, 0.5, 25)
    which = np.digitize(radius, edges) - 1
    power = sum(
        np.abs(np.fft.fft2((b - b.mean()) * window)) ** 2 for b in bands.astype(np.float64)
    )
    return np.array([power[which == k].mean() for k in range(len(edges) - 1)])


def s2(sample: str) -> dict:
    run = module("s2")
    arrays = dict(run.scenes())[sample]
    ten = arrays[0]
    low, high = np.percentile(ten[[2, 1, 0]], (1, 99))
    reference = spectrum(ten)
    folder = HERE / "s2" / "views" / sample
    save(s2_rgb(ten, low, high), folder / "original.webp")

    def view(codec: str, setting: str, size: float, decoded) -> dict:
        e = ten.astype(np.float64) - decoded[0].astype(np.float64)
        name = f"{codec}-{setting.replace('=', '-')}"
        save(s2_rgb(decoded[0], low, high), folder / f"{name}.webp")
        save(ramp(np.sqrt((e**2).mean(0)) / S2_ERROR), folder / f"{name}-error.webp")
        return {
            "codec": codec,
            "setting": setting,
            "bits_per_pixel": size * 8 / run.SIDE**2,
            **run.errors(arrays, decoded),
            "image": f"{name}.webp",
            "error": f"{name}-error.webp",
            "spectrum": [round(float(v), 4) for v in spectrum(decoded[0]) / reference],
        }

    views = [
        view("georvq-s2-v1", "rung=" + "-".join(map(str, rung)), bits / 8, decoded)
        for rung, bits, decoded, _, _ in run.georvq_decodes(arrays)
    ]
    for make in run.classical():
        for tau in run.TAUS:
            configs = [make(Budget(float(tau))) for _ in arrays]
            specs = [ArraySpec(a.shape, a.dtype) for a in arrays]
            if not all(c.supports(s) for c, s in zip(configs, specs)):
                continue
            size, decoded = 0, []
            for config, spec, array in zip(configs, specs, arrays):
                codec = config.factory(spec)
                data = codec.encode(np.ascontiguousarray(array))
                decoded.append(codec.decode(data))
                size += len(data)
            views.append(view(configs[0].id.rsplit("-tau", 1)[0], f"tau={tau}", size, decoded))
    return finish(folder, views, S2_STOPS, "georvq-s2-v1")


# AlphaEarth


def ae(sample: str) -> dict:
    run = module("alphaearth")
    from earthcompress.corpus import load_samples

    codes = next(s.data for s in load_samples(run.CORPUS) if s.id == sample)
    side = codes.shape[1]
    h = (side - CROP) // 2
    window = (slice(None), slice(h, h + CROP), slice(h, h + CROP))
    valid = (codes != run.NODATA).all(0)
    a = run.embedding(codes).reshape(codes.shape[0], -1)
    mean = a[:, valid.ravel()].mean(1, keepdims=True)
    _, _, vt = np.linalg.svd((a[:, valid.ravel()][:, ::7] - mean).T, full_matrices=False)
    axes = vt[:3]
    projected = axes @ (a - mean)
    low, high = np.percentile(projected[:, valid.ravel()], (2, 98), axis=1)
    folder = HERE / "alphaearth" / "views" / sample

    def colour(c: np.ndarray) -> np.ndarray:
        p = axes @ (run.embedding(c).reshape(c.shape[0], -1) - mean)
        rgb = np.clip((p - low[:, None]) / (high - low)[:, None], 0, 1)
        rgb = (rgb.T.reshape(side, side, 3) * 255).round().astype(np.uint8)
        rgb[~valid] = 200
        return rgb

    save(colour(codes), folder / "original.webp", lossless=True)
    (folder / "original.bin").write_bytes(np.ascontiguousarray(codes[window]).tobytes())

    def view(codec: str, setting: str, size: float, decoded) -> dict:
        b = run.embedding(decoded).reshape(decoded.shape[0], -1)
        cos = (a * b).sum(0) / np.maximum(np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0), 1e-12)
        error = ramp((1 - cos).reshape(side, side) / AE_ERROR)
        error[~valid] = 200
        name = f"{codec}-{setting.replace('=', '-')}"
        return {
            "codec": codec,
            "setting": setting,
            "bits_per_pixel": size * 8 / (codes.shape[1] * codes.shape[2]),
            **run.errors(codes, decoded),
            "image": f"{name}.webp",
            "error": f"{name}-error.webp",
            "codes": f"{name}.bin",
            "_pictures": (colour(decoded), error, np.ascontiguousarray(decoded[window]).tobytes()),
        }

    views = [
        view("georvq-ae-v2", "rung=" + "-".join(map(str, rung)), bits / 8, decoded)
        for rung, bits, decoded, _, _ in run.georvq_decodes(codes)
    ]
    shifted = (codes.astype(np.int16) + 128).astype(np.uint8)
    spec = ArraySpec(shifted.shape, shifted.dtype)
    for make in run.classical():
        for tau in run.TAUS:
            config = make(Budget(float(tau)))
            if not config.supports(spec):
                continue
            codec = config.factory(spec)
            data = codec.encode(shifted)
            back = (codec.decode(data).astype(np.int16) - 128).astype(np.int8)
            views.append(view(config.id.rsplit("-tau", 1)[0], f"tau={tau}", len(data), back))
    return finish(folder, views, AE_STOPS, "georvq-ae-v2")


def finish(folder: Path, views: list[dict], stops, georvq: str) -> dict:
    """Write the pictures of the matched views and the description of the sample."""
    stops = matched(views, stops)
    for chosen in stops.values():
        for v in chosen.values():
            if "_pictures" in v:
                image, error, codes = v["_pictures"]
                save(image, folder / v["image"], lossless=True)
                save(error, folder / v["error"], lossless=True)
                (folder / v["codes"]).write_bytes(codes)
    clean = lambda v: {k: x for k, x in v.items() if not k.startswith("_")}  # noqa: E731
    out = {
        "stops": {s: {c: clean(v) for c, v in chosen.items()} for s, chosen in stops.items()},
        "rungs": [
            {"setting": v["setting"], "bits_per_pixel": v["bits_per_pixel"]}
            for v in views
            if v["codec"] == georvq
        ],
    }
    # Pictures of views no stop chose are not kept.
    keep = {"original.webp", "original.bin", "sample.json"} | {
        v[k] for chosen in stops.values() for v in chosen.values() for k in ("image", "error", "codes") if k in v
    }
    for path in folder.iterdir():
        if path.name not in keep:
            path.unlink()
    (folder / "sample.json").write_text(json.dumps(out))
    return out


def task(item: tuple[str, str]) -> str:
    kind, sample = item
    (s2 if kind == "s2" else ae)(sample)
    return f"{sample} done"


def main() -> None:
    items = [("ae", s) for s in AE_SAMPLES] + [("s2", s) for s in S2_SAMPLES]
    if len(sys.argv) > 1:
        items = [i for i in items if i[1] in sys.argv[1:]]
    with ProcessPoolExecutor(6) as pool:
        for line in pool.map(task, items):
            print(line, flush=True)


if __name__ == "__main__":
    main()
