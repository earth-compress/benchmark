# Tolerance

The error budget each dataset can afford, and why.

A near-lossless configuration declares one budget, `tolerance`, as a maximum
absolute error per element in the native units of the sample. This document
sets the default budget for every corpus in the benchmark. It is the number a
near-lossless sweep starts from, not a licence: a budget that is right for
storage may still be wrong for a particular downstream task, and section 5
says how to check.

## 1. How the budget is chosen

Every value in these corpora already carries an error before any codec touches
it: the instrument's noise, the model's uncertainty, the resampling that put it
on its grid. Compression adds a second, independent error on top. The two add
in quadrature, so a compression error of `sigma / 5` against a product
uncertainty of `sigma` raises the total by

```text
sqrt(sigma^2 + (sigma/5)^2) / sigma = 1.02
```

two percent. That is the rule used here: **`tolerance` is at most one fifth of
the product's own uncertainty**, rounded down to a round number of native
units. At that budget the compressed data is, for practical purposes, as
accurate as the data that went in.

The budget is therefore not a free parameter. It follows from two published
numbers:

```text
headroom = product uncertainty / quantisation step
```

`quantisation step` is what one native unit is worth. `headroom` is how many
steps of slack the producer left. A product stored far below its own
uncertainty has a large headroom and can afford a real budget; a product
stored at its own noise floor has none, and such a corpus gets no
near-lossless point at all. The two extremes are both present in this benchmark: ERA5 2 m
temperature is stored in hundredths of a kelvin against an uncertainty near
half a kelvin, a headroom of about fifty, while GOES ABI already quantises each
band to about half its own noise-equivalent temperature difference.

Where the producer's uncertainty is a distribution rather than a bound, the
figure used is the one that governs a single element: the vertical accuracy of
a DEM, the noise-equivalent difference of a radiometer, the speckle of a single
SAR pixel, the ensemble spread of a reanalysis.

## 2. Default budgets

`tolerance` is in native units. "At that budget" states what the error means
physically, and "sits under" names the uncertainty it was measured against.

### Reanalysis and model output

| corpus | native unit | `tolerance` | at that budget | sits under |
| --- | --- | ---: | --- | --- |
| `era5-t2m-1h` | 0.01 K | 10 | 0.1 K | ERA5 ensemble spread in 2 m temperature, around 0.5 K over land |
| `era5-msl-1h` | 1 Pa | 10 | 10 Pa (0.1 hPa) | ERA5 spread in mean sea-level pressure, around 50 Pa |
| `era5-u10-1h` | 0.01 m/s | 10 | 0.1 m/s | ERA5 spread in 10 m wind, around 0.5 m/s |
| `era5-tcc-1h` | 1e-4 fraction | 100 | 0.01 cloud fraction | ERA5 cloud-cover bias, of order 0.05 |
| `era5-tp-1h` | 0.002 mm | 5 | 0.01 mm | the 0.1 mm below which an hourly accumulation is not a measurement |

ERA5 packs each GRIB field to 16 bits and the archive republishes it as
`float32`, so these corpora store the packed integers. The headroom is large
because the packing resolution was chosen for the field's range, not for its
uncertainty.

### Precipitation

| corpus | native unit | `tolerance` | at that budget | sits under |
| --- | --- | ---: | --- | --- |
| `imerg-pcp-12` | 0.01 mm/hr | 2 | 0.02 mm/hr | the 0.2 mm/hr detection threshold of IMERG |

Precipitation is the one quantity here where an absolute bound is close to the
wrong instrument. The field is mostly exact zeros, and the interesting error is
not the magnitude of a rain rate but whether a cell rains at all: a budget that
turns a trace into zero, or zero into a trace, has done damage no `max_abs_error`
will show. The budget above is deliberately an order of magnitude below the
detection threshold, and section 4 requires zeros to survive exactly.

### Elevation

| corpus | native unit | `tolerance` | at that budget | sits under |
| --- | --- | ---: | --- | --- |
| `cop-dem-glo30` | 1 m | 1 | 1 m | the 4 m LE90 vertical accuracy of GLO-30 |

The published COG is `float32` and the corpus rounds it to whole metres, so one
native unit is already a quarter of the product's accuracy. A budget of 1 m is
the last step that stays inside the rule; 2 m would not.

### Optical and thermal imagery

| corpus | native unit | `tolerance` | at that budget | sits under |
| --- | --- | ---: | --- | --- |
| `s2-l1c-10m-4` | 1e-4 reflectance | 2 | 2e-4 reflectance | Sentinel-2 MSI noise, about 13 DN at a reflectance of 0.2 |
| `s2-l1c-20m-6` | 1e-4 reflectance | 2 | 2e-4 reflectance | as above |
| `s2-l1c-60m-3` | 1e-4 reflectance | 2 | 2e-4 reflectance | as above, and B1/B9/B10 are the noisiest of the three groups |
| `l8-oli-8` | 1 DN (12-bit in `uint16`) | 8 | 1.6e-4 reflectance | OLI noise, about 50 DN at a reflectance of 0.3 |
| `l8-oli-pan` | 1 DN (12-bit in `uint16`) | 8 | 1.6e-4 reflectance | as above |
| `l8-tirs-2` | 1 DN | 4 | about 0.013 K | the 0.05 K NEdT of TIRS B10 |
| `emit-l2a-285` | 1e-4 reflectance | 2 | 2e-4 reflectance | EMIT radiometric noise, about 1.5e-3 reflectance at 0.3 |
| `goes-abi-16` | 1 count | 1 | 0.04 to 0.06 K emissive, 3e-4 reflectance factor | the 0.1 K NEdT of the ABI window bands |

