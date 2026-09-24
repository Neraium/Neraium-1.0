# Historical certification contract

Decision: HISTORICAL_CERTIFICATION_TEST; EXPLICIT_HISTORICAL_CERTIFICATION_SUITE.

The original RC1 decision was RELEASE_BLOCKED_REPRODUCIBILITY. Its complete records are preserved in history/20260924T205356Z-entry/. REPRODUCIBILITY_AUDIT.json records the evidence, timing limits, and the three previously omitted post-freeze packaging changes.

The 146-leaf test audits the pre-repair production-processing-2026 warmup/run-1 difference inventory. It reads frozen evidence and does not execute an upload or analytical producer. It checks exact path coverage, cardinality, shape, and producer/consumer/representation metadata. It is distinct from the neighboring current-product tests, which remain selected by ordinary CI. All original test assertions and comparator bytes remain unchanged.

Ordinary CI explicitly runs:

```sh
python -m pytest tests -m "not slow and not integration and not historical_certification"
```

Dedicated retained-evidence audit (replace the root with your authoritative evidence checkout):

```sh
python -m pytest tests/test_complete_upload_semantics.py -m historical_certification --historical-evidence-root=/home/ubuntu/Neraium-current-integration
```

The supplied root must contain exactly the relative paths listed in tests/fixtures/historical_certification.json. That release manifest pins compressed file bytes, sizes, and SHA-256 copied from the retained integration SOURCE_HASHES record. The conftest fixture validates all three before executing the unchanged assertion body. Omit the option to require them under this checkout. Absent or mismatched evidence fails the suite; there is no skip, reconstruction, fallback, or generation. The inventory is explicitly marked at collection by exact node ID to preserve the frozen test file.

The external evidence is optional only for ordinary product CI. It is mandatory for the dedicated historical suite. Its snapshots contain synthetic benchmark observations and historical identity/execution details; they are excluded from RC1 distribution and retained untouched in the integration checkout. Do not substitute the similarly named end-to-end-scale campaign files. The existing SOURCE authority is historical evidence, not a newly generated certification campaign.
