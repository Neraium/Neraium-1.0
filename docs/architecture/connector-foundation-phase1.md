# Connector foundation Phase 1: existing authority and stop decision

Status: **implementation stopped under the requested architecture stop conditions**.
This report records the completed pre-edit trace. It does not establish a second
canonical contract or authorize changes to certified analytical semantics.

## Baseline

- Branch: `fix/deterministic-governed-output`
- HEAD: `d79cdb6222203e9313b6b4fc9a294a38d5f7c976`
- Tracked worktree and index were clean before investigation.
- Existing untracked validation artifacts and scripts were excluded from the trace
  and remain untouched. No commit, push, adapter, migration, or deployment occurs.

## Existing ingestion architecture

### Production connector path

1. `backend/app/connectors/base.py`: `TelemetryConnector` emits
   `RawObservationEnvelope` records in `ConnectorPage`. The source supplies tag,
   timestamp, value, reported unit/quality, optional event ID and bounded metadata.
   This is already a protocol-independent acquisition boundary.
2. `telemetry_runtime.py` wires `prepare_connector_page` into the scheduler.
   `telemetry_scheduler.py` claims scoped work, loads persisted connection,
   checkpoint, mapping and deduplication state, then fetches an incremental or
   bounded historical page through the provider registry.
3. `telemetry_ingestion.py` applies an authoritative `MappingSnapshot`, checks
   scope/connection, validates metadata, quality, timestamps and explicit units,
   then returns immutable `PreparedObservation` and `PreparedRejection` records.
   Individual source errors do not discard valid siblings.
4. `telemetry_repository.py::persist_ingestion_page` persists observations,
   rejections and checkpoint compare-and-swap in one transaction. It validates
   lease and mapping authority, enforces scoped joins and handles conflicts.
5. `telemetry_analysis_window.py::build_canonical_analysis_window` selects eligible `good`
   numerical observations, validates system/asset/source membership, and pivots
   by canonical signal identity. `telemetry_lineage.py` preserves durable
   source-to-observation evidence and bounded public lineage summaries.
6. The existing analysis service executes the analytical pipeline and persists
   canonical result artifacts. `telemetry_result_artifact.py` and repository
   retrieval verify immutable canonical bytes and identity. Customer projections
   and replay consume those artifacts; they must not re-run or re-rank analysis.

### Upload and historical path

`upload_jobs.process_csv_file` hashes the raw input, calls
`historical_ingestion.prepare_tabular_source`, then `build_historical_ingestion`.
The historical layer preserves raw artifacts, profiles timestamps/units/values,
records human mapping decisions, flags duplicate channels/rows, orders canonical
rows and writes a canonical JSONL artifact. Dataset identity binds raw SHA-256,
parser/canonical/mapping/unit/quality versions and sorted review decisions.
Its trusted handoff supplies analytical rows and provenance to upload processing.
`upload_pipeline.py` disables fill for trusted historical dataset input.

`telemetry_normalization.py` implements existing integrity and analytical
normalization; it is not a replacement acquisition SDK. `upload_persistence.py`
uses dataset-scoped storage and bounded transport projections.
`upload_evidence.py`, `upload_output_semantics.py` and `analysis_provenance.py`
retain evidence ownership, versioned semantic hashes and execution separation.
`upload_replay.py` is a separate legacy replay utility; its fallback-index
timestamp behavior must not become a connector source-time policy.

The historical/manual `ConnectorBase`, `NormalizedTelemetryRecord`, legacy
SQLite live telemetry, and compatibility connector routes are not the production
canonical authority. The `ConnectorBase` docstring explicitly distinguishes them.
Do not route new adapters through them to bypass production admission.

## Canonical ingestion contract: reuse, do not replace

The existing layered contract already supplies the requested principal boundary:

`source -> RawObservationEnvelope / ConnectorPage -> MappingSnapshot ->
prepare_connector_page -> scoped normalized_observations -> analysis window ->
existing analytical pipeline`

| Requested concept | Existing authority / gap |
| --- | --- |
| Version | Source digest `neraium.telemetry.source-record/v1`, timestamp and unit versions, mapping revision and lineage versions exist; no unified observation wire spec exists. |
| Observation identity | Scheduler allocates UUID; persistence owns admission. `CanonicalObservationIdentity` wraps that existing UUID and explicitly forbids re-deriving it. |
| Site/workspace | `TelemetryScopeRef`: tenant, workspace, canonical resource scope, facility. Server authority, not source input. |
| Source/native identity | Scoped connection, external signal/tag, provider event ID, typed source-record digest. |
| Semantic identity | Approved mapping supplies system, asset and canonical signal/concept. |
| Provenance | Mapping actor/time/revision/digest, raw timestamp, offsets, original unit/value, source metadata, connection and source ingestion run. |
| Value | Raw scalar and normalized finite numerical value are separate. Admitted numerical representation is float. |
| Quality | Reported text and admission quality exist; source `UNKNOWN` and `UNCERTAIN` are not distinct canonical states. |
| Time | Original source time, normalized observation time and ingestion time exist; no typed acquisition time. |

