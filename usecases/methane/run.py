"""The methane use case, on the patches of build.py.

uv run python usecases/methane/run.py
"""

import csv
import shutil
from pathlib import Path

import numpy as np

from earthcompress.codecs import fixed, jpegxl, quantize
from earthcompress.contract import Budget
from earthcompress.spec import ArraySpec
from earthcompress.usecase import compress, fetch, iou, run

HERE = Path(__file__).resolve().parent
RMS = (1, 2, 4, 8, 16, 32, 64)
"""Root-mean-square errors of the sweep, in DN, the stored unit of every patch."""


def makers():
    """GeoZL with PIVCO and with PFOR behind the lossy quantiser, and JPEG XL with
    its distance searched, all holding the root-mean-square error of each array
    within tau."""
    lossless = {c.id: c for c in fixed()}
    return (
        quantize.rms_family(lossless["geozl-med-pivco"]),
        quantize.rms_family(lossless["geozl-planar-pfor"]),
        jpegxl.distance,
    )


def enhancement(target: np.ndarray, bg: np.ndarray, sign: float = 1.0) -> np.ndarray:
    t = target.astype(np.float64)
    r = np.median(bg, axis=0).astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return sign * ((t[1] / r[1]) / (t[0] / r[0]) - 1)


def fit(target: np.ndarray, bg: np.ndarray, plume: np.ndarray) -> tuple[float, float]:
    """The sign that makes the plume positive, and the threshold outside it."""
    e = enhancement(target, bg)
    sign = 1.0 if np.nanmean(e[plume]) > np.nanmean(e[~plume]) else -1.0
    return sign, float(np.nanpercentile(sign * e[~plume], 99.5))


def outline(mask: np.ndarray) -> np.ndarray:
    """The cells of ``mask`` that touch a cell outside it."""
    inside = np.pad(
        mask[1:-1, 1:-1]
        & mask[:-2, 1:-1]
        & mask[2:, 1:-1]
        & mask[1:-1, :-2]
        & mask[1:-1, 2:],
        1,
    )
    return mask & ~inside


KEPT, LOST, NEW = (245, 158, 11), (56, 189, 248), (244, 63, 94)


def detections(
    e: np.ndarray,
    plume: np.ndarray,
    original: np.ndarray,
    decoded: np.ndarray | None = None,
):
    """The detection over the enhancement in grey, with the plume mask outlined.

    With a decoded detection, pixels detected on both are orange, pixels the
    decoded copy loses are blue, and pixels it adds are red.
    """
    from PIL import Image

    low, high = np.nanpercentile(e, (2, 99.5))
    grey = np.nan_to_num(np.clip((e - low) / (high - low), 0, 1))
    image = np.repeat((40 + 150 * grey).astype(np.uint8)[..., None], 3, axis=2)
    if decoded is None:
        image[original] = KEPT
    else:
        image[original & decoded] = KEPT
        image[original & ~decoded] = LOST
        image[~original & decoded] = NEW
    image[outline(plume)] = 255
    return Image.fromarray(image).resize((600, 600), Image.NEAREST)


def task(row: dict[str, str]) -> list[dict]:
    with np.load(HERE / row["npz_path"]) as patch:
        target, bg, plume = patch["target"], patch["bg"], patch["plume"]

    # The sign and the threshold are fitted on the original and kept.
    sign, threshold = fit(target, bg, plume)
    e = enhancement(target, bg, sign)
    original = e > threshold
    before = iou(original, plume)
    figures = HERE / "png" / row["id"]
    shutil.rmtree(figures, ignore_errors=True)
    figures.mkdir(parents=True)
    detections(e, plume, original).save(figures / "original.png", optimize=True)

    spec = ArraySpec(target.shape, target.dtype)
    rows = []
    for make in makers():
        for dn in RMS:
            config = make(Budget(tau=dn))
            if not config.supports(spec):
                continue
            decoded, size = compress(config, target, spec)
            squared = np.sum(np.square(decoded - target.astype(np.float64)))
            decoded_bg = []
            for x in bg:
                values, n = compress(config, np.ascontiguousarray(x), spec)
                decoded_bg.append(values)
                size += n
                squared += np.sum(np.square(values - x.astype(np.float64)))
            detection = enhancement(decoded, np.stack(decoded_bg), sign) > threshold
            image = detections(e, plume, original, detection)
            image.save(figures / f"{config.id}.png", optimize=True)
            rows.append(
                {
                    "id": row["id"],
                    "sensor": row["sensor"],
                    "configuration": config.id,
                    "codec": config.id.split("-tau")[0],
                    "rms_bound_dn": dn,
                    "rmse_dn": np.sqrt(squared / (target.size + bg.size)),
                    "compression_ratio": (target.nbytes + bg.nbytes) / size,
                    "delta_iou": iou(detection, plume) - before,
                }
            )
    return rows


def preview(path: Path) -> None:
    """The enhancement of the patch the detector finds best, its mask outlined."""
    from PIL import Image

    from earthcompress.build import colour

    with np.load(HERE / "npz" / "methane-s2-05.npz") as patch:
        target, bg, plume = patch["target"], patch["bg"], patch["plume"]
    e = enhancement(target, bg, fit(target, bg, plume)[0])
    low, high = np.nanpercentile(e, (2, 99.5))
    image = colour(np.nan_to_num(np.clip((e - low) / (high - low), 0, 1)), "magma")
    image[outline(plume)] = 255
    Image.fromarray(image).resize((600, 600), Image.NEAREST).save(path, optimize=True)


def main() -> None:
    with (HERE / "manifest.csv").open(newline="") as stream:
        patches = list(csv.DictReader(stream))
    fetch(HERE, [row["npz_path"] for row in patches])
    run(task, patches, HERE / "results.csv")
    preview(HERE / "preview.png")


if __name__ == "__main__":
    main()
