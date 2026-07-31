from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Any


def match_findings_to_events(
    findings: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    max_lead_hours: float = 168.0,
) -> dict[str, Any]:
    """Match each documented event to the earliest compatible preceding finding."""

    normalized_findings = sorted(
        (_normalize_finding(item) for item in findings),
        key=lambda item: item["detected_at"],
    )
    normalized_events = sorted(
        (_normalize_event(item) for item in events),
        key=lambda item: item["event_at"],
    )
    used: set[str] = set()
    matches: list[dict[str, Any]] = []
    unmatched_events: list[str] = []

    for event in normalized_events:
        earliest = event["event_at"] - timedelta(hours=max(0.0, max_lead_hours))
        candidates = [
            finding
            for finding in normalized_findings
            if finding["finding_id"] not in used
            and earliest <= finding["detected_at"] <= event["event_at"]
            and _contexts_compatible(finding, event)
        ]
        if not candidates:
            unmatched_events.append(event["event_id"])
            continue
        finding = candidates[0]
        used.add(finding["finding_id"])
        lead_hours = (event["event_at"] - finding["detected_at"]).total_seconds() / 3600
        matches.append(
            {
                "event_id": event["event_id"],
                "finding_id": finding["finding_id"],
                "event_at": event["event_at"].isoformat(),
                "detected_at": finding["detected_at"].isoformat(),
                "lead_time_hours": round(lead_hours, 3),
                "system_id": event.get("system_id") or finding.get("system_id"),
            }
        )

    unmatched_findings = [
        item["finding_id"] for item in normalized_findings if item["finding_id"] not in used
    ]
    lead_times = [item["lead_time_hours"] for item in matches]
    return {
        "events_total": len(normalized_events),
        "events_matched": len(matches),
        "events_detected_earlier": sum(value > 0 for value in lead_times),
        "event_match_rate": round(len(matches) / len(normalized_events), 4) if normalized_events else None,
        "median_lead_time_hours": round(median(lead_times), 3) if lead_times else None,
        "findings_total": len(normalized_findings),
        "unmatched_finding_count": len(unmatched_findings),
        "unmatched_finding_rate": round(len(unmatched_findings) / len(normalized_findings), 4)
        if normalized_findings
        else None,
        "matches": matches,
        "unmatched_event_ids": unmatched_events,
        "unmatched_finding_ids": unmatched_findings,
        "matching_policy": {
            "version": "chronological_event_match.v1",
            "max_lead_hours": max_lead_hours,
            "requires_preceding_detection": True,
            "requires_system_match_when_present": True,
            "requires_signal_overlap_when_both_present": True,
        },
    }


def assert_no_future_leakage(findings: list[dict[str, Any]]) -> None:
    for finding in findings:
        detected_at = _timestamp(finding.get("detected_at"), "finding.detected_at")
        source_window_end = _timestamp(
            finding.get("source_window_end") or finding.get("detected_at"),
            "finding.source_window_end",
        )
        if source_window_end > detected_at:
            raise ValueError(f"future_data_leakage:{finding.get('finding_id') or 'unknown'}")


def _contexts_compatible(finding: dict[str, Any], event: dict[str, Any]) -> bool:
    finding_system = str(finding.get("system_id") or "").strip().lower()
    event_system = str(event.get("system_id") or "").strip().lower()
    if finding_system and event_system and finding_system != event_system:
        return False
    finding_signals = set(finding.get("signals") or [])
    event_signals = set(event.get("signals") or [])
    return not finding_signals or not event_signals or bool(finding_signals & event_signals)


def _normalize_finding(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "finding_id": str(item.get("finding_id") or item.get("condition_id") or "").strip(),
        "detected_at": _timestamp(item.get("detected_at"), "finding.detected_at"),
        "signals": _signals(item.get("signals") or item.get("affected_signals")),
    }


def _normalize_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "event_id": str(item.get("event_id") or "").strip(),
        "event_at": _timestamp(item.get("event_at"), "event.event_at"),
        "signals": _signals(item.get("signals") or item.get("related_signals")),
    }


def _signals(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.replace(",", "|").split("|")
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip().lower() for item in value if str(item).strip()})


def _timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_timestamp:{field}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"timezone_required:{field}")
    return parsed
