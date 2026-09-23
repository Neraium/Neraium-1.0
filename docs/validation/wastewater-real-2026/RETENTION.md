# Closed validation package: retention and restoration

This package is closed to further analytical execution. Closure added documentation, claim reconciliation and integrity checks only. No Neraium analysis or tests were run during closure. The system under test remains commit `97d267d317fcce4b4424cf2141e97e87680acfc0`; the documentation commit is a separate retention event.

## What is retained

- Current summaries, original detailed findings/reviews, repeatability report, claim traceability and closure verification.
- Exact pre-closure document versions in `history/pre-closure/`, with their own source-path/hash manifest. The original report and limitations also remain verbatim before their new addenda.
- Every original raw artifact, including all checkpoint responses, normalized inputs, repeat-run outputs, logs, configurations, provenance, source snapshots and field-level differences, in ordered lossless archive parts under `archives/`.
- Selected raw JSON summaries directly in Git for convenient review. They are byte-identical duplicates of archive members.
- Exact small copies of the existing controlled-prize report, assessment, claim map and focused regression XML under `reference-evidence/prize-2026/`, supporting the combined application answer. These do not replace or modify the original prize package.
- Wastewater validation scripts and a standard-library-only archive restore utility. Embedded historical harnesses remain in the raw archive.

The original external `/home/ubuntu/Data.csv` is not committed or modified. Derived normalized data and retained engine inputs are included in the evidence archive for reproducibility with the saved CC BY 4.0 attribution; see DATA_LICENSE_AND_ATTRIBUTION.md. The repository's ignored CSV/log/JSONL working files are not staged directly. No generated runtime database is included.

## Integrity and recovery

From the repository root:

```bash
sha256sum -c docs/validation/wastewater-real-2026/SHA256SUMS
python scripts/restore_wastewater_evidence.py --verify-only
python scripts/restore_wastewater_evidence.py
```

The first command verifies all committed package files and validation scripts listed in the final checksum manifest. The second independently verifies every archived raw member without extracting files. The third restores missing raw files in place, preserving original bytes. It refuses to overwrite any differing existing file and rejects unexpected paths. **None of these commands runs Neraium.**

Archive parts are ordered in ARCHIVE_MANIFEST.json. Concatenating them produces one gzip-compressed tar stream. Every member is under `raw/`; each original member hash appears in ARCHIVE_MANIFEST.json and RAW_EVIDENCE_SHA256.json. The archive stores deterministic metadata; byte hashes apply to file content, not filesystem timestamps. Restored files resolve all original report paths, including checkpoint and JSONL references.

Original analytical and test-time manifests remain unchanged, even where their historical paths point to superseded current documents. Their exact former document bytes are in history/pre-closure/. Use the **final** SHA256SUMS for the closed package, and the archived original manifests for historical verification. The final checksum manifest excludes itself; the Git commit records its bytes. CLOSURE_VERIFICATION.json records pre-commit integrity and claim reconciliation. COMMITTED_FILES.txt identifies the intended commit scope.

## Interpretation boundaries

All four promoted states and specified analytical components reproduced, but strict complete outputs did not. Execution-dependent timestamps (including condition timelines), run IDs and performance metadata remain different. The original failed exact comparisons are retained. No independently documented plant-event correspondence, accuracy result, physical consequence or prospective field validation follows from this package.

Earlier statements that the four promoted observations had not been repeat-tested are preserved as dated historical reviews; the later targeted repeatability report supplies the subsequent evidence. No previous report or failure is silently replaced.
