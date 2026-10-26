# clay-embeddings

## Source

LGND Clay v1.5 Sentinel-2 L2A embeddings on Source Cooperative (`clay/lgnd-clay-v1-5-sentinel-2-l2a`), monthly aggregated product, June 2024, read as GeoParquet over HTTPS.

## Sample

1024 embedding dimensions on a block of 32 rows by 32 MajorTOM cells of 2560 m, about 82 km on a side, centred on the AlphaEarth sites. Rows run north to south and cells west to east. MajorTOM rows are not aligned with each other, so `cells/<id>.csv` gives the cell id, the source scene, the time, and the exact bounds of every cell. The manifest transform is the mean cell size from the north-west corner.

## Representation

Embeddings as published, float32. They use the full float32 precision, so there is no integer representation to recover.

## Licence

CC BY 4.0. Clay v1.5 embeddings produced by LGND (lgnd.ai) with the Clay Foundation Model.
