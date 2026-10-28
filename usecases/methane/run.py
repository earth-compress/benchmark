"""The methane use case, on the patches of build.py.

uv run python usecases/methane/run.py
"""

import csv
from pathlib import Path

import numpy as np

from earthcompress.budgets import budgets_for
from earthcompress.contract import Budget
from earthcompress.spec import ArraySpec
from earthcompress.usecase import configurations, iou, roundtrip, run

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


def task(row: dict[str, str]) -> list[dict]:
    with np.load(HERE / row["npz_path"]) as patch:
        target, bg, plume = patch["target"], patch["bg"], patch["plume"]

    # The sign and the threshold are fitted on the original and kept.
    e = enhancement(target, bg)
    sign = 1.0 if np.nanmean(e[plume]) > np.nanmean(e[~plume]) else -1.0
    threshold = np.nanpercentile(sign * e[~plume], 99.5)
    before = iou(sign * e > threshold, plume)

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


def main() -> None:
    with (HERE / "manifest.csv").open(newline="") as stream:
        patches = list(csv.DictReader(stream))
    run(task, patches, HERE / "results.csv")


if __name__ == "__main__":
    main()