No machine-readable replacement schema is issued: doing so before reconciling
these authorities would incorrectly imply an approved competing contract.

## Identity, provenance and deterministic replay

The current authority is the 2026-09-24
[architectural decision](../validation/validated-candidate-integration-2026/ARCHITECTURAL_DECISION.md),
not its superseded unresolved investigation. It separates SEMANTIC,
SOURCE_IDENTITY, BEHAVIORAL_IDENTITY, PROVENANCE and EXECUTION_METADATA by producer,
version, derivation and consumer, never just a field name.

`stable_source_record_digest` uses type-preserving scalar encodings for tag,
source timestamp, raw value, reported unit, reported quality and provider event
ID. Metadata enrichment, worker and attempt identity do not enter this digest.
Scope and mapping authority are enforced separately by persistence. Changing a
source-owned tag/event/value/unit/quality changes the digest. Equivalent instants
spelled with different raw offsets need not have equal source-record digests:
raw provenance is intentionally part of the existing version.

Connector source-ingestion runs and deterministic analytical windows are
explicitly source-owned in the certified contract. They must not be reclassified
as runtime just because their names contain `run` or `connection`. New process,
retry, session and worker identifiers must remain execution metadata. Behavioral
snapshot lineage and exact historical artifact bytes remain unchanged.

Replay of admitted records reuses their identity. Fresh admission into an empty
store is not promised to regenerate the same UUID or artifact. Deterministic
normalized numbers do not imply byte equality of execution/provenance records.

## Timestamp contract

`normalize_telemetry_timestamp` is the reusable source-time authority:

- Explicit numeric offsets normalize to UTC; original timestamp and offset remain.
- Naive times require an explicit IANA zone. Ambiguous/nonexistent DST wall times
  and invalid zones/timestamps are rejected.
- Missing source time is rejected, never replaced by acquisition or ingress time.
- Future source times beyond the configured tolerance (default five minutes)
  are rejected. There is no automatic source-clock correction.
- Earlier observations are accepted with `out_of_order_accepted`; delayed history
  is not rejected merely for age. Backfill uses bounded ranges and checkpoints.
- Preparation deduplicates source-record digests, not timestamps alone. Different
  values at the same timestamp are not automatically the same source record.
- Ingress uses the current existing preparation/persistence clocks. The scheduler
  passes claim time as normalization `now`; this is not evidence of acquisition.

Future acquisition time must mean actual connector receipt/read completion, and
ingress must mean Neraium acceptance. Persisting those separately requires an
additive storage/lineage decision, not a fabricated source timestamp or an
undocumented metadata convention.

## Quality and value/unit semantics: precise conflicts

1. `_reported_quality_decision(None)` currently returns `GOOD`: the empty token
   is in `_GOOD_QUALITY`. Suspect/uncertain/bad all become `INVALID_VALUE`;
   literal `unknown` becomes `FORMAT_INVALID`. The analytical window explicitly
   admits only `quality_state == good` and `analysis_eligible is True`.
   Replacing absent quality with `UNKNOWN` in the existing field would remove
   presently eligible observations. Treating unknown as good would violate the
   requested source-quality vocabulary. A separately versioned source-quality
   field with unchanged legacy admission is a possible resolution, but it must
   explicitly establish that distinction and its storage/consumer semantics.
2. `PreparedObservation` carries `reported_quality`, but the normalized observation
   INSERT does not include that field. An in-memory envelope alone therefore
   cannot promise durable reconstruction of every supplied native quality code.
3. Raw values and digests distinguish bool, int, float, Decimal and string.
   Unit normalization rejects booleans and nonnumeric states rather than making
   them numerical evidence. Accepted values are converted to float, so arbitrary
   integer/decimal precision is not retained in the analytical representation.
   For example, `Decimal('9007199254740993')` becomes `9007199254740992.0` for
   the explicit degC-to-degC normalization. A lossless source representation
   must not be advertised as lossless analytical arithmetic.
4. Explicit source/target unit mappings and conversion versions already govern
   conversion. Missing reported units may use the approved source unit; unknown
   units without that authority remain unresolved. No point-name guessing is
   needed or allowed in the connector boundary.

The source-quality/admission separation and durable nonnumeric/lossless source
representation require an agreed extension to the current contract. They cannot
be solved by changing evidence sufficiency, coercing states, or adding another
canonical analytical authority.

## Connector SDK and family mapping

Reuse `TelemetryConnector`, `ConnectorProviderDescriptor`,
`ConnectorExecutionContext`, `ConnectorCheckpoint`, `BoundedBackfillRange`,
`DiscoveredSignal`, `ConnectorPage` and `ProviderHealthResult`.

| Future family | Acquisition mapping, not implemented here |
| --- | --- |
| Enterprise API | REST/vendor reads use incremental pages; SSE/webhooks need bounded subscription/receipt support. |
| BACnet/IP edge | Discovery and read polling; COV needs subscription support. No WriteProperty. |
| Industrial OT | OPC UA read/subscription primary; Modbus TCP read adapter. No control methods/register writes. |
| Historian/database | Explicit bounded historical reads and optional incremental reads. No database write-back. |

