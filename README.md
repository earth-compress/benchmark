<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/earth-compress-dark.svg">
    <img src="docs/assets/earth-compress.svg" alt="Earth Compress" width="420">
  </picture>
</p>

# benchmark

Compression benchmark for Earth observation data. Lossless, near-lossless and
lossy under one measurement protocol.

**Lossless** reproduces the input exactly, and is compared on ratio and
throughput.

**Near-lossless** declares a `tolerance`: a maximum absolute error per element,
in the native units of the sample, that the benchmark verifies on every sample.
Two configurations are comparable only at equal tolerance. The tolerance each
dataset can afford, and why, is in [docs/tolerance.md](docs/tolerance.md).

**Lossy** declares no bound. A single measurement is a point, so these are
compared as rate-distortion curves over a sweep of operating points.

Part of [Earth Compress](https://asterisk.coop/project-pages/earth-compress.html),
a project funded by [ARIA](https://www.aria.org.uk/) and led by the
[National Oceanography Centre](https://noc.ac.uk/) and
[Asterisk Labs](https://asterisk.coop/).

## License

[Apache License 2.0](LICENSE).
