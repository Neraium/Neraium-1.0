# LBNL Validation v2 — Phase 1 determinism and provenance

This package measures repeatability of governed relationship evidence. It does not evaluate fault classification, diagnosis, prediction, or field performance. Baseline LBNL Validation v1 is immutable historical evidence; its full governed-output result remains 5/720 under its original normalization. This package does not change that normalization or replace that result.

## Prospective scope

The corrected user instruction authorizes the existing CASE_001 / CASE_022 repeat protocol after remediation. Two fresh executions each make 720 calls through app.engine.sii_engine.evaluate_sii, with no analytical configuration overrides. Each case uses the original 120 chronological windows, original 32/32/13 signal blocks, fixed first-seven-day reference, and exact hourly observations. Engine-owned persistence/recurrence states are copied chronologically within each block. No source values, sampling rules, thresholds, or qualification gates are changed. The runner opens neutral hourly inputs and units only, never the label mapping.

The two runs use distinct Python hash seeds and fresh runtime directories. Primary outputs are hash-frozen before the repeat starts. Both output sets are frozen before comparison. The source/protocol freeze is checked before and after execution. Complete engine returns, source row positions, input provenance, incoming/outgoing state digests, and checkpoint chain hashes are preserved.

## Output semantics fixed before execution

Production output_semantics.py declares governed-output-semantics.v1.

- Semantic analytical content: relationships, numerical calculations, classifications, persistence/recurrence, consequence status, summaries, source windows, source identities/hashes, limitations, and analytical state.
- Source provenance: times derived from source timestamps; absent source windows remain absent. Execution IDs cannot supply upload/source identities or evidence-reference identifiers.
- Runtime metadata: reserved runtime_metadata namespaces contain execution IDs, generation events, profiling and timings. Version-marked objects retain analysis_id and generated_at as documented runtime compatibility aliases; these two aliases are also omitted from semantic serialization. Other timestamps, IDs and fields are retained.

Canonical JSON sorts mapping keys and explicit sets, preserves every list/tuple order, rejects nonfinite numbers and unsupported objects, and does not round numbers. It does not apply generic timestamp-name exclusions or sort evidence lists to hide differences.

Acceptance: 720/720 identical complete semantic analysis_result objects. Additional exact comparisons cover semantic whole engine returns, relationship graphs, supplied-reference descriptors, and outgoing persistence/recurrence state hashes. Every mismatch is retained. No comparison definition changes in response to LBNL output are permitted.

A separate prospective bridge compares v2 relationship graphs to v1 graphs, removing only v1's old runtime_seconds envelope field and v2's declared runtime metadata. This checks preservation of relationship mathematics, not reproducibility of v1's full governed representation.

## Root-cause trace and remediation design

Trace and implementation plan were delivered before production edits. The trace covered:

1. analysis_result_contract.build_analysis_result supplies wall-clock completion/generation time to ConditionCorroborationService.build_conditions; _condition_timeline mislabeled the generated event source_timestamp. analysis_explanations.build_finding_activity_timeline had the same defect. Generation events now have runtime precision/time basis and are retained separately.
2. Both build_time_window implementations fell back to last-processed/completed time when source timestamps were absent. A synthetic runtime perturbation test independently exposed this defect; unavailable source time now stays unavailable.
3. _shared_signals iterated a set into insertion-ordered counts. Coherence/localization and common[:3] summary text inherited that order. These sets now use lexical signal order.
4. Corroboration rank ties, missing relationship IDs, and system-prefix selection depended on incidental input order. Numerical rank criteria are unchanged; ties use ascending stable relationship identity, missing IDs use canonical content hashes, and system prefixes use lexical order. Ranked findings, chronological observations, and directional pairs preserve meaningful order.
5. build_analysis_result.add_evidence embedded execution identity into evidence references. References are now analysis-local evidence seeds with existing collision handling; execution correlation remains separately available. Upload identities no longer fall back to execution IDs.
6. BackendSiiRunner.ingest placed wall-clock-derived run ID in its state envelope. It is now explicitly runtime metadata; engine-owned relationship state never uses it.
7. evaluate_temporal_math, SII module_envelope, and the engine processing trace embedded profiling/timings with evidence. Producers now place these in runtime metadata; upload consumers follow the new path. Historical baseline reports retain their existing operational performance schema.
8. Phase 4 _source_run_id could use execution run/job IDs as behavioral source identity. Only explicit source identity or deterministic observation identity now drives that path. Runtime IDs remain in the trace's runtime namespace. Missing-time behavioral attribution now uses UTC rather than host-local timezone.
9. Input row mappings are normalized to explicit supplied-column order, retaining extra keys deterministically. Chronological rows and schema column order are not reordered; this prevents dictionary insertion order from selecting context features.
10. Canonical governed hashing uses the declared contract instead of arbitrary object representations. Historical unversioned provenance hashes retain their legacy verification path.
11. Consequence execution correlation is retained in its runtime namespace; quantities, eligibility, units and calculation provenance are unchanged.
12. Graph traversal already sorts nodes, neighbors and component membership. Persistence/recurrence use source chronology. Ranked finding lists intentionally retain ranking order; set membership checks without serialized output are not reordered unnecessarily.

No analytical thresholds, persistence/recurrence rules, consequence integration formulas, or qualification criteria were tuned. Fixes implement the deterministic representation/source-provenance contract, not agreement with fault labels.

## Boundaries

This is software repeatability validation on one environment, not cross-platform floating-point equivalence. Explicit source IDs and incoming state are inputs and must match. Source chronology, schema order and ranked evidence sequences carry meaning. Phase 4 still has an explicitly limited deterministic missing-time attribution fallback; it does not constitute observed source time. No physical consequence capability, fault-label endpoint, or field usefulness claim is inferred.

Phases 2–7 require separately frozen protocols: independent telemetry relationship ground truth; controlled persistence sequences; physical consequence eligibility/calculation; abstention; independent datasets; then blinded operator review. They are not established by this Phase 1 result.
