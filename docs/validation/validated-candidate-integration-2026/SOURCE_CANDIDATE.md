# Source candidate — verified, not promoted
Source: /home/ubuntu/Neraium-current-integration, HEAD 97d267d317fcce4b4424cf2141e97e87680acfc0. The dirty worktree, not HEAD alone, is the candidate. Target HEAD is a4ea0a992841d281e19de8119ecd1275a0d7e654; their merge-base is source HEAD.

Independent read-only verification is recorded in lineage.json. All 605 production files and the production file set match optimization-05-normalized-telemetry-metadata-2026/raw/500k/raw/production-start-hashes.json. Consecutive retained manifests isolate exactly:

| Optimization | Required implementation | Status |
|---|---|---|
| #1 | upload_validator.stream_csv_snapshot: construct numeric_column_schema once, retain each source index, reuse normalized names and important-column membership | ACCEPTED, PRESENT |
| #2 | operating_modes.explicit_mode_features and mode_conditioned_baseline selection/matching callers: feature-only matching; full descriptors retained elsewhere | ACCEPTED, PRESENT |
| #3 | multiscale_analysis: invocation-local branch-specific timestamp projections; identical cutoff predicates and numeric operations | ACCEPT_WITH_LIMITATIONS, PRESENT |
| #4 | Rejected runner-vector materialization | REJECT_REGRESSION, ABSENT |
| #5 | analysis_result_contract.build_normalized_telemetry: initialize immutable tag metadata once; row parsing, quality and counters remain row-dependent | ACCEPTED, PRESENT |

All four accepted implementation patches pass git apply --reverse --check, without application. Current sii_runner.py SHA-256 is 90f19a86d8f0b5ccffdc15b954fd9d6d50d0b94e47b83eb3fd306bc472dd2f08, identical to the explicit #4 reversion record and accepted #5. Rejected SHA-256 is 18bb2d15ee7307994138cba4076b3398bf853214b1081c0be432c2119d5f3618. Older current-optimization-lineage-2026 prose saying #4 was investigation-only is superseded by optimization-04-runner-vector-implementation-2026/DECISION.md and RESULTS.json: it was implemented, measured, rejected and reverted.

The raw #5 measured times independently reproduce 120.98936049290933, 121.77337649813853 and 121.61011934513226 seconds; median 121.61011934513226. Original → #1 → #2 → #3 → #5 authority remains 141.232 → 138.159 → 128.639 → 128.512359 → 121.610119 seconds. No performance workload was executed here.

Retained #3/#5 10K status and every retained warmup/measured 500K semantic comparison pass (lineage.json). These are source historical evidence, not target validation. #3's small pipeline improvement remains within noise and its accepted limitations are retained. The prior historical integrity audit reports 125 evidence paths without recoverable original SHA-256; this task does not manufacture those hashes or upgrade that audit to unconditional historical byte-integrity PASS.

Production inspection confirms Aletheia generation/sealing is absent from source aletheia_governance and sii_intelligence; list_evp_records remains a read-only historical compatibility reader. observability exposes legacy records. Current runtime governance, product_evidence_contract, Measurable Consequence attachment, telemetry_result_artifact, telemetry_result_projection and replay code remain in the accepted 605-file manifest. Complete-upload repairs reside in upload_output_semantics, output_semantics, analysis_provenance, upload_jobs and their consumers: marked execution envelopes, completed-content hash rebinding, source chronology and immutable canonical artifact hashing remain distinct. Source Measurable Consequence and source-identity semantics are explicitly protected by docs/validation/current-product-integration/PORT_SCOPE.md and tests/test_governed_output_determinism.py.

Important: source's identity contract is not identical to target's. This is a verified lineage, not evidence that combining the candidates preserves analytical semantics. See TARGET_ONLY_RECONCILIATION.md.
