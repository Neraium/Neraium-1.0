# Semantic versus runtime identity contract analysis

Decision: **UNRESOLVED_HUMAN_DECISION_REQUIRED** for the complete cross-repository identity contract. Several producer-specific subcontracts are established below; that does not establish a complete replacement or migration policy for overloaded legacy fields.

## Authority follows producer and version, not a field name

`run_id` is demonstrably two different things in this product. `sii_runner.run_uploaded_telemetry` creates `upload-{datetime.now(UTC).timestamp()}` and passes it into `BackendSiiRunner.ingest`: execution correlation. Both repositories separate this returned value into runtime metadata. In contrast, `telemetry_analysis_window.run_analysis_window` sets `analysis_id=window.window_id`, `run_id=window.source_run_id`, and explicit Phase 4 `source_run_id`. These identify a scoped canonical source/window, not a new engine attempt.

The latter is established by committed connector architecture, not inferred from variable names: `.planning/research/canonical-connector-result-design.md:12–46`, `telemetry_analysis_service.deterministic_analysis_window_id`, window lineage membership validation, and artifact identity checks. TARGET's broad removal of analysis/run identifiers from governed semantics therefore cannot be accepted universally. SOURCE's preservation of every legacy alias also cannot prove that every caller-provided `run_id` is source-owned.

Both modules claim `governed-output-semantics.v1` while applying different exclusion/encoding rules. The same version string does not distinguish historical records between these contracts. Reinterpreting stored v1 objects through the other implementation is not an authorized migration and can change verification results.

## End-to-end producer / storage / replay trace

1. Upload orchestration (`upload_jobs.process_csv_file`, `upload_evidence`) uses `job_id` as run/upload/analysis correlation and durable route/index ownership. It also stores dataset/scope and raw-input digests. The existing fallback is an established upload ownership convention; a new upload of identical bytes is not necessarily the same source record. SOURCE preserves it; TARGET removes parts of the governed fallback but still writes run/upload/job identity in evidence records.
2. Connector service derives a deterministic window from authority scope, connection, source ingestion run, system/asset and source bounds. The canonical window verifies source run belongs to observation lineage. `run_analysis_window` supplies that identity to the engine and result builder. Neither repository changes this producer.
3. `sii_inputs.normalize_rows`: SOURCE retains mapping insertion; TARGET uses schema then sorted extras. Chronology/schema order is not made runtime. Both Phase 4 digest fallbacks use sorted-key JSON, so mapping-order normalization does not by itself change that digest for the same mappings; it can affect downstream schema-sensitive feature construction.
4. `phase4._source_run_id`: SOURCE accepts explicit source_run_id, then run_id, then job_id, else content digest. TARGET accepts explicit source_run_id only, then the same content digest, retaining run/job as trace runtime metadata. Both use the resulting identity in behavioral attribution, learning, storage and snapshot provenance. It is not just a diagnostic label.
5. `behavioral_model.resolve_infrastructure_identity` and `behavioral_model_contract` keep authenticated scope, configured infrastructure/model identity and schema. Model namespace and source-run identity are distinct. `build_behavioral_snapshot` hashes model ID, model version, source_run_id and previous snapshot ID. Store methods attribute immutable records/audit and deduplicate by their established identifiers. Changing a source_run_id can alter snapshot identity/history without changing the business model ID.
6. `analysis_result_contract.build_analysis_result` creates canonical findings/evidence and attaches consequence after sanitization. SOURCE hashes evidence seed plus source file/upload/window/payload; TARGET uses analysis-local seed with collision suffixes. SOURCE retains source-owned metadata. TARGET `govern_runtime` removes run/job/consequence correlation and versioned analysis_id from semantic content.
7. `analysis_provenance.result_digest`: both preserve a legacy unversioned algorithm. SOURCE adds `complete-upload-evidence.v2`, includes source input hash/configuration/active baseline, relocates only producer-owned execution fields, and removes the embedded self-referential result_hash link. TARGET lacks that producer contract/module; marked analysis roots use its different semantic filter.
8. `upload_jobs` SOURCE rebinds final evidence provenance to completed analytical content before sealing; `upload_output_semantics.encode_upload_result` owns enumerated upload clocks/progress, while `upload_compatibility_view` restores only those aliases for transport. TARGET lacks this complete-upload layer. A transport alias is not authority to reclassify arbitrary source fields.
9. `telemetry_result_artifact` hashes exact canonical JSON, rejects nonfinite payloads, validates indexed identities, and stores immutable bytes. TARGET accepts runtime_metadata.run_id before the legacy analysis_metadata location to compensate for its relocation; SOURCE validates analysis_metadata.run_id. Both require equality with source_run_id and analysis_id=window_id. Moving the value did not turn the artifact's source run into an execution attempt.
10. `telemetry_result_projection` SOURCE adds runtime/output-semantics allowlist fields; TARGET has runtime-first run validation. `telemetry_result_service` is byte-identical and reads the verified persisted artifact without engine recomputation. Upload replay routes likewise read persisted results; source/behavioral scope and finding IDs must remain reconstructable. Result hashes, immutable artifact hashes and database route IDs are different identities.
11. Evidence Package v1, governed evidence objects and Measurable Consequence retain their own versions and provenance references. Governance IDs are content hashes; source windows and decision-time knowledge matter. No generic exclusion for all timestamps or all `*_id` fields follows from those contracts.

