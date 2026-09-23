# Baseline

Baseline commit: `e665018993b128d0dbd280879727be8a7181d6fb`.
Branch: `perf/2026-governed-optimization`.

The measured baseline is the **current dirty workspace**, not just that commit.
`raw/initial-status.txt` inventories pre-existing changes; `raw/baseline-source-hashes.json`
identifies Python source bytes. Unrelated work must remain uncommitted by this pass.
Full machine/environment details and installed packages are in `raw/environment.json`
and `raw/packages.txt`. Python 3.12.3; Linux x86_64; two logical CPUs on one Intel
Xeon Platinum 8175M core; approximately 7.6 GiB RAM, no swap.

The reproducible driver is `scripts/performance/governed_benchmark.py`. It uses the
repository virtualenv, default analytical configuration, isolated local runtime
storage, deterministic synthetic telemetry, and authenticated in-memory Phase 4
storage. Inputs contain timestamp, load, flow, and pressure, with smooth correlated
baseline behavior and a pressure violation in the recent engine window.

Workloads: historical CSV ingestion including immutable artifacts and canonical
provenance; baseline candidate construction and persistence; the unified SII engine
including relationship/covariance, temporal persistence, context, and evidence
fusion; and three successive 240-row windows against seeded behavioral memory.
Larger workloads are bounded by observed cost and available memory.

Each workload receives one warm-up, then three timed repetitions. Input generation,
imports, and isolated runtime initialization are outside the timed region. Full
returned outputs are retained as compressed JSON. Comparison excludes observational
performance measurements only; governed values and insertion ordering are preserved.
Metadata clock is fixed; analytical telemetry timestamps are not altered.
Profiling is a separate, untimed run. RSS is the process high-water mark (including
setup and warm-up), not an allocation delta or a claim about production fleet RAM.
