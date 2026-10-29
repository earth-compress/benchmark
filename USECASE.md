# Use cases

A use case runs one analysis on the original samples and on their decoded copies, and reports one metric of how its result changes. The analysis is fitted once on the original and reused on the decoded copy. Every array the analysis reads passes through the codec, and labels never do. Each use case states the configurations of [CODECS.md](CODECS.md) it runs and the error bounds it runs them at.

| use case | data | samples | metric |
| --- | --- | ---: | --- |
| [Methane plumes](#methane-plumes) | MethaneSET, Sentinel-2 and Landsat 8/9 | 20 | `delta_iou` |
| [Drainage networks](#drainage-networks) | `cop-dem-glo30` | 10 | `stream_f1` |
| [Change detection](#change-detection) | AlphaEarth, 2017 and 2025 | 13 | `change_iou` |

Each use case keeps its code and results in `usecases/<use-case>/` and its samples on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/usecases). `run.py` downloads the samples it lacks and writes `results.csv` with one row per sample and configuration. `build.py`, where there is one, rebuilds the samples from their source.

```bash
uv run python usecases/methane/run.py
uv run python usecases/drainage/run.py
uv run python usecases/change-detection/run.py
```

## Methane plumes

Does compression change the plume a methane detector finds in Sentinel-2 and Landsat 8/9?

### Experiment

The experiment takes 20 patches of MethaneSET, 10 from Sentinel-2 and 10 from Landsat 8/9, which are on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/usecases/methane/npz). Each patch holds a target, its backgrounds and a plume mask, on its native grid of 20 m for Sentinel-2 and 30 m for Landsat. A band ratio detector, fitted once on the original, then runs again on each compressed copy. The result is `delta_iou`, how much the overlap between the detection and the plume mask changes.

### Data

Twenty patches from [MethaneSET](https://huggingface.co/datasets/tacofoundation/methaneset), ten per sensor, the ones chosen in [lossy-plume-test](https://github.com/JulioContrerasH/lossy-plume-test). Each patch holds a target, four backgrounds and a plume mask. MethaneSET puts every band on a 10 m grid of 200 × 200 pixels by repeating each pixel, over 2 × 2 cells for the 20 m shortwave infrared bands of Sentinel-2 and over 3 × 3 cells for the 30 m bands of Landsat. `build.py` keeps the two shortwave infrared bands and one value per repeated block, so every patch is compressed and evaluated on its native grid. The plume mask, drawn at 10 m, becomes plume where it covers most of a native pixel.

| sensor | collection | bands | pixel | shape | patches |
| --- | --- | --- | ---: | --- | ---: |
| Sentinel-2 | `methaneset-s2-finetune` | B11, B12 | 20 m | 2 × 100 × 100 or one row or column less | 10 |
| Landsat 8/9 | `methaneset-l89-finetune` | B6, B7 | 30 m | 2 × 66 × 66 | 10 |

The target and each background are compressed as separate arrays, all uint16. The plume mask is never compressed. Landsat uses only `bg0` as background, because `bg1` to `bg3` are stored in DN and the target in reflectance, and `build.py` stores its reflectance as uint16 DN of 2e-5, as `l8-oli-8` does, which moves no value by more than half a DN. In `methane-s2-08` the background `bg0` is not repeated in MethaneSET, so its native grid keeps one of every 2 × 2 values. The patches keep the CC BY-NC-SA 4.0 licence of MethaneSET.

### Detector

1. The reference `R` is the median of the backgrounds.
2. The enhancement is `e = (T2 / R2) / (T1 / R1) - 1`, with its sign chosen on the original so that the plume is positive.
3. The threshold `t` is the 99.5th percentile of `e` outside the mask, and the detection is `D = e > t`.

The sign and `t` of the original are kept for the decoded copy.

### Compression

GeoZL with PIVCO, GeoZL with PFOR and JPEG XL compress the two shortwave infrared bands of the target and of each background, and the plume mask stays as it is. The use case runs the lossy mode of the benchmark, which holds the root-mean-square error of each array within a bound. The bounds are the same reflectance in both sensors, from 1 to 64 × 10⁻⁴, doubling at each step. One DN is 10⁻⁴ of reflectance in Sentinel-2 L1C and 2 × 10⁻⁵ in Landsat, so the bounds are 1 to 64 DN in Sentinel-2 and 5 to 320 DN in Landsat. GeoZL with PIVCO (`geozl-med-pivco`) and with PFOR (`geozl-planar-pfor`) runs behind the lossy quantiser of the benchmark, so both decode the same arrays and differ only in size. JPEG XL searches its distance on each array, and stores the array losslessly when no distance keeps the bound.

### Metric

`delta_iou` is the intersection over union of the detection and the plume mask on the compressed copy, minus the same value on the original. A negative value means the decoded copy finds the plume worse, through missed plume pixels or through false alarms around it. On the originals the median IoU is 0.59 in Sentinel-2 and 0.55 in Landsat.

## Drainage networks

Does compression move the streams that flow routing draws on a DEM?

### Experiment

The experiment takes 10 DEMs of the corpus `cop-dem-glo30`, two from each regime, which are on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/cop-dem-glo30/npz) with the rest of the corpus. Flow routing draws the stream network of the original DEM and then runs again on each compressed copy. The result is `stream_f1`, how well the compressed network matches the original one within one cell.

### Data

Ten samples of `cop-dem-glo30`, the first two of each regime (mountain, hill, plain, coastal and desert), each 512 × 512 cells of 1 arcsecond. The corpus stores heights as float32 metres, and `run.py` stores each DEM as uint16 decimetres above its lowest whole metre, which JPEG XL takes and which moves no height by more than 5 cm. The analysis runs on these decimetres, on the original and on every compressed copy.

### Analysis

1. A priority flood from the edges of the sample reaches every cell from the lowest cell around it, and each cell drains to the cell that reached it. Pits and flats drain too, flats in the order the flood reaches them.
2. The upstream count of a cell is the number of cells that drain through it.
3. A cell with 1000 or more upstream cells, under 1 km², is a stream.

### Compression

GeoZL with PIVCO, GeoZL with PFOR and JPEG XL compress the DEM. The use case runs the lossy mode of the benchmark, which holds the root-mean-square error of each array within a bound. The bounds go from 0.1 to 6.4 m and double at each step. GeoZL with PIVCO (`geozl-med-pivco`) and with PFOR (`geozl-planar-pfor`) runs behind the lossy quantiser of the benchmark, so both decode the same arrays and differ only in size. JPEG XL searches the largest distance within the bound, and stores the array losslessly when no distance keeps it. In flat terrain its largest distance already keeps the larger bounds, so it flattens the DEM and those bounds share one point.

### Metric

`stream_f1` is the F1 score of the compressed stream network against the original one. Its precision is the share of compressed stream cells within one cell of an original stream, its recall the share of original stream cells within one cell of a compressed stream. It is 1 when the two networks agree.

## Change detection

Does compression change where AlphaEarth embeddings show change between 2017 and 2025?

### Experiment

The experiment takes 13 AlphaEarth windows where the land changed between 2017 and 2025, from cleared and burned forest to a filled reservoir, a drained one, new lava, new cities, airports and industry. Both years of each window are on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/usecases/change-detection/npz). The change map of the original runs again on each compressed copy of both years. The result is `change_iou`, the overlap of the compressed change map with the original one.

