"""Runtime adapters to the Phase 1–3 contracts. No authority consumer lives here.

Inputs are server-owned analytical snapshots, never request governance fields.
Relationship evidence is the only family whose finding ownership and source
windows are currently retained by all three product paths. Shared inputs stay
shared: adding metrics cannot manufacture independent corroboration.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math

from app.governance.authority_store import RuntimeAuthorityDecisionStore
from app.governance.context import ContextBasis, ContextObject, ContextRegistry
from app.governance.contracts import (
    AuditSnapshot, DependencyRef, EvidenceObject, FindingLifecycleEvent,
    ObservationReference, Provenance, SourceWindow, content_id,
)
from app.governance.dependencies import DependencyGraph
from app.governance.maturity import PersistenceAssessment, PersistenceGate, evaluate_maturity_v2
from app.governance.policy import AuthorityPolicy, PolicyRegistry
from app.governance.registry import time
from app.governance.tiers import classify_tier

VERSION = "runtime-governance-v1"
LABELS = dict(zip(("L0", "L1", "L2", "L3", "L4"),
                  ("Observed", "Persistent", "Corroborated", "Characterized", "Context-qualified")))
POLICY_ID = "runtime-observation-only"
MAX_RELATIONSHIPS = 24
METRICS = ("baseline_correlation", "recent_correlation", "current_correlation",
           "correlation_delta", "baseline_strength", "current_strength",
           "baseline_slope", "recent_slope", "baseline_sample_size", "recent_sample_size")


class TransactionGovernanceStore(RuntimeAuthorityDecisionStore):
    """Reuse the governance store inside the host finding transaction."""
    def __init__(self, connection):
        self.connection = connection

    def _read(self, key):
        row = self.connection.execute("SELECT payload_json FROM latest_payloads WHERE key = ?", (key,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _mutate(self, key, update):
        result = update(self._read(key))
        from app.services.runtime_db import now_iso
        self.connection.execute(
            "INSERT INTO latest_payloads (key, updated_at, payload_json) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET updated_at=excluded.updated_at, payload_json=excluded.payload_json",
            (key, now_iso(), json.dumps(result, allow_nan=False)))
        return deepcopy(result)

    def _mutate_with_reads(self, key, read_keys, update):
        return self._mutate(key, lambda raw: update(raw, [self._read(k) for k in read_keys]))


def _window(relationship, *, source_ref, fallback=None):
    # Host canonical/live windows come from normalized observations. Product
    # display time_window strings can lose their timezone during projection.
    if fallback and fallback.get("start") and fallback.get("end"):
        return SourceWindow(window_id=content_id("source-window", [source_ref, fallback]),
                            started_at=fallback["start"], ended_at=fallback["end"])
    candidates = []
    raw = relationship.get("time_window")
    if isinstance(raw, dict):
        candidates.append((raw.get("current_start") or raw.get("start"), raw.get("current_end") or raw.get("end")))
    elif isinstance(raw, str) and " to " in raw:
        candidates.append(tuple(raw.split(" to ", 1)))
    for ref in relationship.get("evidence_refs") or []:
        if isinstance(ref, dict) and isinstance(ref.get("recent_window"), dict):
            recent = ref["recent_window"]
            candidates.append((recent.get("start"), recent.get("end")))
    if fallback:
        candidates.append((fallback.get("start"), fallback.get("end")))
    for start, end in candidates:
        if start and end:
            from datetime import datetime
            # A timezone-free display range cannot supply a source instant.
            # Leave chronology unknown instead of silently assuming UTC.
            try:
                if any(datetime.fromisoformat(str(value).replace("Z", "+00:00")).tzinfo is None for value in (start, end)):
                    continue
            except ValueError:
                continue
            return SourceWindow(window_id=content_id("source-window", [source_ref, start, end]),
                                started_at=start, ended_at=end)
    return SourceWindow(window_id=source_ref)


def adapt_relationships(*, finding_id, system, run_id, relationships, available_at,
                        source_ref, source_window=None, persistence=None):
    """Deterministic projection of real finding-owned relationship comparisons.

