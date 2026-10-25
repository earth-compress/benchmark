# EarthCompress Measurement Protocol v1.0

**Status:** Draft

This protocol measures compression of Earth observation and environmental arrays in three fidelity modes: lossless, near-lossless, and lossy.

Each measurement uses one array in memory. The protocol covers compressed size, decode time, distortion, and an indicative encode time. It does not cover storage layout, network transfer, partial reads, parallel or accelerated decoding, or the effect of compression on an analysis. Section 9 describes a separate protocol for that last question. Because the samples are windows, the measurements may miss effects that appear only across a full granule.

## 1. Starting representation

Compression ratios depend on the input representation. For example, a float32 array republished from a 16-bit source may contain precision that was never present in the source. A codec should not get credit for removing those unused bits.

For each dataset, use the smallest integer type that reproduces the published data exactly:

1. Start with the array as published by the producer.
2. Test whether an integer array plus a `(scale, offset)` pair reproduces it bit for bit.
3. If it does, store the integers, scale, and offset. Otherwise, retain the published floating-point array.

Data published as integers, including categorical codes, pass step 2 with `scale = 1` and `offset = 0` and are stored as published.

The second step is an exactness test:

```python
back = (codes.astype(np.float64) * scale + offset).astype(published.dtype)
assert back.shape == published.shape and back.dtype == published.dtype
assert back.tobytes(order="C") == published.tobytes(order="C")
```

The benchmark does not add quantisation. Quantisation already applied by the producer is part of the published data.

## 2. Fidelity modes

Every configuration declares a mode. The mode determines which properties the run checks.

| mode | promises |
| --- | --- |
| `lossless` | `structure`, `determinism`, `exactness` |
| `near-lossless` | `structure`, `determinism`, `bound`, `sentinel`, `zero` |
| `lossy` | `structure`, `determinism`, `sentinel` |

- **`structure`:** decoded shape and dtype match the input.
- **`determinism`:** the same input produces the same bytes, and the same bytes decode to the same array. When a codec provides more than one decoder, such as CPU and GPU, every decoder must produce the same array.
- **`exactness`:** the decoded array is identical to the input, bit for bit.
- **`bound`:** the error bound defined in Section 2.1 holds.
- **`sentinel`:** every NoData value remains in its original position, and no valid input value becomes a sentinel.
- **`zero`:** every exact zero remains an exact zero.

If a configuration breaks a promise for a sample, that row has `fidelity_ok = false`, empty measurements, and no place in the aggregate results.

### 2.1 Error bound

A near-lossless configuration declares an absolute bound `tau`, in the native unit of the sample:

```text
|x - x̂| <= tau
```

An element decoded to exactly its input value always passes, including infinities.

## 3. Error budgets

Near-lossless configurations run at the budgets in `TOLERANCE.md`, which derives up to three levels per corpus, `conservative`, `matched`, and `aggressive`, from the uncertainty of each product. Budgets are in native units and rounded down to whole steps of `scale`; a level smaller than one step is not available for that corpus.

The following rules apply:

1. **Fixed budget.** Each corpus has one `tau` per level, listed in `TOLERANCE.md`, in native units. The codec receives that number and must keep every element within it. A codec mode that rescales the bound from the data it receives, for example by the range of each block, does not meet this rule, because the same `tau` would allow different errors in different parts of the same dataset.
2. **Every element.** The bound limits the largest error, not the average.
3. **NoData is not counted.** `tau` applies to valid elements; NoData values must decode unchanged.
4. **Mixed planes take the smallest budget.** If an array mixes quantities, such as reflectance and brightness temperature in `goes-abi-16`, use the budget of the most sensitive plane.

### 3.1 Corpora without a near-lossless point

Some corpora have no meaningful nonzero error budget. This applies to categorical values, where a change of one may mean a different class; values that are not physical quantities, such as the bytes of a float32 scale; and data for which the effect of a proposed budget on downstream analyses has not been established. These corpora are measured in lossless mode only.

## 4. Corpus layout

```text
corpora/<corpus-id>/
├── spec.md               sample definition, native unit, licence
├── build.py              sample selection, rebuild, and exactness assertions
├── manifest.csv          one row per sample
├── npz/<sample>.npz.zst  sample data
├── png/<sample>.png      preview; never measured
├── results.csv           generated by a run; never an input
└── environment.json      generated by a run
```

Each sample is an uncompressed NumPy `.npz` inside a Zstandard wrapper. It contains `data`, plus `scale` and `offset` when they are not 1 and 0, and `sentinel` where applicable. `scale` and `offset` may be arrays, with one value per band or field.

`manifest.csv` has one row per sample, with these columns:

| column | content |
| --- | --- |
| `id` | sample id |
| `source` | collection or product, with its version |
| `asset` | exact id of the source scene, granule, or tile |
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

Other source metadata may follow as extra columns. These columns are enough to write each sample as a georeferenced raster with its date.

`build.py` has two steps:

1. `select` chooses the samples and writes `manifest.csv`. It runs once.
2. `build` reads only `manifest.csv`, fetches each `asset` over the window given by `transform` and `shape`, writes the sample, and checks `input_sha256`.

A rebuild runs `build` only.

## 5. Measurement

The official run measures the configurations listed in `CODECS.md`.

- Decompress the sample before timing. Each codec receives `data` as an in-memory array; corpus read time is excluded.
- Encode and decode the whole array in one call. Partial, tiled, and windowed access are outside this protocol.
- A codec may use internal planes or blocks. Its transforms, quantisation, model selection, entropy coding, and assembly are all timed.
- Compressed bytes must contain everything needed for decoding except shape and dtype.
- Use one thread.

