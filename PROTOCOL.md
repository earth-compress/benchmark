# EarthCompress Measurement Protocol v2.0

- Status: Draft

EarthCompress measures compression of Earth observation and environmental
arrays under three fidelity modes: lossless, near-lossless and lossy. This
protocol defines the starting representation, what each mode promises and how
that promise is verified, the error budgets, the corpus layout, the timing
procedure, the metrics, and which comparisons between results are valid.

It measures one thing: what a codec costs and what it gives up on an array held
in memory. It does not measure storage layout, network transfer, partial reads,
or whether a given analysis survives compression. Section 9 defines a separate
protocol for the last of these.

## 1. The starting representation

A compression ratio is only meaningful against a stated starting point, and the
starting point is the first thing most published numbers get wrong. A float32
array republished from a 16-bit source carries 16 bits of padding, and
recovering that padding is not compression.

**The starting representation is the one with the fewest bits that reproduces
the published data exactly.**

For each dataset, in order:

1. Take the data as the producer publishes it, whatever its type.
2. Ask whether an integer array and a `(scale, offset)` pair reproduce it bit
   for bit.
3. If they do, store the integers and record `scale` and `offset`. If they do
   not, store the published floating-point array unchanged.

Step 2 is a test, not a judgement:

```python
back = (codes.astype(published.dtype) * scale + offset).astype(published.dtype)
assert np.array_equal(back, published)
```

This rule has one property that matters more than its simplicity: **the
benchmark never introduces a lossy step of its own.** Whatever the producer
quantised is counted; nothing the benchmark quantised is. Whether a corpus is
integer or floating point is therefore a measured result, not a design choice.

### 1.1 Grid

`grid` is the quantisation step of the published data, in the native unit of
the sample. It is the distance between two representable values, and it is the
unit in which every error budget is expressed.

An integer corpus has `grid = scale`. A floating-point corpus whose values fall
on no common step has no grid, and its budgets are stated in native units
directly.

The grid is a property of the producer, not of the benchmark, and it is not
always what a product's documentation implies. ERA5 is the instructive case:
ARCO-ERA5 republishes each field as float32, and the values sit on a grid of
`(max - min) / 65535` per field and per time step, the signature of the 16-bit
GRIB packing underneath. For 2 m temperature that grid is 0.0015564 K, not the
0.01 K a round number would suggest. A corpus built on 0.01 K discards 2.68
bits per value that the producer did transmit, and reports a ratio inflated by
its own loss.

Where the grid varies across a sample, as it does for every ERA5 field, `scale`
and `offset` are stored per slice, not per corpus. A single scale for a whole
corpus cannot be exact.

### 1.2 Exactness

Every corpus records, per sample, whether its stored representation reproduces
the published data bit for bit. This is the `exact` column of the manifest, and
`build.py` asserts it at build time. A corpus that cannot assert it states in
its `spec.md` what was lost and why.

## 2. Fidelity modes

A configuration declares a **mode**. The mode determines what the configuration
promises and therefore what the benchmark verifies. Modes are not points on a
scale; they are different claims.

| mode | promises | verified per sample |
| --- | --- | --- |
| `lossless` | `structure`, `determinism`, `exactness` | decoded bytes equal input bytes |
| `near-lossless` | `structure`, `determinism`, `bound`, `sentinel`, `zero` | the bound holds on every element |
| `lossy` | `structure`, `determinism` | nothing beyond structure |

The promises:

- **`structure`** — the decoded array has the shape and dtype of the input.
- **`determinism`** — encoding the same input twice produces the same bytes,
  and decoding the same bytes twice produces the same array. On accelerated
  decoders, the same bytes on a different device produce the same array.
- **`exactness`** — the decoded bytes equal the input bytes in C order. The
  comparison is on bytes, not values, so a differing representation of an equal
  value is a failure.
- **`bound`** — see section 2.1.
- **`sentinel`** — every NoData or fill value decodes to itself, in its own
  position, and no sentinel value appears where the input had a valid one.
- **`zero`** — every exact zero in the input decodes to exact zero.

A configuration that breaks a promise it made has failed that sample. The row
is recorded with `fidelity_ok = false` and empty measurements, and is excluded
from aggregation.

Three of these promises exist because published compressors broke them. Section
6 gives the checks and the precedents.

### 2.1 Bound