## Identifier classification table (observed behavior, not a newly approved schema)

Categories are those requested. Multiple categories mean one value has multiple roles. “Retained” means a field participates when present in the governed object; it does not claim every top-level field is selected by `result_digest`. Complete-object semantic digests, selected-result digests and immutable artifact hashes must not be conflated.

| Identifier / producer or path | SOURCE classification | TARGET classification | Disagreement / scope |
|---|---|---|---|
| `analysis_result.analysis_id`, including connector window ID | SEMANTIC; SOURCE_IDENTITY; PROVENANCE | PRESENTATION_ONLY / EXECUTION_METADATA in marked semantic roots; still SOURCE_IDENTITY for artifact validation | Yes: excluded from target governed digest even when producer supplies a source window. |
| `analysis_metadata.run_id` | SOURCE_IDENTITY; PROVENANCE; SEMANTIC | EXECUTION_METADATA after relocation | Yes: connector uses a real source-ingestion ID; whole engine lineage still retains source identity elsewhere. |
| `analysis_metadata.job_id` | SOURCE_IDENTITY/PROVENANCE alias and SEMANTIC when present | EXECUTION_METADATA | Yes: source keeps historic upload aliases; target treats these as execution. |
| Top-level durable upload `job_id` / API route | SOURCE_IDENTITY; PROVENANCE; execution correlation | SOURCE_IDENTITY; PROVENANCE; execution correlation outside the governed relocation | Not universally removed in either repository; changing a route/index key can select another persisted record. |
| `upload_id` explicitly supplied | SOURCE_IDENTITY; PROVENANCE; SEMANTIC | SOURCE_IDENTITY; PROVENANCE; SEMANTIC | Same basic role. |
| Missing historical-upload `upload_id` | SOURCE_IDENTITY synthesized from job_id/analysis_id; SEMANTIC | No governed fallback; empty/missing | Yes. Target evidence record builder still emits upload_id=run_id, so target does not eliminate this convention globally. |
| Connector missing `upload_id` | Absent, no synthetic upload ownership | Absent | Agreed; connector is not an uploaded CSV. |
| `sii_evidence.provenance.analysis_run_id` | PROVENANCE; SOURCE_IDENTITY; SEMANTIC | EXECUTION_METADATA after relocation | Yes; artifact/lineage may still carry the same source identity independently. |
| `measurable_consequence.analysis_run_id` | PROVENANCE; SOURCE_IDENTITY when producer is source-owned; SEMANTIC | EXECUTION_METADATA after relocation | Yes; formula/quantity functions remain the same, provenance representation does not. |
| Runner's wall-clock `run_id` | EXECUTION_METADATA in marked envelope | EXECUTION_METADATA in unmarked reserved envelope | Same intended execution-only role; different serialization marker. |
| Explicit Phase 4 `source_run_id` | SOURCE_IDENTITY; PROVENANCE; contributes to BEHAVIORAL_IDENTITY records | Same | Agreed. |
| Phase 4 fallback `config.run_id/job_id` | SOURCE_IDENTITY; PROVENANCE; contributes to BEHAVIORAL_IDENTITY | EXECUTION_METADATA; replaced by row-content digest for source attribution | Yes; caller intent not encoded in those aliases. |
| Phase 4 content fallback `deterministic-run:<digest>` | SOURCE_IDENTITY; PROVENANCE | Same when fallback used | Same algorithm, different fallback trigger. |
| Dataset/baseline/scope IDs, connection ID and authority digest | SOURCE_IDENTITY; PROVENANCE; SEMANTIC | Same | No general exclusion; preserve authenticated isolation and exact reference ownership. |
| Behavioral `model_id`, schema fingerprint, model/baseline version | BEHAVIORAL_IDENTITY; PROVENANCE; SEMANTIC | Same | Source-run fallback and attribution timestamp may indirectly affect records/history; model namespace algorithm unchanged. |
| Behavioral `snapshot_id`, previous snapshot, event/learning record refs | BEHAVIORAL_IDENTITY; PROVENANCE; SEMANTIC | Same roles | Derivation can differ through source-run policy; do not dismiss as display IDs. |
| Governed `evidence_index` IDs / references | SEMANTIC; PROVENANCE; source-bound seed+content hash | SEMANTIC; PROVENANCE; analysis-local seed+suffix | Yes: equal ID strings are not proof of equal source evidence in target. |
| Missing relationship ID / condition prefix | SEMANTIC; PROVENANCE; index fallback / first system prefix | SEMANTIC; PROVENANCE; canonical content fallback / lexical system prefix | Yes, also affects ranking conflict. Explicit IDs are retained. |
| Governance evidence/decision IDs | SEMANTIC; PROVENANCE; content-addressed immutable snapshots | Same implementation | Neither semantic helper may redefine stored governance identities. |
| `result_hash` and `result_hash_contract` | PROVENANCE; selected semantic content; explicit complete-upload v2 binding when marked | PROVENANCE; legacy or target marked-root digest | Yes: selected inputs, producer encoding and semantic exclusions differ. |
| Raw `input_hash`, observation IDs and lineage digest | SOURCE_IDENTITY; PROVENANCE; SEMANTIC | Same roles | SOURCE complete-upload digest explicitly binds input hash/configuration/baseline; not equivalent to target's result selection. |
| Connector `window_id` / canonical `result_id` | SOURCE_IDENTITY; PROVENANCE; stable window/execution-version UUIDv5 for result | Same artifact identity | Same identity algorithm; root analysis_id filtering disagreement does not remove artifact validation. |
| Canonical `payload_digest` | PROVENANCE, exact-byte artifact integrity | Same | All persisted content, including runtime metadata, affects exact bytes. Not an execution-filtered semantic digest. |
| Source observation times / chronology / calculation bounds | SEMANTIC; SOURCE_IDENTITY/PROVENANCE | Same roles | Retain unchanged. |
| Generation clocks, timings, progress | EXECUTION_METADATA at declared producer paths; generated_at compatibility PRESENTATION_ONLY | EXECUTION_METADATA at reserved namespaces and marked aliases | Intent broadly agrees; complete-upload producer coverage differs. |
| Missing-source-time `build_time_window` fallback | Runtime-origin completion time used as SEMANTIC qualification/window input | No source window fabricated from execution time | Yes; source explicitly characterizes and defers this coupling, target repairs it. |
| Synthetic missing-time behavioral attribution | BEHAVIORAL_IDENTITY/PROVENANCE attribution, explicitly synthetic; host-local formatting | Same role, UTC-stable formatting | Yes in representation under different host zones; no claim it is an observed source timestamp. |
| Arbitrary unmarked `runtime_metadata` field | SEMANTIC if not explicitly execution-version-marked | EXECUTION_METADATA by key name, recursively omitted | Yes; source demonstrates source-owned values with that name. |
| Marked `execution-metadata.v1` attempt IDs | EXECUTION_METADATA | EXECUTION_METADATA (marker not required) | Same exclusion on explicitly marked examples. |

