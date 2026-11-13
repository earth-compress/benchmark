"""The Clouds Decoded use case, on the crops of build.py.

Each crop is compressed with the lossy configurations of the benchmark and with
georvq, and Clouds Decoded runs its full workflow on the original and on every
decoded copy. Its outputs on the original are checked against those in
``reference/``, so a different install of Clouds Decoded shows up before it
changes the results. It needs the ``compressed-readers`` branch of Clouds Decoded and a
GPU, and takes about 7 s per run.

uv run --extra corpus --extra learned python usecases/clouds-decoded/run.py
"""

import csv
import hashlib
import importlib.util
import json
import multiprocessing
import sys
import zipfile
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from affine import Affine
from clouds_decoded.data import Sentinel2Scene, band_source
from clouds_decoded.data.band import BandDict, Sentinel2Band
from clouds_decoded.data.band_source import BandGeoref, BandSource
from clouds_decoded.modules.albedo_estimator.config import AlbedoEstimatorConfig
from clouds_decoded.modules.albedo_estimator.processor import AlbedoEstimator
from clouds_decoded.modules.cloud_height_emulator.config import (
    CloudHeightEmulatorConfig,
)
from clouds_decoded.modules.cloud_height_emulator.processor import (
    CloudHeightEmulatorProcessor,
)
from clouds_decoded.modules.cloud_mask.config import CloudMaskConfig
from clouds_decoded.modules.cloud_mask.processor import CloudMaskProcessor
from clouds_decoded.modules.refl2prop.config import Refl2PropConfig
from clouds_decoded.modules.refl2prop.processor import CloudPropertyInverter
from clouds_decoded.modules.refocus.config import RefocusConfig
from clouds_decoded.modules.refocus.processor import RefocusProcessor
from PIL import Image
from rasterio.crs import CRS

from earthcompress.contract import Budget
from earthcompress.spec import ArraySpec
from earthcompress.usecase import compress, fetch, iou, lossy_codecs, overlay, shade

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
GRIDS = (
    ("B02", "B03", "B04", "B08"),
    ("B05", "B06", "B07", "B8A", "B11", "B12"),
    ("B01", "B09", "B10"),
)
"""The bands of the 10, 20 and 60 m grids, in the order of the S2 corpora."""
SIZE = 2520
"""Pixels of a crop at 10 m."""
RMS = (5, 10, 20, 40, 80)
"""Root-mean-square errors of the sweep, in DN."""
MIN_PIXELS = 1000
"""Fewer ice pixels than this give no radius value, rather than a noisy one."""
CTH_LIMIT = 3000.0
"""Change in cloud top height at the two ends of the colour bar, in metres."""
WORKERS = 16
GEORVQ_THREADS = 16


class CropSource(BandSource):
    """The bands of a crop, for Clouds Decoded to read as a compressed product.

    ``COMPRESSED.json`` gives the grid of the full product and the window of the
    crop, so Clouds Decoded reads the crop's metadata as it would read the window
    of the full product.
    """

    name = "crop"

    def __init__(self, scene_directory: Path, manifest: dict):
        g = manifest["georef"]
        self._georef = BandGeoref(
            CRS.from_wkt(g["crs"]), Affine(*g["transform"]), g["width"], g["height"]
        )
        self._bands = manifest["bands"]
        self._window = tuple(manifest["window"])
        with np.load(Path(scene_directory) / "bands.npz") as z:
            self.arrays = {b: z[b] for b in z.files}

    @property
    def groups(self):
        return {b: [b] for b in self._bands}

    def georef(self):
        return self._georef

    def shape(self, band):
        return tuple(self._bands[band]["shape"])

    def native_resolution(self, band):
        return self._bands[band]["res"]

    def _read_group(self, group, windows):
        (band,) = self.groups[group]
        window = windows[band]
        if window is None or window != self.window(band, self._window):
            raise ValueError(f"the crop holds only the window {self._window}")
        return {band: self.arrays[band]}


band_source.READERS["crop"] = f"{__name__}:CropSource"


