# Tolerance

The error budgets of each corpus for near-lossless configurations, and where they come from.

A near-lossless configuration declares `tau`, a maximum absolute error per element in the native unit of the sample. With these budgets, configurations on the same corpus are compared at the same maximum error, set by one rule for every corpus. They do not recommend a fidelity for any use. See [PROTOCOL.md](PROTOCOL.md) v1.0.

## 1. The rule

Every product carries an error before it is compressed, from instrument noise, retrieval error or model spread. Its typical size for one element is `sigma`. Sentinel-2 L1C at 10 m, for example, has about 10 DN of noise per pixel. A compression error well below `sigma` hides inside that noise, and one several times larger does not.

Each corpus has three budgets, set from its own `sigma`.

| level | `tau` | `s2-l1c-10m-4` | on a pixel of 2,000 DN | compared with the noise |
| --- | --- | ---: | ---: | --- |
| `conservative` | `sigma / 4` | 2 DN | 0.1% | well below it |
| `matched` | `sigma` | 10 DN | 0.5% | equal to it |
| `aggressive` | `4 · sigma` | 40 DN | 2% | four times larger |

If the compression error is independent of the existing error, the two add in quadrature. The root-mean-square error of the decoded data then grows by at most 3% at `conservative` and by at most 41% at `matched`, and at `aggressive` the compression error dominates. These figures describe the error over many elements, not the error of each one. The factors 1/4, 1 and 4 are a choice of this benchmark.

For integer corpora, budgets round down to whole steps of `scale`, the value of one step of the stored integers, taking the largest `scale` in the corpus. In the example above, `sigma / 4` is 2.5 DN and becomes 2 DN. A level below one step is 0, which is lossless, so near-lossless configurations do not run at it and the lossless result stands for it. For floating-point corpora, `tau` is used as stated.

`sigma` is a reference that this benchmark chooses for each corpus from what the producer publishes. It is the standard deviation of the random error of one element, the part that changes from one element to the next. Offsets and errors shared by neighbouring elements are left out, because a compression error also changes from one element to the next and can only hide in the random part. The source is taken in this order.

1. The producer's own figure for that error, for the quantity and time step of the corpus. For an instrument this is the noise measured in orbit at a typical signal, not the requirement of its specification. For a reanalysis it is the ensemble spread, and for a retrieval the random error it reports for each element.
2. Where the producer publishes none, the uncertainty that a standard requires for the same measurement, converted to one standard deviation.
3. Where neither exists, an estimate on the corpus samples.

Where the bands of a corpus differ, `sigma` is a typical value across them. Noise grows with the signal, so bright elements carry more than `sigma` and dark ones less.

## 2. Budgets

`tau` in native units. For integer corpora, the number of steps of the largest `scale` is in brackets. A `0` means the level falls below one step.

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

