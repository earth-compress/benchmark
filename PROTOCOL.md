# Earth Compress Measurement Protocol v1.0

This protocol measures compression of Earth observation and environmental arrays in lossless, near-lossless, and lossy modes.

Each measurement uses one array in memory. We report compressed size, decode time, distortion, and an indicative encode time. Storage layout, network transfer, partial reads, parallel or accelerated decoding, and downstream analyses are outside this protocol. Section 9 gives examples of separate analysis checks.

## 1. Starting representation

Compression ratio depends on the array a codec receives. For instance, ERA5 2 m temperature is archived as 16-bit integer codes with a step of 2^-9 K and an offset per hour. A float32 copy stores each value in 32 bits. Compressing that copy may remove bits the source never had, so its ratio describes the copy rather than the archived field.

For each corpus, use integers when they reproduce the published values exactly.

1. Start with the array as published by the producer.
2. Test whether an integer array plus a `(scale, offset)` pair reproduces it bit for bit.
3. If it does, store the integers, scale, and offset. Otherwise, retain the published floating-point array.

`DATASETS.md` gives the `scale` and `offset` of each corpus, and the `manifest.csv` of each corpus holds the exact values of every sample.

Data published as integers, including categorical codes, pass step 2 with `scale = 1` and `offset = 0` and are stored as published.

Step 2 uses this exactness test.

```python
plane_shape = (-1,) + (1,) * (codes.ndim - 1)
scale = np.asarray(scale, dtype=np.float64).reshape(plane_shape)
offset = np.asarray(offset, dtype=np.float64).reshape(plane_shape)
back = (codes.astype(np.float64) * scale + offset).astype(published.dtype)
assert back.shape == published.shape
assert back.tobytes(order="C") == published.tobytes(order="C")
```

Preparing the starting representation does not add quantisation. Quantisation already applied by the producer is part of the published data. A near-lossless codec may quantise during compression.

## 2. Fidelity modes

Every configuration declares a mode. The mode determines which properties the run checks.

| mode | promises |
| --- | --- |
| `lossless` | `structure`, `determinism`, `exactness` |
| `near-lossless` | `structure`, `determinism`, `bound`, `sentinel`, `zero` |
| `lossy` | `structure`, `determinism`, `rms`, `sentinel` |

- **`structure`** means decoded shape and dtype match the input.
- **`determinism`** means the same input produces the same bytes, and the same bytes decode to the same array.
- **`exactness`** means the decoded array is identical to the input, bit for bit.
- **`bound`** means every valid element meets the error bound of Section 2.1.
- **`rms`** means the root-mean-square error of the valid elements meets the error bound of Section 2.1.
- **`sentinel`** means every NoData value remains in its original position, and no valid input value becomes a sentinel.
- **`zero`** means every value equal to zero in native units decodes to zero.

Lossy mode also runs the `zero` check and reports it in `zero_ok` and `zero_violations`. It is not a promise there, so it does not change `fidelity_ok`.

A broken promise is a result. The row keeps every measurement, sets `fidelity_ok = false` and `status = violation`, and counts the elements that broke each promise, or the sample for `rms`. A configuration that raises an error, or decodes to the wrong shape or dtype, has `status = crash` and no measurements. A configuration that cannot take a corpus, for example one limited to 16-bit integers, does not run on it.

### 2.1 Error bound

A near-lossless or lossy configuration declares an absolute bound `tau` in the sample's native unit. Near-lossless holds every valid element within it. Lossy holds the root-mean-square error of the valid elements of each sample within it.

```text
near-lossless   |x - x̂| <= tau              for every valid element
lossy           sqrt(mean (x - x̂)²) <= tau  over the valid elements
```

An element decoded to exactly its input value has no error, including infinities. Any other element with an error that is not finite breaks both bounds. Errors within `tau` have a root-mean-square within `tau`, so every near-lossless result also meets the lossy bound at the same `tau`. The lossy bound does not limit the error of a single element.

## 3. Error budgets

Near-lossless and lossy configurations use the budgets in `TOLERANCE.md`, with the same `tau` in both modes. That page sets `conservative`, `matched`, and `aggressive` bounds from a reference error for each eligible corpus, and a `recommended` bound where domain experts have published one. Lossy uses a `recommended` bound only where the experts bound a mean error rather than every element. `budgets.csv` lists the modes of each budget. These are benchmark settings, not recommendations for scientific use. Budgets are in native units. For integer data they are rounded down to whole steps of the largest `scale` in the corpus. A level smaller than one step is 0, and the lossless result stands for it.

The same rules apply to every budget.