class CloudsDecoded:
    """The full workflow of Clouds Decoded, its models loaded once."""

    def __init__(self):
        # The settings of ``clouds-decoded full-workflow``.
        self.mask = CloudMaskProcessor(CloudMaskConfig(method="senseiv2"))
        self.height = CloudHeightEmulatorProcessor(CloudHeightEmulatorConfig())
        self.albedo = AlbedoEstimator(AlbedoEstimatorConfig(method="idw"))
        self.refocus = RefocusProcessor(RefocusConfig())
        self.properties = CloudPropertyInverter(Refl2PropConfig())

    def scene(self, safe: Path, bands: dict | None = None):
        """The crop as Clouds Decoded reads it, its bands replaced by ``bands``."""
        manifest = json.loads((safe / "COMPRESSED.json").read_text())
        scene = Sentinel2Scene()
        scene.read(safe, crop_window=tuple(manifest["window"]))
        if bands is not None:
            replaced = BandDict()
            for name, band in scene.bands.items():
                replaced[name] = Sentinel2Band(
                    name=name,
                    data=bands[name],
                    native_resolution=band.native_resolution,
                )
            object.__setattr__(scene, "bands", replaced)
        return scene

    def __call__(self, scene) -> dict:
        raw = self.mask.process(scene)
        mask = raw.to_binary(positive_classes=[1, 2, 3], threshold=0.5)
        height = self.height.process(scene, cloud_mask=mask)
        albedo = self.albedo.process(scene, cloud_mask=mask)
        refocused = self.refocus.process(scene, height)
        properties = self.properties.process(refocused, height, albedo_data=albedo)
        return {
            "mask": layers(raw)[0] == 1,
            "height": layers(height)[0],
            "properties": layers(properties),
        }


def layers(result) -> np.ndarray:
    """The data of a Clouds Decoded result as bands × rows × columns."""
    data = np.asarray(result.data, np.float32)
    return data if data.ndim == 3 else data[None]


def stacks(bands: dict) -> tuple[np.ndarray, ...]:
    return tuple(np.stack([bands[b] for b in grid]) for grid in GRIDS)


def unstack(arrays) -> dict:
    return {
        b: a
        for grid, stack in zip(GRIDS, arrays, strict=True)
        for b, a in zip(grid, stack, strict=True)
    }


def error(arrays, decoded) -> float:
    squares = sum(
        float(np.sum(np.square(a.astype(np.float64) - d)))
        for a, d in zip(arrays, decoded, strict=True)
    )
    return float(np.sqrt(squares / sum(a.size for a in arrays)))