No established rule makes every identifier PRESENTATION_ONLY. An alias can remain visible for humans/API correlation while being excluded from an explicitly defined semantic projection; its persisted value still belongs to the audit record.

## Controlled mutation diagnostics

Only tiny in-memory diagnostics were run in each existing environment, with production files untouched. A minimal governed record contained source-window analysis_id, upload_id, analysis_metadata.run_id/job_id and a consequence analysis_run_id. Each field was changed separately before `govern_runtime`; unmarked/marked runtime envelopes were separately tested directly through `semantic_digest`. These tests expose current functions, not a proposed new comparator.

| Isolated field mutation | SOURCE governed semantic digest changes? | TARGET governed semantic digest changes? |
| `analysis_id` | YES | NO |
| `run_id` | YES | NO |
| `job_id` | YES | NO |
| `upload_id` | YES | YES |
| `consequence_run` | YES | NO |
| `unmarked_runtime` | YES | NO |
| `marked_runtime` | NO | NO |
| `generated_at` | NO | NO |

These results are for the named projection and controlled payload. They do not imply that changing all copies of a connector source_run_id leaves TARGET's complete execution digest unchanged: lineage/window/source fields remain elsewhere. Nor does semantic equality imply artifact-byte equality. TARGET recursively marks nested analysis_id-bearing records in `govern_runtime`, so nested source references can also be reclassified; SOURCE's direct identity-preservation regression protects against that.

