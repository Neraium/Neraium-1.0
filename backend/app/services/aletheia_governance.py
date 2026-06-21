from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings


DOCTRINE_VERSION = "aletheia-doctrine-v1"
ENGINE_VERSION = "neraium-engine-v1"
DOCTRINE_RULES = {
    "evidence_threshold": 2,
    "relationship_corroboration_threshold": 1,
    "minimum_confidence": 60,
}
EVP_LOG_PATH = get_settings().runtime_dir / "evidence" / "evp_records.jsonl"


def govern_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_state = _candidate_state_from_urgency(candidate.get("urgency"))
    reason_codes = _doctrine_reason_codes(candidate)
    passed = candidate_state in {"WATCH", "ALERT"} and len(reason_codes) == 0
    gate_outcome = "PASS" if passed else "NO_PASS"
    now = _now_iso()
    doctrine_hash = _sha256_json(
        {
            "version": DOCTRINE_VERSION,
            "rules": DOCTRINE_RULES,
        }
    )
    input_payload_hash = _sha256_json(candidate.get("source_metadata", {}))
    candidate_output_hash = _sha256_json(
        {
            "facility_state": candidate.get("facility_state"),
            "room_state": candidate.get("room_state"),
            "urgency": candidate.get("urgency"),
            "supporting_evidence": candidate.get("supporting_evidence", []),
            "relationship_evidence": candidate.get("relationship_evidence", []),
            "observed_persistence": candidate.get("observed_persistence"),
            "baseline_comparison": candidate.get("baseline_comparison"),
        }
    )

    persistence_count = _persistence_count(candidate)
    trajectory_direction = _trajectory_direction(candidate, candidate_state)
    recovery_window_status = _recovery_window_status(candidate_state, trajectory_direction, passed)
    why_summary = _why_summary(candidate)
    where_summary = _where_summary(candidate)
    trajectory_basis_hash = _sha256_json(
        {
            "trajectory_direction": trajectory_direction,
            "recovery_window_status": recovery_window_status,
            "observed_persistence": candidate.get("observed_persistence"),
            "review_window_hours": candidate.get("review_window_hours") or candidate.get("projected_time_to_failure_hours"),
        }
    )
    evidence_summary_hash = _sha256_json(
        {
            "supporting_evidence": candidate.get("supporting_evidence", []),
            "relationship_evidence": candidate.get("relationship_evidence", []),
            "baseline_comparison": candidate.get("baseline_comparison"),
        }
    )

    evp_ref: dict[str, Any] | None = None
    if passed:
        evp_ref = _seal_evp(
            timestamp_utc=now,
            gate_outcome=gate_outcome,
            admitted_state=candidate_state,
            doctrine_version=DOCTRINE_VERSION,
            doctrine_hash=doctrine_hash,
            engine_version=ENGINE_VERSION,
            input_payload_hash=input_payload_hash,
            candidate_output_hash=candidate_output_hash,
            decision_reason_codes=reason_codes if reason_codes else ["DOCTRINE_PASS"],
            persistence_count=persistence_count,
            trajectory_direction=trajectory_direction,
            recovery_window_status=recovery_window_status,
            why_summary=why_summary,
            where_summary=where_summary,
            trajectory_basis_hash=trajectory_basis_hash,
            evidence_summary_hash=evidence_summary_hash,
            operator_visible=True,
        )

    return {
        "gate_outcome": gate_outcome,
        "admitted_state": candidate_state if passed else "NONE",
        "operator_visible": passed,
        "transient_only": False,
        "doctrine_version": DOCTRINE_VERSION,
        "doctrine_hash": doctrine_hash,
        "engine_version": ENGINE_VERSION,
        "decision_reason_codes": reason_codes if reason_codes else (["DOCTRINE_PASS"] if passed else ["NO_ADMITTED_CONDITION"]),
        "timestamp_utc": now,
        "evp_reference": evp_ref if passed else None,
        "internal_evp_reference": None,
        "persistence_count": persistence_count if passed else None,
        "trajectory_direction": trajectory_direction if passed else None,
        "recovery_window_status": recovery_window_status if passed else None,
        "why_summary": why_summary if passed else None,
        "where_summary": where_summary if passed else None,
        "primary_evidence_family": _primary_evidence_family(candidate) if passed else None,
        "corroborating_evidence_families": _corroborating_evidence_families(candidate) if passed else [],
        "doctrine_rules_satisfied": _doctrine_rules_satisfied(passed) if passed else [],
        "affected_relationship_path": _affected_relationship_path(candidate) if passed else None,
        "operational_mapping": _operational_mapping(candidate) if passed else None,
        "first_admitted_window": _first_admitted_window(candidate) if passed else None,
        "elapsed_operational_duration": _elapsed_operational_duration(candidate, persistence_count) if passed else None,
        "drift_velocity": _drift_velocity(candidate, trajectory_direction) if passed else None,
        "transition_pressure": _transition_pressure(candidate_state, trajectory_direction) if passed else None,
        "relational_stability_trend": _relational_stability_trend(candidate, candidate_state) if passed else None,
        "structural_drift_trend": _structural_drift_trend(candidate, trajectory_direction) if passed else None,
        "intervention_sensitivity": _intervention_sensitivity(recovery_window_status) if passed else None,
        "trajectory_basis_hash": trajectory_basis_hash if passed else None,
        "evidence_summary_hash": evidence_summary_hash if passed else None,
    }