1. **Fixed budget.** Each corpus has one `tau` per level, in native units. The codec receives that number and must keep every element, or in lossy mode the root-mean-square error, within it. A codec mode that rescales the bound from the data it receives, for example by the range of each block, does not meet this rule, because the same `tau` would allow different errors in different parts of the same dataset. A wrapper may convert `tau` into the kind of target a codec takes, such as a PSNR, when the converted target is the same error over the sample.
2. **NoData is not counted.** `tau` applies to valid elements. NoData positions must be preserved, and no new NoData values may appear.
3. **Only adapters around a codec.** A codec receives `tau` in the units of the stored values, and the sentinel only where its interface takes one. A wrapper may change the type or layout of the data to one the codec accepts, and back; it may not correct the codec's output. Corrections belong to a separate configuration that declares them, such as a safeguarded one in `CODECS.md`.
4. **A searched setting.** A codec with no error target of its own may have one setting searched on each sample. The wrapper encodes with several values of the setting and keeps one whose decoded sample meets the bound. Every trial is part of the encode, so the encode time includes the search.

### 3.1 Corpora without a budget

The corpora in the lossless-only table of `TOLERANCE.md` have no budget. That page gives the reason for each corpus. They are measured in lossless mode only.

## 4. Corpus layout

```text
corpora/<corpus-id>/
├── spec.md               sample definition, native unit, licence
├── build.py              sample selection, rebuild, and exactness assertions
├── manifest.csv          one row per sample
├── npz/<sample>.npz.zst  sample data
├── png/<sample>.png      preview; never measured
├── results.csv           generated by runs; never an input
└── environment.json      generated by a run
```

Each sample is an uncompressed NumPy `.npz` inside a Zstandard wrapper. It contains `data`, plus `scale` and `offset` when they are not 1 and 0, and `nodata` where applicable. `scale` and `offset` may be arrays, with one value per band or field.

Each `manifest.csv` has one row per sample and the columns below.

| column | content |
| --- | --- |
| `id` | sample id |
| `source` | collection or product, with its version |
| `asset` | source scene, granule, tile, or file; several are separated by `|` |
| `crs` | EPSG code or WKT |
| `transform` | six values of the affine geotransform, in GDAL order |
| `datetime_start`, `datetime_end` | ISO 8601 UTC; for products without an acquisition time, the period they cover |
| `bands` | source name of each plane, in array order |
| `shape`, `dtype` | of `data` |
| `unit` | native unit after `scale` and `offset` |
| `scale`, `offset` | as stored in the sample |
| `nodata` | sentinel value, empty if none |
| `input_sha256` | SHA-256 of `data` |
| `npz_path`, `png_path` | relative paths |

Values that differ by plane, such as `bands`, `scale`, and `offset`, are separated by `|`. Other source metadata may follow as extra columns. These columns are enough to write each sample as a georeferenced raster with its date, except `clay-embeddings`, whose cells are listed in `cells/`.

Each corpus's `build.py` has two steps.

1. `select` chooses the samples and writes `manifest.csv`. It runs once.
2. `build` uses the existing `manifest.csv` to fetch each `asset` over the window given by `transform` and `shape`, write the sample, and check `input_sha256`.

A rebuild runs `build` only.

## 5. Measurement

Each run measures its selected configurations under the same rules. `CODECS.md` describes the configurations the benchmark can run and identifies the separate reference. Published measurements are in each corpus's `results.csv`.

- Each codec receives `data` as an in-memory array; corpus read time is excluded.
- Encode and decode the whole array in one call. Partial, tiled, and windowed access are outside this protocol.
- A codec may use internal planes or blocks. Everything the codec does is timed.
- Compressed bytes must contain everything needed for decoding except shape and dtype.
- Use one thread.
- **Size, error, and encode time.** Encode each sample and decode the result. The compressed size and the encode time come from the encode, and the distortion from the decode. The encode time is a single call without warm-up, so it is indicative.
- **Decode time.** On every sample, call decode up to 10 times, stopping after 0.5 s, with at least 3 calls. Report the median, minimum, and maximum time per call. The decode of the previous step serves as the warm-up.
- **Determinism.** The repeated decodes of each sample must return the same array. On three samples per corpus, the first, the middle, and the last in the manifest, encode once more and check that the bytes match the first encode.

`environment.json` records the machine; quote it with any throughput.

## 6. Verification

Each promised property has a check. The failures below were observed by Reichelt et al. (2026) in released compressors.

| check | assertion | observed precedent |
| --- | --- | --- |
| `bound` | Every valid element meets the bound | SPERR exceeded its stated bound |
| `rms` | The root-mean-square error of the valid elements meets the bound | None, as Reichelt et al. checked pointwise bounds only |
| `sentinel` | Sentinels remain in place and appear nowhere else | SZ3 3.2.2 replaced NaNs with interpolated values, and ZFP filled in values at NaN boundaries, without raising an error |
| `zero` | Exact zeros survive | ZFP, ZFP-ROUND, and SPERR turned zeros in a biomass field into nonzero values |