An observation references the retained analytical input snapshot, not invented
raw rows. Unknown window bounds or omitted siblings limit maturity. No score,
consequence, confidence label, or frontend trajectory becomes a governance gate.
"""
    provenance = Provenance(source="app.services.runtime_governance", source_version=VERSION,
                            reference_ids=(source_ref,))
    evidence, observations, gates = [], {}, []
    for index, relationship in enumerate(relationships[:MAX_RELATIONSHIPS]):
        signals = relationship.get("columns") or relationship.get("signals") or []
        if not signals:
            pairs = relationship.get("supporting_metric_pairs") or []
            if len(pairs) == 1:
                signals = [pairs[0].get("left"), pairs[0].get("right")]
        if not isinstance(signals, (list, tuple)) or len(signals) < 2 or not all(isinstance(s, str) and s.strip() for s in signals):
            continue
        metrics = {key: relationship[key] for key in METRICS
                   if isinstance(relationship.get(key), (float, int)) and not isinstance(relationship[key], bool)
                   and math.isfinite(relationship[key])}
        if not metrics:
            continue
        window = _window(relationship, source_ref=source_ref, fallback=source_window)
        reported_window = relationship.get("time_window")
        reported_times = (reported_window.split(" to ", 1) if isinstance(reported_window, str) and " to " in reported_window
                          else [reported_window.get(key) for key in ("start", "end", "current_start", "current_end")]
                          if isinstance(reported_window, dict) else [])
        for value in reported_times:
            if not value:
                continue
            try:
                instant = time(value)
            except ValueError:
                continue  # Display text without timezone is not an instant.
            if instant > time(available_at):
                raise ValueError("reported_window_contains_later_knowledge")
        limitations = ["Relationship metrics share their analytical inputs; they are not independent families.",
                       "No admissible evolution-rate or causal assessment is supplied."]
        limitations.extend(value for value in relationship.get("limitations") or [] if isinstance(value, str))
        source_limited = relationship.get("status") in {"limited", "unavailable", "failed"} or relationship.get("role") == "uncertain evidence"
        if source_limited:
            limitations.append("The source analytical relationship is limited or uncertain.")
        complete = bool(window.started_at) and len(relationships) <= MAX_RELATIONSHIPS
        if not window.started_at:
            limitations.append("Chronological source window unavailable.")
        if len(relationships) > MAX_RELATIONSHIPS:
            limitations.append("Finding evidence exceeds the bounded adapter capacity.")
        source_windows = [{key: ref[key] for key in ("column", "baseline_window", "recent_window", "source_rows") if key in ref}
                          for ref in relationship.get("evidence_refs", []) if isinstance(ref, dict)]
        if len(source_windows) > 32:
            raise ValueError("source_window_capacity_exceeded")
        for ref in source_windows:
            for name in ("baseline_window", "recent_window"):
                raw_window = ref.get(name)
                if isinstance(raw_window, dict):
                    for field in ("start", "end"):
                        if raw_window.get(field) and time(raw_window[field]) > time(available_at):
                            raise ValueError("source_window_contains_later_knowledge")
            for row in ref.get("source_rows") or []:
                if isinstance(row, dict) and row.get("timestamp") and time(row["timestamp"]) > time(available_at):
                    raise ValueError("source_row_contains_later_knowledge")
        observation = ObservationReference(
            observation_id=content_id("analytical-input", [source_ref, list(signals), window.as_dict()]),
            source_id=source_ref, system_scope=system, source_signals=tuple(signals),
            source_window=window, provenance=provenance)
        observations[observation.observation_id] = observation
        item = EvidenceObject(evidence_family="relational", evidence_method="retained_relationship_comparison_v1",
            source_module=__name__, source_run_id=run_id, system_scope=system,
            source_signals=tuple(signals), source_window=window,
            derived_from=(DependencyRef(kind="observation", dependency_id=observation.observation_id),),
            assumption_set=("retained_baseline_comparison",), context_refs=(), provenance=provenance,
            created_at=available_at, lineage_complete=complete, result_ref=source_ref,
            payload={"status": "available" if complete and not source_limited else "limited", "metrics": metrics,
                     "source_windows": source_windows,
                     "reported_window": relationship.get("time_window"),
                     "source_evidence_refs": [ref for ref in relationship.get("evidence_refs") or [] if isinstance(ref, str)],
                     "source_relationship_id": str(relationship.get("relationship_id") or relationship.get("id") or index),
                     "limitations": limitations,
                     "role": relationship.get("role", "finding_support"),
                     "governance_conditions": {"relationship_change": "present" if metrics.get("correlation_delta", 0) != 0 else "unknown"}})
        evidence.append(item)
        assessment = relationship.get("persistence") or persistence or {}
        windows = assessment.get("windows") or []
        # Only the existing pilot's explicit fixed-window contract is admitted.
        # Narrative persistence and aggregate scores are not equivalent gates.
        if complete and not source_limited and windows and isinstance(assessment.get("persistent"), bool):
            if len(windows) > 128:
                raise ValueError("persistence_window_capacity_exceeded")
            for sample in windows:
                if not isinstance(sample.get("supports_change"), bool) or not sample.get("start") or not sample.get("end"):
                    raise ValueError("persistence_window_incomplete")
                records, score = sample.get("records"), sample.get("deviation_score")
                if (type(records) is not int or records < 8 or type(score) not in (int, float)
                        or not math.isfinite(score) or score < 0):
                    raise ValueError("persistence_window_measurements_unavailable")
                # The engine rounds score for transport; do not invert a gate
                # at its rounding boundary. Retain its explicit assertion.
                if abs(score - 3.0) > .00005 and sample["supports_change"] != (score >= 3.0):
                    raise ValueError("persistence_window_gate_mismatch")
                if not time(window.started_at) <= time(sample["start"]) <= time(sample["end"]) <= time(window.ended_at):
                    raise ValueError("persistence_window_outside_source")
            support = [i for i, w in enumerate(windows) if w["supports_change"]]
            passed = len(support) >= 2 and sum(w["supports_change"] for w in windows[support[0]:]) / len(windows[support[0]:]) >= .6 if support else False
            if passed != assessment["persistent"]:
                raise ValueError("persistence_assertion_mismatch")
            # Freeze the exact upstream gates as evidence payload, avoiding a
            # dependency on mutable result reads during historical replay.
            item = EvidenceObject.model_validate({**item.as_dict(), "evidence_id": "",
                "payload": {**item.payload, "persistence_windows": windows}})
            evidence[-1] = item
            gates.append(PersistenceGate(requirement_id=f"pilot-fixed-windows:{index}", requirement_version="1",
                basis="fixed_observations", satisfied=passed, evidence_ids=(item.evidence_id,),
                reasons=("At least two supporting windows and 60% subsequent support required by pilot_assessment.",)))
    if len(evidence) < min(len(relationships), MAX_RELATIONSHIPS):
        evidence = [EvidenceObject.model_validate({**item.as_dict(), "evidence_id": "", "payload": {
            **item.payload, "status": "limited", "limitations": [*item.payload["limitations"],
                "Some finding-owned relationship inputs could not be adapted."]}}) for item in evidence]
        gates = []
    graph = DependencyGraph(system_scope=system, evidence=tuple(evidence), observations=tuple(observations.values()))
    graph.validate_available_at(available_at)
    return graph, PersistenceAssessment(finding_id=finding_id, gates=tuple(gates))


def unavailable(reason, *, run_id=None):
    return {"schema_version": VERSION, "status": "unavailable", "source_run_id": run_id,
            "maturity_label": None, "authority_label": "Observation only", "execution_authorized": False,
            "limitations": [reason], "context_label": "Context unavailable", "adaptation": None, "review_history": []}


def evaluate_runtime_finding(*, storage, scope, finding_id, system, run_id, at,
                             relationships, source_ref, source_window=None, persistence=None,
                             model_snapshot=None, identity=None, consequence=None, lifecycle_writer=None, lifecycle_state=None):
    """Append one finding/run snapshot. Exact retry reads the frozen result.

