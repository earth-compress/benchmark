<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/earth-compress-dark.svg">
    <img src="docs/assets/earth-compress.svg" alt="Earth Compress" width="420">
  </picture>
</p>

# benchmark

Compression benchmark for Earth observation data. Lossless, near-lossless and
lossy under one measurement protocol.

| mode | what it guarantees | how it is compared |
| --- | --- | --- |
| lossless | the input is reproduced exactly | ratio and throughput |
| near-lossless | a `tolerance`: a maximum absolute error per element, in the native units of the sample, verified on every sample | ratio and throughput, at equal tolerance only |
| lossy | nothing | rate-distortion curves over a sweep of operating points, since one measurement is only a point |

The tolerance each dataset can afford, and why, is in
[docs/tolerance.md](docs/tolerance.md).

Part of [Earth Compress](https://asterisk.coop/project-pages/earth-compress.html),
a project funded by [ARIA](https://www.aria.org.uk/) and led by the
[National Oceanography Centre](https://noc.ac.uk/) and
[Asterisk Labs](https://asterisk.coop/).

## License

[Apache License 2.0](LICENSE).
