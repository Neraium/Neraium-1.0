from __future__ import annotations

import hashlib
import json
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
    admitted_state = _admitted_state_from_urgency(candidate.get("urgency"))
    reason_codes = _doctrine_reason_codes(candidate)
    passed = len(reason_codes) == 0
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

    should_persist_evp = passed and admitted_state in {"WATCH", "ALERT"}
    should_seal_internal = not passed

    evp_ref: dict[str, Any] | None = None
    if should_persist_evp or should_seal_internal:
        evp_ref = _seal_evp(
            timestamp_utc=now,
            gate_outcome=gate_outcome,
            admitted_state=admitted_state if passed else "NON_ADMITTED",
            doctrine_version=DOCTRINE_VERSION,
            doctrine_hash=doctrine_hash,
            engine_version=ENGINE_VERSION,
            input_payload_hash=input_payload_hash,
            candidate_output_hash=candidate_output_hash,
            decision_reason_codes=reason_codes if reason_codes else ["DOCTRINE_PASS"],
            operator_visible=should_persist_evp,
        )

    return {
        "gate_outcome": gate_outcome,
        "admitted_state": admitted_state if passed else "NONE",
        "operator_visible": passed,
        "transient_only": passed and admitted_state == "STABLE",
        "doctrine_version": DOCTRINE_VERSION,
        "doctrine_hash": doctrine_hash,
        "engine_version": ENGINE_VERSION,
        "decision_reason_codes": reason_codes if reason_codes else ["DOCTRINE_PASS"],
        "timestamp_utc": now,
        "evp_reference": evp_ref if passed and admitted_state in {"WATCH", "ALERT"} else None,
        "internal_evp_reference": evp_ref if not passed else None,
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


def _admitted_state_from_urgency(urgency: Any) -> str:
    normalized = str(urgency or "").lower()
    if normalized in {"unstable", "elevated", "critical", "alert"}:
        return "ALERT"
    if normalized in {"review", "watch"}:
        return "WATCH"
    return "STABLE"


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