GOES ABI is the instructive case. The per-band scales in the manifest are
3.1746e-4 reflectance factor per count for C01–C06 and 0.013 to 0.061 K per
count for C07–C16, so one count is already about half the NEdT of the emissive
bands. A budget of 2 counts would exceed the instrument's own noise on those
bands, which is why this corpus gets 1 and not more. It also carries two
unrelated physical quantities in one array, so a budget in counts means a
different physical error per plane; 1 count is the only value that is defensible
for every plane at once.

### Eight-bit imagery

| corpus | native unit | `tolerance` | at that budget | sits under |
| --- | --- | ---: | --- | --- |
| `lm-mss-4` | 1 DN (8-bit) | 1 | 1/255 of range | nothing: see below |
| `l5-tm-6` | 1 DN (8-bit) | 1 | 1/255 of range | nothing |
| `l5-tm-tir` | 1 DN (8-bit) | 1 | 1/255 of range | nothing |
| `l7-etm-6` | 1 DN (8-bit) | 1 | 1/255 of range | nothing |
| `l7-etm-tir-2` | 1 DN (8-bit) | 1 | 1/255 of range | nothing |
| `l7-etm-pan` | 1 DN (8-bit) | 1 | 1/255 of range | nothing |

These products were quantised to eight bits because eight bits was roughly what
the instrument could resolve, so the headroom is about one and the rule gives
no budget at all. The single step of 1 DN is listed because it is the smallest
measurable near-lossless point and the sweep needs somewhere to start, not
because it is free: it doubles the quantisation error of the product. Read these
rows as a lossless benchmark with one near-lossless point attached.

### Synthetic aperture radar

| corpus | native unit | `tolerance` | at that budget | sits under |
| --- | --- | ---: | --- | --- |
| `s1-grd-iw-2` | 0.01 dB | 25 | 0.25 dB | single-pixel speckle in IW GRD, about 2 dB |

The largest headroom in the benchmark. Earth Engine publishes the decibels as
`float32` and the corpus stores hundredths of a decibel, two orders of
magnitude below the speckle that dominates any single pixel. A budget of
0.25 dB is about a ninth of that speckle and is still well inside the rule.

## 3. Corpora with no near-lossless budget

Three corpora are measured in lossless mode only, and are not offered a
near-lossless configuration at any tolerance. This is not caution, it is
arithmetic: there is no error in these arrays that is small enough to be
harmless.

| corpus | why |
| --- | --- |
| `esa-wc-v200` | The values are land-cover class codes. An error of 1 does not make the class slightly wrong, it makes it a different class, and the codes are not ordered: 95 is mangrove and 100 is moss. `max_abs_error` is meaningless here; the metric would be the fraction of relabelled pixels. |
| `tessera-v2-128` | Planes 0–127 hold `int8` embedding codes, planes 128–131 hold the four little-endian bytes of a per-pixel `float32` scale. An error of 1 in an exponent byte scales that pixel's whole embedding by a factor of two. No single budget can cover both kinds of plane, so the corpus admits none. A codec that treats the scale planes separately could declare a budget on the code planes alone, and the protocol would then need a per-plane budget it does not currently have. |
| `alphaearth-v1-64` | The producer already quantised the embedding to `int8`, so one native unit is 1/254 of the full range and the headroom is one. A budget of 1 LSB is measurable and may well be harmless, but "harmless" for an embedding is a statement about a downstream task, not about the array, and we have not measured it. Until it is measured this corpus stays lossless. |

## 4. Rules that apply to every budget

**NoData is exact.** Several corpora use an in-range sentinel: DN 0 is fill
throughout the Landsat corpora, `-128` is reserved in `alphaearth-v1-64`, and
the Sentinel-2 corpora carry real empty pixels, up to 43% of a 10 m sample, 47%
at 20 m and 49% at 60 m. A budget that moves a sentinel by one destroys the
only thing that marks the pixel as absent, and a budget that invents a sentinel
in valid data is worse. `tolerance` applies to valid elements only; sentinel
values must round-trip exactly in every mode.

**The budget is declared, never derived.** A configuration may not read its
budget from the sample. The number comes from this document before the run, and
is the same for every sample of the corpus.

**The budget is per element, not per sample.** It bounds the worst element, not
the mean. A configuration that meets `tolerance` on average and misses it on one
pixel has failed that sample.

**Heterogeneous planes take the strictest budget.** Where one array holds more
than one physical quantity, as in `goes-abi-16`, or more than one kind of value,
as in `tessera-v2-128`, the corpus budget is the smallest that is defensible
for any plane in it.

## 5. What this document does not settle

A budget chosen against the product's uncertainty answers one question: does
the compressed array still represent the measurement as well as the original
did. It does not answer whether a given analysis survives, and the two can
differ.

An error below the noise floor can still be correlated with the signal where
white noise is not, and a derived quantity can amplify it: a budget of 1 m on a
DEM is a budget of 1 m per cell on the elevation and rather more than that on
the slope computed from two neighbouring cells. Index arithmetic does the same
to reflectance, since a difference of two near-equal bands subtracts most of the
signal and keeps all of the error.

So these budgets are the defaults for the rate side of the benchmark, where the
question is how many bits a given fidelity costs. Choosing a budget for a
pipeline means measuring that pipeline: run the analysis on the original and on
the decoded array and compare the outputs, rather than the arrays. Where we have
done that, it will be recorded here with the task it was measured on.
