<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/earth-compress-dark.svg">
    <img src="docs/assets/earth-compress.svg" alt="Earth Compress" width="420">
  </picture>
</p>

# benchmark

Compression benchmark for Earth observation data. The results are at [earth-compress.github.io/benchmark](https://earth-compress.github.io/benchmark/) and the data on [Hugging Face](https://huggingface.co/datasets/earth-compress/benchmark).

[Protocol](PROTOCOL.md) · [Datasets](DATASETS.md) · [Codecs](CODECS.md) · [Tolerance](TOLERANCE.md)

```bash
git clone https://github.com/earth-compress/benchmark
cd benchmark
uv run earthcompress corpora/s2-l1c-10m-4
```

The first run on a corpus downloads its samples. Results are written to `corpora/<corpus-id>/results.csv` over the published ones, so `git diff` compares the two.

Part of [Earth Compress](https://asterisk.coop/project-pages/earth-compress.html), funded by [ARIA](https://www.aria.org.uk/) and led by the [National Oceanography Centre](https://noc.ac.uk/) and [Asterisk Labs](https://asterisk.coop/). [Apache 2.0](LICENSE).
