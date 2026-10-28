# Use cases

A use case runs one analysis on the original samples and on their decoded copies, and reports how its result changes. The bounds in [TOLERANCE.md](TOLERANCE.md) hold element by element, while an analysis can combine elements in ways that amplify the error or hide it ([PROTOCOL.md](PROTOCOL.md), Section 9). Each use case tests one such way.

| use case | data | what it tests | status |
| --- | --- | --- | --- |
| [Methane plumes](#2-methane-plumes) | MethaneSET, Sentinel-2 and Landsat 8/9 | A signal of a few percent in a ratio of two bands and two dates, close to the noise | draft |
| Cloud properties | Sentinel-2 L1C, cloudy scenes | Band ratios, parallax between bands, and the texture of convective cells | planned |
| Change detection | `alphaearth-v1-64` | Distances between the embeddings of two years, for a corpus that is lossless only today | planned |
| Drainage networks | `cop-dem-glo30` | Flow routing, where a small error in flat terrain can move a divide far away | planned |

## 1. Rules

Every use case follows these rules.

1. **The analysis is fixed on the original.** Every value the analysis fits, such as a threshold, a sign or a set of weights, is fitted once on the original sample and reused on the decoded copy. Refitting on the decoded copy would absorb part of the damage.
2. **Everything the archive holds is compressed.** When the analysis reads several acquisitions, such as a target and its backgrounds, each one passes through the same configuration. Labels and masks used as reference are never compressed.
3. **The codec receives the product.** Each array starts from the representation of `PROTOCOL.md`, Section 1, on the native grid of its bands. A copy resampled to a finer grid is reduced to the native grid before encoding and resampled again after decoding. Each codec receives an array the size of a corpus sample, 512 × 512 native pixels, that contains the area the analysis reads.
4. **The configurations and budgets are those of the benchmark.** Near-lossless configurations of `CODECS.md` run at the levels that `TOLERANCE.md` gives the corpus holding the same bands. Lossy configurations run at the same budgets and are read as curves. One lossless configuration runs to confirm that the pipeline reports no change.
5. **Each outcome is reported on its own.** A use case reports the quantities its users act on, such as a detection rate, a count of false alarms or an emission rate. A single overlap score can add a loss to a gain and show neither.
6. **Each change is read against noise.** The analysis also runs on the original plus independent Gaussian noise with the `sigma` of `TOLERANCE.md`, rounded to whole stored steps, with a fixed seed. A configuration is within noise for an outcome when its change is no larger than the change from this noise reference, at the median and at the 90th percentile over samples.

Each use case keeps its files in `usecases/<use-case>/`.

```text
usecases/<use-case>/
├── build.py         sample selection, rebuild, and exactness assertions
├── manifest.csv     one row per sample
├── npz/             samples, stored as in a corpus
├── analysis.py      the frozen analysis
└── results.csv      one row per sample and configuration
```

## 2. Methane plumes

We ask whether compression changes three things a methane detector reports from Sentinel-2 and Landsat 8/9. These are the part of a plume it detects, the false alarms it raises elsewhere, and the emission rate it estimates.

Methane absorbs strongly inside the second shortwave infrared band (Sentinel-2 B12, Landsat B7) and much less inside the first (B11, B6). A plume lowers the second band relative to the first by a few percent, which for many plumes is close to the noise. The detector divides the two bands, and divides each by a background from other dates, so independent errors in four arrays enter one ratio.

### 2.1 Data

The samples come from [MethaneSET](https://huggingface.co/datasets/tacofoundation/methaneset), collections `methaneset-s2-finetune` with 3,552 samples and `methaneset-l89-finetune` with 1,353. Each sample is a 2 km chip on a 10 m grid. It holds a target acquisition, four background acquisitions of the same place on other dates, a plume mask, and the wind and emission rate of the detection (`meteo:wind_u`, `meteo:wind_v`, `detection:ch4_fluxrate`, `detection:ch4_fluxrate_std`).

We draw 30 samples per sensor with a fixed seed, ten from each tercile of `detection:ch4_fluxrate`, among onshore samples (`detection:offshore` false) with a cloud-free target (`target:cloud` equal to 0). The lowest tercile holds the faint plumes, where the signal is closest to the noise.

MethaneSET repeats pixels to bring every band to 10 m. In Sentinel-2, B11 and B12 come in blocks of 2 × 2 pixels; in Landsat, every band except the panchromatic one comes in blocks of 3 × 3. Landsat samples also mix representations. The target and the first background are float32 reflectance, and the other three backgrounds are uint16 DN.

We therefore rebuild every acquisition from its source product, Sentinel-2 L1C or Landsat Collection 2 Level-1, as uint16 DN on the native grid of 20 m or 30 m. `build.py` finds each product from the sample metadata (`target:tile`, `bg:tile0`, and `bg:sensor*` with `bg:date*`). It checks that the rebuilt Sentinel-2 target, repeated to 10 m, reproduces the MethaneSET target.

Only the two shortwave infrared bands enter the analysis. Each acquisition is stored as one 2 × 512 × 512 uint16 array of these bands, centred on the chip, which covers 10.24 km at 20 m and 15.36 km at 30 m.

### 2.2 Analysis

The detector is a ratio form of the multi-band multi-pass method (Varon et al., 2021). It runs in five steps.

1. Convert each acquisition from DN to reflectance with the scale and offset of its own product. Sentinel-2 products from processing baseline 04.00 onwards carry an offset of -1000 DN (`RADIO_ADD_OFFSET`), and Landsat products give `REFLECTANCE_MULT_BAND_x` and `REFLECTANCE_ADD_BAND_x`. Backgrounds can come from other baselines, so a ratio of raw DN would mix offsets.
2. Repeat each band to the 10 m grid of the chip, and cut the chip out of the window.
3. Take the per-pixel median of the four backgrounds, for each band, as the reference `R`.
4. Compute the enhancement `e = 1 - (T2 / R2) / (T1 / R1)`, where `T` is the target, band 1 is B11 or B6, and band 2 is B12 or B7. A plume makes `e` positive.
5. Set the threshold `t` to the 99.5th percentile of `e` outside the plume mask `P`, on the original. The detection is `D = e > t`.

The threshold and the reference of the original are kept, and steps 1 to 4 and the detection are repeated on the decoded copy. Each sample gives four outcomes.

| outcome | definition |
| --- | --- |
| `recall` | `count(D and P) / count(P)`, the part of the plume detected |
| `false_alarms` | `count(D and not P)`, the detections outside the plume |
| `ime_ratio` | the sum of `e` over `P` on the decoded copy, divided by the same sum on the original |
| `flux` | `detection:ch4_fluxrate × ime_ratio` |

The conversion from enhancement to column mass, the wind speed and the plume length are the same for the original and the decoded copy. To first order the emission rate then scales with the enhancement integrated over the mask (Varon et al., 2018), so the decoded rate is the reported rate times `ime_ratio`. Its change is also read against `detection:ch4_fluxrate_std`, the uncertainty the producers report.

### 2.3 Budgets

Sentinel-2 uses the budgets of `s2-l1c-20m-6`, which holds B11 and B12, and Landsat those of `l8-oli-8`, which holds B6 and B7. The noise reference uses the `sigma` of the same corpora, added to the target and to each background. Landsat 9 uses the Landsat 8 values.

| sensor | corpus | `sigma` | `conservative` | `matched` | `aggressive` |
| --- | --- | ---: | ---: | ---: | ---: |
| Sentinel-2 | `s2-l1c-20m-6` | 7 DN | 1 DN | 7 DN | 28 DN |
| Landsat 8/9 | `l8-oli-8` | 10 DN | 2 DN | 10 DN | 40 DN |

### 2.4 Results

`results.csv` has one row per sample and configuration, with `sample_id`, `sensor`, `configuration`, `family`, `tau`, `budget_level`, `recall`, `recall_original`, `false_alarms`, `false_alarms_original`, `ime_ratio`, `flux`, `flux_std` and `fidelity_ok`. The noise reference is a row with configuration `noise`.

The summary is given per sensor, budget level and configuration, and again per tercile of emission rate. It reports the median and the 90th percentile over samples of three changes, which are the change in `recall`, the ratio of `false_alarms` to the original, and the relative change in `flux`. Beside them it gives the same values for the noise reference and the fraction of samples whose `flux` changed by more than `flux_std`.

A first check, on the ten clearest Sentinel-2 plumes and on the MethaneSET grid, used a uniform quantiser. With a bound of 28 DN, `recall` and `ime_ratio` stayed within 3% of the original while `false_alarms` grew by a factor of 2.4. With 7 DN, `false_alarms` grew by 6%. An overlap score with the original detection fell to 0.72 at 28 DN and could not tell these effects apart.

### 2.5 Limits

- The detector is the classical ratio method. A detector trained on MethaneSET may respond differently, in particular to block artefacts, and can be added as a second analysis under the same rules.
- The emission rate is scaled from the reported one, not retrieved again. A retrieval that converts enhancement to column mass with radiative transfer is not linear for strong plumes.
- The plume mask is fixed, so a codec that widens a plume beyond the mask shows as false alarms rather than as a larger plume.
- Two bands enter the analysis, so a codec that exploits the correlation across all bands of a sensor is measured on two of them.

## References

- Varon, D. J., et al. (2018). Quantifying methane point sources from fine-scale satellite observations of atmospheric methane plumes. *Atmos. Meas. Tech.*, 11, 5673–5686.
- Varon, D. J., et al. (2021). High-frequency monitoring of anomalous methane point sources with multispectral Sentinel-2 satellite observations. *Atmos. Meas. Tech.*, 14, 2771–2785.
