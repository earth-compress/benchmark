# Tolerance

Near-lossless and lossy runs use three error bounds for each eligible corpus, and the ERA5 corpora add a fourth recommended by experts.

A near-lossless configuration declares `tau`, the largest absolute error allowed for any element in the sample's native units. A lossy configuration uses the same `tau` as the largest root-mean-square error of the sample. The three levels let us compare configurations on a corpus at the same error bound. They are benchmark settings, not recommendations for scientific use. [PROTOCOL.md](PROTOCOL.md) v1.0 defines how the bound is checked.

## 1. The rule

We use a reference error, `sigma`, to set the three bounds. It comes from instrument noise, retrieval error or model spread, depending on the product. For Sentinel-2 L1C at 10 m, `sigma` is about 10 DN of noise per pixel. The bounds are 2, 10 and 40 DN after rounding to whole DN.

| level | `tau` | `s2-l1c-10m-4` | error on a 2,000 DN pixel | relative to the noise |
| --- | --- | ---: | ---: | --- |
| `conservative` | `sigma / 4` | 2 DN | 0.1% | well below it |
| `matched` | `sigma` | 10 DN | 0.5% | equal to it |
| `aggressive` | `4 · sigma` | 40 DN | 2% | four times larger |

If compression error is independent of the existing random error and has no overall bias, their mean squared errors add. Even if every compression error reaches `tau` in magnitude, the root-mean-square error across the array could rise by up to about 3% at `conservative` or 41% at `matched`. These percentages describe the array, not individual elements. They hold in lossy mode too, where `tau` bounds the root-mean-square error itself. The factors 1/4, 1 and 4 are choices for this benchmark.

For integer corpora, we round each bound down to a multiple of the largest `scale` in the corpus. `scale` is the value of one stored integer step. In the Sentinel-2 example, `sigma / 4` is 2.5 DN and rounds to 2 DN. A bound below one step rounds to zero, so the lossless result stands for it. Floating-point bounds use `tau` as shown.

`sigma` approximates the standard deviation of random error at a typical element. We leave out offsets and errors shared by neighbouring elements when the source lets us distinguish them. We choose `sigma` in this order.

1. A producer value for the same quantity and time step. For instruments we use noise measured in orbit at a typical signal. For reanalyses we use ensemble spread, and for retrievals the reported random error per element.
2. If the producer has no such value, a standard's uncertainty requirement for the same measurement, converted to one standard deviation.
3. Otherwise, an estimate from the corpus samples.

For multiband corpora, `sigma` is a typical value across bands. Noise can also vary with signal level, so `sigma` does not describe every element.

## 2. Budgets

`tau` is shown in native units. For integer corpora, parentheses give the number of stored steps at the largest `scale`. Zero means the bound rounds below one step.

| corpus | unit | dtype | `scale` | `sigma` | `conservative` | `matched` | `aggressive` |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `era5-tcc-1h` | fraction | uint16 | 2^-15 | 0.09 | 0.022491455078125 (737) | 0.089996337890625 (2949) | 0.3599853515625 (11796) |
| `era5-u10-1h` | m/s | uint16 | 2^-10 | 0.3 | 0.07421875 (76) | 0.2998046875 (307) | 1.19921875 (1228) |
| `era5-t2m-1h` | K | uint16 | 2^-9 | 0.3 | 0.07421875 (38) | 0.298828125 (153) | 1.19921875 (614) |
| `era5-msl-1h` | Pa | uint16 | 2^-2 | 15 | 3.75 (15) | 15 (60) | 60 (240) |
| `era5-tp-1h` | m | uint16 | 2^-21 to 2^-19 | 5e-5 | 1.1444091796875e-05 (6) | 4.9591064453125e-05 (26) | 1.983642578125e-04 (104) |
| `cop-dem-glo30` | m | float32 |  | 1 | 0.25 | 1 | 4 |
| `emit-l2a-285` | reflectance | float32 |  | 5e-4 | 1.25e-4 | 5e-4 | 2e-3 |
| `l8-oli-8` | DN | uint16 | 1 | 10 | 2 (2) | 10 (10) | 40 (40) |
| `l8-oli-pan` | DN | uint16 | 1 | 15 | 3 (3) | 15 (15) | 60 (60) |
| `l8-tirs-2` | DN | uint16 | 1 | 20 | 5 (5) | 20 (20) | 80 (80) |
| `s2-l1c-10m-4` | DN | uint16 | 1 | 10 | 2 (2) | 10 (10) | 40 (40) |
| `s2-l1c-20m-6` | DN | uint16 | 1 | 7 | 1 (1) | 7 (7) | 28 (28) |
| `s2-l1c-60m-3` | DN | uint16 | 1 | 2 | 0 | 2 (2) | 8 (8) |
| `imerg-pcp-12` | mm/hr | uint16 | 0.01 | 0.24 | 0.06 (6) | 0.24 (24) | 0.96 (96) |
| `lm-mss-4` | DN | uint8 | 1 | 1 | 0 | 1 (1) | 4 (4) |
| `l5-tm-6` | DN | uint8 | 1 | 1 | 0 | 1 (1) | 4 (4) |
| `l5-tm-tir` | DN | uint8 | 1 | 0.5 | 0 | 0 | 2 (2) |
| `l7-etm-6` | DN | uint8 | 1 | 1 | 0 | 1 (1) | 4 (4) |
| `l7-etm-tir-2` | DN | uint8 | 1 | 0.5 | 0 | 0 | 2 (2) |
| `l7-etm-pan` | DN | uint8 | 1 | 1.5 | 0 | 1 (1) | 6 (6) |