Checks that do not apply, such as the sentinel check when a sample has no sentinel, leave their result field empty rather than report a pass.

## 7. Metrics

```text
compression_ratio = input_bytes / compressed_bytes
bits_per_value    = compressed_bytes * 8 / element count
encode_MB_s       = input_bytes / encode_ns * 1000
decode_MB_s       = input_bytes / decode_ns * 1000
```

`input_bytes` is the size of `data` in its starting representation, excluding metadata and container overhead. `MB` uses decimal units.

For near-lossless and lossy modes, distortion is computed over the valid elements of the sample, in float64 and native units.

```text
max_abs_error = max |x - x̂|        mae        = mean |x - x̂|
rmse          = sqrt(mean (x-x̂)²)  mean_error = mean (x̂ - x)
psnr_dB       = 20·log10(peak / rmse)
```

`mean_error` detects bias. `peak` is the range of the valid reference values, not the range of the dtype. Exact decoding gives infinite `psnr_dB`; an inexact decode of a constant sample has no defined PSNR. In `lossless` mode, `max_abs_error`, `mae`, `rmse`, and `mean_error` are zero. `psnr_dB` is infinite, while `error_spread` and `error_lag1` are undefined.

Two additional metrics describe the distribution and spatial structure of error:

```text
error_spread = p99(|x - x̂|) / max(|x - x̂|)
error_lag1   = autocorrelation of (x - x̂) at lag 1 along the last axis
```

`results.csv` has one row per sample and configuration: `sample_id`, `codec`, `codec_version`, `configuration`, `mode`, `family`, `tau`, `budget_level`, `input_bytes`, `compressed_bytes`, `compression_ratio`, `bits_per_value`, `encode_ns`, `decode_ns`, `decode_ns_min`, `decode_ns_max`, `encode_MB_s`, `decode_MB_s`, `max_abs_error`, `mae`, `rmse`, `mean_error`, `psnr_dB`, `error_spread`, `error_lag1`, `sentinel_ok`, `zero_ok`, `bound_violations`, `rms_violations`, `sentinel_violations`, `zero_violations`, `fidelity_ok`, and `status`. A run replaces the rows of the configurations it measures and keeps the others.

## 8. Aggregation and comparability

Compute aggregate rates from totals across samples, not from averages of per-sample rates. `count` is the number of elements:

```text
compression_ratio = sum(input_bytes) / sum(compressed_bytes)
bits_per_value    = sum(compressed_bytes) * 8 / sum(count)
encode_MB_s       = sum(input_bytes) / sum(encode_ns) * 1000
decode_MB_s       = sum(input_bytes) / sum(decode_ns) * 1000
max_abs_error     = max over samples
rmse              = sqrt(sum(rmse² · count) / sum(count))
```

Do not aggregate `psnr_dB`, because its peak differs by sample. Include a configuration in aggregate results only if every sample has measurements, and report its violations beside its ratio. Crashed rows remain in `results.csv`.

Results should show operating points and curves rather than name an overall winner. Comparisons follow these rules:

- Two `lossless` configurations can be compared directly.
- Two `near-lossless` configurations can be compared at the same `tau`, and so can two `lossy` ones.
- A `near-lossless` configuration and a `lossy` one can be compared at the same `tau`, with the difference in their guarantees stated. Their ratio is the cost of holding every element rather than the root-mean-square.
- Ratios computed from different starting representations of the same data do not isolate codec performance.

Any quoted near-lossless or lossy ratio must include its mode, `tau`, `budget_level`, and whether every promise held. A quoted lossy ratio should also give `max_abs_error`, which the lossy bound does not limit.

## 9. Task validation

Neither an elementwise bound nor a root-mean-square one guarantees that a derived result is stable. Subtracting two nearly equal fields, for example, amplifies their compression errors (Baker et al., 2016).

Task validation is outside this protocol. The tasks below are examples of checks that could compare an analysis on the original and decoded arrays.

| task | corpus | effect tested |
| --- | --- | --- |
| NDVI | `s2-l1c-10m-4` | Difference between two similar bands |
| slope | `cop-dem-glo30` | Sensitivity of a spatial derivative |
| rain mask | `imerg-pcp-12` | Threshold crossing |

## References

- Baker, A. H., et al. (2016). [Evaluating lossy data compression on climate simulation data within a large ensemble](https://gmd.copernicus.org/articles/9/4381/2016/). *Geosci. Model Dev.*, 9, 4381–4403.
- Reichelt, T., et al. (2026). [ClimateBenchPress (v1.0): a benchmark for lossy compression of climate data](https://gmd.copernicus.org/articles/19/5933/2026/index.html). *Geosci. Model Dev.*, 19, 5933–5960.
