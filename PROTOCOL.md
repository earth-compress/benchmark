# EarthCompress Measurement Protocol v1.0

**Status:** Draft

This protocol measures compression of Earth observation and environmental arrays in three fidelity modes: lossless, near-lossless, and lossy.

Each measurement uses one array in memory. The protocol covers compressed size, encode and decode time, and distortion. It does not cover storage layout, network transfer, partial reads, parallel or accelerated decoding, or the effect of compression on an analysis. Section 9 describes a separate protocol for that last question. Because the samples are windows, the measurements may miss effects that appear only across a full granule. Small samples still represent large archives reasonably well, because those archives are stored in chunks that rarely exceed 100 MB (ClimateBenchPress).

The benchmark compares codecs. It does not establish that a codec is safe for a particular use; that requires validation against the use itself (Section 9).

## 1. Starting representation

Compression ratios depend on the input representation. For example, a float32 array republished from a 16-bit source may contain precision that was never present in the source. A codec should not get credit for removing those unused bits.

For each dataset, use the smallest integer type that reproduces the published data exactly:

1. Start with the array as published by the producer.
2. Test whether an integer array plus a `(scale, offset)` pair reproduces it bit for bit.
3. If it does, store the integers, scale, and offset. Otherwise, retain the published floating-point array.

Data published as integers, including categorical codes, pass step 2 with `scale = 1` and `offset = 0` and are stored as published.

The second step is an exactness test. The reconstruction runs in float64 and is cast once at the end, so that a valid integer representation is not rejected over a rounding difference in the test itself:

```python
back = (codes.astype(np.float64) * scale + offset).astype(published.dtype)
assert back.shape == published.shape and back.dtype == published.dtype
assert back.tobytes(order="C") == published.tobytes(order="C")
```

The benchmark does not add quantisation. Quantisation already applied by the producer is part of the published data. If a corpus cannot reproduce that data exactly, `spec.md` must disclose the difference.

ClimateBenchPress makes the opposite choice: it uses unquantised model output, so that the producer's quantisation stays out of the measurement. This protocol measures data in the form users receive it.

`grid` is the quantisation step of the published data, in the sample's native unit. All error budgets use that unit. For an integer corpus, `grid = scale`. A float corpus whose values do not fall on a common step has no grid. When the step differs within a sample, for example per band, `scale` and `offset` are stored per slice.

The published form can hide how the data was produced. ARCO-ERA5 republishes ERA5 as float32. In 2 m temperature, its values are spaced about 0.0016 K apart, about 2¹⁶ steps across the field's range, yet no `(scale, offset)` pair reproduces them bit for bit. By the rule above, ARCO-ERA5 remains float32. Quantising it to 0.01 K, as an earlier version of this corpus did, coarsens that spacing by a factor of about 6.4. ClimateBenchPress reports that ERA5 from the Climate Data Store is packed to 24 bits. Recovering the producer's integers requires the original GRIB messages and their packing parameters, not the republished float32.

`exact` records whether the stored representation reproduces each published sample bit for bit. `build.py` asserts this property. If a corpus cannot meet it, `spec.md` must describe what was lost.

## 2. Fidelity modes

Every configuration declares a mode. The mode determines which properties the run checks.

| mode | promises |
| --- | --- |
| `lossless` | `structure`, `determinism`, `exactness` |
| `near-lossless` | `structure`, `determinism`, `bound`, `sentinel`, `zero` |
| `lossy` | `structure`, `determinism`, `sentinel` |

- **`structure`:** decoded shape and dtype match the input.
- **`determinism`:** the same input produces the same bytes, and the same bytes decode to the same array. When a codec provides more than one decoder, such as CPU and GPU, every decoder must produce the same array.
- **`exactness`:** decoded bytes equal input bytes in C order. Equal numerical values with different byte representations do not pass.
- **`bound`:** the error bound defined in Section 2.1 holds.
- **`sentinel`:** every NoData value remains in its original position, and no valid input value becomes a sentinel. Exactness implies this in `lossless` mode.
- **`zero`:** every exact zero remains an exact zero.

If a configuration breaks a promise for a sample, that row has `fidelity_ok = false`, empty measurements, and no place in the aggregate results.

### 2.1 Error bounds

The term *relative error* is used inconsistently in compression literature (ClimateBenchPress, Z-checker). This protocol names the bound explicitly:

```text
absolute        |x - x̂| <= tau
relative        |x - x̂| <= tau · |x|              → requires exact zeros
range-relative  |x - x̂| <= tau · (max x - min x)
```

A relative bound requires `x̂ = 0` when `x = 0`. A range-relative bound, which SDRBench calls a value-range-based relative bound and which SZ3 and EBCC expose as their relative mode, is an absolute bound whose size the codec computes from the data it receives. Rule 1 of Section 3 excludes that, so a range-relative bound does not qualify as a near-lossless claim here. A codec that offers only a range-relative bound is measured in `lossy` mode.

All bounds also allow `x ≡ x̂`, meaning an exactly preserved value passes even when subtraction is undefined. Without this clause, `∞ - ∞` would be NaN and a correctly preserved infinity would fail (ClimateBenchPress).

Use `absolute` bounds for fields with a bounded range and roughly uniform uncertainty, such as reflectance, elevation, and temperature. Use `relative` bounds for fields that span orders of magnitude, such as precipitation, trace concentrations, and biomass. ClimateBenchPress and Delaunay et al. make the same distinction.

## 3. Error budgets

Values have uncertainty before compression. If that uncertainty is `sigma` and compression contributes an independent error of `sigma / k`, their quadrature sum is `sigma · sqrt(1 + 1/k²)`.

| level | `tau` | increase in total error |
| --- | --- | ---: |
| `conservative` | uncertainty / 5 | 2% |
| `matched` | uncertainty / 2 | 12% |
| `aggressive` | uncertainty | 41% |

ClimateBenchPress also uses three levels, but derives them from the 0%, 1%, and 5% percentiles of the ERA5 ensemble spread and checks them against bounds given by ECMWF scientists. Most corpora here have no ensemble, so this protocol starts from the product's published uncertainty. The three levels give more than one operating point for each codec. Budgets are rounded down to whole grid steps, making them no looser than the stated value. If a level falls below one grid step, that level is unavailable for the corpus.

`docs/tolerance.md` records the uncertainty used for each corpus, its source, and the resulting budgets.

The following rules apply:

1. **Declare budgets independently of the sample.** A codec cannot derive any part of its budget from the data being compressed. EBCC and SZ3 internally convert a relative bound to `tau · (max x - min x)`. Because the range changes by chunk, this can apply different absolute bounds to chunks of the same dataset (ClimateBenchPress). The harness may tighten a budget to fit a codec's accepted bound kind (Section 8); it never loosens one.
2. **Check every valid element.** Meeting a budget on average does not compensate for one element exceeding it.
3. **Exclude NoData from the numeric budget.** `tau` applies only to valid elements. Sentinels must round-trip exactly in every mode.
4. **Use the strictest applicable budget for heterogeneous planes.** If one array contains several physical quantities (`goes-abi-16`) or value types (`tessera-v2-128`), use the smallest defensible budget across its planes.

### 3.1 Corpora without a near-lossless point

Some corpora have no meaningful nonzero error budget. This applies to categorical values, where a change of one may mean a different class; values that are not physical quantities, such as the bytes of a float32 scale; and data for which the effect of a proposed budget on downstream analyses has not been established. These corpora are measured in lossless mode only.

## 4. Corpus layout

```text
corpora/<corpus-id>/
├── spec.md               sample definition, native unit, grid, licence
├── build.py              sample generation and exactness assertions
├── manifest.csv          one row per sample
├── npz/<sample>.npz.zst  sample data
├── png/<sample>.png      preview; never measured
├── results.csv           generated by a run; never an input
└── environment.json      generated by a run
```

Each sample is an uncompressed NumPy `.npz` inside a Zstandard wrapper. It contains `data`, plus `scale` and `offset` when the grid is not 1, and `sentinel` where applicable. `scale` and `offset` may be arrays, because a producer may pack each band or field with its own range.

The sample container is for benchmarking, not data distribution. Starting from a Zarr or NetCDF store with its own compressor would mix the store's behavior with the codec measurement. Here, corpus decompression happens before timing, and the codec receives only the in-memory array.

`manifest.csv` contains `id`, `shape`, `dtype`, `grid`, `grid_unit`, `exact`, `input_sha256`, `npz_path`, `png_path`, and any source metadata.

Exports do not replace the canonical corpus. `export_zarr.py` writes uncompressed Zarr v3, so codecs wrapped for numcodecs, as ClimateBenchPress requires, can run on the same samples without this harness. `export_netcdf.py` writes NetCDF-4 with CF attributes. Released corpora receive a version and DOI; previews are deposited separately.

