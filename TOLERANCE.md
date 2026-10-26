# Tolerance

The error budgets of each corpus for near-lossless configurations, and where they come from.

A near-lossless configuration declares `tau`, a maximum absolute error per element in the native unit of the sample. These budgets make ratios comparable at equal fidelity. They do not recommend a fidelity for any use. See [PROTOCOL.md](PROTOCOL.md) v1.0.

## 1. The rule

Data already carry an uncertainty `sigma` before compression: instrument noise, retrieval error, or model spread. If compression adds an independent error of `sigma / k`, the two add in quadrature and the total error becomes `sigma · sqrt(1 + 1/k²)`. The three levels set `k` to 5, 2, and 1:

| level | `tau` | total error | increase |
| --- | --- | --- | ---: |
| `conservative` | `sigma / 5` | `sigma · sqrt(1 + 1/25) = 1.02 · sigma` | 2% |
| `matched` | `sigma / 2` | `sigma · sqrt(1 + 1/4) = 1.12 · sigma` | 12% |
| `aggressive` | `sigma` | `sigma · sqrt(1 + 1) = 1.41 · sigma` | 41% |

The values of `k` are a choice of this benchmark. Because `tau` is a maximum, most elements have a smaller compression error, so these increases are upper bounds.

For integer corpora, budgets round down to whole steps of `scale`, the distance between two values the stored integers can represent. A level below one step does not exist for that corpus. For floating-point corpora, `tau` is used as stated.

Where the uncertainty is a distribution, the figure used is the one that applies to a single element: the vertical accuracy of a DEM, the noise of a radiometer, the ensemble spread of a reanalysis, or the detection threshold of a retrieval.

## 2. Budgets

`tau` in native units. For integer corpora, the number of `scale` steps is in brackets. `n/a` means the level falls below one step.

| corpus | unit | dtype | `scale` | `sigma` | `conservative` | `matched` | `aggressive` |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `era5-tcc-1h` | fraction | float32 | | 0.05 | 0.01 | 0.025 | 0.05 |
| `era5-u10-1h` | m/s | float32 | | 0.5 | 0.1 | 0.25 | 0.5 |
| `era5-t2m-1h` | K | float32 | | 0.5 | 0.1 | 0.25 | 0.5 |
| `era5-msl-1h` | Pa | float32 | | 50 | 10 | 25 | 50 |
| `era5-tp-1h` | m | float32 | | 1e-4 | 2e-5 | 5e-5 | 1e-4 |
| `cop-dem-glo30` | m | float32 | | 4 | 0.8 | 2 | 4 |
| `emit-l2a-285` | reflectance | float32 | | 1.5e-3 | 3e-4 | 7.5e-4 | 1.5e-3 |
| `l8-oli-8` | DN | uint16 | 1 | 50 | 10 (10) | 25 (25) | 50 (50) |
| `l8-oli-pan` | DN | uint16 | 1 | 50 | 10 (10) | 25 (25) | 50 (50) |
| `l8-tirs-2` | DN | uint16 | 1 | 15.4 † | 3 (3) | 7 (7) | 15 (15) |
| `s2-l1c-10m-4` | DN | uint16 | 1 | 13 | 2 (2) | 6 (6) | 13 (13) |
| `s2-l1c-20m-6` | DN | uint16 | 1 | 13 | 2 (2) | 6 (6) | 13 (13) |
| `s2-l1c-60m-3` | DN | uint16 | 1 | 13 | 2 (2) | 6 (6) | 13 (13) |
| `imerg-pcp-12` | mm/hr | uint16 | 0.01 | 0.2 | 0.04 (4) | 0.1 (10) | 0.2 (20) |
| `lm-mss-4` | DN | uint8 | 1 | 1 | n/a | n/a | 1 (1) |
| `l5-tm-6` | DN | uint8 | 1 | 1 | n/a | n/a | 1 (1) |
| `l5-tm-tir` | DN | uint8 | 1 | 1 | n/a | n/a | 1 (1) |
| `l7-etm-6` | DN | uint8 | 1 | 1 | n/a | n/a | 1 (1) |
| `l7-etm-tir-2` | DN | uint8 | 1 | 1 | n/a | n/a | 1 (1) |
| `l7-etm-pan` | DN | uint8 | 1 | 1 | n/a | n/a | 1 (1) |

† unverified, see Section 4.

Sources of `sigma`: Sentinel-2 MSI noise is about 13 DN at reflectance 0.2; OLI about 50 DN at 0.3; EMIT about 1.5e-3 reflectance at 0.3; TIRS B10 has a 0.05 K noise-equivalent temperature difference; GLO-30 has 4 m LE90 vertical accuracy; ERA5 figures are ensemble spread, except precipitation, where 0.1 mm is the smallest hourly accumulation treated as a measurement; IMERG uses its 0.2 mm/hr detection threshold. For the eight-bit Landsat corpora, one DN is the quantisation of the product, so only `aggressive` exists.

## 3. Corpora with no near-lossless point

These corpora are measured in lossless mode only.

| corpus | reason |
| --- | --- |
| `esa-wc-v200` | Land-cover class codes are unordered: 95 is mangrove, 100 is moss. An error of one gives a different class. |
| `tessera-v2-codes` | The effect of a code error on downstream tasks has not been measured with Section 9 of `PROTOCOL.md`. |
| `tessera-v2-scales` | A scale error multiplies all 128 dimensions of a pixel. Its effect on downstream tasks has not been measured. |
| `alphaearth-v1-64` | One int8 step is the quantisation of the product, and its effect on downstream tasks has not been measured. |
| `clay-embeddings` | The effect of an embedding error on downstream tasks has not been measured. |
| `goes-abi-16` | Each band has its own `scale` and mixes reflectance factor with brightness temperature, so one budget in native units does not apply to the whole array. |
| `s1-grd-iw-2` | No per-element uncertainty for the backscatter in dB has been established. |

## 4. Pending

| corpus | status |
| --- | --- |
| `l8-tirs-2` | `sigma` assumes one DN is about 0.00325 K. The DN-to-kelvin factor for TIRS Collection 2 Level-1 is unconfirmed. |
| `s2-l1c-*`, `emit-l2a-285` | The stored representation depends on the checks listed in `DATASETS.md`. The budgets in native units do not change. |

## 5. What this does not settle

A budget from the uncertainty of a product says whether the decoded array still represents the measurement as well as the original. It does not say whether an analysis gives the same result.

An error below the noise can still be correlated with the signal, and a derived quantity can amplify it. A budget of 2 DN on two similar reflectance bands allows a larger error in their normalised difference, and 2 m per cell on a DEM allows a larger error in the slope between neighbours.

On precipitation, the damaging error is often whether a cell rains at all. On IMERG at a bound of 0.05 mm/hr, all 41.0 million exact zeros survived and 690,198 light-rain values at or below the bound decoded as zero. The `zero` promise protects exact zeros, not light rain.

Choosing a budget for a pipeline means measuring that pipeline, as in Section 9 of `PROTOCOL.md`.