A near-lossless configuration declares a bound of one of three kinds. There is
no standard definition of "relative" in this literature and the differences
change results, so the kind is always named.

```text
absolute            |x - x̂| <= tau
relative            |x - x̂| <= tau · |x|           → forces exact zeros
range-relative      |x - x̂| <= tau · (max x - min x)
```

`relative` is satisfied at `x = 0` only when `x̂ = 0`, so it carries zero
preservation by construction. `range-relative` does not, and it is the kind
that SZ3 and EBCC expose under the name "relative". **This protocol does not
accept a `range-relative` bound as a near-lossless claim**, because its bound
depends on the content of whatever block the codec happened to see. A
configuration that only offers one is measured in `lossy` mode.

Every bound carries the equivalence clause:

```text
|x - x̂| <= tau   OR   x ≡ x̂
```

Without it a correctly preserved infinity violates its own bound, because
`∞ - ∞` is NaN under IEEE 754.

`absolute` bounds suit fields whose range is bounded and whose uncertainty is
roughly uniform across it: reflectance, elevation, temperature. `relative`
bounds suit fields spanning orders of magnitude: precipitation, trace
concentrations, biomass.

## 3. Error budgets

### 3.1 Where a budget comes from

Every value in these corpora already carries an error before any codec touches
it. Compression adds a second, independent one, and the two add in quadrature.
A compression error of `sigma / k` against a product uncertainty of `sigma`
raises the total error by `sqrt(1 + 1/k²)`.

Each corpus therefore has three budgets, derived from the product's own
published uncertainty:

| level | `tau` | total error raised by |
| --- | --- | ---: |
| `conservative` | uncertainty / 5 | 2% |
| `matched` | uncertainty / 2 | 12% |
| `aggressive` | uncertainty | 41% |

Three levels rather than one, because a single budget gives a point and three
trace the front: a codec whose advantage appears only at `aggressive` has not
shown an advantage. The names state what is being done; at `aggressive` the
compression error equals the instrument's own.

`docs/tolerance.md` records the uncertainty used for each corpus, its source,
and the resulting three budgets in grid units.

A budget below one grid step is not measurable, and a corpus whose
`conservative` budget rounds to zero grid steps has no near-lossless point at
that level.

### 3.2 Rules on budgets

**A budget is declared, never derived.** A configuration may not read its
budget, or any part of it, from the sample. The budget comes from
`docs/tolerance.md` before the run and is identical for every sample of the
corpus. This rule exists because EBCC and SZ3 convert a relative bound
internally to `tau · (max x - min x)` and that range differs per chunk, so they
silently apply a different bound to each chunk of the same dataset.

**A budget bounds the worst element, not the mean.** A configuration that meets
its budget on average and misses it on one element has failed that sample.

**NoData is outside the budget.** `tau` applies to valid elements only.
Sentinel values round-trip exactly in every mode, including `lossy`.

**Heterogeneous planes take the strictest budget.** Where one array holds more
than one physical quantity, as `goes-abi-16` does with a reflectance factor and
a brightness temperature, or more than one kind of value, as `tessera-v2-128`
does with embedding codes and the bytes of a float32 scale, the corpus budget
is the smallest that is defensible for any plane in it.

### 3.3 Corpora with no near-lossless point

A corpus is lossless-only when no budget above zero is meaningful on it, not
when one is merely risky. Three cases arise:

- **Categorical values.** `esa-wc-v200` holds land-cover class codes. An error
  of one does not make a class slightly wrong, it makes it a different class,
  and the codes are unordered: 95 is mangrove, 100 is moss. `max_abs_error` is
  not a meaningful statistic here; the metric would be the fraction of
  relabelled elements.
- **Values that are not quantities.** `tessera-v2-128` stores the four
  little-endian bytes of a per-element float32 scale in planes 128–131. An
  error of one in an exponent byte scales that element's whole embedding by a
  factor of two.
- **Unmeasured downstream effect.** `alphaearth-v1-64` is already quantised to
  int8 by its producer, so one grid step is 1/254 of the full range. A budget
  of one step may well be harmless, but "harmless" for an embedding is a claim
  about a task, not about the array, and section 9 has not been run on it.

## 4. Corpus layout

```text
corpora/<corpus-id>/
├── spec.md              what the samples are, their native unit and grid, licence
├── build.py             generates the samples and asserts exactness
├── manifest.csv         the index: one row per sample
├── npz/<sample>.npz.zst the sample
├── png/<sample>.png     preview, never measured
├── results.csv          generated by a run, never an input
└── environment.json     generated by a run
```

