# EarthCompress Measurement Protocol v1.0

- Status: Draft

Measures compression of Earth observation and environmental arrays under three
fidelity modes: lossless, near-lossless and lossy.

It measures what a codec costs and what it gives up on one array held in
memory. It does not measure storage layout, network transfer, partial reads,
parallel or accelerated decoding, or whether an analysis survives compression.
Section 10 defines a separate protocol for the last of these. Samples are
windows, so effects that appear only across a full granule are
under-represented.

## 1. The starting representation

A ratio is only meaningful against a stated starting point, and that is what
most published numbers get wrong. A float32 array republished from a 16-bit
source carries 16 bits of padding, and recovering padding is not compression.

**The starting representation is the one with the fewest bits that reproduces
the published data exactly.** Per dataset, in order:

1. Take the data as the producer publishes it, whatever its type.
2. Ask whether an integer array and a `(scale, offset)` pair reproduce it bit
   for bit.
3. If so, store the integers with `scale` and `offset`. If not, store the
   published floating-point array unchanged.

Step 2 is a test, not a judgement:

```python
back = (codes.astype(published.dtype) * scale + offset).astype(published.dtype)
assert np.array_equal(back, published)
```

The property that matters: **the benchmark never introduces a lossy step of its
own.** Whatever the producer quantised is counted; nothing the benchmark
quantised is. Integer or floating point is a measured result, not a choice.

**`grid`** is the quantisation step of the published data in the native unit of
the sample, and the unit every budget is expressed in. An integer corpus has
`grid = scale`; a float corpus whose values fall on no common step has no grid.

The grid belongs to the producer and is not always what documentation implies.
ARCO-ERA5 republishes each field as float32, and its values sit on a grid of
`(max - min) / 65535` per field and per time step — the 16-bit GRIB packing
underneath. For 2 m temperature that is 0.0015564 K, not the 0.01 K a round
number suggests, and a corpus built on 0.01 K discards 2.68 bits per value the
producer did transmit. Where the grid varies within a sample, `scale` and
`offset` are stored per slice: one scale for a corpus cannot be exact.

**`exact`** records, per sample, whether the stored representation reproduces
the published data bit for bit. `build.py` asserts it. A corpus that cannot
states in its `spec.md` what was lost.

## 2. Fidelity modes

A configuration declares a **mode**, which fixes what it promises and therefore
what is verified. Modes are different claims, not points on a scale.

| mode | promises |
| --- | --- |
| `lossless` | `structure`, `determinism`, `exactness` |
| `near-lossless` | `structure`, `determinism`, `bound`, `sentinel`, `zero` |
| `lossy` | `structure`, `determinism` |

- **`structure`** — decoded shape and dtype unchanged.
- **`determinism`** — same input gives the same bytes; same bytes give the same
  array, including on another device.
- **`exactness`** — decoded bytes equal input bytes in C order. On bytes, not
  values: a differing representation of an equal value fails.
- **`bound`** — section 2.1.
- **`sentinel`** — every NoData value decodes to itself in its own position,
  and appears nowhere the input had a valid value.
- **`zero`** — every exact zero decodes to exact zero.

A configuration that breaks a promise it made has failed that sample: the row
carries `fidelity_ok = false` with empty measurements and is excluded from
aggregation.

### 2.1 Bound

There is no standard definition of "relative" in this literature, so the kind is
always named.

```text
absolute        |x - x̂| <= tau
relative        |x - x̂| <= tau · |x|              → forces exact zeros
range-relative  |x - x̂| <= tau · (max x - min x)
```

`relative` holds at `x = 0` only when `x̂ = 0`, so it carries zero preservation
by construction. **A `range-relative` bound is not accepted as a near-lossless
claim**, because it depends on the content of whatever block the codec saw; a
codec offering only that is measured as `lossy`.

Every bound carries the equivalence clause `|x - x̂| <= tau OR x ≡ x̂`. Without
it a correctly preserved infinity violates its own bound, since `∞ - ∞` is NaN.

Use `absolute` for fields with bounded range and roughly uniform uncertainty
(reflectance, elevation, temperature); `relative` for fields spanning orders of
magnitude (precipitation, trace concentrations, biomass).

## 3. Error budgets

Every value already carries an error before any codec touches it, and the two
add in quadrature. A compression error of `sigma / k` against uncertainty
`sigma` raises the total by `sqrt(1 + 1/k²)`:

| level | `tau` | total error raised by |
| --- | --- | ---: |
| `conservative` | uncertainty / 5 | 2% |
| `matched` | uncertainty / 2 | 12% |
| `aggressive` | uncertainty | 41% |

Three levels, because one budget gives a point and three trace the front: a
codec whose advantage appears only at `aggressive` has not shown one. Budgets
round down to whole grid steps, which can only make them stricter. A level
below one grid step does not exist for that corpus.

