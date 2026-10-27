# Tolerance

The error budgets of each corpus for near-lossless configurations, and where they come from.

A near-lossless configuration declares `tau`, a maximum absolute error per element in the native unit of the sample. These budgets make ratios comparable at equal fidelity. They do not recommend a fidelity for any use. See [PROTOCOL.md](PROTOCOL.md) v1.0.

## 1. The rule

Every product carries an error before it is compressed, from instrument noise, retrieval error or model spread. Its typical size for one element is `sigma`. Sentinel-2 L1C at 10 m, for example, has about 10 DN of noise per pixel. A compression error well below `sigma` hides inside that noise, and one several times larger does not.

Each corpus has three budgets, set from its own `sigma`.

| level | `tau` | `s2-l1c-10m-4` | on a pixel of 2,000 DN | compared with the noise |
| --- | --- | ---: | ---: | --- |
| `conservative` | `sigma / 4` | 2 DN | 0.1% | well below it |
| `matched` | `sigma` | 10 DN | 0.5% | equal to it |
| `aggressive` | `4 · sigma` | 40 DN | 2% | four times larger |

An independent compression error adds to the existing error in quadrature. At `conservative` the total error of an element grows by at most 3%, at `matched` by at most 41%, and at `aggressive` the compression error dominates. Because `tau` is a maximum and most elements have a smaller compression error, these are upper bounds. The factors 1/4, 1 and 4 are a choice of this benchmark.

For integer corpora, budgets round down to whole steps of `scale`, the value of one step of the stored integers, taking the largest `scale` in the corpus. In the example above, `sigma / 4` is 2.5 DN and becomes 2 DN. A level below one step is 0, which is lossless, so near-lossless configurations do not run at it and the lossless result stands for it. For floating-point corpora, `tau` is used as stated.

`sigma` is a figure for a single element. For a radiometer it is the noise measured in orbit at a typical radiance, not the requirement of its specification, which is usually larger. Noise grows with the signal, so bright pixels carry more than `sigma` and dark ones less. One value per corpus is a simplification.

## 2. Budgets

`tau` in native units. For integer corpora, the number of steps of the largest `scale` is in brackets. A `0` means the level falls below one step.

| corpus | unit | dtype | `scale` | `sigma` | `conservative` | `matched` | `aggressive` |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `era5-tcc-1h` | fraction | uint16 | 2^-15 | 0.125 | 0.03125 (1024) | 0.125 (4096) | 0.5 (16384) |
| `era5-u10-1h` | m/s | uint16 | 2^-10 | 0.6 | 0.1494140625 (153) | 0.599609375 (614) | 2.3994140625 (2457) |
| `era5-t2m-1h` | K | uint16 | 2^-9 | 0.6 | 0.1484375 (76) | 0.599609375 (307) | 2.3984375 (1228) |
| `era5-msl-1h` | Pa | uint16 | 2^-2 | 30 | 7.5 (30) | 30 (120) | 120 (480) |
| `era5-tp-1h` | m | uint16 | 2^-21 to 2^-19 | 1e-4 | 2.47955322265625e-05 (13) | 9.918212890625e-05 (52) | 3.986358642578125e-04 (209) |
| `cop-dem-glo30` | m | float32 |  | 1 | 0.25 | 1 | 4 |
| `emit-l2a-285` | reflectance | float32 |  | 5e-4 | 1.25e-4 | 5e-4 | 2e-3 |
| `l8-oli-8` | DN | uint16 | 1 | 10 | 2 (2) | 10 (10) | 40 (40) |
| `l8-oli-pan` | DN | uint16 | 1 | 15 | 3 (3) | 15 (15) | 60 (60) |
| `l8-tirs-2` | DN | uint16 | 1 | 20 | 5 (5) | 20 (20) | 80 (80) |
| `s2-l1c-10m-4` | DN | uint16 | 1 | 10 | 2 (2) | 10 (10) | 40 (40) |
| `s2-l1c-20m-6` | DN | uint16 | 1 | 7 | 1 (1) | 7 (7) | 28 (28) |
| `s2-l1c-60m-3` | DN | uint16 | 1 | 2 | 0 | 2 (2) | 8 (8) |
| `imerg-pcp-12` | mm/hr | uint16 | 0.01 | 0.25 | 0.06 (6) | 0.25 (25) | 1 (100) |
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
- **Landsat 1 to 7.** The reflective bands of TM have 0.3 to 1.4 DN of noise (Kieffer et al. 1985). The signal-to-noise ratios of ETM+ at typical radiance (Markham et al. 2011, Table 1), converted with the rescaling gains of Chander et al. (2009), give 0.4 to 1.4 DN for the reflective bands and 1.5 to 2.2 DN for the panchromatic band. The thermal bands of TM and ETM+ have 0.3 to 0.7 DN, from their noise-equivalent temperature difference (Chander et al. 2009). No measured noise in product DN is published for MSS. An estimate from the local variance of flat areas in the corpus samples gives 0.5 to 0.9 DN for MSS and 0.4 to 1.1 DN for TM and ETM+.
- **EMIT.** The measured signal-to-noise ratio is above 500 at 700 nm for a reflectance of 0.2 at a solar zenith of 45° (Thompson et al. 2024, Table 1), about 4e-4 in reflectance. Across the usable bands the instrument noise is 3e-4 to 7e-4. The uncertainty layer of the L2A product is larger, 2e-3 to 1e-2, but it is mostly error of the atmospheric correction, which is smooth in space and is not noise of each pixel.
- **Copernicus DEM.** The relative vertical accuracy between two pixels is 2 m LE90 on slopes up to 20% (Airbus 2022, Table 1). As a standard deviation of one pixel this is 2 / 1.645 / √2 = 0.86 m. Against ICESat, once the mean offset is removed, the standard deviation is 0.85 m (Airbus 2020, Table 3). The absolute accuracy of 4 m LE90 includes regional offsets and is not the error of one pixel.
- **ERA5 temperature, wind and pressure.** `sigma` is twice the median ensemble spread, weighted by area, measured on the `ensemble_spread` product of the Climate Data Store for eight of the ten corpus days. The medians are 0.30 K for 2 m temperature, 0.30 m/s for 10 m eastward wind and 15 Pa for mean sea-level pressure, and they change by less than 3% between three and eight days. ECMWF describes the spread as generally under-dispersive and gives no correction factor (ECMWF 2024).
- **ERA5 cloud cover and precipitation.** Cloud cover is bounded and precipitation is intermittent, so their spread is zero in many cells and large in a few, and the spread of precipitation is a three-hour accumulation. For these two `sigma` follows the uncertainty required by WMO (2008, Annex 1.B). For cloud amount it is one okta, 0.125. For precipitation intensity it is 0.1 mm/h between 0.2 and 2 mm/h, which is 1e-4 m over one hour.
- **IMERG.** The `randomError` field of IMERG V07 has an estimated minimum of 0.24 mm/hr (Google Earth Engine catalog). At the median rain rate of the corpus, 0.37 mm/hr, the random error at overpasses of the GPM microwave imager is about 80% of the rate (Watters et al. 2025), about 0.3 mm/hr. Both give about 0.25 mm/hr.

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