### 4.1 Sample files

A sample is a NumPy `.npz` archive compressed with Zstandard. The archive holds
named arrays:

| array | required | description |
| --- | --- | --- |
| `data` | yes | the sample, in the starting representation of section 1 |
| `scale` | when the grid is not 1 | per-slice or scalar scale |
| `offset` | when the grid is not 1 | per-slice or scalar offset |
| `symbols` | for categorical corpora | the value of each stored index |
| `sentinel` | when a sentinel is used | the sentinel value |

`scale` and `offset` are arrays, not scalars, because a producer that packs per
field packs with a different range per field. `symbols` is an array because a
categorical corpus stores dense indices rather than the published codes:
`esa-wc-v200` holds 11 distinct codes, which need 4 bits, and storing them as
the published 8-bit codes wastes a factor of two before any codec runs.

The container is deliberately not a format anyone would use to distribute Earth
observation data. That is its purpose. A corpus distributed in Zarr with Blosc,
or NetCDF with Deflate, invites a reader to measure the store instead of the
codec, which is the single most common reason published ratios cannot be
compared. `.npz` has no codec inside it, is read by NumPy alone, and its
specification is one page long and has been stable since 2007.

### 4.2 Manifest

`manifest.csv` indexes the corpus. Each row identifies one sample:

| column | description |
| --- | --- |
| `id` | stable, unique sample identifier |
| `shape` | ordered dimensions of `data` |
| `dtype` | element type of `data` |
| `grid` | quantisation step of the published data, in native units |
| `grid_unit` | the native unit |
| `exact` | whether the stored representation reproduces the published data bit for bit |
| `input_sha256` | SHA-256 of `data` in C order |
| `npz_path` | relative path to the sample |
| `png_path` | relative path to the preview |

Corpora may add columns for dates, locations, bands, variables, spatial
references, quality statistics, or other source metadata.

### 4.3 Other formats

The canonical corpus is exported, never replaced:

- `export_zarr.py` writes Zarr v3 with canonical dimension order and **no
  compressor**, readable through numcodecs. This is what lets another benchmark
  read our corpus, and our numbers be checked without our harness.
- `export_netcdf.py` writes NetCDF-4 with CF attributes (`units`,
  `scale_factor`, `add_offset`, `_FillValue`), which is what the data producers
  this project works with already read.

Exporters are versioned code. Comparability comes from the exporter, not from
adopting another project's container.

### 4.4 Archiving

A released corpus is deposited with a DOI and a version. A benchmark whose
corpus cannot be cited by version is not reproducible. Previews are deposited
separately: they are never measured, and they are a tenth of the download.

## 5. Measurement

- The sample is decompressed before measurement. Each codec receives `data` as
  an in-memory NumPy array. The time to read the corpus is not measured.

- Encode and decode the whole array in one call. Partial reads, tiles, chunks
  and windowed access are not measured.

- A codec may use planes or blocks internally. All transforms, quantisation,
  model selection, entropy coding, metadata and assembly stay inside the timed
  operation.

- The compressed data contains everything needed to decode except the shape and
  dtype in the manifest. Quantisation steps, offsets, scale factors, symbol
  tables, dictionaries and shared state are inside the compressed bytes.

- Each codec uses one thread. After one untimed warm-up, the benchmark runs five
  timed rounds. In each round the operation repeats until the total reaches at
  least one second, and the median time per operation is reported.

- Throughput includes a 95% confidence interval for the median, from 10,000
  percentile-bootstrap resamples with seed 0.

- The compressed size may not change between rounds, and the decoded array may
  not change between rounds.

Wall-clock throughput is a property of the machine as much as of the codec.
`environment.json` records the machine and the timing settings of the run, and
a throughput figure is quoted with them or not at all.

## 6. Verification

Every mode verifies `structure` and `determinism`. Beyond that, each promise has
a check. The precedents are published compressors that failed them.