def _doctrine_reason_codes(candidate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    supporting_evidence = candidate.get("supporting_evidence", []) or []
    relationship_evidence = candidate.get("relationship_evidence", []) or []
    confidence = _confidence_from_candidate(candidate)
    persistence = str(candidate.get("observed_persistence", "")).lower()
    baseline = str(candidate.get("baseline_comparison", "")).lower()
    why = str(candidate.get("why_flagged", "")).lower()

    if len(supporting_evidence) < DOCTRINE_RULES["evidence_threshold"]:
        reasons.append("EVIDENCE_BELOW_THRESHOLD")
    if len(relationship_evidence) < DOCTRINE_RULES["relationship_corroboration_threshold"]:
        reasons.append("CORROBORATION_BELOW_THRESHOLD")
    if confidence < DOCTRINE_RULES["minimum_confidence"]:
        reasons.append("CONFIDENCE_BELOW_THRESHOLD")
    if "limited" in persistence or "insufficient" in persistence or "awaiting" in persistence:
        reasons.append("PERSISTENCE_NOT_CONFIRMED")
    if "not ready" in baseline or "limited" in baseline or "insufficient" in baseline:
        reasons.append("BASELINE_INSUFFICIENT")
    if "candidate" in why or "preliminary" in why or "weak" in why:
        reasons.append("SUPPRESSED_WEAK_SIGNAL")
    return sorted(set(reasons))


def _confidence_from_candidate(candidate: dict[str, Any]) -> int:
    if isinstance(candidate.get("rooms"), list) and candidate["rooms"]:
        room_conf = candidate["rooms"][0].get("confidence")
        if isinstance(room_conf, (int, float)):
            return int(room_conf)
    value = candidate.get("neraium_score")
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _candidate_state_from_urgency(urgency: Any) -> str:
    normalized = str(urgency or "").lower()
    if normalized in {"unstable", "elevated", "critical", "alert"}:
        return "ALERT"
    if normalized in {"review", "watch"}:
        return "WATCH"
    return "NONE"


def _persistence_count(candidate: dict[str, Any]) -> int:
    value = candidate.get("persistence_count")
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(candidate.get("observed_persistence", "") or "")
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return max(0, int(match.group(1)))
    return 1 if text.strip() else 0


def _trajectory_direction(candidate: dict[str, Any], candidate_state: str) -> str:
    raw = " ".join(
        str(candidate.get(key, "") or "")
        for key in (
            "trajectory_direction",
            "recovery_window_status",
            "observed_persistence",
            "why_flagged",
            "baseline_comparison",
        )
    ).lower()
    if "accelerat" in raw:
        return "accelerating"
    if "recover" in raw or "convergen" in raw:
        return "recovering"
    if "worsen" in raw or "narrow" in raw or candidate_state == "ALERT":
        return "worsening"
    return "stable"


def _recovery_window_status(candidate_state: str, trajectory_direction: str, passed: bool) -> str:
    if not passed:
        return "RECOVERY_WINDOW_UNCLEAR"
    if candidate_state == "ALERT":
        return "RECOVERY_WINDOW_CRITICAL"
    if trajectory_direction in {"worsening", "accelerating"}:
        return "RECOVERY_WINDOW_NARROWING"
    if trajectory_direction == "recovering":
        return "RECOVERY_WINDOW_OPEN"
    return "RECOVERY_WINDOW_OPEN"


def _why_summary(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("why_summary")
        or candidate.get("why_flagged")
        or candidate.get("baseline_comparison")
        or "Doctrine-admitted structural relationship evidence satisfied persistence and corroboration requirements."
    )


def _where_summary(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("where_summary")
        or candidate.get("facility_state")
        or candidate.get("room_state")
        or candidate.get("affected_subsystem")
        or "Facility relationship scope"
    )


def _primary_evidence_family(candidate: dict[str, Any]) -> str:
    relationship = candidate.get("relationship_evidence", []) or []
    supporting = candidate.get("supporting_evidence", []) or []
    if relationship:
        return "Structural relationship evidence"
    if supporting:
        return "Telemetry corroboration evidence"
    return "Doctrine evidence family"


def _corroborating_evidence_families(candidate: dict[str, Any]) -> list[str]:
    families: list[str] = []
    if candidate.get("relationship_evidence"):
        families.append("Relationship corroboration")
    if candidate.get("supporting_evidence"):
        families.append("Telemetry window corroboration")
    if candidate.get("baseline_comparison"):
        families.append("Baseline comparison")
    if candidate.get("observed_persistence"):
        families.append("Persistence confirmation")
    return families


def _doctrine_rules_satisfied(passed: bool) -> list[str]:
    if not passed:
        return []
    return [
        "Evidence threshold satisfied",
        "Persistence requirement satisfied",
        "Relationship corroboration satisfied",
        "Baseline sufficiency satisfied",
        "Suppression rules cleared",
    ]


def _affected_relationship_path(candidate: dict[str, Any]) -> str:
    evidence = candidate.get("relationship_evidence", []) or []
    if evidence:
        return str(evidence[0])
    return str(candidate.get("affected_relationship_path") or "Primary subsystem relationship path")


def _operational_mapping(candidate: dict[str, Any]) -> str:
    return str(candidate.get("operational_mapping") or candidate.get("affected_subsystem") or "Operational loop under admitted finding")


def _first_admitted_window(candidate: dict[str, Any]) -> str:
    metadata = candidate.get("source_metadata", {}) or {}
    return str(candidate.get("first_admitted_window") or metadata.get("first_window") or metadata.get("window_start") or "First Gate-admitted window")


def _elapsed_operational_duration(candidate: dict[str, Any], persistence_count: int) -> str:
    return str(candidate.get("elapsed_operational_duration") or f"{persistence_count} corroborated window{'s' if persistence_count != 1 else ''}")


def _drift_velocity(candidate: dict[str, Any], trajectory_direction: str) -> str:
    return str(candidate.get("drift_velocity") or f"{trajectory_direction.title()} structural drift")


def _transition_pressure(candidate_state: str, trajectory_direction: str) -> str:
    if candidate_state == "ALERT":
        return "High"
    if trajectory_direction in {"worsening", "accelerating"}:
        return "Elevated"
    return "Controlled"


def _relational_stability_trend(candidate: dict[str, Any], candidate_state: str) -> str:
    return str(candidate.get("relational_stability_trend") or ("Degrading" if candidate_state == "ALERT" else "Under admitted watch"))


def _structural_drift_trend(candidate: dict[str, Any], trajectory_direction: str) -> str:
    return str(candidate.get("structural_drift_trend") or trajectory_direction.title())


def _intervention_sensitivity(recovery_window_status: str) -> str:
    if recovery_window_status == "RECOVERY_WINDOW_CRITICAL":
        return "Urgent intervention sensitivity"
    if recovery_window_status == "RECOVERY_WINDOW_NARROWING":
        return "Elevated intervention sensitivity"
    if recovery_window_status == "RECOVERY_WINDOW_OPEN":
        return "Recovery remains responsive to intervention"
    return "Recovery sensitivity unclear"


def _seal_evp(
    *,
    timestamp_utc: str,
    gate_outcome: str,
    admitted_state: str,
    doctrine_version: str,
    doctrine_hash: str,
    engine_version: str,
    input_payload_hash: str,
    candidate_output_hash: str,
    decision_reason_codes: list[str],
    persistence_count: int,
    trajectory_direction: str,
    recovery_window_status: str,
    why_summary: str,
    where_summary: str,
    trajectory_basis_hash: str,
    evidence_summary_hash: str,
    operator_visible: bool,
) -> dict[str, Any]:
    previous_hash = _latest_evp_hash()
    evp_id = f"evp-{uuid.uuid4().hex[:16]}"
    payload = {
        "evp_id": evp_id,
        "timestamp_utc": timestamp_utc,
        "gate_outcome": gate_outcome,
        "admitted_state": admitted_state,
        "doctrine_version": doctrine_version,
        "doctrine_hash": doctrine_hash,
        "engine_version": engine_version,
        "input_payload_hash": input_payload_hash,
        "candidate_output_hash": candidate_output_hash,
        "decision_reason_codes": decision_reason_codes,
        "persistence_count": persistence_count,
        "trajectory_direction": trajectory_direction,
        "recovery_window_status": recovery_window_status,
        "why_summary": why_summary,
        "where_summary": where_summary,
        "trajectory_basis_hash": trajectory_basis_hash,
        "evidence_summary_hash": evidence_summary_hash,
        "previous_evp_hash": previous_hash,
        "operator_visible": operator_visible,
    }
    evp_hash = _sha256_json(payload)
    record = {
        **payload,
        "evp_hash": evp_hash,
        "signature": "SIGNATURE_PLACEHOLDER",
    }
    _append_evp_record(record)
    return {"evp_id": evp_id, "evp_hash": evp_hash, "timestamp_utc": timestamp_utc}


def _append_evp_record(record: dict[str, Any]) -> None:
    EVP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVP_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def _latest_evp_hash() -> str:
    if not EVP_LOG_PATH.exists():
        return ""
    try:
        last_line = ""
        with EVP_LOG_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last_line = line
        if not last_line:
            return ""
        parsed = json.loads(last_line)
        return str(parsed.get("evp_hash", ""))
    except Exception:
        return ""


def list_evp_records(*, limit: int = 100, operator_visible: bool | None = None) -> list[dict[str, Any]]:
    if not EVP_LOG_PATH.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        with EVP_LOG_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                item = json.loads(text)
                if operator_visible is not None and bool(item.get("operator_visible")) is not operator_visible:
                    continue
                records.append(item)
    except Exception:
        return []
    records.reverse()
    return records[: max(1, min(limit, 1000))]


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
