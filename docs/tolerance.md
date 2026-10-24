# Tolerance

The error budgets each dataset can afford, and where they come from.

A near-lossless configuration declares a budget, `tau`, as a maximum absolute
error per element in the native unit of the sample. This document derives three
budgets per corpus from the product's own published uncertainty. They exist to
make ratios comparable at equal fidelity, not to recommend a fidelity: anyone
applying lossy compression validates their own budget for their own use, and
section 6 says how.

## 1. How a budget is derived

Every value in these corpora already carries an error before any codec touches
it: the instrument's noise, the model's uncertainty, the resampling that put it
on its grid. Compression adds a second, independent error, and the two add in
quadrature. A compression error of `sigma / k` against a product uncertainty of
`sigma` raises the total by `sqrt(1 + 1/k²)`:

| level | `tau` | total error raised by | what it means |
| --- | --- | ---: | --- |
| `conservative` | uncertainty / 5 | 2% | the compressed data is as accurate as what went in |
| `matched` | uncertainty / 2 | 12% | a visible but modest contribution |
| `aggressive` | uncertainty | 41% | the compression error equals the instrument's own |

Three levels rather than one, because a single budget gives a point and three
trace the front. A codec whose advantage shows up only at `aggressive` has not
shown an advantage.

Every budget is rounded **down** to a whole number of grid steps. Rounding down
can only make a budget stricter, so it never violates the rule.

## 2. Grid and headroom

`grid` is the quantisation step of the published data in its native unit: the
distance between two values the producer can represent. It is the unit every
budget is expressed in, and it sets the floor on what is measurable.

```text
headroom = product uncertainty / grid
```

`headroom` is how many steps of slack the producer left. It decides how many of
the three levels exist:

- Large headroom: all three levels are many grid steps wide, and the sweep has
  room to show a rate-distortion front.
- `headroom < 5`: the `conservative` level falls below one grid step and does
  not exist. The budget would be smaller than the smallest representable
  difference.
- `headroom = 1`: only `aggressive` exists, at one grid step. The producer
  already quantised the data to its own noise floor.

The last case is not a defect of the benchmark; it is the honest answer. A
corpus with no headroom is a lossless benchmark with one near-lossless point
attached.

Where the producer's uncertainty is a distribution rather than a bound, the
figure used is the one that governs a single element: the vertical accuracy of a
DEM, the noise-equivalent difference of a radiometer, the ensemble spread of a
reanalysis, the detection threshold of a precipitation retrieval.

## 3. Budgets

`tau` is given in native units with the number of grid steps in brackets. A dash
means the level falls below one grid step and does not exist.

### Reanalysis

| corpus | unit | grid | uncertainty | headroom | `conservative` | `matched` | `aggressive` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `era5-t2m-1h` | K | 0.0015564 | 0.5 | 321x | 0.1 (64) | 0.25 (160) | 0.5 (321) |
| `era5-msl-1h` | Pa | 0.171875 | 50 | 291x | 10 (58) | 25 (145) | 50 (290) |
| `era5-u10-1h` | m/s | 0.000679 | 0.5 | 736x | 0.1 (147) | 0.25 (368) | 0.5 (736) |
| `era5-tcc-1h` | fraction | 1.526e-05 | 0.05 | 3277x | 0.01 (655) | 0.025 (1638) | 0.05 (3276) |
| `era5-tp-1h` | mm | 0.00063 | 0.1 | 159x | 0.02 (31) | 0.05 (79) | 0.1 (158) |

The grids are measured, not assumed. ARCO-ERA5 republishes each field as
float32, and the values sit on a grid of `(max - min) / 65535` per field and per
time step, which is the 16-bit GRIB packing underneath: `rango/paso` comes out
at 62 661, 66 016, 59 474, exactly 65 536, and 38 593 for the five fields above.

These are the largest headrooms in the benchmark, and the reason is that ERA5's
packing resolution was chosen for each field's range, not for its uncertainty.