## Effects of each disagreement

“Replay changes” below distinguishes a changed newly generated artifact from replaying an already stored immutable record. No sanctioned replay reader recalculates or overwrites historical IDs.

| Disagreement | Semantic digest / evidence identity | Source and behavioral identity | Replay / execution-only determination |
|---|---|---|---|
| analysis_id alias exclusion | SOURCE mutation changes digest; TARGET isolated alias mutation does not. Source evidence IDs are not simply prefixed with analysis_id, but upload fallback can bind it indirectly. | Connector analysis_id is the window ID; changing it alone violates artifact identity. Not a direct behavioral model key. | Original ID must be retained for replay/routes. Connector case is not execution-only. Ambiguous upload aliases need explicit ownership policy. |
| run_id/job_id relocation | SOURCE retained metadata affects governed digest; TARGET moved-only copy does not. Upload/evidence fallback can also change references. | Connector source run remains lineage-owned. Phase 4 config aliases separately affect source attribution and snapshot history. | Artifact validator still requires exact source equality, even at runtime location. A runtime namespace does not make a source-ingestion ID optional. |
| upload fallback removal | Changes governed upload_id, evidence binding and digest for callers without explicit upload_id. | Changes asserted upload ownership, not necessarily raw bytes. | Historical upload retrieval/evidence routes use durable IDs. Distinguish retry of same source from a new ingestion of equal bytes; no universal equality contract was found. |
| consequence/provenance analysis_run_id removal | SOURCE binds value; TARGET moved copy is excluded; recorded provenance shape differs. | May be source-owned connector ingestion or legacy run attribution; quantity formula is not modified. | Exact consequence provenance must survive immutable replay. Whether a particular producer's value is execution-only requires producer/version knowledge. |
| evidence ID derivation | SOURCE seed+source-window/payload hash responds to content; TARGET seed+collision suffix may stay unchanged for changed evidence. Both retain references in semantics. | Neither alone substitutes for source identity; target references are analysis-local. | Changing reference scheme requires preserving old references and defining prospective scope; neither scheme is globally interchangeable. |
| Phase 4 fallback identity | Different config aliases alter SOURCE source ID; TARGET ignores them and hashes rows. Source ID appears in trace and behavioral provenance. | Snapshot identity, attribution and storage history can change; infrastructure model ID need not. | Explicit source_run_id is agreed. Whether legacy run/job means immutable ingestion or attempt is not encoded; cannot safely infer. |
| arbitrary runtime_metadata exclusion | SOURCE unmarked source content affects digest; TARGET omits it. | Can hide source evidence, including scalar source values with that key, from semantic comparison; not from immutable artifact bytes. | SOURCE marker requirement has direct source-data regression support; broad key-name removal is not a safe general rule. |
| full-upload hash contract | SOURCE binds input/configuration/baseline and completed result with self-reference handling; TARGET lacks v2. | Different semantic result identity; raw input hashes remain independently recorded. | Existing hashes must be checked with their original algorithm; do not silently rehash old artifacts. |
| absent-source-time fallback | SOURCE completion time can change evidence/window/qualification and digest; TARGET leaves source window unavailable. | Runtime time is not observed evidence; this can affect qualification and finding-owned consequence window. | SOURCE explicitly defers correction to preserve prior analytical behavior; TARGET asserts correction. A migration/qualification decision is needed, not a comparator omission. |
| UTC synthetic attribution | SOURCE local-zone formatting can vary; TARGET UTC is stable for the same digest. | Both keep synthetic attribution limitation; possible provenance/snapshot content changes across zones, not a new observed time. | Supports target's determinism intent; historical representations still must not be rewritten. |
| schema-ordered normalization | Can change downstream feature selection if mapping insertion used as order; chronology and schema remain inputs. | Sorted-key fallback source digest itself is mapping-order-insensitive. | TARGET intent explicitly preserves schema and fixes accidental mapping order. This does not settle ambiguous ID ownership or rank ties. |
| runtime-aware artifact/projection validation | Accepts relocated run ID while retaining equality checks. Canonical bytes reflect the representation used. | Required source run is still required, not discarded. | Historical compatibility improvement; does not authorize redefining it as execution-only. |