### Sources of `sigma`

- **Sentinel-2 MSI.** ESA's 2023 performance report gives measured signal-to-noise ratios for both satellites at each band's reference radiance (ESA 2024, Table 13). Converting these to DN with the solar irradiance of 2023 products gives 9.4 to 10.1 DN for B2 to B4 and 14.2 DN for B8 at its brighter reference. The 20 m bands span 3.2 to 10.8 DN. B11 and B12 reach 6 to 7 DN at reflectance 0.2 to 0.3, while the 60 m bands have 1.3 to 1.6 DN.
- **Landsat 8 OLI.** At typical radiance, the noise model of Morfitt et al. (2015, Equations 1 and 2, Table 3) gives 8.4 to 15.8 DN for the eight bands after conversion with the 2e-5 reflectance step per DN. The panchromatic value is 13.6 DN. At reflectance 0.3, the eight bands rise to 13 to 31 DN.
- **Landsat 8 TIRS.** Measured noise-equivalent radiance (Montanaro et al. 2014, Tables 1 and 2) gives 16 to 17 DN at 250 K and 19 to 21 DN at 300 K after conversion with the Collection 2 radiance step of 3.342e-4 per DN. Radiance noise changes little with temperature, though noise expressed in kelvin is higher in cold scenes.
- **Landsat 1 to 7.** TM reflective bands have 0.3 to 1.4 DN of measured noise (Kieffer et al. 1985). For ETM+, signal-to-noise ratios at typical radiance (Markham et al. 2011, Table 1), converted with the gains of Chander et al. (2009), give 0.4 to 1.4 DN for reflective bands and 1.5 to 2.2 DN for the panchromatic band. TM and ETM+ thermal bands have 0.3 to 0.7 DN based on their noise-equivalent temperature difference (Chander et al. 2009). MSS has no published noise in product DN, so we estimate it from local variance in flat areas of the corpus samples. This gives 0.5 to 0.9 DN for MSS and 0.4 to 1.1 DN for TM and ETM+, close to their published values.
- **EMIT.** At 700 nm and reflectance 0.2, the measured signal-to-noise ratio exceeds 500 (Thompson et al. 2024a, Table 1), or roughly 4e-4 in reflectance noise. This measurement assumes a solar zenith angle of 45°. Noise is higher toward the ends of the spectrum, where the signal is weaker. L2A also publishes per-pixel, per-band uncertainty as a standard deviation (Carmon and Brodrick 2022, Section 3.3). It includes atmospheric correction error. The correction uses estimates from segments of several hundred pixels and spatial smoothing, so some of that error is shared between neighbouring pixels (Thompson et al. 2024b, Sections 4.2.3 and 4.2.4). We therefore use 5e-4 as a typical instrument-noise reference across bands. This is an exception to the first rule and a proxy for the random part, below the published L2A uncertainty.
- **Copernicus DEM.** Airbus (2022, Table 1) gives 2 m LE90 for relative vertical error between pixels on slopes up to 20%. If pixel errors are independent, that corresponds to 2 / 1.645 / √2 = 0.86 m standard deviation per pixel. An ICESat comparison gives 0.85 m after removing the mean offset (Airbus 2020, Table 3). We use 1 m. The 4 m absolute LE90 includes regional offsets.
- **ERA5 temperature, wind, pressure and cloud cover.** We use the area-weighted median of CDS ensemble spread across the ten corpus days (`docs/sigma/era5_spread.py` and `docs/sigma/era5_spread.txt`). The medians are 0.30 K for 2 m temperature, 0.30 m/s for 10 m eastward wind, 15 Pa for mean sea-level pressure and 0.094 for total cloud cover. ECMWF (2024) says the spread is generally smaller than the error it estimates, so these bounds tend to be strict.
- **ERA5 precipitation.** The published ensemble spread covers three-hour accumulations, while the corpus uses hourly values. We use the WMO requirement of 0.1 mm/h uncertainty for precipitation intensity from 0.2 to 2 mm/h at 95% probability (WMO 2008, Annex 1.B, note 5). This is about two standard deviations, giving a reference of 0.05 mm/h, or 5e-5 m over one hour.
- **IMERG.** The `randomError` field reports error per cell in mm/hr (Huffman et al. 2023). Its median over all corpus cells is 0.24 mm/hr (`docs/sigma/imerg_random_error.py` and `docs/sigma/imerg_random_error.txt`). Most cells are dry and carry this value. The median among rainy cells is 2.7 mm/hr. The producers caution that the half-hourly error estimate is not fully consistent at this scale (Huffman et al. 2023).