The host must hold a writer transaction when using TransactionGovernanceStore.
Historical reads never invoke this function. A later run appends; it cannot
rewrite an earlier run, decision, context basis, or lifecycle event.
"""
    key = f"{VERSION}::{storage._key(scope, system)}::{content_id('finding', finding_id)}"
    history = storage._read(key) or {"records": []}
    expected_history = deepcopy(history)
    input_digest = content_id("runtime-input", {"relationships": relationships, "source_ref": source_ref,
        "source_window": source_window, "persistence": persistence, "consequence": consequence,
        "model": model_snapshot.payload if model_snapshot else None, "identity": identity, "lifecycle_state": lifecycle_state})
    existing = next((r for r in history["records"] if r["source_run_id"] == run_id), None)
    if existing:
        if time(at) < time(existing["evaluated_at"]):
            raise ValueError("runtime_governance_retry_precedes_record")
        if existing["status"] == "unavailable" and "input_digest" not in existing:
            return deepcopy(existing)
        if existing.get("input_digest") != input_digest:
            raise ValueError("runtime_governance_immutable_source_conflict")
        return deepcopy(existing)
    prior = history["records"][-1] if history["records"] else None
    if prior and time(at) < time(prior["evaluated_at"]):
        raise ValueError("runtime_governance_chronology_regressed")
    graph, assessment = adapt_relationships(finding_id=finding_id, system=system, run_id=run_id,
        relationships=relationships, available_at=at, source_ref=source_ref,
        source_window=source_window, persistence=persistence)
    provenance = Provenance(source="app.services.runtime_governance", source_version=VERSION, reference_ids=(source_ref,))
    contexts = ContextRegistry(storage)
    if identity:
        # The caller supplies an existing server-bound identity, not a product
        # label or an operating-mode inference. Identity alone cannot grant L4.
        context_key = "runtime-system-identity"
        chain = [c for c in contexts.history(scope, system) if c.context_key == context_key]
        previous = chain[-1] if chain else None
        if previous is None or previous.payload != identity:
            contexts.append(scope, ContextObject(context_key=context_key, context_type="infrastructure_identity",
                system_scope=system, source_type="server_bound_identity", source_reference=source_ref,
                provenance=provenance, verification_status="verified", created_at=at, effective_from=at,
                version=previous.version + 1 if previous else 1, supersedes=previous.context_id if previous else None,
                payload=identity))
    context = ContextBasis(system_scope=system, evaluated_at=at, relevant_at=at,
        records=contexts.as_of(scope, system, at), facts={}, facts_available_at=at, facts_provenance=provenance)
    snapshot = {**unavailable("No supported finding-owned analytical evidence.", run_id=run_id),
                "finding_id": finding_id, "evaluated_at": at, "source_ref": source_ref,
                "input_digest": input_digest,
                "consequence": deepcopy(consequence), "context_basis": context.as_dict()}
    if graph.evidence:
        maturity = evaluate_maturity_v2(finding_id=finding_id, relevant_evidence_ids=tuple(e.evidence_id for e in graph.evidence),
            graph=graph, persistence=assessment, evaluated_at=at, source_run_id=run_id, context_basis=context)
        state = lifecycle_state or ("persistent" if assessment.gates and all(g.satisfied for g in assessment.gates) else "new")
        previous_lifecycle = next((r["lifecycle"] for r in reversed(history["records"]) if r.get("lifecycle")), None)
        if previous_lifecycle and state == "new" and lifecycle_state is None:
            state = "unresolved"
        lifecycle = FindingLifecycleEvent(event_id=content_id("runtime-lifecycle", [finding_id, run_id, graph.snapshot_id]),
            finding_id=finding_id, version=(previous_lifecycle["version"] + 1 if previous_lifecycle else 1),
            recorded_at=at, effective_at=at, actor="runtime_governance",
            state=state, previous_event_id=previous_lifecycle["event_id"] if previous_lifecycle else None,
            evidence_ids=maturity.relevant_evidence_ids,
            reasons=("existing_runtime_finding_state",) if lifecycle_state else ("finding_scoped_persistence_assessment",),
            source_run_id=run_id, provenance=provenance)
        if lifecycle_writer:
            lifecycle = lifecycle_writer(lifecycle)
        snapshot.update(status="evaluated", maturity_label=LABELS[maturity.level.value], maturity=maturity.as_dict(),
            lifecycle=lifecycle.as_dict(), graph=graph.as_dict(), classification=classify_tier(graph, maturity.relevant_evidence_ids).as_dict(),
            context_qualification=maturity.context_qualification.as_dict(),
            limitations=sorted({reason for e in graph.evidence for reason in e.payload["limitations"]}),
            authority_decision=None, audit_record=None)
        snapshot["context_label"] = "External context qualified" if maturity.context_qualification.applicable_context_ids else "External context unavailable"
        if model_snapshot is not None:
            policies = PolicyRegistry(storage)
            if not any(p.policy_id == POLICY_ID for p in policies.history(scope, system)):
                policies.append(scope, AuthorityPolicy(policy_id=POLICY_ID, policy_version=1,
                    applicable_system_scope=system, requested_operation="evaluate_adaptation", minimum_maturity="L4",
                    allowed_lifecycle_states=("persistent",), required_evidence_families=(),
                    prohibited_evidence_conditions=("instrumentation_concern", "physics_contradiction", "excessive_evolution_rate"),
                    required_context_types=(), human_review_requirement=True, created_at=at, effective_from=at, provenance=provenance))
            decision, basis = storage.admit_policy_decision(scope, system_scope=system, policy_id=POLICY_ID,
                facts={}, facts_available_at=at, facts_provenance=provenance, graph=graph, maturity=maturity,
                lifecycle=lifecycle, requested_operation="evaluate_adaptation", decision_timestamp=at,
                source_run_id=run_id, active_model=model_snapshot,
                supersedes_decision_id=next((r["authority_decision"]["decision_id"] for r in reversed(history["records"])
                                             if r.get("authority_decision")), None))
            snapshot.update(authority_decision=decision.as_dict(), audit_record={"decision": decision.as_dict(), "basis": basis.as_dict()},
                adaptation={"status": decision.decision_outcome.value, "candidate_ref": None,
                            "label": decision.decision_outcome.value.replace("_", " ").capitalize(),
                            "reason": "Required evidence or safety checks remain unresolved.",
                            "execution_authorized": False, "reasons": list(decision.decision_reasons)})
        else:
            snapshot["limitations"].append("Immutable model and baseline references unavailable; authority decision not admitted.")
    elif lifecycle_state is not None:
        previous_lifecycle = next((r["lifecycle"] for r in reversed(history["records"]) if r.get("lifecycle")), None)
        lifecycle = FindingLifecycleEvent(event_id=content_id("runtime-lifecycle", [finding_id, run_id, lifecycle_state]),
            finding_id=finding_id, version=previous_lifecycle["version"] + 1 if previous_lifecycle else 1,
            recorded_at=at, effective_at=at, actor="runtime_governance", state=lifecycle_state,
            previous_event_id=previous_lifecycle["event_id"] if previous_lifecycle else None,
            evidence_ids=(), reasons=("existing_runtime_finding_state_without_new_changed_evidence",),
            source_run_id=run_id, provenance=provenance)
        snapshot["lifecycle"] = (lifecycle_writer(lifecycle) if lifecycle_writer else lifecycle).as_dict()
    if len(json.dumps(snapshot, allow_nan=False).encode()) > 512 * 1024:
        raise ValueError("runtime_governance_snapshot_capacity_exceeded")
    history["records"].append(snapshot)
    def append_snapshot(raw):
        if (raw or {"records": []}) != expected_history:
            raise ValueError("runtime_governance_concurrent_append_conflict")
        return history
    storage._mutate(key, append_snapshot)
    return deepcopy(snapshot)


def read_runtime_history(storage, scope, system, finding_id):
    key = f"{VERSION}::{storage._key(scope, system)}::{content_id('finding', finding_id)}"
    return deepcopy((storage._read(key) or {}).get("records", []))


def model_reference_snapshot(*, model_id, model_hash, system, at, source_ref):
    """Freeze an analytical model's versioned content reference, never 'active'."""
    if not model_id or not model_hash:
        return None
    reference = f"behavioral-model:{model_id}:{model_hash}"
    return AuditSnapshot(kind="model", object_id=str(model_id), version=str(model_hash),
        system_scope=system, created_at=at,
        provenance=Provenance(source="runtime_analytical_model_reference", source_version=VERSION, reference_ids=(source_ref,)),
        payload={"model_ref": reference, "baseline_ref": reference})


