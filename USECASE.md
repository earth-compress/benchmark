# Use cases

These use cases check whether compression changes methane plume detection, drainage mapping, land change detection, cloud masking or cloud properties. Each analysis runs on original data and decoded copies, then compares the outputs. Settings fitted on the original are reused. Labels are never compressed. Each case lists its codec configurations and error bounds.

| use case | data | samples | metric |
| --- | --- | ---: | --- |
| [Methane plumes](#methane-plumes) | MethaneSET, Sentinel-2 and Landsat 8/9 | 20 | `delta_iou` |
| [Drainage networks](#drainage-networks) | `cop-dem-glo30` | 10 | `stream_f1` |
| [Change detection](#change-detection) | AlphaEarth, 2017 and 2025 | 13 | `change_iou` |
| [Clouds Decoded](#clouds-decoded) | `EC-prototype-S2L1C`, Sentinel-2 L1C | 100 | `cloud_iou` and five others |

Code, manifests and results live in `usecases/<use-case>/`. `run.py` reads the samples and writes one row per sample and configuration to `results.csv`. Where provided, `build.py` rebuilds samples from their source.

```bash
uv run --extra corpus python usecases/methane/run.py
uv run --extra corpus python usecases/drainage/run.py
uv run --extra corpus python usecases/change-detection/run.py
uv run --extra corpus python usecases/clouds-decoded/run.py
```

## Methane plumes

Does compression change the plume a methane detector finds in Sentinel-2 and Landsat 8/9?

### Experiment

We use 20 MethaneSET patches at their native grids, ten from Sentinel-2 at 20 m and ten from Landsat 8/9 at 30 m. Each has a target image, backgrounds and a plume mask. We fit a band ratio detector on the original images, run it after compression and compare each detection's overlap with the mask. The difference is `delta_iou`.

### Data

The patches come from [MethaneSET](https://huggingface.co/datasets/tacofoundation/methaneset) and were chosen in [lossy-plume-test](https://github.com/JulioContrerasH/lossy-plume-test). MethaneSET provides four backgrounds per target and repeats each pixel on a 10 m grid of 200 × 200 cells. `build.py` keeps the two shortwave infrared bands and one value per 2 × 2 block for Sentinel-2 or 3 × 3 block for Landsat, bringing each patch back to its native grid. A native pixel counts as plume when most of its 10 m mask cells are plume.

| sensor | collection | bands | pixel | shape | patches |
| --- | --- | --- | ---: | --- | ---: |
| Sentinel-2 | `methaneset-s2-finetune` | B11, B12 | 20 m | 2 × 100 × 100 or one row or column less | 10 |
| Landsat 8/9 | `methaneset-l89-finetune` | B6, B7 | 30 m | 2 × 66 × 66 | 10 |

The target and backgrounds are separate uint16 arrays. The plume mask is never compressed. Landsat uses only `bg0` because `bg1` to `bg3` are stored in DN while the target is in reflectance. `build.py` converts the target to uint16 DN at 2e-5, as `l8-oli-8` does. The conversion moves no value by more than half a DN. In `methane-s2-08`, MethaneSET does not repeat `bg0`, so `build.py` keeps one value per 2 × 2 block. The patches retain MethaneSET's CC BY-NC-SA 4.0 licence.

### Detector

1. The reference `R` is the median of the backgrounds.
2. The enhancement is `e = (T2 / R2) / (T1 / R1) - 1`, with its sign chosen on the original so that the plume is positive.
3. The threshold `t` is the 99.5th percentile of `e` outside the mask, and the detection is `D = e > t`.

The sign and `t` of the original are kept for the decoded copy.

### Compression

GeoZL PIVCO, GeoZL PFOR and JPEG XL compress the two shortwave infrared bands of the target and each background. The plume mask stays untouched. The root-mean-square error limit doubles from 1 to 64 × 10⁻⁴ reflectance in both sensors. One DN is 10⁻⁴ reflectance for Sentinel-2 L1C and 2 × 10⁻⁵ for Landsat. The sweep therefore covers 1 to 64 DN in Sentinel-2 and 5 to 320 DN in Landsat. The GeoZL recipes (`geozl-med-pivco` and `geozl-planar-pfor`) share the benchmark's lossy quantiser, so they decode to the same arrays and differ in size. JPEG XL searches for a distance within the limit and stores an array losslessly if none fits.

### Metric

`delta_iou` is the detection's intersection over union with the plume mask on the compressed copy, minus the same value on the original. A negative value means less overlap with the mask, from missed plume pixels or false alarms around it. On the originals, the median IoU is 0.59 in Sentinel-2 and 0.55 in Landsat.

## Drainage networks

Does compression move the streams that flow routing draws on a DEM?

### Experiment

We run flow routing on ten DEM patches from `cop-dem-glo30`, before and after compression. `stream_f1` compares the resulting stream networks within one cell.

### Data

We take the first two samples from each regime in [`cop-dem-glo30`](https://huggingface.co/datasets/earth-compress/benchmark/tree/main/cop-dem-glo30/npz) (mountain, hill, plain, coastal and desert). Each has 512 × 512 cells at 1 arcsecond. The corpus stores heights as float32 metres. To let JPEG XL run, `run.py` converts each DEM to uint16 decimetres above its lowest whole metre, moving heights by at most 5 cm. Flow routing uses these decimetres for both the original and decoded DEMs.

### Analysis

1. A priority flood from the edges of the sample reaches every cell from the lowest cell around it, and each cell drains to the cell that reached it. Pits and flats drain too, flats in the order the flood reaches them.
2. The upstream count of a cell is the number of cells that drain through it.
3. A cell with 1000 or more upstream cells, under 1 km², is a stream.

### Compression

The DEM goes through GeoZL PIVCO, GeoZL PFOR or JPEG XL at root-mean-square error limits from 0.1 to 6.4 m, doubling each step. The GeoZL recipes `geozl-med-pivco` and `geozl-planar-pfor` use the same lossy quantiser. They decode to the same heights, but their compressed sizes differ. JPEG XL searches for the largest distance within the limit and falls back to lossless if none fits. On some flat DEMs, its largest distance already meets the larger limits, so those limits give the same point.

### Metric

`stream_f1` is the F1 score of the compressed stream network against the original one. Precision is the share of compressed stream cells within one cell of an original stream. Recall is the share of original stream cells within one cell of a compressed stream. `stream_f1` is 1 when the two networks agree.

## Change detection

Does compression change where AlphaEarth embeddings show change between 2017 and 2025?

### Experiment

At 13 sites with known land change, we take matching AlphaEarth windows from 2017 and 2025. The sites include the Dixie Fire, the GERD reservoir and areas of new construction. We make a change map from the original embeddings, compress both years and make the map again. `change_iou` measures the overlap between the maps.

### Data

`build.py` reads a 5 km window for each site from the [annual AlphaEarth files](https://developers.google.com/earth-engine/guides/aef_on_gcs_readme). The windows were picked by eye within 10 km of each site to include both changed and unchanged land. On the original change maps, 27–50% of pixels are marked as changed. Each year is an int8 array of 64 × 512 × 512 at 10 m, with NoData at -128. `run.py` shifts the codes by 128 to uint8 for JPEG XL. This is reversible, and NoData becomes 0. The windows retain the CC BY 4.0 licence of the AlphaEarth Foundations Satellite Embedding dataset, produced by Google and Google DeepMind.

### Analysis

1. Each year is dequantised as `(v / 127.5)² · sign(v)`, with `v` the int8 code.
2. The similarity of a pixel is the cosine between its two embeddings.
3. A pixel has changed when its similarity is below 0.8. A pixel with NoData in either year has not changed.

### Compression

Both years are compressed separately with GeoZL PIVCO, GeoZL PFOR and JPEG XL. The root-mean-square error limit doubles from 1 to 16 codes of the quantised embedding. The GeoZL recipes (`geozl-med-pivco` and `geozl-planar-pfor`) use the same lossy quantiser, so they decode to identical arrays and differ only in size. JPEG XL searches for a distance within the limit and stores an array losslessly if none fits.

### Metric

`change_iou` is the intersection over union of the compressed change map and the original one. It is 1 when the two maps agree.

## Clouds Decoded

Does compression affect the cloud mask and cloud properties retrieved by Clouds Decoded from Sentinel-2 data?

### Experiment

We use 100 Sentinel-2 Level-1C products of one Bay of Bengal tile, sensed between 2017 and 2026. The products were compressed with georvq, SZ3 and JPEG XL and are on [Hugging Face](https://huggingface.co/datasets/earth-compress/EC-prototype-S2L1C). We run Clouds Decoded on each original product and each compressed copy. We then compare the two sets of outputs on cloud mask, cloud top height, optical thickness and ice effective radius.

### Data

All products are of tile T44PNB, with the 13 bands at their native resolution (10, 20 and 60 m) as uint16 DN. Each product is a `.SAFE` directory with the original metadata and the compressed bands at every level of one codec. The `compressed-readers` branch of [Clouds Decoded](https://github.com/asterisk-labs/clouds-decoded) reads them like ESA products. The products follow the Copernicus Sentinel data terms.

### Analysis

1. Clouds Decoded (CD) runs its full workflow on the original product.
2. It runs again on the data from each compression level, with the same settings.
3. `run.py` compares the CD outputs and writes `results.csv`. Since running CD takes a long time, `run.py` downloads the outputs of these runs (about 48 GB): the cloud mask, cloud top height and cloud properties as GeoTIFFs, with local paths removed from their metadata.

`levels.csv` holds the compression ratio and root-mean-square error of each product and level. `run.py` reads them from it because measuring them again needs the original products and decoding every level. The compression ratio is the bytes of the 13 bands as uint16 over the bytes of their compressed image data, leaving out metadata. The root-mean-square error compares the decoded bands with the original ones in DN, over all pixels of the 13 bands except where the original is 0.

### Compression

georvq, SZ3 and JPEG XL compress all 13 bands. georvq s2-v1 codes the 13 bands of each 36 pixel window together with learned codebooks, at levels 8-8, 8-4 and 8-0. SZ3 codes each band separately with an absolute error limit of 45, 90, 125 or 180 DN. JPEG XL codes each band separately as a 16-bit image at distances 0.094, 0.33 and 1.2, with effort 7. The SZ3 and JPEG XL settings were tuned on 4 products to match the georvq rates. Both cut each band into 10 × 10 tiles and store the zero mask of each tile losslessly. Rates are in bits per 10 m pixel. The 13 original bands take about 52 in lossless JPEG 2000.

### Metric

| | metric | meaning | no change |
| ---: | --- | --- | ---: |
| 1 | `cloud_iou` | Intersection over union of the two cloud masks | 1 |
| 2 | `cth_mae` | Mean absolute change in cloud top height, in metres | 0 |
| 3 | `cth_bias` | Mean change in cloud top height, in metres | 0 |
| 4 | `tau_median_rel_error` | Median of the absolute relative change in optical thickness, in % | 0 |
| 5 | `re_ice_mae` | Mean absolute change in ice effective radius, in µm | 0 |
| 6 | `re_ice_texture` | Mean difference between neighbouring pixels of ice effective radius, compressed over original | 1 |
