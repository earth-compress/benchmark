# Use cases

A use case runs one analysis on the original samples and on their decoded copies, and reports one metric of how its result changes. The analysis is fitted once on the original and reused on the decoded copy. Every array the analysis reads passes through the codec, and labels never do. Each use case states the configurations of [CODECS.md](CODECS.md) it runs and the error bounds it runs them at.

| use case | data | samples | metric |
| --- | --- | ---: | --- |
| [Methane plumes](#methane-plumes) | MethaneSET, Sentinel-2 and Landsat 8/9 | 20 | `delta_iou` |
| [Drainage networks](#drainage-networks) | `cop-dem-glo30` | 10 | `stream_f1` |
| [Change detection](#change-detection) | `alphaearth-v1-64`, 2017 and 2025 | 6 | `change_iou` |

Each use case keeps its code and results in `usecases/<use-case>/` and its samples on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/usecases). `run.py` downloads the samples it lacks and writes `results.csv` with one row per sample and configuration. `build.py`, where there is one, rebuilds the samples from their source.

```bash
uv run python usecases/methane/run.py
uv run python usecases/drainage/run.py
uv run python usecases/change-detection/run.py
```

## Methane plumes

Does compression change the plume a methane detector finds in Sentinel-2 and Landsat 8/9?

### Experiment

The experiment takes 20 patches of MethaneSET, 10 from Sentinel-2 and 10 from Landsat 8/9, which are on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/usecases/methane/npz). Each patch holds a target, its backgrounds and a plume mask. GeoZL with PIVCO and JPEG XL compress the two shortwave infrared bands of the target and of each background in lossy mode, at root-mean-square errors from 1 to 64 DN, while the mask stays as it is. A band ratio detector, fitted once on the original, then runs again on the decoded copy. The result is `delta_iou`, how much the overlap between the detection and the plume mask changes.

### Data

Twenty patches from [MethaneSET](https://huggingface.co/datasets/tacofoundation/methaneset), ten per sensor, the ones chosen in [lossy-plume-test](https://github.com/JulioContrerasH/lossy-plume-test). Each patch is 200 × 200 pixels at 10 m and holds a target, four backgrounds and a plume mask. `build.py` keeps the two shortwave infrared bands.

| sensor | collection | bands | dtype | patches |
| --- | --- | --- | --- | ---: |
| Sentinel-2 | `methaneset-s2-finetune` | B11, B12 | uint16 | 10 |
| Landsat 8/9 | `methaneset-l89-finetune` | B6, B7 | float32 reflectance | 10 |

The target and each background are compressed as separate arrays of 2 × 200 × 200. The plume mask is never compressed. Landsat uses only `bg0` as background, because `bg1` to `bg3` are stored in DN and the target in reflectance. The patches keep the CC BY-NC-SA 4.0 licence of MethaneSET.

### Detector

1. The reference `R` is the median of the backgrounds.
2. The enhancement is `e = (T2 / R2) / (T1 / R1) - 1`, with its sign chosen on the original so that the plume is positive.
3. The threshold `t` is the 99.5th percentile of `e` outside the mask, and the detection is `D = e > t`.

The sign and `t` of the original are kept for the decoded copy.

### Errors

The use case runs the lossy mode of the benchmark, which holds the root-mean-square error of each array within a bound. The bounds go from 1 to 64 DN and double at each step, and Landsat converts them to reflectance at 2e-5 per DN. GeoZL with PIVCO (`geozl-med-pivco`) runs behind the lossy quantiser of the benchmark, and JPEG XL searches its distance on each array. JPEG XL takes integers only, so it runs on Sentinel-2.

### Metric

`delta_iou` is the intersection over union of `D` and the plume mask on the decoded copy, minus the same value on the original. A negative value means the decoded copy finds the plume worse, through missed plume pixels or through false alarms around it. On the originals the median IoU is 0.57 in Sentinel-2 and 0.55 in Landsat.

### Results

Both codecs leave the detection almost unchanged up to an error of 4 DN in Sentinel-2, below the 7 DN noise of its bands. GeoZL with PIVCO then reaches 14 times at 8 DN with a median change of -0.010, and 20 times at 16 DN, where the median falls to -0.083 and the worst patch to -0.305. JPEG XL holds the detection better at the same error, -0.021 at 16 DN with 18 times and -0.093 at 32 DN with 41 times. Below 8 DN it finds no distance within the bound and stores the patches losslessly, at 8 times. In Landsat, GeoZL with PIVCO reaches 27 times at 8 DN with a median of -0.002, and 32 times at 16 DN with -0.010. MethaneSET repeats each 20 m pixel of Sentinel-2 over 2 × 2 cells and each 30 m pixel of Landsat over 3 × 3, so every ratio here is higher than it would be on the native grid.

## Drainage networks

Does compression move the streams that flow routing draws on a DEM?

### Experiment

The experiment takes 10 DEMs of the corpus `cop-dem-glo30`, two from each regime, which are on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/cop-dem-glo30/npz) with the rest of the corpus. Every codec compresses the DEM, and flow routing draws the stream network of the original and of the decoded copy, where a stream is every cell with 1000 or more cells upstream. The result is `stream_f1`, how well the decoded network matches the original one within one cell.

### Data

Ten samples of `cop-dem-glo30` as stored in the corpus, the first two of each regime (mountain, hill, plain, coastal and desert).

### Analysis

1. A priority flood from the edges of the sample reaches every cell from the lowest cell around it, and each cell drains to the cell that reached it. Pits and flats drain too, flats in the order the flood reaches them.
2. The upstream count of a cell is the number of cells that drain through it.
3. A cell with 1000 or more upstream cells, under 1 km², is a stream.

### Budgets

The levels of `cop-dem-glo30`, 0.25 m, 1 m and 4 m.

### Metric

`stream_f1` is the F1 score of the decoded stream network against the original one, where a stream cell matches when the other network passes within one cell. It is 1 when the two networks agree.

### Results

Median and worst `stream_f1` over the two samples of each regime and 17 configurations.

| regime | conservative | matched | aggressive |
| --- | ---: | ---: | ---: |
| mountain | 0.97 (0.96) | 0.93 (0.90) | 0.79 (0.76) |
| hill | 0.99 (0.98) | 0.96 (0.96) | 0.91 (0.86) |
| plain | 0.86 (0.43) | 0.65 (0.24) | 0.27 (0.09) |
| coastal | 0.76 (0.50) | 0.66 (0.34) | 0.50 (0.15) |
| desert | 0.89 (0.79) | 0.64 (0.60) | 0.36 (0.32) |

The network holds in relief and moves in flat terrain, where a bound of 0.25 m already brings the Pampas sample to 0.43.

## Change detection

Does compression change where AlphaEarth embeddings show change between 2017 and 2025?

### Experiment

The experiment takes 6 AlphaEarth windows where the land changed between 2017 and 2025. The 2025 embeddings are samples of the corpus `alphaearth-v1-64`, and the 2017 ones are on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/usecases/change-detection/npz) next to them. Every codec compresses both years, and a pixel counts as changed when the cosine similarity of its two years is below 0.8, on the original and on the decoded copy. The result is `change_iou`, the overlap of the decoded change map with the original one.