def _evaluate_in_transaction(connection, **inputs):
    """Invalid governance inputs do not discard valid analytical results.

Rollback partial registry/lifecycle writes, then retain an explicit failure for
this run. Storage errors propagate; there is no permissive or in-memory fallback.
"""
    import logging
    storage = TransactionGovernanceStore(connection)
    connection.execute("SAVEPOINT runtime_governance")
    try:
        snapshot = evaluate_runtime_finding(storage=storage, **inputs)
    except ValueError as error:
        connection.execute("ROLLBACK TO runtime_governance")
        logging.getLogger(__name__).warning("runtime_governance_evaluation_rejected", extra={
            "finding_id": inputs["finding_id"], "source_run_id": inputs["run_id"], "error_type": type(error).__name__})
        snapshot = {**unavailable("Required governance inputs failed validation; authority remains unavailable.", run_id=inputs["run_id"]),
            "finding_id": inputs["finding_id"], "evaluated_at": inputs["at"], "source_ref": inputs["source_ref"]}
        import re
        code = str(error)
        snapshot["rejection_code"] = code if re.fullmatch(r"[a-z0-9_.:-]{1,160}", code) else "governance_contract_validation_failed"
        if snapshot["rejection_code"] in {"policy_expired_at_decision", "policy_unavailable_at_decision"}:
            snapshot["limitations"] = ["The required authority policy was unavailable or expired at evaluation time."]
        key = f"{VERSION}::{storage._key(inputs['scope'], inputs['system'])}::{content_id('finding', inputs['finding_id'])}"
        def append_failure(raw):
            history = raw or {"records": []}
            if not any(r["source_run_id"] == inputs["run_id"] for r in history["records"]):
                history["records"].append(snapshot)
            return history
        storage._mutate(key, append_failure)
    finally:
        connection.execute("RELEASE runtime_governance")
    return snapshot


