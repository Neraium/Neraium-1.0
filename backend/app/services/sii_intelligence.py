from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.aletheia_governance import govern_candidate
from app.services.structural_cognition import build_structural_cognition


REQUIRED_INTELLIGENCE_FIELDS = [
    "facility_state",
    "room_state",
    "urgency",
    "intervention_window",
    "neraium_score",
    "primary_driver",
    "supporting_evidence",
    "relationship_evidence",
    "structural_explanation",
    "confidence_basis",
    "recommended_operator_review",
    "what_to_check",
    "why_flagged",
    "baseline_comparison",
    "observed_persistence",
    "last_updated",
]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_sample_intelligence() -> dict[str, Any]:
    """Return backend-provided SII sample intelligence for no-upload sessions."""

    last_updated = now_iso()
    rooms = [
        {
            "room": "Flower Room 2",
            "room_state": "Drift observed",
            "urgency": "review",
            "intervention_window": "8 hours",
            "primary_driver": "Humidity recovery is lagging behind recent room behavior.",
            "supporting_evidence": [
                "Humidity recovery remained slower than recent room behavior.",
                "Temperature and humidity recovery are less synchronized than baseline.",
                "Pattern persisted across recent monitoring windows.",
            ],
            "relationship_evidence": [
                "Temperature recovery is decoupling from humidity stabilization.",
                "Environmental coupling is becoming less consistent.",
            ],
            "structural_explanation": [
                "Temperature recovery is decoupling from humidity stabilization.",
                "Environmental coupling is less consistent than the room's recent baseline.",
                "Room recovery behavior is compressing the intervention horizon.",
            ],
            "confidence_basis": "Persistent multi-signal drift compared to recent baseline.",
            "recommended_operator_review": "Review humidity recovery behavior",
            "what_to_check": [
                "Review dehumidification response",
                "Check room moisture load",
                "Compare recent recovery time to normal room behavior",
            ],
            "why_flagged": "Humidity recovery has remained slower than recent room behavior across recent monitoring windows.",
            "baseline_comparison": "Recovery behavior is shorter than this room's recent operating baseline.",
            "observed_persistence": "Observed across 3 monitoring windows",
            "projected_time_to_failure": "Approximately 8 hours at current trajectory",
            "projected_time_to_failure_hours": 8,
            "last_updated": last_updated,
            "confidence": 86,
        },
        {
            "room": "Veg Room 1",
            "room_state": "Stable",
            "urgency": "nominal",
            "intervention_window": "5 weeks",
            "primary_driver": "Environmental coupling remains consistent compared to recent baseline.",
            "supporting_evidence": [
                "Temperature response remains inside recent room behavior.",
                "Humidity recovery remains visible and controlled.",
            ],
            "relationship_evidence": [
                "Environmental coupling remains stable.",
            ],
            "structural_explanation": [
                "Room temperature response remains within expected behavior.",
                "Environmental coupling remains stable.",
                "Cycle settling remains the current operating state.",
            ],
            "confidence_basis": "Stable relationship behavior across recent monitoring windows.",
            "recommended_operator_review": "Continue monitoring",
            "what_to_check": [
                "Continue routine room walk",
                "Watch recovery timing after the next transition",
                "Review changes only if the window shortens",
            ],
            "why_flagged": "Room behavior remains visible and controllable across recent monitoring windows.",
            "baseline_comparison": "Room behavior is inside recent operating baseline.",
            "observed_persistence": "Stable across recent monitoring windows",
            "projected_time_to_failure": "More than 5 weeks at current trajectory",
            "projected_time_to_failure_hours": 840,
            "last_updated": last_updated,
            "confidence": 74,
        },
    ]
    structural_cognition = build_structural_cognition(
        baseline_analysis={
            "column_drift": [
                {"column": "humidity", "percent_change": 18, "drift_flag": "review"},
                {"column": "temperature", "percent_change": 11, "drift_flag": "watch"},
            ]
        },
        engine_result={
            "system_evidence": {
                "corroboration_level": "strong",
                "categories_showing_meaningful_change": 3,
                "categories": {
                    "moisture_control": {"signals": [1, 2], "evidence": [1]},
                    "thermal_control": {"signals": [1], "evidence": [1]},
                    "flow_restriction": {"signals": [1], "evidence": [1]},
                },
            },
            "evidence": [
                {"type": "relationship_change", "columns": ["airflow", "humidity"], "change": 0.82},
                {"type": "relationship_change", "columns": ["temperature", "humidity"], "change": 0.76},
            ],
            "persistence_assessment": {"persistent_columns": ["humidity", "temperature"]},
        },
        driver_attribution={
            "likely_driver": rooms[0]["primary_driver"],
            "driver_category": "humidity_control",
            "supporting_evidence": rooms[0]["supporting_evidence"],
        },
        room_summary={"room_count": len(rooms), "rooms": [{"room": room["room"]} for room in rooms]},
        urgency="review",
    )
    operator_explanation = structural_cognition["operator_explanation_v2"]
    candidate = {
        "source": "sii_engine",
        "mode": "sample",
        "facility_state": "Drift observed",
        "room_state": rooms[0]["room_state"],
        "urgency": "review",
        "intervention_window": rooms[0]["intervention_window"],
        "neraium_score": 82,
        "primary_room": rooms[0]["room"],
        "primary_driver": rooms[0]["primary_driver"],
        "supporting_evidence": rooms[0]["supporting_evidence"],
        "relationship_evidence": rooms[0]["relationship_evidence"],
        "structural_explanation": rooms[0]["structural_explanation"],
        "confidence_basis": rooms[0]["confidence_basis"],
        "recommended_operator_review": rooms[0]["recommended_operator_review"],
        "what_to_check": rooms[0]["what_to_check"],
        "why_flagged": rooms[0]["why_flagged"],
        "baseline_comparison": rooms[0]["baseline_comparison"],
        "observed_persistence": rooms[0]["observed_persistence"],
        "projected_time_to_failure": rooms[0]["projected_time_to_failure"],
        "projected_time_to_failure_hours": rooms[0]["projected_time_to_failure_hours"],
        "last_updated": last_updated,
        "rooms": rooms,
        **structural_cognition,
        "structural_explanation": [
            operator_explanation["summary"],
            *rooms[0]["structural_explanation"][:2],
        ],
    }
    candidate["aletheia_gate"] = govern_candidate(candidate)
    return candidate