| check | what it asserts | precedent |
| --- | --- | --- |
| `structure` | shape and dtype unchanged | — |
| `determinism` | compressed size and decoded array stable across rounds | — |
| `exactness` | decoded bytes equal input bytes | — |
| `bound` | the declared bound holds on every valid element | SPERR exceeded its own bound; JPEG2000 targets PSNR, an average |
| `sentinel` | sentinels decode to themselves, and appear nowhere else | SZ3 and ZFP filled NaN with interpolated values, silently, raising no error |
| `zero` | exact zeros decode to exact zero | ZFP and SPERR turned zeros in a biomass field into nonzero values |

Two further behaviours are recorded rather than enforced, because they are
properties of the data that a codec must not hide:

- **Subnormals.** A codec that rounds subnormal inputs away changes no useful
  statistic, and also removes the only evidence that the producer emits them.
  The run records whether the input contained subnormals and whether they
  survived. Bit rounding failed a relative bound on exactly this.
- **Property preservation.** A bound on each element does not protect a property
  computed from elements. Section 9 covers this; here the run records, for any
  corpus with a declared property, whether that property changed.

A check that cannot be run is reported as not run, never as passed.

## 7. Metrics

### 7.1 Rate

```text
compression_ratio = input_bytes / compressed_bytes
bits_per_value    = compressed_bytes * 8 / element count
```

`input_bytes` is the size of `data` in its starting representation, with no
metadata and no container. It is a property of the array, not of any file
format. This definition is the reason ratios in this benchmark can be compared
with each other.

### 7.2 Speed

```text
encode_MB_s = input_bytes / encode_ns * 1,000
decode_MB_s = input_bytes / decode_ns * 1,000
```

`MB/s` uses decimal megabytes: 1 MB = 1,000,000 bytes.

### 7.3 Distortion

Computed in float64 over the whole sample, in native units:

```text
max_abs_error = max |x - x̂|
mae           = mean |x - x̂|
rmse          = sqrt(mean (x - x̂)²)
psnr_dB       = 20 · log10(peak / rmse)
```

`peak` is the dynamic range of the reference sample, `max(x) - min(x)`, not the
range of the element type. A sample that decodes exactly has infinite
`psnr_dB`; a constant sample that does not decode exactly has none.

In `lossless` mode these are zero by construction and are reported without
being recomputed.

### 7.4 Shape of the error

A maximum tells you how far the worst element moved. It does not tell you
whether the codec spent its budget or wasted it, and it does not tell you
whether the error will amplify in a derived quantity. Two further numbers do:

```text
error_spread  = p99(|x - x̂|) / max(|x - x̂|)
error_lag1    = spatial autocorrelation of (x - x̂) at lag 1
```

`error_spread` near 1 means the error is spread uniformly through the budget,
which raises the ratio and also raises `mae`; a high mean error is not by itself
a defect. `error_spread` well below 1 means the error is concentrated near zero
and the codec is leaving ratio unclaimed. SZ3, SPERR and stochastic rounding sit
at the first; ZFP sits at the second.

`error_lag1` near 0 means the error is white noise, which averages out of a
spatial derivative. A high `error_lag1` means the error has spatial structure
and a gradient or a band difference will amplify it.

Both replace a figure with a column, and both are reported in every lossy and
near-lossless row.

### 7.5 Result columns

`results.csv` has one row per sample and configuration:

| column | description |
| --- | --- |
| `sample_id` | sample ID from the manifest |
| `codec`, `codec_version`, `configuration` | what was run |
| `mode` | `lossless`, `near-lossless` or `lossy` |
| `bound_kind` | `absolute`, `relative`, or empty |
| `tau` | declared budget in native units; empty in `lossless` and `lossy` |
| `budget_level` | `conservative`, `matched`, `aggressive`, or empty |
| `input_bytes`, `compressed_bytes` | sizes |
| `compression_ratio`, `bits_per_value` | rate |
| `encode_ns`, `decode_ns` | median times |
| `encode_MB_s`, `decode_MB_s` | throughput |
| `encode_MB_s_ci95_low` … `decode_MB_s_ci95_high` | the four interval bounds |
| `max_abs_error`, `mae`, `rmse`, `psnr_dB` | distortion |
| `error_spread`, `error_lag1` | shape of the error |
| `exact` | whether `max_abs_error` is zero |
| `sentinel_ok`, `zero_ok`, `subnormals_ok` | the checks of section 6 |
| `fidelity_ok` | whether every promise the configuration made holds |
| `converted` | whether the budget was transformed to reach this codec |

`results.csv` is generated by a run and is never an input to one.

## 8. Aggregation and comparability

### 8.1 Corpus totals

