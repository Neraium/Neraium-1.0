# Prerequisite resolved prospectively

Frozen at 2026-09-24T18:00:22.498313+00:00, before any final workload. No production source was edited.

## Exact prerequisite discrepancy

`pre-gate-freeze.json` expects output_semantics.py SHA-256 `dd2480dcfb89dbab6a10fd8f66f6bdc60986345c23a07a1a4a7639d00110483c`. Current corrected candidate has `8127748ff4fa0cb625c8b24a722f803ea5e8c4480620cc57da9a6dac7a5d4c33`. Current candidate matches TARGET_POSTINTEGRATION_HASHES.json. Gate test, worker, bridge, upload encoder, provenance digest implementation and historical readers match their historical freeze.

The historical freeze filesystem mtime is 2026-09-24 17:26:49.831488510 UTC; first gate JUnit mtime is 17:27:36.622948019. Signal-order regression XML is 17:29:57.256474509; current comparator mtime is 17:30:53.827898377; terminal regression XML is 17:34:28.900016492. These are retained filesystem timestamps, not claims of authenticated authorship time. Architecture reconciliation script identity.py is dated 17:14 and architecture test XML 17:17:49; the freeze contains v2 comparator/bridge hashes. Thus it follows the initial architecture implementation and precedes both post-gate corrections. The architecture document was later updated at 17:43:05; that mtime does not date the original human decision.

Production changed after the freeze: the documented signal-order and terminal attempt fixes, plus the documented comparator alias responsibility correction and projection identity-contract propagation. The comparator discrepancy is not caused by the two defect fixes alone: it is a separate explicit post-gate change. EQUIVALENCE.md and TARGET_ONLY_RECONCILIATION.md record it.

The retained reconciliation script /tmp/neraium-promotion-20260924/identity.py shows aliases selected from runtime_metadata.legacy_root_aliases. Current semantic_content selects generated_at by governed v2 and analysis_id/upload_id only by execution.v1 producer contract. It no longer lets mutable runtime descriptions exclude arbitrary analytical fields. This enforces the already-authorized typed responsibility contract. No signal-order, consequence, evidence-reference or attempt_id exclusion was added to the comparator; attempt_id was already in the unchanged upload encoder.

The historical hash manifest is available, but an exact full byte copy matching its comparator hash was not found. Consequently this record proves the exact hash discrepancy and documents the retained script/current-source rule difference; it does not claim a reconstructed historical file or a byte-complete historical diff. All historical manifests and failure evidence remain untouched.

## Authority

The old frozen comparator cannot represent the corrected contract unchanged: mutable runtime alias lists are not semantic authority. Current user authorization explicitly permits a new prospective freeze of the already-authorized current comparator. This certification therefore freezes existing current bytes (also copied to current-comparator.py.txt), not a newly edited algorithm. No production semantics changed in this task. Historical v1 readers and SOURCE bridge remain unchanged.

## Static evidence

#1: upload_validator.numeric_column_schema hoisted outside row loop. #2: mode_conditioned_baseline uses explicit_mode_features and _recent_feature_support. #3: multiscale timestamp_projections reused, retained timezone branch/limitations. #5: build_normalized_telemetry caches tag classification/metadata in tag_summaries. #4: runner top-level AST functions equal validated SOURCE.

_relationship_rank is the three-value analytical tuple; stable sorting retains supplied ties. Both affected-signal producers use encounter-order _dedupe. Terminal current upload result is re-encoded after assigning attempt_id. Behavioral UTC, schema normalization and runtime-aware artifact validation match preintegration hashes; Phase 4 retains explicit source/content fallback and marked execution trace. Aletheia module contains only historical read compatibility; current intelligence has no gate/generation calls. No actuation or equipment write-back change exists in this certification. Retained focused tests establish exact-tie and identity edge cases; no broad suite is run.