## 5. Measurement

- Decompress the sample before timing. Each codec receives `data` as an in-memory array; corpus read time is excluded.
- Encode and decode the whole array in one call. Partial, tiled, and windowed access are outside this protocol.
- A codec may use internal planes or blocks. Its transforms, quantisation, model selection, entropy coding, and assembly are all timed.
- Compressed bytes must contain everything needed for decoding except shape and dtype. This includes quantisation steps, offsets, symbol tables, dictionaries, and shared state.
- Use one thread. After one untimed warm-up, run five timed rounds. In each round, repeat the operation until the total reaches one second, then report the median time per operation.
- Report a 95% confidence interval for median throughput from 10,000 percentile-bootstrap resamples with seed 0.
- Confirm that the compressed bytes and the decoded array do not change between rounds.

Throughput depends on the machine as well as the codec. `environment.json` records the test environment, which must accompany any quoted throughput result. Wall-clock time is not reproducible across machines; ClimateBenchPress reports WebAssembly instruction counts for that reason, and warns that fewer instructions do not guarantee faster decoding. This protocol reports wall-clock time with its environment.

## 6. Verification

Each promised property has a check. The precedents below were observed in released compressors by ClimateBenchPress.

| check | assertion | observed precedent |
| --- | --- | --- |
| `bound` | Every valid element meets the bound | SPERR exceeded its stated bound; JPEG2000 only targets PSNR, an average |
| `sentinel` | Sentinels remain in place and appear nowhere else | SZ3 3.2.2 replaced NaNs with interpolated values, and ZFP filled in values at NaN boundaries, without raising an error |
| `zero` | Exact zeros survive | ZFP, ZFP-ROUND, and SPERR turned zeros in a biomass field into nonzero values |

Two other properties are recorded without causing failure. For **subnormals**, record whether the input contains them and whether they survive; bit rounding has failed a relative bound on such values. For **declared corpus properties**, record whether compression changes them.

If a check cannot run, report it as *not run* rather than *passed*.

## 7. Metrics

```text
compression_ratio = input_bytes / compressed_bytes
bits_per_value    = compressed_bytes * 8 / element count
encode_MB_s       = input_bytes / encode_ns * 1,000
decode_MB_s       = input_bytes / decode_ns * 1,000
```

`input_bytes` is the size of `data` in its starting representation, excluding metadata and container overhead, as in ClimateBenchPress. Z-checker, Delaunay et al. and Baker et al. use file sizes instead, so their ratios depend on the file format; Baker et al. also define the ratio inverted, as compressed over original size. `MB` uses decimal units.

Distortion is computed over the whole sample in float64, using native units:

```text
max_abs_error = max |x - x̂|        mae        = mean |x - x̂|
rmse          = sqrt(mean (x-x̂)²)  mean_error = mean (x̂ - x)
psnr_dB       = 20·log10(peak / rmse)
```

`mean_error` detects bias, which Delaunay et al. track and which truncating codecs introduce towards zero (Baker et al.). `peak` is the dynamic range of the reference sample, not the range of its dtype, as in SDRBench and Z-checker. Exact decoding gives infinite `psnr_dB`; an inexact decode of a constant sample has no defined PSNR. In `lossless` mode, the error metrics are zero by construction.

Two additional metrics describe the distribution and spatial structure of error:

```text
error_spread = p99(|x - x̂|) / max(|x - x̂|)
error_lag1   = autocorrelation of (x - x̂) at lag 1 along the last axis
```

`error_spread` near 1 means the 99th percentile is close to the maximum error; a low value means the largest errors are less typical. `error_lag1` describes whether neighboring errors tend to have similar values; Z-checker computes the same quantity over several lags. Both help interpret error beyond its maximum, but neither by itself predicts the effect on a derived quantity.

Version 1.0 does not compute DSSIM or spectral error (ClimateBenchPress), 2D SSIM (SDRBench), or the Pearson correlation between original and decoded data (Z-checker).

`results.csv` has one row per sample and configuration: `sample_id`, `codec`, `codec_version`, `configuration`, `mode`, `bound_kind`, `tau`, `budget_level`, `input_bytes`, `compressed_bytes`, `compression_ratio`, `bits_per_value`, `encode_ns`, `decode_ns`, `encode_MB_s`, `decode_MB_s`, the four CI bounds, `max_abs_error`, `mae`, `rmse`, `mean_error`, `psnr_dB`, `error_spread`, `error_lag1`, `exact`, `sentinel_ok`, `zero_ok`, `subnormals_ok`, `fidelity_ok`, and `converted`.