def govern_evidence_case(connection, *, record, finding_id, finding):
    from app.services.phase4_scope import current_authenticated_phase4_scope, current_server_bound_system_identity
    from app.services.runtime_db import now_iso
    scope = current_authenticated_phase4_scope()
    identity = current_server_bound_system_identity()
    if scope is None or identity is None:
        return unavailable("Authenticated runtime scope and system identity unavailable.", run_id=record.get("run_id"))
    from app.services.dataset_scope import current_dataset_scope, dataset_scope_from_payload
    dataset = current_dataset_scope()
    record_scope = dataset_scope_from_payload(record)
    if (scope.tenant_scope_id != dataset.tenant_id or scope.workspace_id != dataset.workspace_id
            or identity.dataset_scope_storage_id != dataset.storage_id
            or (record_scope is not None and record_scope != dataset)
            or (record.get("system_id") and record["system_id"] != identity.system_id)):
        return unavailable("Runtime finding scope does not match the authenticated system.", run_id=record.get("run_id"))
    system, run_id, at = identity.system_id, str(record["run_id"]), now_iso()
    source_ref = f"evidence-run:{run_id}:{record.get('result_hash') or record.get('evidence_hash') or finding_id}"
    relationships = [r for key in ("supporting_relationships", "conflicting_relationships", "uncertain_relationships")
                     for r in finding.get(key, []) if isinstance(r, dict)]
    return _evaluate_in_transaction(connection, scope=scope,
        finding_id=finding_id, system=system, run_id=run_id, at=at, relationships=relationships,
        source_ref=source_ref, identity=identity.as_dict(), lifecycle_writer=_lifecycle_writer(connection),
        model_snapshot=model_reference_snapshot(model_id=record.get("baseline_id"), model_hash=record.get("baseline_hash"),
            system=system, at=at, source_ref=source_ref), consequence=finding.get("measurable_consequence"))