## Historical intent and evidence strength

- Phase 4's configured source_run_id/run_id/job_id fallback originates in `c7d57ad594e1c554669e6a0593c62c0963e35eef` (“activate phase 4 in unified evaluation path”), as shown by blame. The public source-run storage interfaces preserve attribution. History proves acceptance of the aliases, not that every future caller means source ingestion.
- Connector producer identity is shared committed work: `c3e5e4d5e337633c162512b67c373675bdbaa23c` introduces generic telemetry workflow; `4838b1c073397db76fbd9e60a6d733f24d9fbb5f` persists canonical connector results. Its committed design specifies exact source/window identity, original generated IDs, no SII on completed-result replay and divergence rejection for the same artifact owner. This positively establishes semantic/source ownership in that path.
- TARGET's stable ranking, runtime/semantic split, UTC attribution, schema ordering and runtime-aware artifact checks are uncommitted worktree changes. `lbnl-determinism-v2/METHODOLOGY.md:29–46` records their intended purposes: repair runtime contamination, source-time misattribution, incidental order and replay compatibility. No source benchmark speedup is offered as their reason. The methodology is evidence of intent, not proof of a completed campaign or of authority to reclassify connector-owned IDs.
- SOURCE's output_semantics and complete-upload layer are also worktree additions. `current-product-integration/PORT_SCOPE.md` explicitly rejects wholesale old-base fallback removal, protects source-window analysis_id/run_id and consequence ownership, and defers missing-time qualification changes. It reports an adversarial correction: unmarked source runtime_metadata must remain semantic. This is deliberate current-source intent, not just legacy accident.
- Shared `docs/EVIDENCE_GOVERNANCE_FOUNDATION_V1.md:7–35` requires content-addressed evidence, exact provenance/decision bases and historical reconstruction; meaningful source and decision timestamps are not universally volatile. `docs/ANALYSIS_RESULT_CONTRACT.md:101–102` calls analysis_id a stable analysis-run ID and upload_id the telemetry source ID, but does not resolve every source-versus-attempt overload. `docs/EVIDENCE_PACKAGE_V1.md` preserves persisted provenance and does not fabricate source onset from completion time. These support producer-specific classification, not either implementation's global name-based inference.

## Retained validation and tests

SOURCE current-product integration retained `repair-focused-tests.xml` (62 cases, no failures) includes source identity preservation, runtime isolation, missing-time coupling characterization, provenance hashes, canonical artifact round-trip and consequence certification. `repair-compatibility-tests.xml` also retains the tie test. Relevant direct nodes in `tests/test_governed_output_determinism.py` are:

- `test_runner_incoming_history_and_persistence_ignore_execution_ids`
- `test_runtime_changes_do_not_change_semantic_hash_or_summaries`
- `test_source_analysis_identity_is_never_runtime_noise`
- `test_current_consequence_and_source_ownership_survive_runtime_changes`
- `test_missing_source_time_known_contract_coupling_is_preserved`
- `test_missing_source_time_known_execution_dependence_is_not_repaired`
- `test_legacy_canonical_artifact_hash_and_versioned_round_trip`
- `test_generation_provenance_survives_connector_projection`
- `test_runtime_named_source_data_is_not_excluded` (current adversarial regression; not claimed present in the earlier 62-case XML).

