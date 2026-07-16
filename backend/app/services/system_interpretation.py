from __future__ import annotations

from typing import Any

from app.services.analysis_explanations import build_analysis_explanation
from app.services.upload_state import has_active_session_artifact


def _normalize_instability_percent(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number <= 1.0:
        number *= 100.0
    return round(max(0.0, min(100.0, number)), 2)


def _to_text(value) -> str:
    text = str(value or "").strip()
    return text


def _timeline_events_from_frames(frames: list[dict], snapshot: dict, result: dict) -> list[dict]:
    if frames:
        first = frames[0] or {}
        mid = frames[len(frames) // 2] or {}
        last = frames[-1] or {}

        def _summary(frame: dict) -> str:
            cognition = frame.get("cognition_state") or {}
            relationship_changes = frame.get("relationship_changes") or []
            if isinstance(relationship_changes, list) and relationship_changes:
                first_change = relationship_changes[0]
                if isinstance(first_change, dict):
                    first_change = first_change.get("summary") or first_change.get("relationship") or ""
                return f"{cognition.get('facility_state', 'State')}: {first_change}"
            drift_velocity = frame.get("drift_velocity")
            if drift_velocity is not None:
                return f"{cognition.get('facility_state', 'State')}: drift velocity {round(float(drift_velocity), 3)}"
            return str(cognition.get("facility_state") or "Replay frame available.")

        return [
            {"stage": "onset", "summary": _summary(first)},
            {"stage": "progression", "summary": _summary(mid)},
            {"stage": "escalation", "summary": _summary(last)},
        ]

    first_ts = ((result.get("timestamp_profile") or {}).get("first_timestamp")) if isinstance(result, dict) else None
    last_ts = ((result.get("timestamp_profile") or {}).get("last_timestamp")) if isinstance(result, dict) else None
    return [
        {"stage": "onset", "summary": str(first_ts or snapshot.get("created_at") or "Initial telemetry window captured.")},
        {"stage": "progression", "summary": "Structural relationships remained under review across processing windows."},
        {"stage": "escalation", "summary": str(snapshot.get("status") or result.get("operating_state") or "Current escalation trajectory under active evaluation.")},
    ]


def _normalize_relationship_change_entries(replay_frame: dict[str, Any]) -> list[dict[str, Any]]:
    changes = replay_frame.get("relationship_changes") if isinstance(replay_frame.get("relationship_changes"), list) else []
    refs = replay_frame.get("relationship_change_evidence_refs") if isinstance(replay_frame.get("relationship_change_evidence_refs"), list) else []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(changes[:5]):
        if isinstance(raw, dict):
            entry = dict(raw)
            entry.setdefault("summary", _to_text(entry.get("summary") or entry.get("relationship")))
            entry.setdefault("evidence_refs", entry.get("evidence_refs") if isinstance(entry.get("evidence_refs"), list) else [])
            normalized.append(entry)
            continue
        evidence_refs: list[dict[str, Any]] = []
        if index < len(refs) and isinstance(refs[index], dict):
            maybe_refs = refs[index].get("evidence_refs")
            if isinstance(maybe_refs, list):
                evidence_refs = maybe_refs
        normalized.append({"summary": _to_text(raw), "evidence_refs": evidence_refs})
    return normalized


def _clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _severity_from_score(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 35:
        return "elevated"
    return "contained"


def _confidence_label(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "moderate"
    return "low"


def _score_relationship_change(entry: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    baseline_n = int(entry.get("baseline_sample_size") or 0)
    recent_n = int(entry.get("recent_sample_size") or 0)
    coupling = abs(float(entry.get("coupling_strength") or 0.0))
    delta = abs(float(entry.get("correlation_delta") or 0.0))
    refs = entry.get("evidence_refs") if isinstance(entry.get("evidence_refs"), list) else []
    refs_with_columns = [ref for ref in refs if isinstance(ref, dict) and _to_text(ref.get("column"))]
    evidence_completeness = min(1.0, len(refs_with_columns) / 2.0)

    baseline_factor = min(1.0, baseline_n / 24.0)
    recent_factor = min(1.0, recent_n / 12.0)
    coupling_factor = min(1.0, coupling)
    delta_factor = min(1.0, delta)

    confidence_score = _clamp_score(
        (baseline_factor * 30.0)
        + (recent_factor * 20.0)
        + (coupling_factor * 20.0)
        + (delta_factor * 20.0)
        + (evidence_completeness * 10.0)
    )
    drift_score = _clamp_score((delta_factor * 70.0) + (coupling_factor * 30.0))

    scored = dict(entry)
    scored["relationship_drift_score"] = round(drift_score, 4)
    scored["severity"] = _severity_from_score(drift_score)
    scored["confidence_score"] = round(confidence_score, 4)
    scored["confidence"] = _confidence_label(confidence_score)
    return drift_score, confidence_score, scored


def _build_relationship_divergence_metrics(result: dict[str, Any], replay_frame: dict[str, Any]) -> dict[str, Any]:
    baseline_analysis = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    baseline_changes = baseline_analysis.get("top_relationship_changes") if isinstance(baseline_analysis.get("top_relationship_changes"), list) else []
    raw_changes = baseline_changes if baseline_changes else _normalize_relationship_change_entries(replay_frame)

    scored_changes: list[dict[str, Any]] = []
    drift_scores: list[float] = []
    confidence_scores: list[float] = []
    for raw in raw_changes[:5]:
        if not isinstance(raw, dict):
            raw = {"summary": _to_text(raw), "evidence_refs": []}
        drift_score, confidence_score, scored = _score_relationship_change(raw)
        scored_changes.append(scored)
        drift_scores.append(drift_score)
        confidence_scores.append(confidence_score)

    aggregate_drift_score = round(sum(drift_scores) / len(drift_scores), 4) if drift_scores else 0.0
    aggregate_confidence_score = round(sum(confidence_scores) / len(confidence_scores), 4) if confidence_scores else 0.0
    return {
        "entries": scored_changes,
        "aggregate_drift_score": aggregate_drift_score,
        "aggregate_confidence_score": aggregate_confidence_score,
        "severity": _severity_from_score(aggregate_drift_score),
        "confidence": _confidence_label(aggregate_confidence_score),
        "from_baseline_analysis": bool(baseline_changes),
    }


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _frame_drift_score(frame: dict[str, Any]) -> float:
    topology = frame.get("topology_state") if isinstance(frame.get("topology_state"), dict) else {}
    raw = frame.get("relationship_drift_score") or topology.get("drift_index") or topology.get("instability_score") or 0.0
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return score * 100.0 if score <= 1.0 else score


def _frame_time(frame: dict[str, Any]) -> str:
    return _to_text(frame.get("timestamp_start") or frame.get("timestamp") or frame.get("timestamp_end"))


def _first_frame_at_or_above(frames: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        if _frame_drift_score(frame) >= threshold:
            return frame
        relationship_changes = frame.get("relationship_changes")
        if threshold <= 24.0 and isinstance(relationship_changes, list) and relationship_changes:
            return frame
    return None


def _build_relationship_evidence_lines(relationship_metrics: dict[str, Any], frames: list[dict[str, Any]]) -> list[str]:
    entries = relationship_metrics.get("entries") if isinstance(relationship_metrics.get("entries"), list) else []
    shifted_count = len(entries)
    baseline_periods = max((int(entry.get("baseline_sample_size") or 0) for entry in entries if isinstance(entry, dict)), default=0)
    recent_periods = max((int(entry.get("recent_sample_size") or 0) for entry in entries if isinstance(entry, dict)), default=0)
    confidence = _to_text(relationship_metrics.get("confidence")).title() or "Unknown"

    evidence: list[str] = []
    if shifted_count > 0:
        evidence.append(f"{_pluralize(shifted_count, 'operating relationship')} shifted simultaneously.")
    if len(frames) > 1:
        evidence.append(f"Drift persisted across the full {_pluralize(len(frames), 'replay frame')} in this analysis window.")
    elif recent_periods > 0:
        evidence.append(f"Current behavior was compared across {_pluralize(recent_periods, 'recent operating period')}.")
    evidence.append(f"Detection confidence: {confidence}.")
    if baseline_periods > 0:
        evidence.append(f"Historical baseline established from {_pluralize(baseline_periods, 'operating period')}.")
    return evidence


def _build_relationship_timeline(frames: list[dict[str, Any]], relationship_metrics: dict[str, Any]) -> dict[str, Any]:
    valid_frames = [frame for frame in frames if isinstance(frame, dict)]
    first = valid_frames[0] if valid_frames else {}
    last = valid_frames[-1] if valid_frames else {}
    detected = _first_frame_at_or_above(valid_frames, 24.0)
    significant = _first_frame_at_or_above(valid_frames, 65.0)
    aggregate_drift = float(relationship_metrics.get("aggregate_drift_score") or 0.0)
    if detected is None and aggregate_drift > 0 and valid_frames:
        detected = valid_frames[0]
    if significant is None and aggregate_drift >= 65.0 and valid_frames:
        significant = detected or valid_frames[-1]
    current_severity = _to_text(relationship_metrics.get("severity")).title() or "Contained"
    if not valid_frames and aggregate_drift > 0:
        return {
            "events": [
                {"time": "Baseline window", "label": "Normal", "detail": "Historical operating relationship pattern established."},
                {"time": "Current window", "label": "Current state", "detail": f"Current severity: {current_severity}."},
            ],
            "facts": [
                {"label": "Drift first detected", "value": "Current analysis window"},
                {"label": "Became statistically significant", "value": "Current analysis window" if aggregate_drift >= 65.0 else "Not available"},
                {"label": "Current severity", "value": current_severity},
            ],
        }

    events: list[dict[str, str]] = []
    if first:
        events.append({
            "time": _frame_time(first) or "Window start",
            "label": "Normal",
            "detail": "Historical operating relationship pattern established.",
        })
    if detected:
        events.append({
            "time": _frame_time(detected) or "Detected",
            "label": "Relationship begins diverging",
            "detail": "Relationship behavior moved outside the expected operating pattern.",
        })
    if significant:
        events.append({
            "time": _frame_time(significant) or "Significant",
            "label": "Drift becomes significant",
            "detail": "Relationship drift crossed the statistical review threshold.",
        })
    if last:
        events.append({
            "time": _frame_time(last) or "Current",
            "label": "Current state",
            "detail": f"Current severity: {current_severity}.",
        })

    facts = [
        {"label": "Drift first detected", "value": _frame_time(detected) if detected else "Not available"},
        {"label": "Became statistically significant", "value": _frame_time(significant) if significant else "Not available"},
        {"label": "Current severity", "value": current_severity},
    ]
    return {"events": events, "facts": facts}


def _format_metric(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _to_text(value)
    return f"{number:.{digits}f}"



def _clean_evidence_refs(refs: Any) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        cleaned.append(
            {
                "column": _to_text(ref.get("column")),
                "baseline_window": _to_text(ref.get("baseline_window")),
                "recent_window": _to_text(ref.get("recent_window")),
                "baseline_value": ref.get("baseline_value"),
                "recent_value": ref.get("recent_value"),
            }
        )
    return cleaned



def _clean_source_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cleaned.append(
            {
                "window": _to_text(row.get("window")),
                "timestamp": _to_text(row.get("timestamp")),
                "values": row.get("values") if isinstance(row.get("values"), dict) else {},
            }
        )
    return cleaned



def _columns_from_entry(entry: dict[str, Any]) -> list[str]:
    refs = _clean_evidence_refs(entry.get("evidence_refs"))
    columns = [ref["column"] for ref in refs if ref.get("column")]
    if columns:
        return list(dict.fromkeys(columns))[:4]
    relationship = _to_text(entry.get("relationship"))
    if "<->" in relationship:
        return [part.strip() for part in relationship.split("<->") if part.strip()][:4]
    return []



def _matching_engine_relationships(engine_result: dict[str, Any], columns: list[str]) -> list[dict[str, Any]]:
    expected = {column for column in columns if column}
    matches: list[dict[str, Any]] = []
    for item in engine_result.get("evidence", []):
        if not isinstance(item, dict) or item.get("type") != "relationship_change":
            continue
        item_columns = {str(column) for column in (item.get("columns") or []) if column}
        if expected and (expected == item_columns or expected <= item_columns or item_columns <= expected or expected & item_columns):
            matches.append(item)
    return matches[:4]



def _stage(stage: str, detail: str, *, evidence_refs: list[dict[str, Any]] | None = None, source_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "stage": stage,
        "detail": detail,
        "evidence_refs": evidence_refs or [],
        "source_rows": source_rows or [],
    }



def _build_primary_finding_chain(
    *,
    result: dict[str, Any],
    intelligence: dict[str, Any],
    relationship_divergence: dict[str, Any],
    relationship_change_entries: list[dict[str, Any]],
    label: str,
    driver: str,
    summary_text: str,
) -> dict[str, Any] | None:
    driver_attribution = result.get("driver_attribution") if isinstance(result.get("driver_attribution"), dict) else {}
    engine_result = result.get("engine_result") if isinstance(result.get("engine_result"), dict) else {}
    baseline_analysis = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    top_change = relationship_change_entries[0] if relationship_change_entries else {}
    refs = _clean_evidence_refs(top_change.get("evidence_refs"))
    source_rows = _clean_source_rows(top_change.get("source_rows"))
    persistent_columns = [
        str(column)
        for column in ((engine_result.get("persistence_assessment") or {}).get("persistent_columns") or [])
        if column
    ]
    supporting = [str(item) for item in (driver_attribution.get("supporting_evidence") or intelligence.get("supporting_evidence") or []) if item][:3]
    if not (summary_text or driver or refs or source_rows or supporting):
        return None

    baseline_detail = (
        f"Baseline relationship drift moved from correlation {_format_metric(top_change.get('baseline_correlation'))} "
        f"to {_format_metric(top_change.get('recent_correlation'))} "
        f"(delta {_format_metric(top_change.get('correlation_delta'))}) across "
        f"{int(top_change.get('baseline_sample_size') or 0)} baseline and {int(top_change.get('recent_sample_size') or 0)} recent samples."
        if top_change else
        f"Baseline analysis reviewed {len(baseline_analysis.get('column_drift') or [])} drifted columns and {len(baseline_analysis.get('top_relationship_changes') or [])} relationship changes."
    )
    engine_detail = (
        f"Engine corroboration was {str((engine_result.get('system_evidence') or {}).get('corroboration_level') or 'limited')} "
        f"with {int((engine_result.get('system_evidence') or {}).get('categories_showing_meaningful_change') or 0)} affected categories "
        f"and {len(persistent_columns)} persistent columns."
    )
    attribution_detail = (
        f"Driver attribution selected '{driver or driver_attribution.get('likely_driver') or 'Unknown'}' "
        f"because {supporting[0] if supporting else 'the evidence cluster remained the strongest available chain.'}"
    )
    conclusion_detail = (
        f"Operator conclusion '{label}' surfaced as '{summary_text}' with {relationship_divergence.get('confidence') or intelligence.get('attribution_confidence') or 'unknown'} confidence."
    )
    return {
        "finding_id": "primary_conclusion",
        "finding_type": "primary_conclusion",
        "title": driver or driver_attribution.get("likely_driver") or "Primary conclusion",
        "conclusion": label,
        "operator_summary": summary_text,
        "confidence": str(relationship_divergence.get("confidence") or intelligence.get("attribution_confidence") or "unknown"),
        "evidence_refs": refs,
        "source_rows": source_rows,
        "supporting_evidence": supporting,
        "evidence_chain": [
            _stage("baseline_comparison", baseline_detail, evidence_refs=refs, source_rows=source_rows),
            _stage("engine_corroboration", engine_detail),
            _stage("driver_attribution", attribution_detail),
            _stage("operator_conclusion", conclusion_detail),
        ],
    }



def _build_relationship_finding_chain(
    *,
    entry: dict[str, Any],
    index: int,
    engine_result: dict[str, Any],
    relationship_divergence: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    refs = _clean_evidence_refs(entry.get("evidence_refs"))
    source_rows = _clean_source_rows(entry.get("source_rows"))
    columns = _columns_from_entry(entry)
    engine_matches = _matching_engine_relationships(engine_result, columns)
    persistent_columns = {
        str(column)
        for column in ((engine_result.get("persistence_assessment") or {}).get("persistent_columns") or [])
        if column
    }
    persistent_hits = [column for column in columns if column in persistent_columns]
    baseline_detail = (
        f"Relationship {entry.get('relationship') or entry.get('summary') or f'#{index + 1}'} moved from "
        f"{_format_metric(entry.get('baseline_correlation'))} to {_format_metric(entry.get('recent_correlation'))} "
        f"with delta {_format_metric(entry.get('correlation_delta'))} and coupling strength {_format_metric(entry.get('coupling_strength'))}."
    )
    engine_detail = (
        f"Engine reproduced this change with {len(engine_matches)} corroborating relationship event(s) under "
        f"{str((engine_result.get('system_evidence') or {}).get('corroboration_level') or 'limited')} corroboration."
    )
    persistence_detail = (
        f"Persistent columns carried into this finding: {', '.join(persistent_hits)}."
        if persistent_hits else
        "No persistent-column boost was applied to this finding."
    )
    conclusion_detail = (
        f"This relationship fed the operator-facing state '{label}' at {entry.get('confidence') or relationship_divergence.get('confidence') or 'unknown'} confidence "
        f"with {entry.get('severity') or relationship_divergence.get('severity') or 'contained'} severity."
    )
    return {
        "finding_id": f"relationship_change_{index + 1}",
        "finding_type": "relationship_change",
        "title": _to_text(entry.get("relationship") or entry.get("summary") or f"Relationship change {index + 1}"),
        "conclusion": _to_text(entry.get("summary") or entry.get("relationship") or f"Relationship change {index + 1}"),
        "operator_summary": _to_text(entry.get("summary") or entry.get("relationship")),
        "confidence": str(entry.get("confidence") or relationship_divergence.get("confidence") or "unknown"),
        "severity": str(entry.get("severity") or relationship_divergence.get("severity") or "contained"),
        "evidence_refs": refs,
        "source_rows": source_rows,
        "supporting_evidence": [_to_text(item.get("summary")) for item in engine_matches if item.get("summary")][:3],
        "evidence_chain": [
            _stage("baseline_comparison", baseline_detail, evidence_refs=refs, source_rows=source_rows),
            _stage("engine_corroboration", engine_detail),
            _stage("persistence_check", persistence_detail),
            _stage("operator_conclusion", conclusion_detail),
        ],
    }



def _build_finding_evidence_chains(
    *,
    result: dict[str, Any],
    intelligence: dict[str, Any],
    relationship_divergence: dict[str, Any],
    relationship_change_entries: list[dict[str, Any]],
    label: str,
    driver: str,
    summary_text: str,
) -> list[dict[str, Any]]:
    engine_result = result.get("engine_result") if isinstance(result.get("engine_result"), dict) else {}
    chains: list[dict[str, Any]] = []
    primary = _build_primary_finding_chain(
        result=result,
        intelligence=intelligence,
        relationship_divergence=relationship_divergence,
        relationship_change_entries=relationship_change_entries,
        label=label,
        driver=driver,
        summary_text=summary_text,
    )
    if primary is not None:
        chains.append(primary)
    for index, entry in enumerate(relationship_change_entries[:5]):
        if not isinstance(entry, dict):
            continue
        chains.append(
            _build_relationship_finding_chain(
                entry=entry,
                index=index,
                engine_result=engine_result,
                relationship_divergence=relationship_divergence,
                label=label,
            )
        )
    return chains


def build_system_interpretation(result: dict | None, summary: dict | None, snapshot: dict | None, frames: list[dict]) -> dict:
    result = result if isinstance(result, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    current_upload = snapshot.get("current_upload") if isinstance(snapshot.get("current_upload"), dict) else {}
    intelligence = (result.get("sii_intelligence") or {}) if isinstance(result, dict) else {}
    replay_frame = frames[-1] if frames else {}
    cognition_state = replay_frame.get("cognition_state") or {}
    topology_state = replay_frame.get("topology_state") or {}
    propagation_state = replay_frame.get("propagation_state") or {}
    evidence_state = replay_frame.get("evidence_state") or {}
    relationship_changes = replay_frame.get("relationship_changes") if isinstance(replay_frame.get("relationship_changes"), list) else []
    dominant_paths = propagation_state.get("dominant_paths") if isinstance(propagation_state.get("dominant_paths"), list) else []

    session_job_id = _to_text(
        result.get("job_id")
        or summary.get("job_id")
        or current_upload.get("job_id")
        or snapshot.get("job_id")
    )
    if current_upload:
        has_session = has_active_session_artifact(current_upload, job_id=session_job_id or None)
    else:
        has_session = any(
            (
                has_active_session_artifact(result, job_id=session_job_id or None),
                has_active_session_artifact(summary, job_id=session_job_id or None),
            )
        )
    lineage = (result.get("traceability") if isinstance(result.get("traceability"), dict) else (summary.get("traceability") if isinstance(summary.get("traceability"), dict) else {}))
    raw_facility_state = _to_text(cognition_state.get("facility_state") or intelligence.get("facility_state") or result.get("operating_state") or snapshot.get("status"))
    raw_confidence = _to_text(evidence_state.get("corroboration_strength") or replay_frame.get("confidence_tier") or cognition_state.get("confidence_tier") or intelligence.get("telemetry_profile_confidence"))
    raw_instability = replay_frame.get("instability_score")
    if raw_instability is None:
        raw_instability = topology_state.get("instability_score")
    if raw_instability is None:
        raw_instability = intelligence.get("instability_index")
    if raw_instability is None:
        raw_instability = ((result.get("emerging_instability") or {}).get("instability_score")) if isinstance(result.get("emerging_instability"), dict) else None
    if raw_instability is None and frames:
        raw_instability = 0.0
    instability_index = _normalize_instability_percent(raw_instability)
    relationship_metrics = _build_relationship_divergence_metrics(result, replay_frame)
    relationship_change_entries = relationship_metrics["entries"]
    relationship_drift_score = relationship_metrics["aggregate_drift_score"]
    if relationship_change_entries:
        instability_index = round(max(instability_index, relationship_drift_score), 4)

    compound_components = [
        1 if len(dominant_paths) > 1 else 0,
        1 if len(relationship_changes) > 2 else 0,
        1 if float(replay_frame.get("drift_velocity") or 0) > 0.35 else 0,
        1 if "degrad" in _to_text(cognition_state.get("canonical_phase")).lower() else 0,
    ]
    compound_systems_score = sum(compound_components)
    propagation_scope = "none"
    if len(dominant_paths) >= 3:
        propagation_scope = "broad"
    elif len(dominant_paths) >= 1:
        propagation_scope = "localized"

    fallback_flags: list[str] = []
    missing_fields: list[str] = []
    engine_native_fields: list[str] = []
    fallback_fields: list[str] = []

    if not has_session:
        fallback_flags.extend(["no_active_session_defaults", "instability_default_zero", "timeline_fallback"])
        missing_fields.extend(["result", "summary", "replay_timeline"])
        fallback_fields.extend(
            [
                "facility_state_enum",
                "facility_state_label",
                "confidence",
                "instability_index",
                "primary_driver",
                "escalation_window",
                "relationship_divergence",
                "relationship_events",
                "evidence_packet",
                "forensic",
            ]
        )
        return {
            "facility_state_enum": "no_active_session",
            "facility_state_label": "No Dataset Analyzed",
            "confidence": "Calm",
            "instability_index": 0.0,
            "instability_scale": "0-100",
            "primary_driver": "None",
            "escalation_window": "Awaiting telemetry session",
            "state_derivation_reason": "No active upload/live session found.",
            "relationship_divergence": {
                "severity": "contained",
                "confidence": "Calm",
                "affected_systems": [],
                "top_relationship_changes": [],
            },
            "finding_evidence_chains": [],
            "relationship_events": _timeline_events_from_frames([], snapshot, result),
            "compound_systems_score": 0,
            "propagation_scope": "none",
            "evidence_packet": {
                "packet_id": "",
                "filename": "",
                "row_count": 0,
                "column_count": 0,
                "timestamp_start": "",
                "timestamp_end": "",
                "replay_frame_count": 0,
                "processing_trace_summary": "",
                "archived": False,
                "confidence_trace_stored": False,
                "relationship_snapshot_archived": False,
            },
            "lineage": {
                "job_id": "",
                "run_id": "",
                "upload_id": "",
                "aligned": False,
                "traceability_complete": False,
                "source_rows": [],
                "evidence_windows": [],
                "timestamps": {},
            },
            "run_alignment_verified": False,
            "forensic": {
                "correlation_matrix_summary": "",
                "temporal_geometry_summary": "",
                "confidence_lineage": "",
                "historical_similarity_matches": [],
            },
            "missing_fields": missing_fields,
            "fallback_flags": fallback_flags,
            "engine_native_fields": [],
            "fallback_fields": sorted(set(filter(None, fallback_fields))),
            "interpretation_quality": {
                "level": "fallback",
                "engine_native_count": 0,
                "fallback_count": 4,
                "summary": "Fallback interpretation: no active session.",
            },
        }

    enum = "stable"
    label = "Stable"
    reason = "Relationships are coherent with no material divergence."
    raw_state_lower = raw_facility_state.lower()
    if "recovery" in raw_state_lower:
        enum = "recovery_state"
        label = "Recovery State"
        reason = "Recovery signal detected in facility state."
        engine_native_fields.append("facility_state_enum")
    elif compound_systems_score >= 3 or instability_index >= 75:
        enum = "cascade_risk"
        label = "Cascade Risk"
        reason = "Multi-path propagation and/or high instability indicate cascade risk."
    elif compound_systems_score >= 2 or instability_index >= 55:
        enum = "structural_degradation"
        label = "Structural Degradation"
        reason = "Compounding subsystem pressure indicates structural degradation."
    elif relationship_changes or dominant_paths or instability_index >= 25:
        enum = "relationship_drift"
        label = "Relationship Drift"
        reason = "Relationship divergence detected in replay/topology evidence."

    if not raw_confidence:
        fallback_flags.append("confidence_fallback_empty")
        missing_fields.append("confidence")
        fallback_fields.append("confidence")
    else:
        engine_native_fields.append("confidence")

    if raw_instability is None:
        fallback_flags.append("instability_fallback_zero")
        missing_fields.append("instability_score")
        fallback_fields.append("instability_index")
    else:
        engine_native_fields.append("instability_index")

    if not raw_facility_state:
        fallback_flags.append("facility_state_fallback")
        missing_fields.append("facility_state")
        fallback_fields.append("facility_state_enum")
    else:
        engine_native_fields.append("facility_state_enum")

    timestamp_profile = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    timestamp_start = _to_text(replay_frame.get("timestamp_start") or timestamp_profile.get("first_timestamp"))
    timestamp_end = _to_text(replay_frame.get("timestamp_end") or timestamp_profile.get("last_timestamp"))
    if not timestamp_start or not timestamp_end:
        missing_fields.append("timestamp_coverage")
        fallback_fields.append("evidence_packet.timestamp_coverage")
    else:
        engine_native_fields.append("evidence_packet.timestamp_coverage")

    processing_trace = result.get("processing_trace") if isinstance(result.get("processing_trace"), dict) else {}
    processing_trace_summary_parts = []
    if processing_trace.get("sii_pipeline_ran") is True:
        processing_trace_summary_parts.append("SII pipeline ran")
    if processing_trace.get("sii_completed") is True:
        processing_trace_summary_parts.append("SII completed")
    if processing_trace.get("rows_processed") is not None:
        processing_trace_summary_parts.append(f"rows_processed={processing_trace.get('rows_processed')}")
    if processing_trace.get("columns_analyzed") is not None:
        processing_trace_summary_parts.append(f"columns_analyzed={processing_trace.get('columns_analyzed')}")
    processing_trace_summary = " | ".join(processing_trace_summary_parts)
    if processing_trace_summary:
        engine_native_fields.append("evidence_packet.processing_trace_summary")
    else:
        fallback_fields.append("evidence_packet.processing_trace_summary")

    evidence_packet_id = _to_text((result.get("evidence_packet") or {}).get("packet_id") if isinstance(result.get("evidence_packet"), dict) else "")
    lineage_job_id = _to_text((lineage or {}).get("job_id") or result.get("job_id") or summary.get("job_id"))
    lineage_run_id = _to_text((lineage or {}).get("run_id") or lineage_job_id)
    lineage_upload_id = _to_text((lineage or {}).get("upload_id") or lineage_job_id)
    run_alignment_verified = bool(lineage_job_id and lineage_job_id == lineage_run_id == lineage_upload_id)
    if not evidence_packet_id:
        evidence_packet_id = _to_text((result.get("decision_integrity") or {}).get("run_id") if isinstance(result.get("decision_integrity"), dict) else "")
    if not evidence_packet_id:
        evidence_packet_id = _to_text(result.get("job_id") or summary.get("job_id"))

    forensic_confidence_lineage = evidence_state.get("lineage_events") or evidence_state.get("confidence_lineage") or processing_trace.get("confidence_lineage") or ""
    historical_matches = ((intelligence.get("structural_memory") or {}).get("memory_matches")) if isinstance(intelligence.get("structural_memory"), dict) else []
    if not isinstance(historical_matches, list):
        historical_matches = []

    replay_frame_count = len(frames or [])

    relationship_divergence = {
        "severity": relationship_metrics["severity"],
        "confidence": relationship_metrics["confidence"],
        "confidence_score": relationship_metrics["aggregate_confidence_score"],
        "relationship_drift_score": relationship_drift_score,
        "affected_systems": [
            _to_text(replay_frame.get("affected_subsystem") or replay_frame.get("affected_area") or intelligence.get("primary_room") or result.get("primary_room"))
        ] if _to_text(replay_frame.get("affected_subsystem") or replay_frame.get("affected_area") or intelligence.get("primary_room") or result.get("primary_room")) else [],
        "top_relationship_changes": relationship_change_entries,
        "evidence": _build_relationship_evidence_lines(relationship_metrics, frames),
        "relationship_timeline": _build_relationship_timeline(frames, relationship_metrics),
    }

    if relationship_changes or dominant_paths or relationship_change_entries:
        engine_native_fields.append("relationship_divergence")
        if relationship_metrics.get("from_baseline_analysis"):
            engine_native_fields.extend([
                "relationship_divergence.severity",
                "relationship_divergence.confidence",
                "relationship_divergence.relationship_drift_score",
                "relationship_divergence.confidence_score",
                "instability_index",
            ])
    else:
        fallback_fields.append("relationship_divergence")

    if intelligence.get("review_window") or intelligence.get("review_window_hours") or result.get("review_window") or intelligence.get("projected_time_to_failure") or intelligence.get("projected_time_to_failure_hours") or result.get("projected_time_to_failure"):
        engine_native_fields.append("escalation_window")
    else:
        fallback_fields.append("escalation_window")

    if replay_frame.get("affected_subsystem") or replay_frame.get("affected_area") or intelligence.get("primary_driver") or intelligence.get("primary_room") or result.get("primary_room"):
        engine_native_fields.append("primary_driver")
    else:
        fallback_fields.append("primary_driver")

    key_fields = ["facility_state_enum", "instability_index", "confidence", "relationship_divergence"]
    engine_native_set = set(filter(None, engine_native_fields))
    fallback_set = set(filter(None, fallback_fields))
    engine_native_count = sum(1 for field in key_fields if field in engine_native_set)
    fallback_count = sum(1 for field in key_fields if field in fallback_set)
    if engine_native_count == len(key_fields):
        quality_level = "engine_native"
    elif fallback_count >= 3:
        quality_level = "fallback"
    else:
        quality_level = "partial_engine"
    quality_summary = (
        f"{engine_native_count}/{len(key_fields)} key interpretation fields are engine-native; "
        f"{fallback_count} are fallback-derived."
    )

    primary_driver_text = _to_text(replay_frame.get("affected_subsystem") or replay_frame.get("affected_area") or intelligence.get("primary_driver") or intelligence.get("primary_room") or result.get("primary_room") or "Facility relationship scope")
    relationship_summary_text = _to_text((result.get("relationship_summary") or {}).get("text") if isinstance(result.get("relationship_summary"), dict) else "") or reason
    finding_evidence_chains = _build_finding_evidence_chains(
        result=result,
        intelligence=intelligence,
        relationship_divergence=relationship_divergence,
        relationship_change_entries=relationship_change_entries,
        label=label,
        driver=primary_driver_text,
        summary_text=relationship_summary_text,
    )
    analysis_explanation = result.get("analysis_explanation") if isinstance(result.get("analysis_explanation"), dict) else build_analysis_explanation(result)

    return {
        "facility_state_enum": enum,
        "facility_state_label": label,
        "confidence": relationship_metrics["confidence"] if relationship_change_entries else (raw_confidence or "unknown"),
        "instability_index": instability_index,
        "instability_scale": "0-100",
        "primary_driver": primary_driver_text,
        "escalation_window": _to_text(intelligence.get("review_window") or intelligence.get("review_window_hours") or result.get("review_window") or intelligence.get("projected_time_to_failure") or intelligence.get("projected_time_to_failure_hours") or result.get("projected_time_to_failure") or snapshot.get("last_processed_at") or ""),
        "state_derivation_reason": reason,
        "relationship_divergence": relationship_divergence,
        "finding_evidence_chains": finding_evidence_chains,
        "analysis_explanation": analysis_explanation,
        "relationship_events": _timeline_events_from_frames(frames, snapshot, result),
        "compound_systems_score": compound_systems_score,
        "propagation_scope": propagation_scope,
        "evidence_packet": {
            "packet_id": evidence_packet_id,
            "filename": _to_text(result.get("filename") or snapshot.get("last_filename") or summary.get("filename")),
            "row_count": int(result.get("row_count") or result.get("rows_processed") or snapshot.get("rows_processed") or summary.get("row_count") or 0),
            "column_count": int(result.get("column_count") or result.get("columns_detected") or snapshot.get("columns_detected") or summary.get("column_count") or 0),
            "timestamp_start": timestamp_start,
            "timestamp_end": timestamp_end,
            "replay_frame_count": replay_frame_count,
            "processing_trace_summary": processing_trace_summary,
            "archived": bool(evidence_packet_id),
            "confidence_trace_stored": bool(raw_confidence),
            "relationship_snapshot_archived": replay_frame_count > 0,
        },
        "lineage": {
            "job_id": lineage_job_id,
            "run_id": lineage_run_id,
            "upload_id": lineage_upload_id,
            "aligned": run_alignment_verified and bool((lineage or {}).get("aligned", True)),
            "traceability_complete": bool((lineage or {}).get("traceability_complete")),
            "source_rows": list((lineage or {}).get("source_rows") or []),
            "evidence_windows": list((lineage or {}).get("evidence_windows") or []),
            "timestamps": dict((lineage or {}).get("timestamps") or {}),
        },
        "run_alignment_verified": run_alignment_verified and bool((lineage or {}).get("aligned", True)),
        "forensic": {
            "correlation_matrix_summary": _to_text(replay_frame.get("correlation_matrix") or topology_state.get("correlation_matrix") or ""),
            "temporal_geometry_summary": _to_text(replay_frame.get("temporal_geometry") or topology_state.get("temporal_geometry") or propagation_state.get("geometry") or ""),
            "confidence_lineage": forensic_confidence_lineage,
            "historical_similarity_matches": historical_matches[:5],
        },
        "missing_fields": sorted(set(filter(None, missing_fields))),
        "fallback_flags": sorted(set(filter(None, fallback_flags))),
        "engine_native_fields": sorted(set(filter(None, engine_native_fields))),
        "fallback_fields": sorted(set(filter(None, fallback_fields))),
        "interpretation_quality": {
            "level": quality_level,
            "engine_native_count": engine_native_count,
            "fallback_count": fallback_count,
            "summary": quality_summary,
        },
    }


# Compatibility alias to preserve existing router call naming.
_build_system_interpretation = build_system_interpretation