- **Sentinel-2 MSI.** The 2023 annual performance report gives the signal-to-noise ratio measured on both satellites at the reference radiance of each band (ESA 2024, Table 13). Converted to DN with the solar irradiance of 2023 products, B2, B3 and B4 have 9.4 to 10.1 DN, and B8 has 14.2 DN at its brighter reference. The 20 m bands have 3.2 to 10.8 DN, and B11 and B12, whose references are dark, reach 6 to 7 DN at a reflectance of 0.2 to 0.3. The 60 m bands have 1.3 to 1.6 DN. Gascon et al. (2017) give the same ratios within about 4%.
- **Landsat 8 OLI.** The noise model of Morfitt et al. (2015, Equations 1 and 2, Table 3) at the typical radiance of each band, converted with the reflectance rescaling of 2e-5 per DN, gives 8.4 to 15.8 DN for the eight bands and 13.6 DN for the panchromatic band. At a reflectance of 0.3 these rise to 13 to 31 DN.
- **Landsat 8 TIRS.** The noise-equivalent radiance measured by Montanaro et al. (2014, Tables 1 and 2), converted with the Collection 2 radiance rescaling of 3.342e-4 per DN, gives 16 to 17 DN at 250 K and 19 to 21 DN at 300 K. The radiance noise is almost constant with temperature, so the noise in kelvin grows in cold scenes.
- **Landsat 1 to 7.** The reflective bands of TM have 0.3 to 1.4 DN of noise (Kieffer et al. 1985). The signal-to-noise ratios of ETM+ at typical radiance (Markham et al. 2011, Table 1), converted with the rescaling gains of Chander et al. (2009), give 0.4 to 1.4 DN for the reflective bands and 1.5 to 2.2 DN for the panchromatic band. The thermal bands of TM and ETM+ have 0.3 to 0.7 DN, from their noise-equivalent temperature difference (Chander et al. 2009). No measured noise in product DN is published for MSS, so its `sigma` follows the third rule. An estimate from the local variance of flat areas in the corpus samples gives 0.5 to 0.9 DN for MSS, and 0.4 to 1.1 DN for TM and ETM+, close to the published values.
- **EMIT.** The measured signal-to-noise ratio is above 500 at 700 nm for a reflectance of 0.2 at a solar zenith of 45° (Thompson et al. 2024a, Table 1), about 4e-4 in reflectance, and the noise is larger toward the ends of the spectrum, where the signal is weaker. The L2A product also publishes an uncertainty for each pixel and band, as a standard deviation (Carmon and Brodrick 2022, Section 3.3). It combines the instrument noise with the error of the atmospheric correction, which is retrieved on segments of several hundred pixels and carried to each pixel with spatial smoothing (Thompson et al. 2024b, Sections 4.2.3 and 4.2.4), so part of it is shared by neighbouring pixels. As an exception to the first rule, `sigma` is the instrument noise, 5e-4 as a typical value across bands, which approximates the random part and is smaller than the published uncertainty.
- **Copernicus DEM.** The relative vertical accuracy between two pixels is 2 m LE90 on slopes up to 20% (Airbus 2022, Table 1). If the errors of the two pixels are independent, the standard deviation of one pixel is 2 / 1.645 / √2 = 0.86 m. Against ICESat, once the mean offset is removed, the standard deviation is 0.85 m (Airbus 2020, Table 3). The absolute accuracy of 4 m LE90 includes regional offsets and is not the error of one pixel.
- **ERA5 temperature, wind, pressure and cloud cover.** `sigma` is the median ensemble spread of the `ensemble_spread` product of the Climate Data Store over the ten corpus days, weighted by the area of each cell (`docs/sigma/era5_spread.py`, output in `docs/sigma/era5_spread.txt`). The medians are 0.30 K for 2 m temperature, 0.30 m/s for 10 m eastward wind, 15 Pa for mean sea-level pressure and 0.094 for total cloud cover. ECMWF describes the spread as generally under-dispersive, that is smaller than the error it estimates (ECMWF 2024), so these budgets tend to be strict.
- **ERA5 precipitation.** The spread of precipitation is published for three-hour accumulations, not for the hourly values of the corpus, so `sigma` follows the second rule. WMO requires an uncertainty of 0.1 mm/h for precipitation intensity between 0.2 and 2 mm/h, stated at a probability of 95%, which is two standard deviations (WMO 2008, Annex 1.B, note 5). One standard deviation is 0.05 mm/h, or 5e-5 m over one hour.
- **IMERG.** IMERG reports a random error for each cell in its `randomError` field, in mm/hr (Huffman et al. 2023). Its median over the cells of the corpus is 0.24 mm/hr (`docs/sigma/imerg_random_error.py`, output in `docs/sigma/imerg_random_error.txt`). Cells without rain take this value, and most cells of the corpus do not rain. Over the cells that rain the median is 2.7 mm/hr. The producers describe the half-hourly field as not entirely consistent at such fine scales (Huffman et al. 2023).

## 3. Corpora with no near-lossless point

These corpora are measured in lossless mode only.

| corpus | reason |
| --- | --- |
| `esa-wc-v200` | Land-cover class codes are unordered, so 95 is mangrove and 100 is moss. An error of one gives a different class. |
| `tessera-v2-codes` | Embedding codes; the effect of an error on downstream tasks is not measured. |
| `tessera-v2-scales` | A scale error multiplies all 128 dimensions of a pixel; the effect on downstream tasks is not measured. |
| `alphaearth-v1-64` | Embedding codes; the effect of an error on downstream tasks is not measured. |
| `clay-embeddings` | Embeddings; the effect of an error on downstream tasks is not measured. |
| `goes-abi-16` | Each band has its own `scale` and mixes reflectance factor with brightness temperature, so one budget in native units does not apply to the whole array. |
| `s1-grd-iw-2` | No per-element uncertainty of the linear backscatter is established. |