### Data

`build.py` reads 13 windows of 5 km from the annual AlphaEarth files of 2017 and 2025, at places of known change. Each window was picked by eye within 10 km of the place, among those with about 40% of their pixels changed, so it holds both land that changed and land that did not. Each year is an int8 array of 64 × 512 × 512 at 10 m with NoData at -128. `run.py` adds 128 to every code to store it as uint8, which JPEG XL takes, so no value changes and NoData becomes 0. The windows keep the CC BY 4.0 licence of the AlphaEarth Foundations Satellite Embedding dataset, produced by Google and Google DeepMind.

### Analysis

1. Each year is dequantised as `(v / 127.5)² · sign(v)`, with `v` the int8 code.
2. The similarity of a pixel is the cosine between its two embeddings.
3. A pixel has changed when its similarity is below 0.8. A pixel with NoData in either year has not changed.

### Compression

GeoZL with PIVCO, GeoZL with PFOR and JPEG XL compress the embeddings of both years. The use case runs the lossy mode of the benchmark, which holds the root-mean-square error of each array within a bound. The bounds go from 1 to 16 codes of the quantised embedding and double at each step. GeoZL with PIVCO (`geozl-med-pivco`) and with PFOR (`geozl-planar-pfor`) runs behind the lossy quantiser of the benchmark, so both decode the same arrays and differ only in size. JPEG XL searches its distance on each array, and stores the array losslessly when no distance keeps the bound.

### Metric

`change_iou` is the intersection over union of the compressed change map and the original one. It is 1 when the two maps agree.
