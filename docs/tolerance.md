# Tolerance

The error budgets each dataset can afford, and where they come from.

A near-lossless configuration declares `tau`, a maximum absolute error per
element in the native unit of the sample. The budgets here exist to make ratios
comparable at equal fidelity, not to recommend a fidelity: anyone applying lossy
compression validates their own budget for their own use. See
[PROTOCOL.md](../PROTOCOL.md) v1.0.

## 1. The rule

Every value already carries an error before any codec touches it, and the two
add in quadrature. A compression error of `sigma / k` against uncertainty
`sigma` raises the total by `sqrt(1 + 1/k²)`:

| level | `tau` | total error raised by |
| --- | --- | ---: |
| `conservative` | uncertainty / 5 | 2% |
| `matched` | uncertainty / 2 | 12% |
| `aggressive` | uncertainty | 41% |

`grid` is the quantisation step of the published data: the distance between two
values the producer can represent. Budgets round **down** to whole grid steps,
which can only make them stricter.

```text
headroom = uncertainty / grid
```

`headroom` is the slack the producer left, and it decides how many levels exist.
Below 5, `conservative` falls under one grid step and does not exist. At 1, only
`aggressive` exists: the producer already quantised to its own noise floor. That
is not a defect of the benchmark, it is the honest answer — such a corpus is a
lossless benchmark with one near-lossless point attached.

Where the uncertainty is a distribution rather than a bound, the figure used is
the one governing a single element: the vertical accuracy of a DEM, the
noise-equivalent difference of a radiometer, the ensemble spread of a
reanalysis, the detection threshold of a retrieval.

## 2. Budgets

`tau` in native units, grid steps in brackets. A dash means the level falls
below one grid step.