## 4. What this does not settle

A budget sets how large the compression error may be relative to a reference error of the product. It does not say whether an analysis gives the same result.

An error below the noise can still be correlated with the signal, and a derived quantity can amplify it. The `matched` budget of 10 DN on two similar reflectance bands allows a larger relative error in their normalised difference than in either band, and 1 m per cell on a DEM allows up to 2 m of error in the height difference between neighbours.

On precipitation, the damaging error is often whether a cell rains at all. In the IMERG corpus, 41.0 million of the 47.2 million cells are exact zeros, and 952,771 of the 6.2 million cells that rain, 15%, have 0.06 mm/hr or less, the `conservative` budget. A codec within that budget may decode any of them as zero. The `zero` promise protects exact zeros, not light rain.

Choosing a budget for a pipeline means measuring that pipeline, as in Section 9 of `PROTOCOL.md`.

## References

- Airbus Defence and Space (2020). *Copernicus DEM Validation Report*, version 3.0. GEO.2018-1988-2. https://s3.waw3-1.cloudferro.com/swift/v1/portal_uploads_prod/GEO1988-CopernicusDEM-RP-001_ValidationReport_I3.0_08.2024.pdf
- Airbus Defence and Space (2022). *Copernicus DEM Product Handbook*, version 5.0. GEO.2018-1988-2. https://dataspace.copernicus.eu/sites/default/files/media/files/2024-06/geo1988-copernicusdem-spe-002_producthandbook_i5.0.pdf
- Carmon, N., and Brodrick, P. (2022). *EMIT L2A Data Product User Guide*, version 1.0. JPL D-107863. https://lpdaac.usgs.gov/documents/1569/EMITL2ARFL_User_Guide_v1.pdf
- Chander, G., Markham, B. L., and Helder, D. L. (2009). Summary of current radiometric calibration coefficients for Landsat MSS, TM, ETM+, and EO-1 ALI sensors. *Remote Sens. Environ.*, 113, 893–903.
- ECMWF (2024). ERA5 uncertainty estimation. Copernicus Knowledge Base. https://confluence.ecmwf.int/display/CKB/ERA5%3A+uncertainty+estimation
- ESA (2024). *Sentinel-2 MSI Annual Performance Report 2023*. OMPC.CS.APR.003, issue 1.0. https://sentinels.copernicus.eu/documents/d/sentinel/ompc-cs-apr-003-i1r0-s2-msi-annual-performance-report-2023
- Gascon, F., et al. (2017). Copernicus Sentinel-2A calibration and products validation status. *Remote Sens.*, 9, 584.
- Huffman, G. J., et al. (2023). *Integrated Multi-satellitE Retrievals for GPM (IMERG) Technical Documentation*. NASA Goddard Space Flight Center. https://gpm.nasa.gov/sites/default/files/2023-07/IMERG_TechnicalDocumentation_final_230713.pdf
- Kieffer, H. H., Cook, D. A., Eliason, E. M., and Eliason, P. T. (1985). Intraband radiometric performance of the Landsat Thematic Mappers. *Photogramm. Eng. Remote Sens.*, 51, 1331–1350.
- Markham, B., Dabney, P., and Pedelty, J. (2011). The Landsat Data Continuity Mission Operational Land Imager, radiometric performance. *IGARSS 2011*. https://ntrs.nasa.gov/citations/20120002315
- Montanaro, M., Levy, R., and Markham, B. (2014). On-orbit radiometric performance of the Landsat 8 Thermal Infrared Sensor. *Remote Sens.*, 6, 11753–11769.
- Morfitt, R., et al. (2015). Landsat-8 Operational Land Imager (OLI) radiometric performance on-orbit. *Remote Sens.*, 7, 2208–2237.
- Thompson, D. R., et al. (2024a). On-orbit calibration and performance of the EMIT imaging spectrometer. *Remote Sens. Environ.*, 303, 113986.
- Thompson, D. R., et al. (2024b). *EMIT L2A Algorithm, Surface Reflectance and Scene Content Masks, Theoretical Basis*, version 1.5. JPL D-104255. https://lpdaac.usgs.gov/documents/1571/EMITL2A_ATBD_v1.pdf
- WMO (2008). *Guide to Meteorological Instruments and Methods of Observation*, WMO-No. 8, seventh edition.