def lossy_s2():
    """``lossy/s2/run.py``, for its georvq encoder."""
    spec = importlib.util.spec_from_file_location(
        "lossy_s2", ROOT / "lossy" / "s2" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jobs(safe: Path) -> list[tuple]:
    """One job per lossy configuration and bound, and one for every georvq rung."""
    return [(i, bound, safe) for i in range(len(lossy_codecs())) for bound in RMS] + [
        (None, None, safe)
    ]


def versions(job: tuple) -> list[dict]:
    """The decoded copies of a crop from one job, with their sizes."""
    index, bound, safe = job
    with np.load(safe / "bands.npz") as z:
        arrays = stacks({b: z[b] for b in z.files})
    if index is None:
        import torch

        s2 = lossy_s2()
        s2.georvq()
        torch.set_num_threads(GEORVQ_THREADS)
        return [
            {
                "configuration": f"georvq-s2-v1-rung{'-'.join(map(str, rung))}",
                "codec": "georvq-s2-v1",
                "rms_bound": rung[-1],
                "bytes": bits / 8,
                "decoded": decoded,
            }
            for rung, bits, decoded, _, _ in s2.georvq_decodes(arrays)
        ]
    config = lossy_codecs()[index](Budget(tau=float(bound)))
    decoded, size = [], 0
    for array in arrays:
        values, n = compress(config, array, ArraySpec(array.shape, array.dtype))
        decoded.append(values.astype(np.uint16))
        size += n
    return [
        {
            "configuration": config.id,
            "codec": config.id.rsplit("-tau", 1)[0],
            "rms_bound": bound,
            "bytes": size,
            "decoded": decoded,
        }
    ]


def texture(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> float:
    """The mean step between neighbouring valid pixels, in ``b`` over ``a``."""
    rows, columns = valid[1:] & valid[:-1], valid[:, 1:] & valid[:, :-1]

    def steps(x: np.ndarray) -> float:
        return (
            np.abs(np.diff(x, axis=0))[rows].sum()
            + np.abs(np.diff(x, axis=1))[columns].sum()
        )

    return float(steps(b) / steps(a))


def compare(original: dict, decoded: dict) -> dict:
    """The metrics from compressed data against those from the original."""
    h0, h1 = original["height"], decoded["height"]
    both = np.isfinite(h0) & np.isfinite(h1)
    change = h1[both] - h0[both]

    t0, t1 = original["properties"][0], decoded["properties"][0]
    positive = (t0 > 0) & (t1 > 0)

    # A radius retrieved as the other phase is not comparable, so a pixel counts
    # only when it is ice in the original and stays on the ice side.
    r0, r1 = original["properties"][3], decoded["properties"][3]
    ice = (
        (original["properties"][1] > 0.6)
        & (decoded["properties"][1] > 0.5)
        & np.isfinite(r0)
        & np.isfinite(r1)
    )
    enough = ice.sum() >= MIN_PIXELS

    return {
        "cloud_iou": iou(original["mask"], decoded["mask"]),
        "cth_mae": float(np.abs(change).mean()) if change.size else None,
        "cth_bias": float(change.mean()) if change.size else None,
        "tau_median_rel_error": float(
            100 * np.median(np.abs(t1[positive] / t0[positive] - 1))
        )
        if positive.any()
        else None,
        "re_ice_mae": float(np.abs(r1[ice] - r0[ice]).mean()) if enough else None,
        "re_ice_texture": texture(r0, r1, ice) if enough else None,
    }


def background(bands: dict) -> np.ndarray:
    """The crop in grey at 60 m, from the 10 m red, green and blue."""
    rgb = np.stack([bands[b][::6, ::6] for b in ("B04", "B03", "B02")]).astype(
        np.float32
    )
    return rgb.mean(axis=0)


def true_colour(bands: dict) -> np.ndarray:
    """The crop in true colour at 20 m, from the 10 m red, green and blue,
    stretched from 1000 DN up to 3500 DN or its 99th percentile, if brighter."""
    rgb = np.stack([bands[b][::2, ::2] for b in ("B04", "B03", "B02")], axis=-1)
    rgb = rgb.astype(np.float32)
    high = max(3500.0, float(np.percentile(rgb, 99)))
    stretched = np.clip((rgb - 1000) / (high - 1000), 0, 1) ** (1 / 1.6)
    return (255 * stretched).astype(np.uint8)


def outputs(bands: dict, original: dict) -> dict[str, Image.Image]:
    """What Clouds Decoded finds on the original crop, in colour over it at 20 m.

    The cloud mask is tinted and outlined in orange. Cloud top height runs from 0 to 15 km,
    optical thickness from 0.1 to 100 on a log scale and ice effective radius from
    15 to 45 µm.
    """
    from earthcompress.build import colour

    rgb = true_colour(bands)
    side = rgb.shape[0]
    mask = original["mask"][np.ix_(*[np.arange(side) * 4 // 3] * 2)]
    inner = mask.copy()
    inner[1:-1, 1:-1] &= (
        mask[:-2, 1:-1] & mask[2:, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:]
    )
    edge = mask & ~inner
    edge[1:] |= edge[:-1]
    edge[:, 1:] |= edge[:, :-1]
    orange = np.array((240, 140, 30), np.float32)
    tinted = rgb.astype(np.float32)
    tinted[mask] = 0.6 * tinted[mask] + 0.4 * orange
    tinted[edge] = orange
    images = {"mask": tinted.astype(np.uint8)}

    height = original["height"]
    tau, ice, radius = original["properties"][[0, 1, 3]]
    for name, scaled, valid, cmap in (
        ("height", height / 15000, np.isfinite(height) & (height > 0), "viridis"),
        ("thickness", (np.log10(np.where(tau > 0, tau, 1)) + 1) / 3, tau > 0, "magma"),
        ("ice", (radius - 15) / 30, (ice > 0.6) & np.isfinite(radius), "plasma"),
    ):
        image = rgb.copy()
        found = np.kron(valid, np.ones((3, 3), bool))
        paint = colour(np.clip(np.nan_to_num(scaled), 0, 1), cmap)
        image[found] = np.kron(paint, np.ones((3, 3, 1), np.uint8))[found]
        images[name] = image
    return {name: Image.fromarray(image) for name, image in images.items()}


def maps(grey: np.ndarray, original: np.ndarray, decoded: np.ndarray) -> Image.Image:
    """The two cloud masks over the crop in grey, every 4th pixel of the 15 m mask.

    Cloud on both is orange, cloud the compressed data loses is blue, and cloud it
    adds is red.
    """
    a, b = original[::4, ::4], decoded[::4, ::4]
    return Image.fromarray(overlay(shade(grey), a & b, a & ~b, ~a & b))


def height_change(
    grey: np.ndarray, original: np.ndarray, decoded: np.ndarray
) -> Image.Image:
    """The change in cloud top height at 60 m.

    Blue is lower than the original, red higher and white unchanged. A pixel without
    a height in both stays grey.
    """
    from earthcompress.build import colour

    change = decoded - original
    found = np.isfinite(change)
    image = shade(grey)
    image[found] = colour(np.clip((change[found] / CTH_LIMIT + 1) / 2, 0, 1), "RdBu_r")
    return Image.fromarray(image)


def save(image: Image.Image, path: Path) -> None:
    """``image`` as a PNG of at most 256 colours, which halves its size."""
    image.quantize(256, dither=Image.Dither.NONE).save(path, optimize=True)


def check(sample: str, original: dict) -> None:
    """Compare what Clouds Decoded gives on the original crop with the reference
    outputs, or write them where there are none."""
    path = HERE / "reference" / f"{sample}.npz"
    if not path.is_file():
        path.parent.mkdir(exist_ok=True)
        np.savez_compressed(path, **original)
        return
    with np.load(path) as reference:
        for name, values in original.items():
            if not np.array_equal(values, reference[name], equal_nan=True):
                print(f"{sample}: {name} differs from the reference", flush=True)


def unpacked(row: dict) -> Path:
    """The ``.SAFE`` directory of a crop, unpacked next to its zip."""
    safe = HERE / "safe" / row["id"] / f"{row['product']}.SAFE"
    if not (safe / "bands.npz").is_file():
        with zipfile.ZipFile(HERE / "crops" / f"{row['id']}.zip") as z:
            z.extractall(safe.parent)
    return safe


def digest(arrays) -> str:
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def crop(row: dict, cd: CloudsDecoded, futures: list[Future]) -> list[dict]:
    """Clouds Decoded on a crop and on each copy as its compression finishes."""
    safe = unpacked(row)
    scene = cd.scene(safe)
    bands = {b: scene.bands[b].data for b in scene.bands}
    arrays = stacks(bands)
    original = cd(scene)
    check(row["id"], original)
    grey = background(bands)
    figures = HERE / "png" / row["id"]
    figures.mkdir(parents=True, exist_ok=True)
    Image.fromarray(true_colour(bands)).save(figures / "rgb.png", optimize=True)
    for name, image in outputs(bands, original).items():
        image.save(figures / f"{name}.png", optimize=True)

    raw = sum(a.nbytes for a in arrays)
    done: dict[str, dict] = {}
    rows = []
    for version in (v for f in as_completed(futures) for v in f.result()):
        key = digest(version["decoded"])
        if key not in done:
            done[key] = cd(cd.scene(safe, unstack(version["decoded"])))
        decoded = done[key]
        name = version["configuration"]
        save(maps(grey, original["mask"], decoded["mask"]), figures / f"{name}.png")
        save(
            height_change(grey, original["height"], decoded["height"]),
            figures / f"{name}-cth.png",
        )
        rmse = error(arrays, version["decoded"])
        rows.append(
            {
                "id": row["id"],
                "surface": row["surface"],
                "configuration": name,
                "codec": version["codec"],
                "rms_bound": version["rms_bound"],
                "rmse": rmse,
                "compression_ratio": raw / version["bytes"],
                "bits_per_pixel": version["bytes"] * 8 / SIZE**2,
                **compare(original, decoded),
            }
        )
    print(f"{row['id']}: {len(rows)} copies, {len(done)} runs", flush=True)
    return sorted(rows, key=lambda r: (r["codec"], r["rmse"]))


def main() -> None:
    with (HERE / "manifest.csv").open(newline="") as stream:
        samples = list(csv.DictReader(stream))
    if len(sys.argv) > 1:
        samples = [row for row in samples if row["id"] in sys.argv[1:]]
    fetch(
        HERE,
        [
            f"{kind}/{row['id']}.{ext}"
            for row in samples
            for kind, ext in (("crops", "zip"), ("reference", "npz"))
        ],
    )

    cd = CloudsDecoded()
    context = multiprocessing.get_context("spawn")
    rows = []
    with ProcessPoolExecutor(WORKERS, mp_context=context) as pool:

        def submit(row: dict) -> list[Future]:
            return [pool.submit(versions, job) for job in jobs(unpacked(row))]

        # The next crop compresses while Clouds Decoded runs on this one.
        pending = submit(samples[0])
        for i, row in enumerate(samples):
            futures = pending
            if i + 1 < len(samples):
                pending = submit(samples[i + 1])
            rows += crop(row, cd, futures)
    with (HERE / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