Existing capabilities are validate, discover signals, incremental polling,
bounded backfill, health check and read events. Descriptors require validation
and health plus `retrieval_only=True`. No write capability exists. Discovery,
incremental and backfill methods are nevertheless all abstract today; unsupported
operations need explicit safe defaults in a future extension. Subscription,
native-quality, source-timestamp and topology declarations are gaps, not aliases
to silently invent now. Do not expand provider availability without adapters.

## Batching and backpressure

Reuse page/checkpoint transactions, scheduler leases and continuation work;
partial rejections and replay deduplication already exist. Repository persistence
bounds each observations/rejections sequence at 5,000. The existing HTTPS provider
also applies transport byte/page/record/retry/time budgets. `ConnectorPage` itself
does not enforce a universal bound, and this is not a universal subscription
queue. Future subscription support needs bounded admission with explicit retry
or overflow reporting and checkpoint advancement only after durable acceptance.
No throughput capacity is claimed. Ordering must retain the existing source and
analytical contracts; sorting cannot silently choose a new analytical winner.

## Read-only, security and errors

The SDK exposes retrieval and health only. Descriptor validation rejects a
non-retrieval provider or unknown capability. This enforces the declared interface,
not arbitrary third-party code behavior; protocol credentials/permissions must
also be read-only. No control, setpoint, actuator, command, PLC write, write-back
or automatic remediation interface may be added.

Reuse server-bound scope and approved mappings. Sources cannot choose workspace,
site or analytical authority. `SecretBinding` and existing secret providers are
server-only configuration handles, bound to connection and resource scope.
Credentials must never be observation metadata, identity, evidence, exports or
logs. Existing recursive sensitive-field rejection and public sanitization are
defenses, not proof that arbitrary strings cannot contain secrets. Future adapters
must project allowlisted source fields and never attach raw requests/responses.

Keep `TelemetryConnectorError` and safe failure codes for runtime/provider errors;
`ConnectorRecordIssue` and prepared rejections for malformed/source-quality data;
and existing analysis eligibility/sufficiency for analytical availability.
Disconnection does not create an analytical condition. Do not expose provider
exception text or credentials as customer diagnostics or forensic metadata.

## Decision and next implementation phase

Stop applies because a second canonical model would compete with existing
authority, and the requested quality behavior requires an eligibility decision
not established by current contracts. Existing authority is reused conceptually;
no production contract, schema, SDK, analytical math or stored bytes are changed.

Next phase should explicitly resolve source quality versus admission quality,
durable lossless source values/native codes/acquisition time, and compatibility
versioning. Then extend the existing envelope, persistence and SDK in place, with
bounded optional capabilities and focused regression tests. Preserve canonical
UUID allocation, source-owned connector runs and certified output semantics.
Only after that foundation is verified should any protocol adapter be implemented.

## Verification

The following focused baseline run completed with **190 passed, 7 failed**, two
warnings, in 112.22 seconds. These verify current contracts only; they do not
certify the unimplemented extensions. No tests were changed or weakened.

```sh
.venv/bin/python -m pytest -q \
  tests/test_telemetry_connector_contract.py \
  tests/test_telemetry_ingestion.py \
  tests/test_telemetry_timestamps.py \
  tests/test_telemetry_units.py \
  tests/test_authority_identity.py \
  tests/test_analysis_provenance.py \
  tests/test_telemetry_lineage.py \
  tests/test_governed_output_determinism.py \
  tests/test_measurable_consequence.py \
  tests/test_consequence_certification.py \
  tests/test_promotion_architecture_contracts.py \
  tests/test_aletheia_retirement.py \
  tests/test_telemetry_canonical_result_persistence.py \
  tests/test_telemetry_secrets.py \
  tests/test_phase4_upload_system_identity.py
```

- `test_canonical_analysis_attaches_exact_finding_owned_consequence`: actual
  consequence runtime metadata includes `contract_version: execution-metadata.v1`;
  expected metadata omits that marker. Other reported fields are identical.
- Six `test_phase4_upload_system_identity.py` cases fail on setup mutations with
  HTTP 403 `Untrusted request origin`: ordinary authorized upload, stable per-system
  identity, cross-workspace identity, both unresolved-system cases, and replay.
  These failures prevent those cases from verifying their intended behavior.
- All selected connector, timestamp, unit, authority identity, provenance, lineage,
  governed determinism, consequence certification, promotion architecture,
  Aletheia retirement, canonical persistence and secret suites passed.
- Direct production-function probes confirmed the quality decisions and precision
  example documented above. No change to existing eligibility was made.
- Reviewed the new-file diff and tracked diff; ran `git diff --check` and the
  equivalent whitespace check for the untracked new document. Production and
  test diffs remain empty. No performance campaign or browser test was run.