### The `recommended` level

For the ERA5 corpora we add a fourth level, the bounds that ECMWF scientists recommend for these variables in the community recommendations for safe lossy compression (Tyree et al. 2026, version 0.1.0b1). It does not follow the rule of Section 1, so we report it as a separate level.

| corpus | recommendation | kind | `tau` |
| --- | --- | --- | ---: |
| `era5-t2m-1h` | 0.01 K | maximum per point | 0.009765625 (5) |
| `era5-msl-1h` | 1 Pa | maximum per point | 1 (4) |
| `era5-u10-1h` | 0.001 m/s | mean absolute | 0.0009765625 (1) |
| `era5-tcc-1h` | 0.05 | mean absolute | 0.04998779296875 (1638) |
| `era5-tp-1h` | 1e-5 m | mean absolute | 9.5367431640625e-06 (5) |

Two recommendations are maximum errors per point and apply as they stand. The other three bound the mean absolute error. Near-lossless needs a maximum, so we apply them as a maximum, which is stricter than the recommendation. Lossy applies them to the root-mean-square error, which is never below the mean absolute error, so it is stricter too. A root-mean-square bound cannot meet a maximum per point, so `era5-t2m-1h` and `era5-msl-1h` have no lossy `recommended` level. Each rounds down to whole steps of the largest `scale`, given in parentheses. At these bounds a codec may change little more than the GRIB packing of ERA5 already did.

## 3. Lossless-only corpora

These corpora have no budget, so they run in lossless mode only.

| corpus | reason |
| --- | --- |
| `esa-wc-v200` | Land-cover class codes are unordered, so 95 is mangrove and 100 is moss. An error of one gives a different class. |
| `tessera-v2-codes` | Embedding codes; the effect of an error on downstream tasks is not measured. |
| `tessera-v2-scales` | A scale error multiplies all 128 dimensions of a pixel; the effect on downstream tasks is not measured. |
| `alphaearth-v1-64` | Embedding codes; the effect of an error on downstream tasks is not measured. |
| `clay-embeddings` | Embeddings; the effect of an error on downstream tasks is not measured. |
| `goes-abi-16` | Each band has its own `scale` and mixes reflectance factor with brightness temperature, so one budget in native units does not apply to the whole array. |
| `s1-grd-iw-2` | No per-element uncertainty of the linear backscatter is established. |

## 4. Limits of these budgets

The bounds compare compression error with a reference error. They do not measure the effect on an analysis.

Compression error can be correlated with the signal, even when it is smaller than the noise. A derived quantity can also amplify it. A 10 DN bound on two similar reflectance bands allows a larger relative error in their normalised difference than in either band. A 1 m bound on DEM pixels allows up to 2 m of error in the height difference between neighbours.

