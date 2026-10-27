"""Median of the IMERG `randomError` field over the cells of the imerg-pcp-12 corpus.

Reads the field from Earth Engine on the grid of each sample, so it needs
`earthengine authenticate` first. Run from the repository root:

    uv run --extra corpus python docs/sigma/imerg_random_error.py
"""

from pathlib import Path

import numpy as np

from earthcompress import build as b
from earthcompress import sources as src
from earthcompress.corpus import load_samples

CORPUS = Path("corpora/imerg-pcp-12")
BAND = "randomError"


def main() -> None:
    ee = src.ee_init()
    errors, rates = [], []
    for sample, row in zip(load_samples(CORPUS), b.read_manifest(CORPUS), strict=True):
        transform = b.parse_transform(row["transform"])
        size = tuple(int(n) for n in row["shape"].split("x")[1:])
        errors.append(
            np.stack(
                [
                    src.ee_pixels(
                        ee.Image(asset).select([BAND]),
                        [BAND],
                        row["crs"],
                        transform,
                        size,
                    )[0]
                    for asset in b.split(row["asset"])
                ]
            ).ravel()
        )
        rates.append((sample.data * sample.scale[0]).ravel())
        print(row["id"], flush=True)
    error, rate = np.concatenate(errors), np.concatenate(rates)
    for name, cells in (("all cells", rate >= 0), ("raining", rate > 0)):
        p10, p50, p90 = np.percentile(error[cells], [10, 50, 90])
        print(
            f"{name:10} {cells.sum():>10}  p10 {p10:.3f}  median {p50:.3f}  p90 {p90:.3f} mm/hr"
        )


if __name__ == "__main__":
    main()