> **The five ERA5 corpora do not yet use these grids.** They were built with a
> fixed scale we chose — 0.01 K, 1 Pa, 0.01 m/s, 1e-4, 2e-6 m — which is between
> 3.2x and 14.7x coarser than the producer's, discarding 1.67 to 3.88 bits per
> value. The budgets above apply once the corpora are rebuilt with `scale` and
> `offset` per time step. Until then their ratios are measured on data we
> degraded ourselves.

### Precipitation

| corpus | unit | grid | uncertainty | headroom | `conservative` | `matched` | `aggressive` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `imerg-pcp-12` | mm/hr | 0.01 | 0.2 | 20x | 0.04 (4) | 0.1 (10) | 0.2 (20) |

Precipitation is where an absolute bound is closest to the wrong instrument. The
field is mostly exact zeros, and the damaging error is not the magnitude of a
rain rate but whether a cell rains at all. On this corpus at a respected bound
of 0.05 mm/hr, all 41.0 million exact zeros survived and 690,198 light-rain
values at or below the bound decoded as zero: the bound held and the number of
raining elements changed. The `zero` promise of the protocol, not the budget, is
what protects this.

### Elevation

| corpus | unit | grid | uncertainty | headroom | `conservative` | `matched` | `aggressive` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cop-dem-glo30` | m | 1 | 4 | 4x | — | 2 (2) | 4 (4) |

With a headroom of four, `conservative` would be 0.8 m, below the grid. The
corpus has two near-lossless levels, not three.

> The grid is **unverified**. The published COG is float32 and the corpus rounds
> it to whole metres; nobody has checked whether those float32 values were
> already integral. If they were not, the stored int16 carries up to 0.5 m of
> our own loss and `exact` is false for this corpus.

### Optical and thermal

| corpus | unit | grid | uncertainty | headroom | `conservative` | `matched` | `aggressive` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `s2-l1c-10m-4` | DN (1e-4 refl.) | 1 | 13 | 13x | 2 (2) | 6 (6) | 13 (13) |
| `s2-l1c-20m-6` | DN (1e-4 refl.) | 1 | 13 | 13x | 2 (2) | 6 (6) | 13 (13) |
| `s2-l1c-60m-3` | DN (1e-4 refl.) | 1 | 13 | 13x | 2 (2) | 6 (6) | 13 (13) |
| `l8-oli-8` | DN | 1 | 50 | 50x | 10 (10) | 25 (25) | 50 (50) |
| `l8-oli-pan` | DN | 1 | 50 | 50x | 10 (10) | 25 (25) | 50 (50) |
| `l8-tirs-2` | DN | 1 | 15.4 | 15x | 3 (3) | 7 (7) | 15 (15) |
| `emit-l2a-285` | DN (1e-4 refl.) | 1 | 15 | 15x | 3 (3) | 7 (7) | 15 (15) |

Uncertainties: the Sentinel-2 MSI noise is about 13 DN at a reflectance of 0.2;
OLI is about 50 DN at 0.3; EMIT is about 1.5e-3 reflectance at 0.3.

> `l8-tirs-2`'s uncertainty is **unverified**: it assumes one DN is about
> 0.00325 K, which puts the 0.05 K NEdT of B10 at 15 steps. The DN-to-kelvin
> factor for TIRS Collection 2 Level-1 has not been confirmed against the
> product specification.

> `emit-l2a-285`'s grid is **unverified**. Its `spec.md` states the product is
> packed at a resolution of 1e-4, which would make the stored int16 exact, but
> no round-trip check was run against the published float32.

### Geostationary

| corpus | unit | grid | uncertainty | headroom | `conservative` | `matched` | `aggressive` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `goes-abi-16` | count | 1 | 2 | 2x | — | 1 (1) | 2 (2) |

The per-band scales in the manifest are 3.1746e-4 reflectance factor per count
for C01–C06 and 0.013 to 0.061 K per count for C07–C16, so one count is already
about half the 0.1 K NEdT of the window bands. Headroom is two, and
`conservative` does not exist.

This corpus also carries two unrelated physical quantities in one array, so a
budget in counts means a different physical error per plane. The budgets above
are the strictest defensible for any plane, which is what the protocol requires.

### Eight-bit imagery

| corpus | unit | grid | uncertainty | headroom | `conservative` | `matched` | `aggressive` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `lm-mss-4` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l5-tm-6` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l5-tm-tir` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l7-etm-6` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l7-etm-tir-2` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |
| `l7-etm-pan` | DN (8-bit) | 1 | 1 | 1x | — | — | 1 (1) |

These products were quantised to eight bits because eight bits was roughly what
the instrument could resolve. Headroom is one, so only `aggressive` exists, at a
single grid step, and it doubles the quantisation error of the product. Read
these rows as a lossless benchmark with one near-lossless point attached.

The six are not interchangeable even though their budgets match: MSS, TM and
ETM+ have different signal-to-noise, different ground sampling and different
acquisition eras, and the SNR is what fixes the budget. They share a budget
because they share a bit depth, not because they are the same measurement.

## 4. Corpora with no near-lossless point

Lossless mode only, at any budget. Not caution: there is no error in these
arrays small enough to be harmless.

| corpus | why |
| --- | --- |
| `esa-wc-v200` | Land-cover class codes. An error of one does not make a class slightly wrong, it makes it a different class, and the codes are unordered: 95 is mangrove, 100 is moss. `max_abs_error` is not a meaningful statistic here. The 50 samples contain 11 distinct codes with a GCD of 5, so the corpus stores dense indices and the symbol table, which also removes the factor of two wasted by storing 11 symbols in 8 bits. |
| `tessera-v2-128` | Planes 0–127 hold int8 embedding codes; planes 128–131 hold the four little-endian bytes of a per-element float32 scale. An error of one in an exponent byte scales that element's whole embedding by a factor of two. No single budget covers both kinds of plane. |
| `alphaearth-v1-64` | Already quantised to int8 by the producer, so one grid step is 1/254 of the full range and headroom is one. A budget of one step may well be harmless, but "harmless" for an embedding is a claim about a task, not about the array, and the task validation of PROTOCOL.md section 9 has not been run on it. |

## 5. Corpora with no budget yet

| corpus | status |
| --- | --- |
| `s1-grd-iw-2` | Earth Engine delivered decibels as float32 and the corpus quantised them to hundredths of a decibel. The native product is amplitude DN in uint16, so the grid we would need is two steps upstream of our own code. No budget is stated until the corpus is rebuilt from the published product, in a unit the producer distributes. |

The float corpora of the benchmark — `ifs-msl-wind`, `s5p-no2-l2`,
`clay-embeddings` — have no grid, so their budgets are stated in native units
directly and some of them need a `relative` rather than an `absolute` bound.
Those rows are added when the corpora are.

## 6. What this document does not settle

A budget derived from the product's uncertainty answers one question: does the
compressed array still represent the measurement as well as the original did. It
does not answer whether a given analysis survives, and the two differ.

An error below the noise floor can still be correlated with the signal where
white noise is not, and a derived quantity amplifies it. Two radiative fluxes
compressed at 0.3% and 0.02% relative error, each harmless alone, gave their
difference an 8.0% relative error. A budget of 2 DN on two near-equal
reflectance bands is far more than 2 DN on their normalised difference, and a
budget of 2 m per cell on a DEM is more than 2 m on the slope between two
neighbouring cells.

So these are the defaults for the rate side of the benchmark, where the question
is how many bits a given fidelity costs. Choosing a budget for a pipeline means
measuring that pipeline, which is the separate protocol in PROTOCOL.md section
9. Where we have run it, the result will be recorded here with the task it was
measured on.
