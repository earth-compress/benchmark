# alphaearth-v1-64

## Source

AlphaEarth Foundations Satellite Embedding V1 annual COGs in `gs://alphaearth_foundations`, read over HTTPS. The Earth Engine collection holds the same values decoded to float64.

## Sample

64 embedding dimensions of 512×512 pixels at 10 m, inside one COG. The COGs are stored south up; only the row order changes. The manifest gives the CRS, the geotransform, and the time of every sample.

## Representation

Quantised embeddings as published, int8. NoData is -128. The embedding is `(v / 127.5)² · sign(v)`.

## Licence

The dataset is licensed under CC BY 4.0. Required attribution: "The AlphaEarth
Foundations Satellite Embedding dataset is produced by Google and Google
DeepMind."
