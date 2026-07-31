from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


USEFUL_FEEDBACK = {"confirmed_issue", "useful_warning", "maintenance_event"}
IRRELEVANT_FEEDBACK = {"false_positive", "nothing_meaningful", "ignore"}
OPEN_STATES = {"open", "acknowledged", "investigating", "monitoring"}


def build_pilot_metrics(evidence_runs: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = 0
    suppressed = 0
    surfaced = 0
    useful = 0
    irrelevant = 0
    reviewed = 0
    accepted_rows = 0
    received_rows = 0
    timestamps: list[datetime] = []
    sites: set[str] = set()
    state_counts: Counter[str] = Counter()

    for run in evidence_runs:
        authority = _mode_authority(run)
        gates = authority.get("gates") if isinstance(authority.get("gates"), dict) else {}
        if gates.get("candidate_present") is True:
            candidates += 1
        if authority.get("applied") is True:
            suppressed += 1
        if _is_surfaced_finding(run):
            surfaced += 1

        category = _latest_feedback_category(run)
        if category:
            reviewed += 1
            useful += int(category in USEFUL_FEEDBACK)
            irrelevant += int(category in IRRELEVANT_FEEDBACK)

        status = _latest_finding_state(run)
        state_counts[status] += 1
        accepted_rows += _integer(run.get("rows_accepted"))
        received_rows += _integer(run.get("rows_received"))
        parsed = _parse_timestamp(run.get("completed_at") or run.get("created_at"))
        if parsed is not None:
            timestamps.append(parsed)
        sites.add(str(run.get("site_id") or run.get("adaptive_site_key") or "unassigned"))

    elapsed_weeks = _elapsed_weeks(timestamps)
    site_weeks = max(1.0, elapsed_weeks * max(1, len(sites)))
    return {
        "window_run_count": len(evidence_runs),
        "candidate_findings": candidates,
        "suppressed_candidates": suppressed,
        "surfaced_findings": surfaced,
        "reviewed_findings": reviewed,
        "useful_findings": useful,
        "irrelevant_findings": irrelevant,
        "irrelevant_finding_rate": round(irrelevant / reviewed, 4) if reviewed else None,
        "finding_state_counts": dict(state_counts),
        "open_findings": sum(state_counts[state] for state in OPEN_STATES),
        "data_coverage_rate": round(accepted_rows / received_rows, 4) if received_rows else None,
        "findings_per_site_week": round(surfaced / site_weeks, 4),
        "site_count": len(sites),
        "window_weeks": round(elapsed_weeks, 4),
    }


def _mode_authority(run: dict[str, Any]) -> dict[str, Any]:
    phase_2 = run.get("phase_2_supporting_evidence")
    if not isinstance(phase_2, dict):
        return {}
    trace = phase_2.get("processing_trace")
    if not isinstance(trace, dict):
        return {}
    authority = trace.get("mode_aware_authority")
    return authority if isinstance(authority, dict) else {}


def _is_surfaced_finding(run: dict[str, Any]) -> bool:
    if str(run.get("observation_status") or "").lower() in {"withheld", "suppressed"}:
        return False
    return bool(
        run.get("condition_id")
        or run.get("finding_title")
        or str(run.get("observation_type") or "") == "corroborated_condition"
        or _integer((run.get("drift_metrics") or {}).get("active_observations")) > 0
    )


def _latest_feedback_category(run: dict[str, Any]) -> str:
    direct = str(run.get("latest_feedback_category") or "").strip().lower()
    if direct:
        return direct
    history = run.get("operator_feedback_history")
    if isinstance(history, list) and history and isinstance(history[0], dict):
        return str(history[0].get("category") or "").strip().lower()
    return ""


def _latest_finding_state(run: dict[str, Any]) -> str:
    history = run.get("finding_status_history")
    if isinstance(history, list) and history and isinstance(history[0], dict):
        state = str(history[0].get("state") or "").strip().lower()
        if state:
            return state
    return str(run.get("observation_status") or "open").strip().lower() or "open"


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _elapsed_weeks(values: list[datetime]) -> float:
    if len(values) < 2:
        return 1.0
    return max(1.0, (max(values) - min(values)).total_seconds() / (7 * 86400))


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