`docs/tolerance.md` records the uncertainty used per corpus, its source, and
the resulting budgets.

Four rules:

**Declared, never derived.** A configuration may not read any part of its
budget from the sample. EBCC and SZ3 convert a relative bound internally to
`tau · (max x - min x)`, and that range differs per chunk, so they silently
apply a different bound to each chunk of one dataset.

**Bounds the worst element, not the mean.** Meeting a budget on average and
missing it on one element fails that sample.

**NoData is outside the budget.** `tau` applies to valid elements only;
sentinels round-trip exactly in every mode, `lossy` included.

**Heterogeneous planes take the strictest budget.** Where one array holds more
than one physical quantity (`goes-abi-16`) or more than one kind of value
(`tessera-v2-128`), the corpus budget is the smallest defensible for any plane.

### 3.1 Corpora with no near-lossless point

Lossless only when no budget above zero is meaningful, not when one is merely
risky. Three grounds: **categorical values**, where an error of one makes a
different class and `max_abs_error` means nothing; **values that are not
quantities**, such as the bytes of a float32 scale, where an error in an
exponent byte scales an element by two; and **unmeasured downstream effect**,
where a budget may be harmless but harmlessness is a claim about a task.

## 4. Corpus layout

```text
corpora/<corpus-id>/
├── spec.md               what the samples are, native unit, grid, licence
├── build.py              generates them and asserts exactness
├── manifest.csv          index, one row per sample
├── npz/<sample>.npz.zst  the sample
├── png/<sample>.png      preview, never measured
├── results.csv           generated by a run, never an input
└── environment.json      generated by a run
```

A sample is a NumPy `.npz` compressed with Zstandard, holding `data`, plus
`scale` and `offset` when the grid is not 1, `symbols` for categorical corpora,
and `sentinel` where one is used. These are arrays, not scalars: a producer
packing per field packs with a different range per field, and a categorical
corpus stores dense indices rather than published codes.

The container is deliberately not a format anyone would use to distribute Earth
observation data. A corpus in Zarr with Blosc, or NetCDF with Deflate, invites a
reader to measure the store instead of the codec, which is the commonest reason
published ratios cannot be compared. `.npz` has no codec inside, is read by
NumPy alone, and its specification is one page and stable since 2007.

`manifest.csv` carries `id`, `shape`, `dtype`, `grid`, `grid_unit`, `exact`,
`input_sha256`, `npz_path`, `png_path`, plus any source metadata.

The canonical corpus is exported, never replaced: `export_zarr.py` writes Zarr
v3 with no compressor, readable through numcodecs, so another benchmark can read
our corpus and check our numbers without our harness; `export_netcdf.py` writes
NetCDF-4 with CF attributes, which is what these data producers already read.
A released corpus is deposited with a DOI and a version, previews separately.

## 5. Measurement

- The sample is decompressed first; each codec receives `data` as an in-memory
  array. Corpus read time is not measured.
- Encode and decode the whole array in one call. No partial, tiled or windowed
  access.
- A codec may use planes or blocks internally. Every transform, quantisation,
  model selection, entropy coding and assembly step stays inside the timed
  operation.
- The compressed bytes contain everything needed to decode except shape and
  dtype: quantisation steps, offsets, symbol tables, dictionaries, shared state.
- One thread. After one untimed warm-up, five timed rounds; in each, the
  operation repeats until the total reaches one second, and the median time per
  operation is reported.
- Throughput carries a 95% confidence interval for the median from 10,000
  percentile-bootstrap resamples with seed 0.
- Compressed size and decoded array may not change between rounds.

Wall-clock throughput is a property of the machine as much as the codec.
`environment.json` records both, and a throughput figure is quoted with them or
not at all.

## 6. Verification

Each promise has a check. The precedents are published compressors that failed
them.

| check | asserts | precedent |
| --- | --- | --- |
| `bound` | holds on every valid element | SPERR exceeded its own bound; JPEG2000 targets PSNR, an average |
| `sentinel` | sentinels decode to themselves and appear nowhere else | SZ3 and ZFP filled NaN with interpolated values, silently |
| `zero` | exact zeros survive | ZFP and SPERR turned zeros in a biomass field nonzero |

Two behaviours are recorded, not enforced, because a codec must not hide a
property of the data. **Subnormals**: rounding them away changes no useful
statistic and also removes the only evidence the producer emits them, so the run
records whether the input had them and whether they survived; bit rounding
failed a relative bound on exactly this. **Declared properties**: where a corpus
declares one, the run records whether it changed.

A check that cannot be run is reported as not run, never as passed.

## 7. Metrics

```text
compression_ratio = input_bytes / compressed_bytes
bits_per_value    = compressed_bytes * 8 / element count
encode_MB_s       = input_bytes / encode_ns * 1,000
decode_MB_s       = input_bytes / decode_ns * 1,000
```