## 4. Pending

| corpus | status |
| --- | --- |
| `lm-mss-4` | No measured noise in product DN is published. `sigma` comes from TM and from the estimate on the corpus. |
| `l8-tirs-2` | The noise figures were measured in 2013 and 2014, before TIRS moved to its backup electronics. |
| `era5-tcc-1h`, `era5-tp-1h` | `sigma` comes from an observation standard, not from the uncertainty of ERA5. |

## 5. What this does not settle

A budget from the uncertainty of a product says whether the decoded array still represents the measurement as well as the original. It does not say whether an analysis gives the same result.

An error below the noise can still be correlated with the signal, and a derived quantity can amplify it. The `matched` budget of 10 DN on two similar reflectance bands allows a larger relative error in their normalised difference than in either band, and 1 m per cell on a DEM allows up to 2 m of error in the height difference between neighbours.

On precipitation, the damaging error is often whether a cell rains at all. In the prototype, on IMERG at a bound of 0.05 mm/hr, all 41.0 million exact zeros survived and 690,198 light-rain values at or below the bound decoded as zero. The `zero` promise protects exact zeros, not light rain.

Choosing a budget for a pipeline means measuring that pipeline, as in Section 9 of `PROTOCOL.md`.

## References

- Airbus Defence and Space (2020). *Copernicus DEM Validation Report*, version 3.0. GEO.2018-1988-2. https://s3.waw3-1.cloudferro.com/swift/v1/portal_uploads_prod/GEO1988-CopernicusDEM-RP-001_ValidationReport_I3.0_08.2024.pdf
- Airbus Defence and Space (2022). *Copernicus DEM Product Handbook*, version 5.0. GEO.2018-1988-2. https://dataspace.copernicus.eu/sites/default/files/media/files/2024-06/geo1988-copernicusdem-spe-002_producthandbook_i5.0.pdf
- Chander, G., Markham, B. L., and Helder, D. L. (2009). Summary of current radiometric calibration coefficients for Landsat MSS, TM, ETM+, and EO-1 ALI sensors. *Remote Sens. Environ.*, 113, 893–903.
- ECMWF (2024). ERA5 uncertainty estimation. Copernicus Knowledge Base. https://confluence.ecmwf.int/display/CKB/ERA5%3A+uncertainty+estimation
- ESA (2024). *Sentinel-2 MSI Annual Performance Report 2023*. OMPC.CS.APR.003, issue 1.0. https://sentinels.copernicus.eu/documents/d/sentinel/ompc-cs-apr-003-i1r0-s2-msi-annual-performance-report-2023
- Gascon, F., et al. (2017). Copernicus Sentinel-2A calibration and products validation status. *Remote Sens.*, 9, 584.
- Google Earth Engine. GPM IMERG Final Precipitation L3 Half Hourly 0.1 degree x 0.1 degree V07. https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
- Kieffer, H. H., Cook, D. A., Eliason, E. M., and Eliason, P. T. (1985). Intraband radiometric performance of the Landsat Thematic Mappers. *Photogramm. Eng. Remote Sens.*, 51, 1331–1350.
- Markham, B., Dabney, P., and Pedelty, J. (2011). The Landsat Data Continuity Mission Operational Land Imager, radiometric performance. *IGARSS 2011*. https://ntrs.nasa.gov/citations/20120002315
- Montanaro, M., Levy, R., and Markham, B. (2014). On-orbit radiometric performance of the Landsat 8 Thermal Infrared Sensor. *Remote Sens.*, 6, 11753–11769.
- Morfitt, R., et al. (2015). Landsat-8 Operational Land Imager (OLI) radiometric performance on-orbit. *Remote Sens.*, 7, 2208–2237.
- Thompson, D. R., et al. (2024). On-orbit calibration and performance of the EMIT imaging spectrometer. *Remote Sens. Environ.*, 303, 113986.
- Watters, D. C., et al. (2025). A diagnosis of oceanic precipitation in IMERG-GMI. *J. Hydrometeorol.* https://doi.org/10.1175/JHM-D-24-0137.1
- WMO (2008). *Guide to Meteorological Instruments and Methods of Observation*, WMO-No. 8, seventh edition.