- **Size, error, and encode time.** Encode each sample and decode the result. The compressed size and the encode time come from the encode, and the distortion from the decode. The encode time is a single call without warm-up, so it is indicative.
- **Decode time.** On every sample, call decode up to 10 times, stopping after 0.5 s, with at least 3 calls. Report the median, minimum, and maximum time per call. The decode in the first bullet serves as the warm-up.
- **Determinism.** The repeated decodes of each sample must return the same array. On three samples per corpus, the first, the middle, and the last in the manifest, encode once more and check that the bytes match the first encode.

Throughput depends on the machine as well as the codec. `environment.json` records the test environment, which must accompany any quoted throughput result.

## 6. Verification

Each promised property has a check. The examples below, observed by Reichelt et al. (2026) in released compressors, show why the checks are necessary.

| check | assertion | observed precedent |
| --- | --- | --- |
| `bound` | Every valid element meets the bound | SPERR exceeded its stated bound; JPEG2000 only targets PSNR, an average |
| `sentinel` | Sentinels remain in place and appear nowhere else | SZ3 3.2.2 replaced NaNs with interpolated values, and ZFP filled in values at NaN boundaries, without raising an error |
| `zero` | Exact zeros survive | ZFP, ZFP-ROUND, and SPERR turned zeros in a biomass field into nonzero values |

If a check cannot run, report it as *not run* rather than *passed*.

## 7. Metrics

```text
compression_ratio = input_bytes / compressed_bytes
bits_per_value    = compressed_bytes * 8 / element count
encode_MB_s       = input_bytes / encode_ns * 1,000
decode_MB_s       = input_bytes / decode_ns * 1,000
```

`input_bytes` is the size of `data` in its starting representation, excluding metadata and container overhead. `MB` uses decimal units.

Distortion is computed over the whole sample in float64, using native units:

```text
max_abs_error = max |x - x̂|        mae        = mean |x - x̂|
rmse          = sqrt(mean (x-x̂)²)  mean_error = mean (x̂ - x)
psnr_dB       = 20·log10(peak / rmse)
```

`mean_error` detects bias. `peak` is the dynamic range of the reference sample, not the range of its dtype. Exact decoding gives infinite `psnr_dB`; an inexact decode of a constant sample has no defined PSNR. In `lossless` mode, the error metrics are zero by construction.

Two additional metrics describe the distribution and spatial structure of error:

```text
error_spread = p99(|x - x̂|) / max(|x - x̂|)
error_lag1   = autocorrelation of (x - x̂) at lag 1 along the last axis
```

`error_spread` near 1 means the 99th percentile is close to the maximum error; a low value means the largest errors are less typical. `error_lag1` describes whether neighboring errors tend to have similar values. Both help interpret error beyond its maximum, but neither by itself predicts the effect on a derived quantity.

`results.csv` has one row per sample and configuration: `sample_id`, `codec`, `codec_version`, `configuration`, `mode`, `tau`, `budget_level`, `input_bytes`, `compressed_bytes`, `compression_ratio`, `bits_per_value`, `encode_ns`, `decode_ns`, `decode_ns_min`, `decode_ns_max`, `encode_MB_s`, `decode_MB_s`, `max_abs_error`, `mae`, `rmse`, `mean_error`, `psnr_dB`, `error_spread`, `error_lag1`, `exact`, `sentinel_ok`, `zero_ok`, and `fidelity_ok`.

## 8. Aggregation and comparability

Compute aggregate rates from totals across samples, not from averages of per-sample rates:

```text
compression_ratio = sum(input_bytes) / sum(compressed_bytes)
bits_per_value    = sum(compressed_bytes) * 8 / sum(count)
encode_MB_s       = sum(input_bytes) / sum(encode_ns) * 1,000      over all samples
decode_MB_s       = sum(input_bytes) / sum(decode_ns) * 1,000      over all samples
max_abs_error     = max over samples
rmse              = sqrt(sum(rmse² · count) / sum(count))
```

Do not aggregate `psnr_dB`, because its peak differs by sample. Include a configuration in aggregate results only if it completes every sample. Failed rows remain in `results.csv`.

Results should show operating points and curves rather than name an overall winner. Comparisons follow these rules:

- Two `lossless` configurations can be compared directly.
- Two `near-lossless` configurations can be compared at the same `tau`.
- A `near-lossless` configuration and a `lossy` one can be compared as curves, with the difference in their guarantees stated.
- Two `lossy` configurations can be compared over a sweep, rather than from a single row.
- Ratios computed from different starting representations of the same data do not isolate codec performance.

Any quoted ratio must include `tau` and `budget_level`.

## 9. Task validation

An elementwise bound does not guarantee that a derived result is stable. Subtracting two nearly equal fields, for example, amplifies their compression errors (Baker et al., 2016).

Task validation is a separate protocol. It runs an analysis on the original and decoded arrays and compares the outputs, not the arrays.

| task | corpus | effect tested |
| --- | --- | --- |
| NDVI | `s2-l1c-10m-4` | Difference between two similar bands |
| slope | `cop-dem-glo30` | Sensitivity of a spatial derivative |
| rain mask | `imerg-pcp-12` | Threshold crossing; on IMERG, a 0.05 mm/hr bound held while 690,198 light-rain values decoded as zero |

## References

- Baker, A. H., et al. (2016). Evaluating lossy data compression on climate simulation data within a large ensemble. *Geosci. Model Dev.*, 9, 4381–4403.
- Reichelt, T., et al. (2026). ClimateBenchPress (v1.0): a benchmark for lossy compression of climate data. *Geosci. Model Dev.*, 19, 5933–5960.
