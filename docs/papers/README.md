# Papers

Reference copies of the work cited in the Earth Compress report. The PDFs sit
in this directory but are **not tracked by git**: several come from publishers
that do not allow redistribution, and the open-access ones add 285 MB. Fetch
them with the links below.

## Benchmarks and evaluation

The five studies the report's section on evaluation is built from.

| key | paper | source |
| --- | --- | --- |
| `reichelt2026climatebenchpress` | ClimateBenchPress (v1.0): a benchmark for lossy compression of climate data | [GMD 19, 5933–5960](https://gmd.copernicus.org/articles/19/5933/2026/) |
| `zhao2020sdrbench` | SDRBench: Scientific Data Reduction Benchmark for Lossy Compressors | [arXiv 2101.03201](https://arxiv.org/abs/2101.03201) |
| `tao2019zchecker` | Z-checker: A framework for assessing lossy compression of scientific data | [arXiv 1707.09320](https://arxiv.org/abs/1707.09320) |
| `baker2016evaluating` | Evaluating lossy data compression on climate simulation data within a large ensemble | [GMD 9, 4381–4403](https://gmd.copernicus.org/articles/9/4381/2016/) |
| `delaunay2019evaluation` | Evaluation of lossless and lossy algorithms for the compression of scientific datasets in netCDF-4 or HDF5 files | [GMD 12, 4099–4113](https://gmd.copernicus.org/articles/12/4099/2019/) |

## Error-bounded compression

| key | paper | source |
| --- | --- | --- |
| `liang2021sz3` | SZ3: A Modular Framework for Composing Prediction-Based Error-Bounded Lossy Compressors | [arXiv 2111.02925](https://arxiv.org/abs/2111.02925) |
| `tian2020cusz` | cuSZ: An Efficient GPU-Based Error-Bounded Lossy Compression Framework | [arXiv 2007.09625](https://arxiv.org/abs/2007.09625) |
| `wu2025boosting` | Boosting Scientific Error-Bounded Lossy Compression through Optimized Synergistic Lossy-Lossless Orchestration | [arXiv 2507.11165](https://arxiv.org/abs/2507.11165) |
| `huang2025error` | EBCC v0.2: error-bounded compression for weather and climate applications | [arXiv 2510.22265](https://arxiv.org/abs/2510.22265) |
| `tyree2026safeguards` | Compression Safeguards: Building Trust into Lossy Data Compression | [EGUsphere 2026-4266](https://egusphere.copernicus.org/preprints/2026/egusphere-2026-4266/) |

## Learned compression

| key | paper | source |
| --- | --- | --- |
| `balle2018variational` | Variational Image Compression with a Scale Hyperprior | [arXiv 1802.01436](https://arxiv.org/abs/1802.01436) |
| `huang2022compressing` | Compressing multidimensional weather and climate data into neural networks | [arXiv 2210.12538](https://arxiv.org/abs/2210.12538) |
| `han2024cra5` | CRA5: Extreme Compression of ERA5 for Portable Global Climate and Weather Research | [arXiv 2405.03376](https://arxiv.org/abs/2405.03376) |
| `mirowski2024neural` | Neural Compression of Atmospheric States | [arXiv 2407.11666](https://arxiv.org/abs/2407.11666) |
| `costawatanabe2025terracodec` | TerraCodec: Compressing Optical Earth Observation Data | [arXiv 2510.12670](https://arxiv.org/abs/2510.12670) |
| `alhumaidi2026can` | Can Deep Neural Networks Improve Compression of Very Large Scientific Data? | [arXiv 2606.14353](https://arxiv.org/abs/2606.14353) |

## Embeddings and spatial primitives

| key | paper | source |
| --- | --- | --- |
| `brown2025alphaearth` | AlphaEarth Foundations: An embedding field model for global mapping from sparse label data | [arXiv 2507.22291](https://arxiv.org/abs/2507.22291) |
| `feng2025tessera-v2` | TESSERA v2: Scaling Pixel-wise Earth Foundation Models | [arXiv 2607.03949](https://arxiv.org/abs/2607.03949) |
| `zhang2024gaussianimage` | GaussianImage: 1000 FPS Image Representation and Compression by 2D Gaussian Splatting | [arXiv 2403.08551](https://arxiv.org/abs/2403.08551) |
| `zhang2025imagegs` | Image-GS: Content-Adaptive Image Representation via 2D Gaussians | [arXiv 2407.01866](https://arxiv.org/abs/2407.01866) |

## Infrastructure

| key | paper | source |
| --- | --- | --- |
| `collet2025openzl` | OpenZL: A Graph-Based Model for Compression | [arXiv 2510.03203](https://arxiv.org/abs/2510.03203) |
| `zukowski2026pivco` | PivCo-Huffman | [arXiv 2606.05765](https://arxiv.org/abs/2606.05765) |
| `francis2024major` | Major TOM: Expandable Datasets for Earth Observation | [arXiv 2402.12095](https://arxiv.org/abs/2402.12095) |

## Not found

Searched and not located. Three of these carry numbers the report leans on.

| key | what the report cites it for | status |
| --- | --- | --- |
| `rao2026planetary` | Planetary Feature Fields: 1800x ratio, 90% of downstream performance, 96 TB per year of global embeddings, 18x faster than the Earth Engine API. Figure 3 and route E rest on it. | No paper of that title or author found. Need the real reference. |
| `liu2025gshsi` | GS-HSI, reuse across bands in hyperspectral Gaussian splatting | Not found |
| `fristrup2026apexquant` | 4-bit weight quantisation within a few percent of full precision without calibration data | Not found |
| `earthcompress2026prototype` | The four GeoRVQ rate points in the rate-distortion figure | Internal, not public |
| `aybar2026ecbenchmark` | The 25 corpora and the measurement protocol | This repository |

## Not openly available

Behind a paywall or served only through a publisher page.

| key | paper | where |
| --- | --- | --- |
| `balle2019integer` | Integer Networks for Data Compression with Latent-Variable Models | ICLR 2019, OpenReview blocks direct fetch |
| `hersbach2020era5` | The ERA5 global reanalysis | QJRMS, Wiley blocks direct fetch |
| `drusch2012sentinel` | Sentinel-2: ESA's Optical High-Resolution Mission | Remote Sensing of Environment, Elsevier |
| `weinberger2000loco` | LOCO-I: the JPEG-LS lossless image compression algorithm | IEEE TIP |
| `lindstrom2014fixed` | Fixed-Rate Compressed Floating-Point Arrays | IEEE TVCG |
| `zukowski2006super` | Super-Scalar RAM-CPU Cache Compression | IEEE ICDE |
| `he2018slang` | Slang: language mechanisms for extensible real-time shading systems | ACM TOG |

Not fetched because they are standards, specifications or textbooks rather
than papers: `ccsds123`, `cng2025guide`, `zarr2025core`, `cornillon2003opendap`,
`taubman2003jpip`, `sodagar2011dash`, `fielding2022http`, `shannon1948mathematical`,
`shannon1959coding`, `cover2006elements`.
