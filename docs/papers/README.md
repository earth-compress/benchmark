# Papers

The benchmark and evaluation studies behind this repository's measurement
protocol. The PDFs sit in this directory but are **not tracked by git**; fetch
them with the links below.

| key | paper | source |
| --- | --- | --- |
| `reichelt2026climatebenchpress` | ClimateBenchPress (v1.0): a benchmark for lossy compression of climate data | [GMD 19, 5933–5960](https://gmd.copernicus.org/articles/19/5933/2026/) |
| `zhao2020sdrbench` | SDRBench: Scientific Data Reduction Benchmark for Lossy Compressors | [arXiv 2101.03201](https://arxiv.org/abs/2101.03201) |
| `tao2019zchecker` | Z-checker: A framework for assessing lossy compression of scientific data | [arXiv 1707.09320](https://arxiv.org/abs/1707.09320) |
| `baker2016evaluating` | Evaluating lossy data compression on climate simulation data within a large ensemble | [GMD 9, 4381–4403](https://gmd.copernicus.org/articles/9/4381/2016/) |
| `delaunay2019evaluation` | Evaluation of lossless and lossy algorithms for the compression of scientific datasets in netCDF-4 or HDF5 files | [GMD 12, 4099–4113](https://gmd.copernicus.org/articles/12/4099/2019/) |

## What each one is used for

- **ClimateBenchPress** is the closest existing work: a benchmark for lossy
  compression of climate data that defines both the datasets and the evaluation,
  with per-variable maximum error bounds every compressor must pass. It is also
  the source of the failure modes worth testing for, since it caught codecs
  that silently replaced missing values, turned exact zeros into nonzero values,
  and exceeded their own declared bound.
- **SDRBench** compares compressors across scientific arrays. Its CESM CLOUD
  result matters here: treating a stack of 2D maps as 3D did not always compress
  better, because values do not vary smoothly between maps.
- **Z-checker** is a framework for inspecting what changed after lossy
  compression, including derivatives and spectra, rather than a fixed corpus for
  ranking codecs. It shows why one maximum error is not a sufficient report.
- **Baker et al.** had climate scientists analyse compressed and uncompressed
  ensemble members blind. A derived quantity, the surface energy balance, fell
  outside the ensemble range because one of its four input fluxes had been
  compressed harder than the others. Checking each variable alone would have
  missed it.
- **Delaunay et al.** test compression through the netCDF-4 and HDF5 tooling
  that producers actually use, and find that byte rearrangement often helps more
  than raising the compression level.