`input_bytes` is the size of `data` in its starting representation, with no
metadata and no container: a property of the array, not of a file format. That
definition is why ratios here can be compared with each other. `MB` is decimal.

Distortion, in float64 over the whole sample, in native units:

```text
max_abs_error = max |x - x̂|        mae     = mean |x - x̂|
rmse          = sqrt(mean (x-x̂)²)  psnr_dB = 20·log10(peak / rmse)
```

`peak` is the dynamic range of the reference sample, not of the element type. An
exact decode has infinite `psnr_dB`; a constant sample decoded inexactly has
none. In `lossless` mode these are zero by construction.

**Shape of the error.** A maximum does not say whether the codec spent its
budget or wasted it, nor whether the error will amplify in a derived quantity:

```text
error_spread = p99(|x - x̂|) / max(|x - x̂|)
error_lag1   = spatial autocorrelation of (x - x̂) at lag 1
```

`error_spread` near 1 means the error fills the budget, which raises the ratio
and also `mae` — a high mean error is not by itself a defect. Well below 1 means
the error sits near zero and ratio is left unclaimed. `error_lag1` near 0 means
white noise, which averages out of a spatial derivative; high means the error
has structure a gradient or band difference will amplify.

`results.csv` has one row per sample and configuration: `sample_id`, `codec`,
`codec_version`, `configuration`, `mode`, `bound_kind`, `tau`, `budget_level`,
`input_bytes`, `compressed_bytes`, `compression_ratio`, `bits_per_value`,
`encode_ns`, `decode_ns`, `encode_MB_s`, `decode_MB_s`, the four CI bounds,
`max_abs_error`, `mae`, `rmse`, `psnr_dB`, `error_spread`, `error_lag1`,
`exact`, `sentinel_ok`, `zero_ok`, `subnormals_ok`, `fidelity_ok`, `converted`.

## 8. Aggregation and comparability

From totals across samples, never by averaging per-sample figures:

```text
compression_ratio = sum(input_bytes) / sum(compressed_bytes)
encode_MB_s       = sum(input_bytes) / sum(encode_ns) * 1,000
max_abs_error     = max over samples
rmse              = sqrt(sum(rmse² · count) / sum(count))
```

`psnr_dB` is not aggregated: its peak differs per sample. A configuration is
included only if it completes every sample; failed rows stay in `results.csv`
and are excluded.

The protocol produces rows, not a winner, and neither should a report built on
it: no lossy compressor dominates rate-distortion everywhere, and naming one
conceals its operating point.

- Two `lossless` configurations compare directly.
- Two `near-lossless` ones compare only at **the same bound kind and the same
  `tau`**. A larger budget is not better for having a larger ratio.
- `near-lossless` against `lossy` compares only as a curve, stating that one of
  them bounds the worst element and the other does not.
- Two `lossy` ones compare only as curves over a sweep. One lossy row is a
  point, not a result.
- Ratios from different starting representations of the same data are not a
  codec comparison; they measure the representation.

**Mark every converted number.** Where a budget was transformed to reach a
codec that does not accept its kind — `tau_abs = min|x| · tau_rel` over nonzero
values, or `tau_rel = tau_abs / max|x|` — the row carries `converted = true` and
its ratio is a lower bound. **Name the budget level**: a ratio quoted without
`tau` and `budget_level` is not a result from this protocol.

## 9. Task validation

A bound on each element does not protect a property computed from elements. Two
radiative fluxes compressed at 0.3% and 0.02% relative error, each harmless
alone, gave their difference an 8.0% relative error: subtracting near-equal
quantities keeps all the error and almost none of the signal. The same applies
to any band index.

Task validation is a second protocol on top of this one. A task is an analysis
plus a criterion on its output, run on the original and on the decoded array,
and **the outputs are compared, not the arrays**.

| task | corpus | amplification exposed |
| --- | --- | --- |
| NDVI | `s2-l1c-10m-4` | difference of two near-equal bands |
| slope | `cop-dem-glo30` | spatial derivative, where `error_lag1` is paid |
| rain mask | `imerg-pcp-12` | threshold crossing |

The third exists because of a measured case: on IMERG at a respected bound of
0.05 mm/hr, all 41.0 million exact zeros survived and 690,198 light-rain values
at or below the bound decoded as zero. The bound held and the number of raining
elements changed.

**Variables feeding a standard derived quantity take the same budget.** You
cannot know how data will be used, but you can know that energy balances and
band ratios get computed, and a derived quantity goes wrong when its inputs are
compressed unevenly.

**Detectable is not consequential, and only a blind test separates them.** An
expert can detect compression effects; that does not make them relevant. What
settles it is giving domain scientists a mixture of compressed and original
data, not saying which is which, and asking them to find the difference on their
own analysis.