def govern_live_findings(connection, *, run_id, config, window, analytics, baseline, at):
    from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
    from app.services.dataset_scope import current_dataset_scope
    from app.services.finding_workflow import _live_snapshot
    dataset = current_dataset_scope()
    scope = AuthenticatedPhase4Scope(tenant_scope_id=dataset.tenant_id, workspace_id=dataset.workspace_id)
    system = str(config["system_id"])
    rows = connection.execute("SELECT * FROM live_findings WHERE scope_storage_id = ? AND source_live_analysis_run_id = ?",
                              (dataset.storage_id, run_id)).fetchall()
    detections = {d["relationship_identity"]: d for d in analytics.get("detections", [])}
    snapshots = {}
    for row in rows:
        connection.execute(
            "INSERT OR IGNORE INTO finding_cases (finding_id, source_kind, source_id, source_finding_key, "
            "scope_storage_id, dataset_scope_json, source_snapshot_json, created_at) VALUES (?, 'live_finding', ?, ?, ?, ?, ?, ?)",
            (row["finding_id"], row["finding_id"], row["finding_id"], dataset.storage_id,
             json.dumps(dataset.as_dict()), json.dumps(_live_snapshot(row)), row["created_at"]))
        if dataset.tenant_id == "anonymous" or dataset.user_id == "anonymous":
            snapshots[row["finding_id"]] = unavailable("Authenticated runtime scope unavailable.", run_id=run_id)
            continue
        detection = detections.get(row["relationship_identity"])
        # A baseline-aligned/resolved run supplies no changed comparison. Do not
        # relabel the previous run's evidence as newly observed or infer absence.
        source_ref = f"live-analysis-result:{run_id}"
        model = model_reference_snapshot(model_id=(baseline or {}).get("model_id"),
            model_hash=content_id("model-content", baseline) if baseline else None, system=system, at=at, source_ref=source_ref)
        if (baseline or {}).get("model_id") != config["approved_baseline_id"]:
            model = None
        if model is not None:
            try:
                model = AuditSnapshot.model_validate({**model.as_dict(), "snapshot_id": "",
                    "payload": {**model.payload, "model_document": baseline}})
            except ValueError:
                # An unarchived external pointer cannot substitute for the
                # immutable model basis required by Phase 2 admission.
                model = None
        snapshot = _evaluate_in_transaction(connection, scope=scope,
            finding_id=row["finding_id"], system=system, run_id=run_id, at=at,
            relationships=[detection] if detection else [], source_ref=source_ref, lifecycle_writer=_lifecycle_writer(connection),
            lifecycle_state={"open": "persistent", "observing": "new", "resolved": "closed"}[row["current_state"]],
            source_window={"start": window["window_start"], "end": window["window_end"]}, model_snapshot=model,
            identity={"system_id": system, "source": "live_analysis_configurations", "baseline_id": config["approved_baseline_id"]},
            consequence=((detection or {}).get("latest_evidence", {}).get("condition") or {}).get("measurable_consequence"))
        snapshots[row["finding_id"]] = snapshot
    return snapshots