## 8. Aggregation and comparability

Compute aggregate rates from totals across samples, not from averages of per-sample rates:

```text
compression_ratio = sum(input_bytes) / sum(compressed_bytes)
bits_per_value    = sum(compressed_bytes) * 8 / sum(count)
encode_MB_s       = sum(input_bytes) / sum(encode_ns) * 1,000
decode_MB_s       = sum(input_bytes) / sum(decode_ns) * 1,000
max_abs_error     = max over samples
rmse              = sqrt(sum(rmse² · count) / sum(count))
```

Do not aggregate `psnr_dB`, because its peak differs by sample. Include a configuration in aggregate results only if it completes every sample. Failed rows remain in `results.csv`.

Results should show operating points and curves rather than name an overall winner. SDRBench found that no lossy compressor had the best rate-distortion at every bit rate. Comparisons follow these rules:

- Two `lossless` configurations can be compared directly.
- Two `near-lossless` configurations can be compared at the same bound kind and `tau`.
- A `near-lossless` configuration and a `lossy` one can be compared as curves, with the difference in their guarantees stated.
- Two `lossy` configurations can be compared over a sweep, rather than from a single row.
- Ratios computed from different starting representations of the same data do not isolate codec performance.

Mark a row `converted = true` when the harness transformed its budget to fit a codec that does not accept the original bound kind. Following ClimateBenchPress, the transforms are `tau_abs = min|x| · tau_rel` over nonzero values and `tau_rel = tau_abs / max|x|`. Both are conservative, so treat the resulting ratio as a lower bound. Any quoted ratio must include `tau` and `budget_level`.

## 9. Task validation

An elementwise bound does not guarantee that a derived result is stable. Baker et al. calculated that compressing two radiative fluxes to relative errors of 0.3% and 0.02% would give their difference, the top-of-model energy balance, a relative error of 8.0%, and compressed both fluxes less aggressively for that reason. Subtracting nearly equal values can amplify the relative effect of small errors. Band indices can have the same problem.

Task validation runs an analysis on both the original and decoded arrays, then compares the analysis outputs against a stated criterion. It is a separate protocol built on these measurements.

| task | corpus | effect tested |
| --- | --- | --- |
| NDVI | `s2-l1c-10m-4` | Difference between two similar bands |
| slope | `cop-dem-glo30` | Sensitivity of a spatial derivative |
| rain mask | `imerg-pcp-12` | Threshold crossing |

The rain-mask task comes from an Earth Compress measurement on IMERG at a 0.05 mm/hr absolute bound. All 41.0 million exact zeros survived, but 690,198 light-rain values at or below the bound decoded as zero. The elementwise bound held while the number of raining elements changed. A relative bound with `tau < 1` would have kept every nonzero value nonzero.

Variables used together in a standard derived quantity should receive the same budget. In Baker et al., the surface energy balance of the compressed ensemble members fell outside the ensemble spread because latent heat flux had been compressed more aggressively than the other three fluxes; with equal precision, the anomaly disappeared.

Detecting a compression effect does not establish that it matters for an analysis. Baker et al. gave climate scientists an ensemble in which some members had been compressed, without saying which, and asked them to look for differences with their own analyses. That design can test whether a difference affects their work.

## References

- Baker, A. H., et al. (2016). Evaluating lossy data compression on climate simulation data within a large ensemble. *Geosci. Model Dev.*, 9, 4381–4403.
- Delaunay, X., Courtois, A., and Gouillon, F. (2019). Evaluation of lossless and lossy algorithms for the compression of scientific datasets in netCDF-4 or HDF5 files. *Geosci. Model Dev.*, 12, 4099–4113.
- Reichelt, T., et al. (2026). ClimateBenchPress (v1.0): a benchmark for lossy compression of climate data. *Geosci. Model Dev.*, 19, 5933–5960.
- Tao, D., Di, S., Guo, H., Chen, Z., and Cappello, F. (2019). Z-checker: A framework for assessing lossy compression of scientific data. *Int. J. High Perform. Comput. Appl.*, 33, 285–303.
- Zhao, K., et al. (2020). SDRBench: Scientific Data Reduction Benchmark for Lossy Compressors. *IEEE BigData 2020*.