| corpus | unit | grid | uncert. | headroom | `conservative` | `matched` | `aggressive` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `era5-tcc-1h` | fraction | 1.526e-05 | 0.05 | 3277x | 0.01 (655) | 0.025 (1638) | 0.05 (3276) |
| `era5-u10-1h` | m/s | 0.000679 | 0.5 | 736x | 0.1 (147) | 0.25 (368) | 0.5 (736) |
| `era5-t2m-1h` | K | 0.0015564 | 0.5 | 321x | 0.1 (64) | 0.25 (160) | 0.5 (321) |
| `era5-msl-1h` | Pa | 0.171875 | 50 | 291x | 10 (58) | 25 (145) | 50 (290) |
| `era5-tp-1h` | mm | 0.00063 | 0.1 | 159x | 0.02 (31) | 0.05 (79) | 0.1 (158) |
| `l8-oli-8` | DN | 1 | 50 | 50x | 10 (10) | 25 (25) | 50 (50) |
| `l8-oli-pan` | DN | 1 | 50 | 50x | 10 (10) | 25 (25) | 50 (50) |
| `l8-tirs-2` | DN | 1 | 15.4 † | 15x | 3 (3) | 7 (7) | 15 (15) |
| `emit-l2a-285` | DN = 1e-4 refl. † | 1 | 15 | 15x | 3 (3) | 7 (7) | 15 (15) |
| `s2-l1c-10m-4` | DN = 1e-4 refl. | 1 | 13 | 13x | 2 (2) | 6 (6) | 13 (13) |
| `s2-l1c-20m-6` | DN = 1e-4 refl. | 1 | 13 | 13x | 2 (2) | 6 (6) | 13 (13) |
| `s2-l1c-60m-3` | DN = 1e-4 refl. | 1 | 13 | 13x | 2 (2) | 6 (6) | 13 (13) |
| `imerg-pcp-12` | mm/hr | 0.01 | 0.2 | 20x | 0.04 (4) | 0.1 (10) | 0.2 (20) |
| `cop-dem-glo30` | m | 1 † | 4 | 4x | — | 2 (2) | 4 (4) |
| `goes-abi-16` | count | 1 | 2 | 2x | — | 1 (1) | 2 (2) |
| `lm-mss-4` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l5-tm-6` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l5-tm-tir` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l7-etm-6` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l7-etm-tir-2` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l7-etm-pan` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |

† unverified, see section 4.

Uncertainties: Sentinel-2 MSI noise is about 13 DN at reflectance 0.2; OLI about
50 DN at 0.3; EMIT about 1.5e-3 reflectance at 0.3; TIRS B10 has a 0.05 K NEdT;
ABI window bands 0.1 K; GLO-30 is 4 m LE90; ERA5 figures are ensemble spread,
except precipitation where it is the 0.1 mm below which an hourly accumulation
is not a measurement; IMERG is its 0.2 mm/hr detection threshold.

Three results worth reading off the table:

**ERA5 has the largest headroom in the benchmark**, 159x to 3277x, because its
packing resolution was chosen for each field's range, not its uncertainty. The
grids are measured, not assumed: `range/grid` comes out at 65 536 exactly for
cloud cover, and 62 661, 66 016, 59 474 and 38 593 for the others — the 16-bit
GRIB packing underneath ARCO's float32.

**GOES ABI has almost none.** One count is already about half the NEdT of the
window bands, so `conservative` does not exist and `aggressive` is two counts.
The array also holds a reflectance factor and a brightness temperature together,
so a budget in counts means a different physical error per plane; these are the
strictest defensible for any plane.

**The eight-bit Landsat corpora have one level.** Headroom is one, so only
`aggressive` exists, at a single grid step, and it doubles the product's own
quantisation error. The six are not interchangeable despite sharing a budget:
MSS, TM and ETM+ differ in signal-to-noise, ground sampling and era, and the SNR
is what fixes a budget. They share a budget because they share a bit depth.

## 3. Corpora with no near-lossless point

Lossless mode only, at any budget.

| corpus | why |
| --- | --- |
| `esa-wc-v200` | Land-cover class codes, unordered: 95 is mangrove, 100 is moss. An error of one makes a different class, so `max_abs_error` means nothing here. The corpus stores the published codes. |
| `tessera-v2-128` | Planes 0–127 are int8 embedding codes; planes 128–131 are the four little-endian bytes of a per-element float32 scale. An error of one in an exponent byte scales that element's embedding by two. No single budget covers both. |
| `alphaearth-v1-64` | Already int8 from the producer, so one grid step is 1/254 of the range and headroom is one. A one-step budget may be harmless, but harmlessness for an embedding is a claim about a task, and PROTOCOL.md section 9 has not been run on it. |

## 4. Unverified and pending

| corpus | status |
| --- | --- |
| `era5-*` (5) | The grids above are measured, but **the corpora do not yet use them.** They were built with a fixed scale we chose — 0.01 K, 1 Pa, 0.01 m/s, 1e-4, 2e-6 m — between 3.2x and 14.7x coarser than the producer's, discarding 1.67 to 3.88 bits per value. The budgets apply once rebuilt with `scale` and `offset` per time step. Until then their ratios are measured on data we degraded ourselves. |
| `cop-dem-glo30` | Grid unverified. The published COG is float32 and the corpus rounds to whole metres; nobody checked whether those values were already integral. If not, the stored int16 carries up to 0.5 m of our own loss. |
| `emit-l2a-285` | Grid unverified. Its `spec.md` states the product is packed at 1e-4, which would make the int16 exact, but no round-trip check was run. |
| `l8-tirs-2` | Uncertainty unverified: assumes one DN is about 0.00325 K. The DN-to-kelvin factor for TIRS Collection 2 Level-1 is unconfirmed. |
| `s1-grd-iw-2` | **No budget.** Earth Engine delivered decibels as float32 and the corpus quantised to hundredths of a decibel, but the native product is amplitude DN in uint16 — the grid we need is two steps upstream of our own code. Stated once the corpus is rebuilt from the published product. |

The float corpora — `ifs-msl-wind`, `s5p-no2-l2`, `clay-embeddings` — have no
grid, so their budgets are stated in native units directly and some need a
`relative` rather than an `absolute` bound. Added when the corpora are.

## 5. What this does not settle

A budget from the product's uncertainty answers one question: does the
compressed array still represent the measurement as well as the original did. It
does not answer whether an analysis survives.

An error below the noise floor can still be correlated with the signal where
white noise is not, and a derived quantity amplifies it. Two radiative fluxes
compressed at 0.3% and 0.02% relative error, each harmless alone, gave their
difference an 8.0% relative error. A budget of 2 DN on two near-equal
reflectance bands is far more than 2 DN on their normalised difference, and 2 m
per cell on a DEM is more than 2 m on the slope between neighbours.

Precipitation is the case where an absolute bound is closest to the wrong
instrument: the field is mostly exact zeros and the damaging error is whether a
cell rains at all, not by how much. On IMERG at a respected bound of 0.05 mm/hr,
all 41.0 million exact zeros survived and 690,198 light-rain values at or below
the bound decoded as zero. The `zero` promise protects this, not the budget.

So these are the defaults for the rate side of the benchmark. Choosing a budget
for a pipeline means measuring that pipeline, which is PROTOCOL.md section 9.
Where we have run it, the result will be recorded here with its task.