### Data

The 15 samples of `alphaearth-v1-64`, which are from 2025, and the same windows in 2017, read by `build.py` from the same AlphaEarth files. Each year is an int8 array of 64 × 512 × 512 with NoData at -128, and both years are compressed. The 2017 windows keep the CC BY 4.0 licence of the AlphaEarth Foundations Satellite Embedding dataset, produced by Google and Google DeepMind.

The use case keeps the six samples whose original change map covers at least 0.5% of the sample. With less change, a single changed pixel on the decoded copy moves the IoU between 1 and 0.

### Analysis

1. Each year is dequantised as `(v / 127.5)² · sign(v)`.
2. The similarity of a pixel is the cosine between its two embeddings.
3. A pixel has changed when its similarity is below 0.8. A pixel with NoData in either year has not changed.

### Budgets

`alphaearth-v1-64` has no budget in `TOLERANCE.md`. The use case runs bounds of 1, 4 and 16 int8 codes, so its result is what such a budget would rest on.

### Metric

`change_iou` is the intersection over union of the decoded change map and the original one. It is 1 when the two maps agree.

### Results

Median and worst `change_iou` over the 17 configurations of each bound.

| site | changed area | 1 code | 4 codes | 16 codes |
| --- | ---: | ---: | ---: | ---: |
| tokyo | 1.1% | 0.98 (0.97) | 0.89 (0.87) | 0.30 (0.27) |
| lagos | 2.6% | 0.97 (0.96) | 0.86 (0.82) | 0.15 (0.13) |
| iowa | 8.3% | 0.99 (0.99) | 0.96 (0.95) | 0.51 (0.46) |
| pampas | 5.8% | 0.95 (0.92) | 0.76 (0.74) | 0.13 (0.09) |
| namib | 0.6% | 0.93 (0.91) | 0.71 (0.64) | 0.02 (0.02) |
| wadden | 1.7% | 0.98 (0.97) | 0.92 (0.90) | 0.47 (0.43) |

A bound of one code keeps every change map above 0.90. At 16 codes the result depends on the codec, from a median of 0.97 with `zfp-accuracy` to 0.20 with the shared quantiser.
