"""The methane use case, on the patches of build.py.

uv run python usecases/methane/run.py
"""

import csv
from pathlib import Path

import numpy as np

from earthcompress.budgets import budgets_for
from earthcompress.contract import Budget
from earthcompress.spec import ArraySpec
from earthcompress.usecase import configurations, fetch, iou, roundtrip, run

HERE = Path(__file__).resolve().parent
CORPUS = {"s2": "s2-l1c-20m-6", "l89": "l8-oli-8"}
UNIT = {"s2": 1.0, "l89": 2e-5}
"""Value of one DN of the corpus in the stored unit of the patches."""


def budgets(sensor: str) -> list[Budget]:
    return [
        Budget(tau=budget.tau * UNIT[sensor], level=budget.level)
        for budget in budgets_for(CORPUS[sensor]).values()
    ]


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


def task(row: dict[str, str]) -> list[dict]:
    with np.load(HERE / row["npz_path"]) as patch:
        target, bg, plume = patch["target"], patch["bg"], patch["plume"]

    # The sign and the threshold are fitted on the original and kept.
    sign, threshold = fit(target, bg, plume)
    before = iou(enhancement(target, bg, sign) > threshold, plume)

    spec = ArraySpec(target.shape, target.dtype)
    rows = []
    for config in configurations(budgets(row["sensor"]), spec):
        decoded = roundtrip(config, target, spec)
        decoded_bg = np.stack(
            [roundtrip(config, np.ascontiguousarray(x), spec) for x in bg]
        )
        after = iou(enhancement(decoded, decoded_bg, sign) > threshold, plume)
        rows.append(
            {
                "id": row["id"],
                "sensor": row["sensor"],
                "configuration": config.id,
                "family": config.family,
                "budget_level": config.budget.level,
                "tau": config.budget.tau,
                "delta_iou": after - before,
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
    inside = np.pad(
        plume[1:-1, 1:-1]
        & plume[:-2, 1:-1]
        & plume[2:, 1:-1]
        & plume[1:-1, :-2]
        & plume[1:-1, 2:],
        1,
    )
    image[plume & ~inside] = 255
    Image.fromarray(image).resize((600, 600), Image.NEAREST).save(path, optimize=True)


def main() -> None:
    with (HERE / "manifest.csv").open(newline="") as stream:
        patches = list(csv.DictReader(stream))
    fetch(HERE, [row["npz_path"] for row in patches])
    run(task, patches, HERE / "results.csv")
    preview(HERE / "preview.png")


if __name__ == "__main__":
    main()