def finding_governance(finding_id, system):
    """Called only after the existing finding/system scope authorization."""
    from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
    from app.services.dataset_scope import current_dataset_scope
    dataset = current_dataset_scope()
    scope = AuthenticatedPhase4Scope(tenant_scope_id=dataset.tenant_id, workspace_id=dataset.workspace_id)
    history = read_runtime_history(RuntimeAuthorityDecisionStore(), scope, system, finding_id)
    return {**history[-1], "history": history} if history else unavailable("No runtime governance snapshot was recorded for this finding.")


def evidence_run_governance(run_id):
    """Read original finding snapshots under the existing dataset authorization."""
    from app.services.dataset_scope import current_dataset_scope
    from app.services.runtime_db import db_connection
    with db_connection() as connection:
        rows = connection.execute("SELECT finding_id, source_finding_key, source_snapshot_json FROM finding_cases "
            "WHERE source_kind = 'evidence_run' AND source_id = ? AND scope_storage_id = ?",
            (run_id, current_dataset_scope().storage_id)).fetchall()
    result = {}
    for row in rows:
        source = json.loads(row["source_snapshot_json"])
        if source.get("governance_system_scope"):
            result[row["source_finding_key"]] = finding_governance(row["finding_id"], source["governance_system_scope"])
        elif "governance" in source:
            result[row["source_finding_key"]] = source["governance"]
    return result


