# Applied surgical promotion changeset

Prior blocked inventory retained [verbatim](history-before-human-authority/CHANGESET.md).

Every production hunk is enumerated in [production-hunks.json](production-hunks.json), with SOURCE/TARGET path, function, feature, retained target behavior, ranking/identity implications and strategy. [promotion.patch](promotion.patch) is the exact delta against the pre-task TARGET worktree, not against HEAD (which already had user changes).

Files unchanged from TARGET include behavioral_model.py (UTC), sii_inputs.py (schema normalization), telemetry_result_artifact.py (runtime-aware strict identity). Phase 4 keeps target identity semantics and adds only an explicit execution-envelope marker. Projection keeps its runtime identity checks. No benchmark/performance optimization or security work was added.

| Target file | Feature | Changed functions/hunks |
|---|---|---|
| `backend/app/engine/sii/common.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations, module_envelope |
| `backend/app/engine/sii/mode_conditioned_baseline.py` | #2 operating context feature extraction | _recent_feature_support, analyze_mode_conditioned_baseline, module/UI declarations |
| `backend/app/engine/sii/multiscale_analysis.py` | #3 timestamp reuse (retained limitations) | analyze_multiscale |
| `backend/app/engine/sii/phase4.py` | Preserve TARGET source/content identity and mark execution trace | evaluate_phase4, module/UI declarations |
| `backend/app/engine/sii_engine.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | evaluate_sii, module/UI declarations |
| `backend/app/engine/temporal_math.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | evaluate_temporal_math, module/UI declarations |
| `backend/app/routers/observability.py` | Historical Aletheia read endpoint labeling | get_evp_governance_records, get_observability_performance |
| `backend/app/services/aletheia_governance.py` | Retire current Aletheia generation; retain historical reader | list_evp_records |
| `backend/app/services/analysis_explanations.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | ensure_finding_context, module/UI declarations |
| `backend/app/services/analysis_provenance.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | build_analysis_provenance, module/UI declarations, result_digest |
| `backend/app/services/analysis_result_contract.py` | #5 normalized telemetry metadata; typed identity and governed evidence | _sii_provenance, add_evidence, build_analysis_result, build_condition_contracts, build_normalized_telemetry, empty_analysis_result, empty_sii_evidence_projection, module/UI declarations |
| `backend/app/services/baseline_analysis_repository.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations, persist_completed_analysis |
| `backend/app/services/behavioral_baseline.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | _correlation, _identify_modes, _relationship_edge, _sequential_product_sum, _signal_characteristics, _std, module/UI declarations |
| `backend/app/services/condition_corroboration.py` | Human decision: evidence-only rank, supplied ties; marked runtime events | _coherent_groups, _condition_change_summary, _condition_classification, _condition_evidence, _condition_headline, _corroboration_result, _relationship_columns, _relationship_rank, build_conditions, localize_condition, module/UI declarations |
| `backend/app/services/data_quality.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | parse_numeric_value |
| `backend/app/services/historical_ingestion.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | _convert_value, _has_unit_marker, add, build_historical_ingestion |
| `backend/app/services/operating_modes.py` | #2 operating context feature extraction | describe_mode, explicit_mode_features, numeric_band_references |
| `backend/app/services/output_semantics.py` | Human decision: v2 producer-typed semantics and explicit historical readers | _legacy_reader, canonical_json, evidence_identifier, govern_runtime, plain, runtime_metadata, runtime_value, semantic_content, semantic_digest, separate_generation_events |
| `backend/app/services/output_semantics_legacy_source.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | canonical_json, plain, semantic_content, semantic_digest |
| `backend/app/services/output_semantics_legacy_target.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | canonical_json, plain, semantic_content, semantic_digest |
| `backend/app/services/sii_intelligence.py` | Retire current Aletheia calls only | build_intelligence_status, build_sample_intelligence, build_upload_intelligence, module/UI declarations |
| `backend/app/services/sii_runner.py` | Validated SOURCE baseline arithmetic/cache; marked runtime correlation; #4 absent | _baseline_distance_contraction_path, _baseline_mahalanobis_distances, _regularized_covariance_matrix, ingest, module/UI declarations |
| `backend/app/services/telemetry_result_projection.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations |
| `backend/app/services/upload_evidence.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | _traceability_timestamps_from_result, module/UI declarations |
| `backend/app/services/upload_jobs.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | _build_csv_result, _finalize_completed_upload, _scope_job_payload, module/UI declarations |
| `backend/app/services/upload_output_semantics.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | _move, _owned_records, encode_upload_result, upload_compatibility_view |
| `backend/app/services/upload_persistence.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations, project_result_for_transport, read_upload_history, summarize_result |
| `backend/app/services/upload_pipeline.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations, run_structural_analysis_pipeline |
| `backend/app/services/upload_state_repository.py` | Current typed execution metadata at terminal publication; runtime-aware immutable attempt readers | _payloads_share_attempt, _upload_attempt_id, module/UI declarations, write_upload_completion |
| `backend/app/services/upload_validator.py` | #1 snapshot schema hoist | stream_csv_snapshot |
| `backend/app/water_intelligence/interpreter.py` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | _build_water_insight, interpret_water_intelligence, module/UI declarations |
| `frontend/src/App.test.js` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations |
| `frontend/src/AuthenticatedApp.jsx` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations |
| `frontend/src/components/GovernanceAdminWorkspace.jsx` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations |
| `frontend/src/components/SystemTopologyWorkspace.jsx` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations |
| `frontend/src/components/SystemTopologyWorkspace.test.js` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations |
| `frontend/src/config.js` | Validated SOURCE candidate provenance/runtime repair or Aletheia UI retirement | module/UI declarations |

Historical helper modules freeze the two incompatible existing v1 readers. They are not current generators. Prospective output uses v2. The complete-upload v2 producer's durable source ownership remains explicitly distinct from generic execution run/job/upload IDs. Paired-reference analysis identity remains source-content-derived.

Supporting changes are limited to four optimization fixture/test modules, the existing complete-upload gate and its predeclared version/build bridge, current architecture tests, the superseded target tie test, Aletheia retirement tests/UI, and exact retained small-gate dependencies. Historical retained files are copied byte-for-byte; no scale controller is executed.
