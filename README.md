<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/earth-compress-dark.svg">
    <img src="docs/assets/earth-compress.svg" alt="Earth Compress" width="420">
  </picture>
</p>

# benchmark

Compression benchmark for Earth observation data. Lossless, near-lossless and
lossy under one measurement protocol.

A configuration declares one error budget, `tolerance`, as a maximum absolute
error per element in the native units of the sample. `0` is lossless, a
positive value is a near-lossless bound verified on every sample, and no budget
at all is lossy. Ratios are only comparable at equal fidelity.

The budget each dataset can actually afford is in
[docs/tolerance.md](docs/tolerance.md).

Part of [Earth Compress](https://asterisk.coop/project-pages/earth-compress.html),
a three-year project funded by [ARIA](https://www.aria.org.uk/) and led by the
[National Oceanography Centre](https://noc.ac.uk/) and
[Asterisk Labs](https://asterisk.coop/).

Early work. Nothing here is stable yet.

## License

[Apache License 2.0](LICENSE).