For precipitation, a small change can turn light rain into zero. In the IMERG corpus, 41.0 million of 47.2 million cells are exact zeros. Among the 6.2 million rainy cells, 952,771, or 15%, have 0.06 mm/hr or less. A codec meeting the `conservative` bound of 0.06 mm/hr could still decode any of them as zero. The `zero` promise preserves input zeros, but not light rain. Lossy mode does not promise zeros and only reports the ones it changes.

A lossy bound limits the error of the sample, not of each element. A codec can meet it while missing a few elements, such as the peaks of a rain field, by many times `tau`. Lossy results therefore report the maximum error beside the ratio.

For a particular pipeline, compare its outputs before and after compression. Section 9 of `PROTOCOL.md` gives examples of such checks.

## References

- Airbus Defence and Space (2020). [*Copernicus DEM Validation Report*](https://s3.waw3-1.cloudferro.com/swift/v1/portal_uploads_prod/GEO1988-CopernicusDEM-RP-001_ValidationReport_I3.0_08.2024.pdf), version 3.0. GEO.2018-1988-2.
- Airbus Defence and Space (2022). [*Copernicus DEM Product Handbook*](https://dataspace.copernicus.eu/sites/default/files/media/files/2024-06/geo1988-copernicusdem-spe-002_producthandbook_i5.0.pdf), version 5.0. GEO.2018-1988-2.
- Carmon, N., and Brodrick, P. (2022). [*EMIT L2A Data Product User Guide*](https://lpdaac.usgs.gov/documents/1569/EMITL2ARFL_User_Guide_v1.pdf), version 1.0. JPL D-107863.
- Chander, G., Markham, B. L., and Helder, D. L. (2009). Summary of current radiometric calibration coefficients for Landsat MSS, TM, ETM+, and EO-1 ALI sensors. *Remote Sens. Environ.*, 113, 893–903.
- ECMWF (2024). [ERA5 uncertainty estimation](https://confluence.ecmwf.int/display/CKB/ERA5%3A+uncertainty+estimation). Copernicus Knowledge Base.
- ESA (2024). [*Sentinel-2 MSI Annual Performance Report 2023*](https://sentinels.copernicus.eu/documents/d/sentinel/ompc-cs-apr-003-i1r0-s2-msi-annual-performance-report-2023). OMPC.CS.APR.003, issue 1.0.
- Huffman, G. J., et al. (2023). [*Integrated Multi-satellitE Retrievals for GPM (IMERG) Technical Documentation*](https://gpm.nasa.gov/sites/default/files/2023-07/IMERG_TechnicalDocumentation_final_230713.pdf). NASA Goddard Space Flight Center.
- Kieffer, H. H., Cook, D. A., Eliason, E. M., and Eliason, P. T. (1985). Intraband radiometric performance of the Landsat Thematic Mappers. *Photogramm. Eng. Remote Sens.*, 51, 1331–1350.
- Markham, B., Dabney, P., and Pedelty, J. (2011). [The Landsat Data Continuity Mission Operational Land Imager, radiometric performance](https://ntrs.nasa.gov/citations/20120002315). *IGARSS 2011*.
- Montanaro, M., Levy, R., and Markham, B. (2014). On-orbit radiometric performance of the Landsat 8 Thermal Infrared Sensor. *Remote Sens.*, 6, 11753–11769.
- Morfitt, R., et al. (2015). Landsat-8 Operational Land Imager (OLI) radiometric performance on-orbit. *Remote Sens.*, 7, 2208–2237.
- Thompson, D. R., et al. (2024a). On-orbit calibration and performance of the EMIT imaging spectrometer. *Remote Sens. Environ.*, 303, 113986.
- Thompson, D. R., et al. (2024b). [*EMIT L2A Algorithm, Surface Reflectance and Scene Content Masks, Theoretical Basis*](https://lpdaac.usgs.gov/documents/1571/EMITL2A_ATBD_v1.pdf), version 1.5. JPL D-104255.
- Tyree, J., Faghih-Naini, S., Klöwer, M., Dueben, P., and Järvinen, H. (2026). [*Recommendations for Safe Lossy Compression of weather and climate data*](https://doi.org/10.5281/zenodo.22761209), version 0.1.0b1. Zenodo.
- WMO (2008). *Guide to Meteorological Instruments and Methods of Observation*, WMO-No. 8, seventh edition.
