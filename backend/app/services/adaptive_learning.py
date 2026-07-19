from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.services.evidence_store import read_evidence_run, upsert_evidence_run
from app.services.runtime_db import now_iso, read_latest_payload, upsert_latest_payload

FEEDBACK_CATEGORIES = [
    "confirmed_issue",
    "useful_warning",
    "expected_behavior",
    "false_positive",
    "maintenance_event",
    "ignore",
]
MAX_EVENT_MEMORY = 120
MAX_FEEDBACK_HISTORY = 20


def derive_site_key(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return "site::default"
    ingestion = result.get("ingestion_metadata") if isinstance(result.get("ingestion_metadata"), dict) else {}
    facility_id = ingestion.get("facility_id") or result.get("connection_id")
    primary_room = ((result.get("room_summary") or {}).get("rooms") or [{}])[0].get("room")
    if facility_id and primary_room:
        return f"site::{slugify(facility_id)}::{slugify(primary_room)}"
    if facility_id:
        return f"site::{slugify(facility_id)}"
    if primary_room:
        return f"site::room::{slugify(primary_room)}"
    return "site::default"


def site_memory_key(site_key: str) -> str:
    return f"adaptive_site_memory::{site_key}"


def event_memory_key(site_key: str) -> str:
    return f"adaptive_event_memory::{site_key}"


def read_site_memory(site_key: str) -> dict[str, Any] | None:
    payload = read_latest_payload(site_memory_key(site_key))
    return payload if isinstance(payload, dict) else None


def read_event_memory(site_key: str, limit: int = MAX_EVENT_MEMORY) -> list[dict[str, Any]]:
    payload = read_latest_payload(event_memory_key(site_key))
    if not isinstance(payload, list):
        return []
    items = [item for item in payload if isinstance(item, dict)]
    items.sort(key=lambda item: item.get("occurred_at") or "", reverse=True)
    return items[:limit]


def derive_interpretive_archetypes(result: dict[str, Any]) -> list[dict[str, Any]]:
    driver = str((result.get("driver_attribution") or {}).get("driver_category") or "").lower()
    warnings = " ".join(result.get("warnings", [])).lower()
    evidence_blob = " ".join(
        str(item.get("type") or item.get("message") or "")
        for item in (result.get("engine_result") or {}).get("evidence", [])
        if isinstance(item, dict)
    ).lower()
    archetypes: list[dict[str, Any]] = []

    def add(name: str, signal: str, basis: list[str]) -> None:
        archetypes.append(
            {
                "name": name,
                "signal": signal,
                "basis": basis,
                "deterministic_diagnosis": False,
            }
        )

    if "airflow" in driver or "flow" in evidence_blob:
        add("airflow imbalance", "relationship learning", ["Driver attribution indicates airflow restriction.", "Evidence memory shows flow-related change."])
    if "hvac" in driver or "temperature" in warnings:
        add("cooling response lag", "adaptive baseline", ["HVAC instability is recurring relative to baseline timing.", "Temperature behavior is slower than the operational fingerprint."])
    if "relationship" in evidence_blob or "drift" in warnings:
        add("relationship decay", "evidence memory", ["Structural relationships changed versus baseline norms.", "Evidence history contains relationship drift markers."])
    if "humidity" in driver or "thermal" in evidence_blob:
        add("thermal instability", "operational fingerprint", ["Thermal or moisture coupling moved outside normal range.", "The adaptive baseline sees instability in environmental control."])
    if "runtime" in warnings or "load" in warnings:
        add("load mismatch", "calibration", ["Equipment runtime is diverging from expected response.", "Historical behavior suggests system load imbalance."])
    if "oscillat" in warnings or "transition" in warnings:
        add("oscillatory behavior", "relationship learning", ["Repeated up/down movement is appearing across samples.", "The recent operating fingerprint includes oscillatory recovery behavior."])

    deduped: dict[str, dict[str, Any]] = {}
    for archetype in archetypes:
        deduped.setdefault(archetype["name"], archetype)
    return list(deduped.values())[:4]


def update_site_memory_from_result(result: dict[str, Any], completed_at: str) -> dict[str, Any]:
    site_key = derive_site_key(result)
    current = read_site_memory(site_key) or build_empty_site_memory(site_key, completed_at)
    event_memory = read_event_memory(site_key)
    operational_ranges = build_operational_ranges(result)
    relationship_norms = build_relationship_norms(result)
    fingerprint = build_operational_fingerprint(result)
    baseline_updates = int(current.get("baseline_updates", 0)) + 1

    updated = {
        **current,
        "site_key": site_key,
        "first_seen_at": current.get("first_seen_at") or completed_at,
        "last_updated_at": completed_at,
        "baseline_updates": baseline_updates,
        "rolling_baseline_statistics": {
            "rows_processed": result.get("row_count", 0),
            "columns_detected": result.get("column_count", 0),
            "sampled_rows": ((result.get("processing_stats") or {}).get("sampled_rows")),
        },
        "relationship_norms": relationship_norms,
        "operational_ranges": operational_ranges,
        "time_of_day_behavior": build_time_of_day_behavior(result),
        "recurring_cycles": build_recurring_cycles(result),
        "seasonal_environmental_patterns": build_seasonal_patterns(result),
        "operational_fingerprint": fingerprint,
        "memory_health": {
            "event_count": len(event_memory),
            "feedback_count": sum(1 for item in event_memory if item.get("feedback_category")),
            "learning_status": learning_status_for_counts(baseline_updates, len(event_memory)),
        },
        "future_modules": {
            "clustering": "module_boundary_ready",
            "anomaly_ranking": "module_boundary_ready",
            "sequence_models": "module_boundary_ready",
            "similarity_search": "module_boundary_ready",
            "probabilistic_calibration": "module_boundary_ready",
        },
        "governance_boundary": {
            "read_only": True,
            "operator_authority_preserved": True,
            "autonomous_control": False,
            "core_detection_rewrites": False,
        },
    }
    upsert_latest_payload(site_memory_key(site_key), updated)
    return updated


def append_event_memory(
    *,
    site_key: str,
    run_id: str,
    completed_at: str,
    summary: dict[str, Any],
    result: dict[str, Any],
    feedback_category: str | None = None,
) -> list[dict[str, Any]]:
    existing = read_event_memory(site_key)
    archetypes = derive_interpretive_archetypes(result)
    confidence = build_calibration_confidence(read_site_memory(site_key), existing)
    record = {
        "run_id": run_id,
        "site_key": site_key,
        "occurred_at": completed_at,
        "drift_status": summary.get("drift_status"),
        "operating_state": summary.get("operating_state"),
        "primary_room": summary.get("primary_room"),
        "neraium_score": summary.get("neraium_score"),
        "evidence_summary": summary.get("warnings", [])[:4] or (result.get("sii_intelligence") or {}).get("supporting_evidence", [])[:4],
        "structural_archetypes": [item["name"] for item in archetypes],
        "feedback_category": feedback_category,
        "confidence_snapshot": confidence,
    }
    filtered = [item for item in existing if item.get("run_id") != run_id]
    updated = [record, *filtered][:MAX_EVENT_MEMORY]
    upsert_latest_payload(event_memory_key(site_key), updated)
    return updated


def build_adaptive_snapshot(result: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    site_key = derive_site_key(result)
    site_memory = read_site_memory(site_key) or build_empty_site_memory(site_key, summary.get("last_processed_at") or now_iso())
    event_memory = read_event_memory(site_key)
    archetypes = derive_interpretive_archetypes(result)
    similar_events = [item for item in event_memory if set(item.get("structural_archetypes", [])) & {entry["name"] for entry in archetypes}]
    feedback_counts = Counter(
        item.get("feedback_category")
        for item in event_memory
        if item.get("feedback_category") in FEEDBACK_CATEGORIES
    )
    sensitivity_adjustment = bounded_sensitivity_adjustment(feedback_counts)
    feedback_profile = build_feedback_calibration_profile(feedback_counts)
    baseline_age = age_summary(site_memory.get("first_seen_at"))
    calibration_confidence = build_calibration_confidence(site_memory, event_memory)
    latest_feedback = [item for item in event_memory if item.get("feedback_category")][:6]

    return {
        "site_key": site_key,
        "learning_status": learning_status_for_counts(int(site_memory.get("baseline_updates", 0)), len(event_memory)),
        "adaptive_baseline": {
            "baseline_age": baseline_age,
            "relationship_norms_tracked": len(site_memory.get("relationship_norms", [])),
            "operational_ranges_tracked": len(site_memory.get("operational_ranges", [])),
            "time_of_day_windows": len(site_memory.get("time_of_day_behavior", [])),
            "recurring_cycles": site_memory.get("recurring_cycles", []),
            "seasonal_environmental_patterns": site_memory.get("seasonal_environmental_patterns", []),
        },
        "calibration": {
            "sensitivity_adjustment": sensitivity_adjustment,
            "feedback_profile": feedback_profile,
            "bounded": True,
            "calibration_confidence": calibration_confidence,
            "nuisance_alert_suppression": min(0.25, round((feedback_counts.get("false_positive", 0) + feedback_counts.get("ignore", 0)) * 0.03, 3)),
            "repetitive_alert_guard": len(similar_events) > 1,
            "deterministic_evidence_preserved": True,
        },
        "event_memory": {
            "watch_alert_history_count": len([item for item in event_memory if str(item.get("drift_status") or "").lower() in {"review", "elevated", "alert", "watch"}]),
            "historical_similar_events": len(similar_events),
            "recent_feedback_history": latest_feedback,
        },
        "pattern_recognition": {
            "interpretive_archetypes": archetypes,
            "message": "Recurring patterns are interpretive archetypes, not deterministic diagnoses.",
        },
        "explainability": {
            "why_watch_or_alert": (result.get("sii_intelligence") or {}).get("structural_explanation", [])[:3],
            "relative_to_baseline": summarize_relative_to_baseline(result),
            "evidence_contributors": (result.get("sii_intelligence") or {}).get("supporting_evidence", [])[:4],
            "confidence_breakdown": {
                "baseline_updates": int(site_memory.get("baseline_updates", 0)),
                "event_history": len(event_memory),
                "operator_feedback": sum(feedback_counts.values()),
                "bounded_adjustment": sensitivity_adjustment,
                "feedback_direction": feedback_profile["direction"],
            },
            "opaque_hidden_scoring": False,
            "autonomous_actions": False,
        },
        "operator_feedback_options": FEEDBACK_CATEGORIES,
        "future_ml_hooks": site_memory.get("future_modules", {}),
    }


def apply_operator_feedback(run_id: str, category: str, note: str | None, actor: str) -> dict[str, Any]:
    normalized = normalize_feedback_category(category)
    if normalized not in FEEDBACK_CATEGORIES:
        raise ValueError("invalid_feedback_category")
    record = read_evidence_run(run_id)
    if record is None:
        raise ValueError("evidence_run_not_found")

    feedback_entry = {
        "category": normalized,
        "note": (note or "").strip() or None,
        "actor": actor,
        "recorded_at": now_iso(),
    }
    history = [item for item in record.get("operator_feedback_history", []) if isinstance(item, dict)]
    updated_history = [feedback_entry, *history][:MAX_FEEDBACK_HISTORY]
    updated_record = {
        **record,
        "latest_feedback_category": normalized,
        "operator_feedback_history": updated_history,
    }
    upsert_evidence_run(updated_record)

    site_key = record.get("adaptive_site_key") or "site::default"
    event_memory = read_event_memory(site_key)
    rewritten = []
    matched = False
    for item in event_memory:
        if item.get("run_id") == run_id:
            matched = True
            rewritten.append({**item, "feedback_category": normalized, "feedback_note": feedback_entry["note"], "feedback_recorded_at": feedback_entry["recorded_at"]})
        else:
            rewritten.append(item)
    if not matched:
        rewritten.insert(
            0,
            {
                "run_id": run_id,
                "site_key": site_key,
                "occurred_at": feedback_entry["recorded_at"],
                "feedback_category": normalized,
                "feedback_note": feedback_entry["note"],
                "feedback_recorded_at": feedback_entry["recorded_at"],
            },
        )
    upsert_latest_payload(event_memory_key(site_key), rewritten[:MAX_EVENT_MEMORY])

    site_memory = read_site_memory(site_key) or build_empty_site_memory(site_key, feedback_entry["recorded_at"])
    feedback_summary = dict(site_memory.get("feedback_summary", {}))
    feedback_summary[normalized] = int(feedback_summary.get(normalized, 0)) + 1
    updated_site_memory = {
        **site_memory,
        "feedback_summary": feedback_summary,
        "last_updated_at": feedback_entry["recorded_at"],
        "memory_health": {
            **site_memory.get("memory_health", {}),
            "feedback_count": sum(feedback_summary.values()),
            "learning_status": learning_status_for_counts(int(site_memory.get("baseline_updates", 0)), len(rewritten)),
        },
    }
    upsert_latest_payload(site_memory_key(site_key), updated_site_memory)
    return updated_record


def build_empty_site_memory(site_key: str, created_at: str) -> dict[str, Any]:
    return {
        "site_key": site_key,
        "first_seen_at": created_at,
        "last_updated_at": created_at,
        "baseline_updates": 0,
        "rolling_baseline_statistics": {},
        "relationship_norms": [],
        "operational_ranges": [],
        "time_of_day_behavior": [],
        "recurring_cycles": [],
        "seasonal_environmental_patterns": [],
        "operational_fingerprint": {},
        "feedback_summary": {},
        "memory_health": {
            "event_count": 0,
            "feedback_count": 0,
            "learning_status": "warming_up",
        },
        "future_modules": {},
        "governance_boundary": {
            "read_only": True,
            "operator_authority_preserved": True,
            "autonomous_control": False,
            "core_detection_rewrites": False,
        },
    }


def build_operational_ranges(result: dict[str, Any]) -> list[dict[str, Any]]:
    ranges = []
    for profile in result.get("numeric_profiles", [])[:16]:
        if not isinstance(profile, dict):
            continue
        ranges.append(
            {
                "column": profile.get("column"),
                "min": profile.get("min"),
                "max": profile.get("max"),
                "mean": profile.get("mean"),
                "std": profile.get("std_dev") or profile.get("std"),
            }
        )
    return ranges


def build_relationship_norms(result: dict[str, Any]) -> list[dict[str, Any]]:
    relationships = ((result.get("baseline_analysis") or {}).get("relationship_drift")) or []
    norms = []
    for item in relationships[:10]:
        if not isinstance(item, dict):
            continue
        norms.append(
            {
                "relationship": item.get("relationship") or item.get("path") or item.get("detail"),
                "status": item.get("status") or item.get("severity"),
                "detail": item.get("detail"),
            }
        )
    return norms


def build_operational_fingerprint(result: dict[str, Any]) -> dict[str, Any]:
    intelligence = result.get("sii_intelligence") if isinstance(result.get("sii_intelligence"), dict) else {}
    room_summary = result.get("room_summary") if isinstance(result.get("room_summary"), dict) else {}
    return {
        "primary_room": intelligence.get("primary_room"),
        "room_count": room_summary.get("room_count"),
        "facility_state": intelligence.get("facility_state"),
        "primary_driver": intelligence.get("primary_driver"),
    }


def build_time_of_day_behavior(result: dict[str, Any]) -> list[dict[str, Any]]:
    timestamp_profile = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    return [
        {
            "first_timestamp": timestamp_profile.get("first_timestamp"),
            "last_timestamp": timestamp_profile.get("last_timestamp"),
            "estimated_sample_interval": timestamp_profile.get("estimated_sample_interval"),
        }
    ]


def build_recurring_cycles(result: dict[str, Any]) -> list[str]:
    room_summary = result.get("room_summary") if isinstance(result.get("room_summary"), dict) else {}
    rooms = room_summary.get("rooms") if isinstance(room_summary.get("rooms"), list) else []
    if len(rooms) > 1:
        return ["multi-room recurring cycle observed"]
    return ["single-environment operating cycle observed"]


def build_seasonal_patterns(result: dict[str, Any]) -> list[str]:
    timestamp_profile = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    first_timestamp = str(timestamp_profile.get("first_timestamp") or "")
    if not first_timestamp:
        return []
    return [f"Seasonal pattern tracking ready from {first_timestamp[:7]} sample history."]


def summarize_relative_to_baseline(result: dict[str, Any]) -> list[str]:
    baseline = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    summary = []
    if baseline.get("overall_assessment"):
        summary.append(f"Baseline assessment: {baseline['overall_assessment']}.")
    for item in (baseline.get("significant_columns") or [])[:2]:
        if isinstance(item, dict) and item.get("column"):
            summary.append(f"{item['column']} shifted outside the normal operating fingerprint.")
    return summary[:3]


def build_calibration_confidence(site_memory: dict[str, Any] | None, event_memory: list[dict[str, Any]]) -> float:
    baseline_updates = int((site_memory or {}).get("baseline_updates", 0))
    feedback_count = len([item for item in event_memory if item.get("feedback_category")])
    raw = 0.35 + min(0.35, baseline_updates * 0.04) + min(0.25, feedback_count * 0.03)
    return round(max(0.35, min(0.95, raw)), 3)


def bounded_sensitivity_adjustment(feedback_counts: Counter[str]) -> float:
    supportive = feedback_counts.get("confirmed_issue", 0) + feedback_counts.get("useful_warning", 0)
    suppressive = feedback_counts.get("false_positive", 0) + feedback_counts.get("ignore", 0) + feedback_counts.get("expected_behavior", 0)
    total = supportive + suppressive + feedback_counts.get("maintenance_event", 0)
    if total == 0:
        return 0.0
    raw = (supportive - suppressive) / total
    return round(max(-0.08, min(0.08, raw * 0.08)), 3)


def learning_status_for_counts(baseline_updates: int, event_count: int) -> str:
    if baseline_updates < 3:
        return "warming_up"
    if event_count < 5:
        return "adaptive_baseline_building"
    if event_count < 12:
        return "calibrating"
    return "calibrated_with_operator_governance"


def age_summary(timestamp: str | None) -> dict[str, Any]:
    parsed = parse_timestamp(timestamp)
    if parsed is None:
        return {"label": "Unavailable", "days": None, "hours": None}
    now = datetime.now(UTC)
    delta = now - parsed
    hours = max(0, int(delta.total_seconds() // 3600))
    days = round(delta.total_seconds() / 86400, 1)
    return {
        "label": f"{hours}h" if hours < 48 else f"{days}d",
        "days": days,
        "hours": hours,
    }


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_feedback_category(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def slugify(value: Any) -> str:
    text = "".join(character.lower() if character.isalnum() else "-" for character in str(value or ""))
    pieces = [piece for piece in text.split("-") if piece]
    return "-".join(pieces) or "default"



def build_feedback_calibration_profile(feedback_counts: Counter[str]) -> dict[str, Any]:
    confirmed = feedback_counts.get("confirmed_issue", 0) + feedback_counts.get("useful_warning", 0)
    suppressed = feedback_counts.get("false_positive", 0) + feedback_counts.get("ignore", 0) + feedback_counts.get("expected_behavior", 0)
    maintenance = feedback_counts.get("maintenance_event", 0)
    total = confirmed + suppressed + maintenance
    if total == 0:
        direction = "neutral"
    elif confirmed > suppressed:
        direction = "increase_sensitivity"
    elif suppressed > confirmed:
        direction = "decrease_sensitivity"
    else:
        direction = "hold"
    return {
        "total_feedback": total,
        "confirmed_or_useful": confirmed,
        "suppressed_or_expected": suppressed,
        "maintenance_context": maintenance,
        "direction": direction,
        "bounded_learning": True,
        "operator_authority_preserved": True,
    }