SOURCE #5 freezes output_semantics and the complete-upload test as part of its declared contract, retains a passing complete 10K test and 500K semantic comparisons. These validate its own definition and inputs; changing fixed source IDs/introducing new attempts was not a demonstrated cross-contract experiment. 121.610119 seconds remains source retained performance evidence only.

TARGET has existing tests `test_runtime_metadata_cannot_change_semantics`, `test_runtime_ids_do_not_create_evidence_identity`, `test_phase4_source_identity_ignores_execution_identity`, `test_legacy_result_hash_is_preserved`, `test_canonical_serialization_preserves_semantic_order`, plus its six-process state/mapping-order test. Prior reconciliation JUnit proves the runtime-ID and Phase 4 tests (and permutation ranking) passed. Do not infer passes for the others from existence. LBNL-v2 has protocol/scripts but no retained completed comparison result in its directory. LBNL-v1's 5/720 full-governed repeat result motivates work but does not validate the target remediation.

Shared supporting contracts/tests inspected: `tests/test_analysis_provenance.py`; `test_telemetry_analysis_handoff.py` (server-owned identity, no upload identity for connector, source cannot override authority); `test_telemetry_analysis_authority.py`; `test_telemetry_analysis_service.py::test_window_identity_is_stable_and_scope_bound` and `test_completed_window_is_idempotent_without_second_sii_call`; `test_telemetry_result_artifact.py` (identity, payload mutation, original versions/IDs, strict encoding, exact consequence replay); `test_telemetry_result_projection.py`; `test_phase4_upload_system_identity.py` (queue binding, retry identity, replay without Phase 4 writes); `test_sii_phase4_primitives.py`, `test_sii_phase4_orchestrator.py`, `test_behavioral_model_store.py`; governance audit/lifecycle/compatibility tests; consequence and replay tests. These establish important subcontracts, not a single global exclusion rule.

## What can already be stated authoritatively

- Numerical evidence, qualification, persistence/recurrence state, consequence quantities and evidence sufficiency are semantic.
- Connector window/source ingestion IDs, observation membership, raw-input provenance, scope, baseline/model references and immutable result identity cannot be treated as arbitrary attempt IDs. The committed producer/storage design establishes this.
- The wall-clock runner correlation and actual profiling/progress measurements are execution metadata. Both current producers and tests establish this.
- Behavioral model/snapshot/lineage identity and decision-time provenance remain reconstructable and protected; an unchanged business model ID does not imply unchanged behavioral history.
- Immutable artifact integrity covers exact bytes, including runtime bookkeeping. Semantic exclusion never licenses mutation of a stored artifact. Replaying the same stored result must retain every original identifier and hash.

## Remaining exact decisions for human authority

**UNRESOLVED_HUMAN_DECISION_REQUIRED**, rather than declaring a fully specified MERGED_IDENTITY_CONTRACT_REQUIRED. A producer-aware separation is necessary in principle, but repository evidence does not establish the complete policy needed for these overlapping public inputs:

1. For legacy upload/Phase 4 callers providing only run_id/job_id, is that a durable ingestion/source identity or an execution attempt? Which observable producer/version distinguishes them? Is a new upload with equal bytes a new source, while a retry keeps the same source? The existing schemas do not answer this universally.
2. Which existing `governed-output-semantics.v1` interpretation owns which stored records, and what prospective version/compatibility policy may supersede it? The two encoders use the same version string with different exclusions (also different nonfinite/datetime representation); historical hashes must not be silently reinterpreted.
3. May missing-source-time qualification change prospectively, or must the source's characterized legacy fallback remain for its established path? Removing the fallback is a semantic correction decision, not merely relocating runtime clocks.
4. Should future governed evidence IDs remain source/content-bound or analysis-local, and how are existing references retained across a new contract? Both can reference evidence, but they define different identity stability and cannot be substituted in immutable records.

It would be possible to design a merged contract with explicit producer ownership and versioned aliases, but claiming that exact design is already authoritative would exceed the retained evidence. No production implementation or migration policy is authorized by this document. The source's precise connector protections and target's runtime/determinism fixes must both inform, rather than pre-empt, the decision.

## Human authority addendum — 2026-09-24

The previous UNRESOLVED conclusion is superseded prospectively by the user-supplied architecture decisions. See [current decision](ARCHITECTURAL_DECISION.md). All preceding investigation and retained evidence remain historical and unchanged.