def _lifecycle_writer(connection):
    def write(lifecycle):
        from app.services.finding_workflow import _append_event
        change = lifecycle.as_dict()
        for key in ("event_id", "finding_id", "version", "recorded_at", "actor"):
            change.pop(key)
        event = _append_event(lifecycle.finding_id, event_type="governance_lifecycle_recorded",
            actor="runtime_governance", payload={"governance_lifecycle": change}, expected_version=None,
            idempotency_key=f"runtime-governance:{lifecycle.source_run_id}", recorded_at=lifecycle.recorded_at,
            connection_override=connection)
        return FindingLifecycleEvent.model_validate(event["governance_lifecycle"])
    return write


def govern_connector_execution(execution, window, *, at):
    """Freeze governance with the canonical artifact before its terminal commit.

The SII result is untouched. Only existing canonical conditions are governed;
no condition, source signal, active baseline or model is manufactured here.
"""
    from dataclasses import replace
    from types import MappingProxyType
    from app.services.runtime_db import db_connection, init_runtime_db
    from app.services.finding_workflow import evidence_finding_id
    analysis = dict(execution.analysis_result)
    conditions = analysis.get("conditions") or []
    if not conditions:
        return execution
    init_runtime_db()
    system = window.phase4_system_identity.system_id
    source_ref = f"canonical-analysis:{execution.window_id}"
    snapshots = {}
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for condition in conditions:
            source_id = condition.get("condition_id") or condition.get("id")
            if not source_id:
                continue
            finding_id = evidence_finding_id(execution.window_id, source_id)
            relationships = [r for key in ("supporting_relationships", "conflicting_relationships", "uncertain_relationships")
                             for r in condition.get(key, []) if isinstance(r, dict)]
            model = dict(execution.sii_result.get("behavioral_model") or {})
            baseline_version = (model.get("baseline_state") or {}).get("active_version")
            model_snapshot = None
            if model.get("model_id") and model.get("model_version") and model.get("snapshot_id") and baseline_version:
                model_snapshot = AuditSnapshot(kind="model", object_id=model["model_id"], version=str(model["model_version"]),
                    system_scope=system, created_at=at,
                    provenance=Provenance(source="sii_result.behavioral_model", source_version=str(model.get("contract_version") or VERSION), reference_ids=(source_ref,)),
                    payload={"model_ref": f"{model['model_id']}:{model['model_version']}:{model['snapshot_id']}",
                             "baseline_ref": f"{model['model_id']}:baseline:{baseline_version}", "canonical_source_ref": source_ref})
            snapshots[source_id] = _evaluate_in_transaction(connection,
                scope=window.phase4_scope, finding_id=finding_id, system=system,
                run_id=execution.source_run_id, at=at,
                relationships=relationships, source_ref=source_ref,
                source_window={"start": window.window_start.isoformat(), "end": window.window_end.isoformat()},
                model_snapshot=model_snapshot,
                identity=window.phase4_system_identity.as_dict(), consequence=condition.get("measurable_consequence"))
    analysis["governance"] = snapshots
    return replace(execution, analysis_result=MappingProxyType(analysis))
