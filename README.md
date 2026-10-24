<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/earth-compress-dark.svg">
    <img src="docs/assets/earth-compress.svg" alt="Earth Compress" width="420">
  </picture>
</p>

# benchmark

Compression benchmark for Earth observation data. Lossless, near-lossless and
lossy under one measurement protocol.

Environmental datasets are growing to petabyte scale, and the cost of hosting,
transferring and analysing them has become a bottleneck for high-impact
research. When storing and moving the data is expensive, fewer people can work
with it, and the science slows down.

Compression is the lever, and this repository is how we tell whether a given
turn of it actually helps. It measures codecs on real Earth observation arrays
and reports what each one costs and what each one gives up: compression ratio,
bits per value, encode and decode throughput, and the error introduced.

## Why a benchmark

Published compression numbers are rarely comparable. A ratio quoted on one
sensor at one resolution says little about another, a lossy ratio quoted
without its error says nothing at all, and a throughput figure measured across
eight threads is not the figure a reader will reproduce. The usual result is a
set of claims that cannot be placed beside each other.

The benchmark fixes the things that make numbers incomparable: a versioned
corpus of real samples with content hashes, one thread, a timing procedure with
confidence intervals, and a declared error budget attached to every
measurement. Everything it reports is reproducible from this repository.

## Fidelity modes

A configuration declares one error budget, `tolerance`, as a maximum absolute
error per element in the native units of the sample. That budget decides how
the configuration is measured, so the three modes are one axis rather than
three separate benchmarks:

| `tolerance` | mode | what is enforced |
| --- | --- | --- |
| `0` | `lossless` | decoded bytes equal the input bytes |
| `> 0` | `near-lossless` | `max_abs_error <= tolerance`, verified on every sample |
| absent | `lossy` | nothing; the measured error is reported |

Native units means the units of the stored array. On a corpus of `int16`
elevation in metres, `tolerance = 2` is two metres.

A near-lossless budget is a bound, not a target: a configuration whose output
exceeds it on a single element of a single sample has failed that sample. This
is the mode most Earth observation archives actually need, and the one most
often reported without proof.

Ratios are only comparable at equal fidelity. A near-lossless configuration at
a larger budget is not better for having a larger ratio, and a single lossy
measurement is a point on a rate-distortion curve rather than a result.

## Status

Early. The measurement protocol and the corpora are being assembled in the
open, and nothing here is stable yet.

## About

[Earth Compress](https://asterisk.coop/project-pages/earth-compress.html) is a
three-year, £7 million project funded by the
[Advanced Research and Invention Agency](https://www.aria.org.uk/) (ARIA), led
by the [National Oceanography Centre](https://noc.ac.uk/) and
[Asterisk Labs](https://asterisk.coop/). It develops and operationalises highly
performant compression algorithms that massively reduce the size and cost of
increasingly large environmental datasets.

We work closely with data producers like ECMWF and EUMETSAT, alongside the
wider Earth observation and environmental communities, to build an open-source
toolbox that democratises data access, letting anyone run global-scale
experiments and analysis on petabytes of data.

To hear more about the project, read
[ARIA's announcement](https://aria.org.uk/insights/2026/doubling-down-on-earth-scale-data).

## License

[Apache License 2.0](LICENSE).