def build_upload_intelligence(
    *,
    filename: str,
    row_count: int,
    data_quality: dict[str, Any],
    baseline_analysis: dict[str, Any],
    engine_result: dict[str, Any],
    driver_attribution: dict[str, Any],
    operator_report: dict[str, Any],
    timestamp_profile: dict[str, Any],
    room_summary: dict[str, Any] | None = None,
    source: str = "uploaded",
    mode: str = "live",
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_updated = now_iso()
    urgency = urgency_from_upload(
        data_quality=data_quality,
        engine_result=engine_result,
        attribution=driver_attribution,
    )
    score = score_from_upload(data_quality, engine_result, driver_attribution)
    primary_driver = driver_attribution.get("likely_driver") or "Available telemetry suggests a room behavior change."
    supporting_evidence = driver_attribution.get("supporting_evidence") or operator_report.get("key_observations", [])
    relationship_evidence = relationship_evidence_from_engine(engine_result)
    structural_explanation = structural_explanation_from_attribution(driver_attribution, relationship_evidence)
    why_flagged = supporting_evidence[0] if supporting_evidence else "Telemetry changed compared to recent baseline."
    what_to_check = checks_from_attribution(driver_attribution, operator_report)
    intervention_window = window_from_urgency(urgency)
    room = driver_attribution.get("room") or "Current room"
    room_state = driver_attribution.get("state") or state_from_urgency(urgency)
    projected_time_to_failure_hours = project_time_to_failure_hours(
        urgency=urgency,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
    )
    projected_time_to_failure = format_projected_time_to_failure(projected_time_to_failure_hours)
    structural_cognition = build_structural_cognition(
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        room_summary=room_summary,
        urgency=urgency,
    )
    operator_explanation = structural_cognition["operator_explanation_v2"]
    structural_explanation = [
        operator_explanation["summary"],
        *structural_explanation[:2],
    ]

    room_records = build_upload_room_records(
        room_summary=room_summary,
        fallback_room=room,
        room_state=room_state,
        urgency=urgency,
        intervention_window=intervention_window,
        primary_driver=primary_driver,
        supporting_evidence=supporting_evidence,
        relationship_evidence=relationship_evidence,
        structural_explanation=structural_explanation,
        confidence_basis=driver_attribution.get("confidence_basis") or "Evidence is being compared across uploaded room signals.",
        recommended_operator_review=driver_attribution.get("next_operator_move") or (what_to_check[0] if what_to_check else "Continue monitoring"),
        what_to_check=what_to_check,
        why_flagged=why_flagged,
        baseline_comparison=baseline_comparison_from_analysis(baseline_analysis),
        observed_persistence=observed_persistence_from_engine(engine_result),
        projected_time_to_failure=projected_time_to_failure,
        projected_time_to_failure_hours=projected_time_to_failure_hours,
        last_updated=last_updated,
        confidence=confidence_number(driver_attribution),
    )
    primary_room_record = room_records[0]
    candidate = {
        "source": source,
        "mode": mode,
        "facility_state": primary_room_record["room_state"],
        "room_state": primary_room_record["room_state"],
        "urgency": urgency,
        "intervention_window": intervention_window,
        "neraium_score": score,
        "primary_room": primary_room_record["room"],
        "priority_room": primary_room_record["room"],
        "primary_driver": primary_driver,
        "supporting_evidence": supporting_evidence,
        "relationship_evidence": relationship_evidence,
        "structural_explanation": structural_explanation,
        "confidence_basis": primary_room_record["confidence_basis"],
        "recommended_operator_review": primary_room_record["recommended_operator_review"],
        "what_to_check": what_to_check,
        "why_flagged": why_flagged,
        "baseline_comparison": primary_room_record["baseline_comparison"],
        "observed_persistence": primary_room_record["observed_persistence"],
        "projected_time_to_failure": primary_room_record["projected_time_to_failure"],
        "projected_time_to_failure_hours": primary_room_record["projected_time_to_failure_hours"],
        "last_updated": last_updated,
        "filename": filename,
        "row_count": row_count,
        "timestamp_coverage": timestamp_profile,
        "room_summary": room_summary or {},
        "rooms": room_records,
        "source_metadata": source_metadata or {},
        **structural_cognition,
    }
    candidate["aletheia_gate"] = govern_candidate(candidate)
    return candidate


def build_upload_room_records(
    *,
    room_summary: dict[str, Any] | None,
    fallback_room: str,
    room_state: str,
    urgency: str,
    intervention_window: str,
    primary_driver: str,
    supporting_evidence: list[str],
    relationship_evidence: list[str],
    structural_explanation: list[str],
    confidence_basis: str,
    recommended_operator_review: str,
    what_to_check: list[str],
    why_flagged: str,
    baseline_comparison: str,
    observed_persistence: str,
    projected_time_to_failure: str,
    projected_time_to_failure_hours: int,
    last_updated: str,
    confidence: int,
) -> list[dict[str, Any]]:
    summary_rooms = room_summary.get("rooms", []) if isinstance(room_summary, dict) else []
    room_names = [
        str(item.get("room"))
        for item in summary_rooms
        if isinstance(item, dict) and item.get("room")
    ]
    if not room_names:
        room_names = [fallback_room or "Current room"]

    records = []
    for index, room_name in enumerate(room_names):
        records.append(
            {
                "room": room_name,
                "room_state": room_state if index == 0 else "Monitoring",
                "urgency": urgency if index == 0 else "nominal",
                "intervention_window": intervention_window if index == 0 else "Monitoring",
                "primary_driver": primary_driver if index == 0 else "Room telemetry included in latest upload.",
                "supporting_evidence": supporting_evidence if index == 0 else [f"{room_name} was detected in the uploaded telemetry."],
                "relationship_evidence": relationship_evidence,
                "structural_explanation": structural_explanation,
                "confidence_basis": confidence_basis,
                "recommended_operator_review": recommended_operator_review if index == 0 else "Continue monitoring",
                "what_to_check": what_to_check,
                "why_flagged": why_flagged if index == 0 else f"{room_name} is part of the uploaded room set.",
                "baseline_comparison": baseline_comparison,
                "observed_persistence": observed_persistence,
                "projected_time_to_failure": projected_time_to_failure if index == 0 else "Monitoring",
                "projected_time_to_failure_hours": projected_time_to_failure_hours if index == 0 else None,
                "last_updated": last_updated,
                "confidence": confidence if index == 0 else max(confidence - 8, 0),
            }
        )
    return records


def project_time_to_failure_hours(
    *,
    urgency: str,
    engine_result: dict[str, Any],
    driver_attribution: dict[str, Any],
) -> int:
    base_hours = {"unstable": 8, "review": 48, "nominal": 504}.get(urgency, 72)
    signal_profile = summarize_signal_profile(engine_result)
    if signal_profile["elevated_count"] > 0:
        base_hours = min(base_hours, 8)
    elif signal_profile["review_count"] > 0:
        base_hours = min(base_hours, 36)
    elif signal_profile["watch_count"] > 0:
        base_hours = min(base_hours, 120)
    if signal_profile["corroboration_level"] == "strong":
        base_hours = max(4, int(base_hours * 0.65))
    elif signal_profile["corroboration_level"] == "moderate":
        base_hours = max(6, int(base_hours * 0.8))
    if signal_profile["persistent_columns"] > 0:
        base_hours = max(4, int(base_hours * 0.7))
    if driver_attribution.get("severity") == "action":
        base_hours = min(base_hours, 8)
    elif driver_attribution.get("severity") == "review":
        base_hours = min(base_hours, 36)
    return base_hours


def format_projected_time_to_failure(hours: int) -> str:
    if hours <= 12:
        return f"Approximately {hours} hours at current trajectory"
    if hours <= 72:
        days = max(1, round(hours / 24))
        return f"Approximately {days} days at current trajectory"
    weeks = max(1, round(hours / 168))
    return f"More than {weeks} weeks at current trajectory"


def build_intelligence_status(intelligence: dict[str, Any] | None = None) -> dict[str, Any]:
    intelligence = intelligence or build_sample_intelligence()
    fields = set(REQUIRED_INTELLIGENCE_FIELDS)
    return {
        "engine_loaded": True,
        "source": intelligence.get("source", "sii_engine"),
        "last_processed_at": intelligence.get("last_updated"),
        "active_rooms_count": len(intelligence.get("rooms", [])),
        "evidence_fields_present": sorted(field for field in fields if field in intelligence),
        "mode": intelligence.get("mode", "sample"),
    }


def build_empty_intelligence_status() -> dict[str, Any]:
    return {
        "engine_loaded": True,
        "source": "none",
        "last_processed_at": None,
        "active_rooms_count": 0,
        "evidence_fields_present": [],
        "mode": "empty",
        "status": "no_data",
    }


def score_from_upload(data_quality: dict[str, Any], engine_result: dict[str, Any], attribution: dict[str, Any]) -> int:
    readiness = data_quality.get("readiness")
    severity = attribution.get("severity", "info")
    signal_profile = summarize_signal_profile(engine_result)
    score = 92 if readiness == "ready" else 80 if readiness == "needs_review" else 64
    score -= signal_profile["watch_count"] * 2
    score -= signal_profile["review_count"] * 4
    score -= signal_profile["elevated_count"] * 7
    if signal_profile["corroboration_level"] == "strong":
        score -= 4
    elif signal_profile["corroboration_level"] == "moderate":
        score -= 2
    score -= min(signal_profile["persistent_columns"] * 2, 4)
    if engine_result.get("overall_result") == "needs_review" and not engine_result.get("signals"):
        score -= 6
    elif engine_result.get("overall_result") == "elevated":
        score -= 4
    if severity == "action":
        score -= 6
    elif severity == "review":
        score -= 3
    return max(0, min(100, score))


def urgency_from_upload(
    *,
    data_quality: dict[str, Any],
    engine_result: dict[str, Any],
    attribution: dict[str, Any],
) -> str:
    severity = attribution.get("severity", "info")
    if severity == "action":
        return "unstable"
    signal_profile = summarize_signal_profile(engine_result)
    if signal_profile["elevated_count"] > 0:
        return "unstable"
    if severity == "review":
        return "review"
    if data_quality.get("readiness") == "not_ready":
        return "review"
    if (
        signal_profile["review_count"] > 0
        or signal_profile["watch_count"] >= 1
        or signal_profile["corroboration_level"] in {"moderate", "strong"}
        or signal_profile["persistent_columns"] > 0
    ):
        return "review"
    return "nominal"


def summarize_signal_profile(engine_result: dict[str, Any]) -> dict[str, Any]:
    signals = engine_result.get("signals", [])
    watch_count = sum(1 for signal in signals if signal.get("level") == "watch")
    review_count = sum(1 for signal in signals if signal.get("level") == "review")
    elevated_count = sum(1 for signal in signals if signal.get("level") == "elevated")
    system_evidence = engine_result.get("system_evidence", {})
    persistence = engine_result.get("persistence_assessment", {})
    return {
        "watch_count": watch_count,
        "review_count": review_count,
        "elevated_count": elevated_count,
        "corroboration_level": system_evidence.get("corroboration_level", "limited"),
        "meaningful_categories": system_evidence.get("categories_showing_meaningful_change", 0),
        "persistent_columns": len(persistence.get("persistent_columns", [])),
    }


def relationship_evidence_from_engine(engine_result: dict[str, Any]) -> list[str]:
    evidence = []
    for item in engine_result.get("evidence", []):
        if item.get("type") == "relationship_change":
            columns = item.get("columns", [])
            if len(columns) >= 2:
                evidence.append(relationship_evidence_sentence(columns[0], columns[1]))
    return evidence[:4] or ["Environmental coupling evidence is limited in the current telemetry."]


def relationship_evidence_sentence(first_column: str, second_column: str) -> str:
    first = display_column(first_column)
    second = display_column(second_column)
    normalized = f"{first} {second}".lower()
    if "intervention window" in normalized:
        return "Intervention windows are shortening as environmental recovery slows."
    if "humidity" in normalized and ("airflow" in normalized or "air movement" in normalized):
        return "Airflow response consistency weakened during active climate periods."
    if "humidity" in normalized:
        return "Humidity recovery is becoming less stable after environmental transitions."
    if "airflow" in normalized or "air movement" in normalized:
        return "Air movement behavior is diverging from this room's recent operating pattern."
    return "Environmental coupling is less consistent than the room's recent baseline."


def display_column(column: str) -> str:
    normalized = str(column).lower().replace("_", " ")
    aliases = {
        "intervention window hours": "intervention window",
        "hvac runtime": "HVAC runtime",
        "co2": "CO2",
    }
    return aliases.get(normalized, normalized)


def structural_explanation_from_attribution(attribution: dict[str, Any], relationship_evidence: list[str]) -> list[str]:
    category = attribution.get("driver_category")
    if category == "humidity_control":
        return [
            "Humidity recovery appears slower than recent room behavior.",
            "Temperature recovery is decoupling from humidity stabilization.",
            "Environmental coupling is less consistent than the room's recent baseline.",
        ]
    if category == "hvac_instability":
        return [
            "Room temperature recovery appears less consistent than baseline.",
            "Temperature and humidity recovery are not moving together as expected.",
            "Environmental coupling is less consistent than the room's recent baseline.",
        ]
    if category == "airflow_restriction":
        return [
            "Airflow response consistency weakened during active climate periods.",
            "Room exchange behavior may be affecting environmental recovery.",
            "Air movement behavior is diverging from this room's recent operating pattern.",
        ]
    return relationship_evidence[:3] or ["Room recovery behavior is being compared against recent operating baseline."]


def checks_from_attribution(attribution: dict[str, Any], operator_report: dict[str, Any]) -> list[str]:
    category = attribution.get("driver_category")
    checks = {
        "humidity_control": [
            "Review dehumidification response",
            "Check room moisture load",
            "Compare recent recovery time to normal room behavior",
        ],
        "hvac_instability": [
            "Review temperature recovery",
            "Check cooling response stability",
            "Compare hot spots against recent room behavior",
        ],
        "airflow_restriction": [
            "Inspect airflow path",
            "Check fan response consistency",
            "Review room exchange behavior",
        ],
        "irrigation_timing": [
            "Review irrigation timing",
            "Check runoff or substrate response if available",
            "Compare recovery behavior after feed events",
        ],
        "sensor_network": [
            "Confirm room telemetry coverage",
            "Review missing or stale readings",
            "Compare connected signals against expected room sources",
        ],
    }.get(category)
    if checks:
        return checks
    report_checks = operator_report.get("recommended_operator_checks", [])
    return report_checks[:3] or ["Continue monitoring", "Review telemetry coverage", "Compare room behavior to recent baseline"]


def baseline_comparison_from_analysis(baseline_analysis: dict[str, Any]) -> str:
    drift = baseline_analysis.get("column_drift", [])
    review_columns = [item.get("column") for item in drift if item.get("drift_flag") == "review"]
    if review_columns:
        return f"{review_columns[0]} moved away from recent baseline."
    return "Current telemetry remains within available baseline comparison."


def observed_persistence_from_engine(engine_result: dict[str, Any]) -> str:
    persistent = engine_result.get("persistence_assessment", {}).get("persistent_columns", [])
    if persistent:
        return f"Observed across persistent readings for {persistent[0]}"
    return "Persistence evidence is limited in the current telemetry."


def confidence_number(attribution: dict[str, Any]) -> int:
    confidence = attribution.get("attribution_confidence")
    if confidence == "high":
        return 88
    if confidence == "medium":
        return 74
    return 58


def window_from_urgency(urgency: str) -> str:
    return {
        "unstable": "8 hours",
        "review": "2 days",
        "nominal": "3 weeks",
    }.get(urgency, "Monitoring")


def state_from_urgency(urgency: str) -> str:
    return {
        "unstable": "Needs action",
        "review": "Drift observed",
        "nominal": "Stable",
    }.get(urgency, "Monitoring")
