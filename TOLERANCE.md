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

For integer corpora, budgets round down to whole steps of `scale`, the value of one step of the stored integers, taking the largest `scale` in the corpus. A level below one step does not exist for that corpus. For floating-point corpora, `tau` is used as stated.

Where the uncertainty is a distribution, the figure used is the one that applies to a single element: the vertical accuracy of a DEM, the noise of a radiometer, the ensemble spread of a reanalysis, or the detection threshold of a retrieval.

## 2. Budgets

`tau` in native units. For integer corpora, the number of steps of the largest `scale` is in brackets. `n/a` means the level falls below one step.

| corpus | unit | dtype | `scale` | `sigma` | `conservative` | `matched` | `aggressive` |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `era5-tcc-1h` | fraction | uint16 | 2^-15 | 0.05 | 0.009979248046875 (327) | 0.024993896484375 (819) | 0.04998779296875 (1638) |
| `era5-u10-1h` | m/s | uint16 | 2^-10 | 0.5 | 0.099609375 (102) | 0.25 (256) | 0.5 (512) |
| `era5-t2m-1h` | K | uint16 | 2^-9 | 0.5 | 0.099609375 (51) | 0.25 (128) | 0.5 (256) |
| `era5-msl-1h` | Pa | uint16 | 2^-2 | 50 | 10 (40) | 25 (100) | 50 (200) |
| `era5-tp-1h` | m | uint16 | 2^-21 to 2^-19 | 1e-4 | 1.9073486328125e-05 (10) | 4.9591064453125e-05 (26) | 9.918212890625e-05 (52) |
| `cop-dem-glo30` | m | float32 | | 4 | 0.8 | 2 | 4 |
| `emit-l2a-285` | reflectance | float32 | | 1.5e-3 | 3e-4 | 7.5e-4 | 1.5e-3 |
| `l8-oli-8` | DN | uint16 | 1 | 50 | 10 (10) | 25 (25) | 50 (50) |
| `l8-oli-pan` | DN | uint16 | 1 | 50 | 10 (10) | 25 (25) | 50 (50) |
| `l8-tirs-2` | DN | uint16 | 1 | 11 | 2 (2) | 5 (5) | 11 (11) |
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

Sources of `sigma`: Sentinel-2 MSI noise is about 13 DN at reflectance 0.2; OLI about 50 DN at 0.3; EMIT about 1.5e-3 reflectance at 0.3; TIRS has a 0.05 K noise-equivalent temperature difference, which is 11 DN for B11 at 250 K, its most sensitive band, and more DN at warmer pixels; GLO-30 has 4 m LE90 vertical accuracy; ERA5 figures are ensemble spread, except precipitation, where 0.1 mm is the wet-hour threshold this benchmark uses; IMERG uses its 0.2 mm/hr detection threshold. For the eight-bit Landsat corpora, `sigma` is one DN, the quantisation of the product rather than its noise, so only `aggressive` exists.

## 3. Corpora with no near-lossless point

These corpora are measured in lossless mode only.

| corpus | reason |
| --- | --- |
| `esa-wc-v200` | Land-cover class codes are unordered: 95 is mangrove, 100 is moss. An error of one gives a different class. |
| `tessera-v2-codes` | Embedding codes; the effect of an error on downstream tasks is not measured. |
| `tessera-v2-scales` | A scale error multiplies all 128 dimensions of a pixel; the effect on downstream tasks is not measured. |
| `alphaearth-v1-64` | Embedding codes; the effect of an error on downstream tasks is not measured. |
| `clay-embeddings` | Embeddings; the effect of an error on downstream tasks is not measured. |
| `goes-abi-16` | Each band has its own `scale` and mixes reflectance factor with brightness temperature, so one budget in native units does not apply to the whole array. |
| `s1-grd-iw-2` | No per-element uncertainty of the linear backscatter is established. |

## 4. Pending

| corpus | status |
| --- | --- |
| all | The sources of `sigma` above need references. |

## 5. What this does not settle

A budget from the uncertainty of a product says whether the decoded array still represents the measurement as well as the original. It does not say whether an analysis gives the same result.

An error below the noise can still be correlated with the signal, and a derived quantity can amplify it. A budget of 2 DN on two similar reflectance bands allows a larger relative error in their normalised difference than in either band, and 2 m per cell on a DEM allows up to 4 m of error in the height difference between neighbours.

On precipitation, the damaging error is often whether a cell rains at all. In the prototype, on IMERG at a bound of 0.05 mm/hr, all 41.0 million exact zeros survived and 690,198 light-rain values at or below the bound decoded as zero. The `zero` promise protects exact zeros, not light rain.

Choosing a budget for a pipeline means measuring that pipeline, as in Section 9 of `PROTOCOL.md`.