Computed from totals across samples, never by averaging per-sample figures:

```text
compression_ratio = sum(input_bytes) / sum(compressed_bytes)
bits_per_value    = sum(compressed_bytes) * 8 / sum(element count)
encode_MB_s       = sum(input_bytes) / sum(encode_ns) * 1,000
decode_MB_s       = sum(input_bytes) / sum(decode_ns) * 1,000
max_abs_error     = max over samples
rmse              = sqrt(sum(rmse² · element count) / sum(element count))
```

`psnr_dB` is not aggregated, because its peak differs per sample. A
configuration is included only if it completes every sample; failed rows stay in
`results.csv` and are excluded from totals.

### 8.2 Which comparisons are valid

The protocol produces rows. It does not produce a winner, and a report built on
it should not either: no lossy compressor dominates rate-distortion everywhere,
and a benchmark that names one is concealing its operating point.

- Two `lossless` configurations compare directly on ratio and throughput.
- Two `near-lossless` configurations compare directly only at **the same bound
  kind and the same `tau`**. A configuration with a larger budget is not better
  for having a larger ratio.
- A `near-lossless` configuration compares against a `lossy` one only as a
  rate-distortion curve, and the comparison must state that only one of them
  bounds the worst element.
- A `lossy` configuration compares against another only as a curve over a sweep
  of operating points. A single lossy row is a point, not a result.
- Ratios from different starting representations of the same data are not a
  codec comparison. They are a measurement of the representation, and are
  reported as such.

### 8.3 Reporting rules

**Mark every converted number.** Where a budget had to be transformed to reach
a codec that does not accept its kind — the conservative transforms being
`tau_abs = min|x| · tau_rel` over nonzero values, and
`tau_rel = tau_abs / max|x|` — the row carries `converted = true` and the
resulting ratio is a lower bound. A number produced by a conversion is not the
same kind of number as a measured one.

**Name the budget level.** A ratio quoted without its `tau` and `budget_level`
is not a result from this protocol.

**Quote throughput with its machine.** See section 5.

## 9. Task validation

A bound on each element does not protect a property computed from elements. The
sharpest published demonstration: two radiative fluxes compressed at 0.3% and
0.02% relative error, each harmless alone, gave their difference an 8.0%
relative error, because subtracting near-equal quantities keeps all of the error
and almost none of the signal. The same arithmetic applies to any band index. A
budget of two grid steps on two near-equal reflectance bands is far more than
two steps on their normalised difference.

Task validation is a second protocol that runs on top of this one. A task is a
pair: an analysis, and a criterion on its output. It runs on the original and on
the decoded array, and **the outputs are compared, not the arrays**.

The initial tasks, chosen because they cover the three ways an element-wise
error amplifies:

| task | corpus | amplification it exposes |
| --- | --- | --- |
| NDVI | `s2-l1c-10m-4` | difference of two near-equal bands |
| slope | `cop-dem-glo30` | spatial derivative, where `error_lag1` is paid |
| rain mask | `imerg-pcp-12` | threshold crossing |

The third is there because of a measured case: on IMERG at a respected bound of
0.05 mm/hr, all 41.0 million exact zeros survived and 690,198 light-rain values
at or below the bound decoded as zero. The bound held and the number of raining
elements changed.

Two further rules:

**Variables feeding a standard derived quantity take the same budget.** You
cannot know how data will be used, but you can know that energy balances and
band ratios get computed. A derived quantity goes wrong when its inputs are
compressed unevenly.

**Detectable is not consequential, and only a blind test separates them.** An
expert can detect compression effects in data; that does not make them relevant.
The test that settles it is the one where domain scientists are given a mixture
of compressed and original data, are not told which is which, and are asked to
find the difference on their own analysis.

## 10. What this protocol does not cover

- **Storage and transfer.** Bytes fetched, chunks decoded, and time from a
  request to usable values are not measured here.
- **Parallel and accelerated decoding.** Every measurement is single-threaded.
- **Encoding cost in depth.** Encode time is recorded; the protocol is written
  for archives that encode once and decode often.
- **Reproducible timing across machines.** Wall-clock is what a user
  reproduces on their own hardware, not what another lab reproduces on theirs.
- **Scene-scale effects.** Samples are windows. Effects that appear only across
  a full granule, such as large contiguous NoData regions or whole-scene
  statistics, are under-represented.
