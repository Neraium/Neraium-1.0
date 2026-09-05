"""Adapt finding-owned evidence; the standalone package alone integrates rates."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from neraium_consequence import RESOURCE_PROFILES, quantify_consequence
from neraium_consequence.provenance import snapshot
from neraium_consequence.validation import timestamp_seconds


def unavailable_consequence() -> dict[str, Any]:
    return {
        "status": "not_quantifiable",
        "statement": "Consequence not quantifiable from available evidence.",
    }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    return (
        [item for item in value if isinstance(item, str)]
        if isinstance(value, list)
        else []
    )


def _relationship_ids(finding: dict[str, Any]) -> list[str]:
    ids = _strings(finding.get("source_relationship_ids"))
    for key in ("supporting_relationships", "contributing_relationships"):
        for item in finding.get(key) or []:
            if isinstance(item, dict):
                value = item.get("relationship_id") or item.get("id")
                if isinstance(value, str):
                    ids.append(value)
            elif isinstance(item, str):
                ids.append(item)
    return ids


def _window(finding: dict[str, Any]) -> tuple[float, float] | None:
    ranges = finding.get("source_time_ranges") or []
    if not isinstance(ranges, list):
        return None
    if len(ranges) == 1 and isinstance(ranges[0], dict):
        start, end = ranges[0].get("current_start"), ranges[0].get("current_end")
    else:
        start, end = finding.get("first_detected_at"), finding.get("last_observed_at")
        if len(ranges) > 1:
            return None  # Never turn disjoint windows into a bounding union.
    try:
        left, right = timestamp_seconds(start), timestamp_seconds(end)
        return (left, right) if right > left else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _profile(metadata: dict[str, Any]) -> str | None:
    explicit = metadata.get("consequence_profile_key")
    unit = (
        metadata.get("canonical_unit")
        or metadata.get("engineering_units")
        or metadata.get("unit")
    )
    if isinstance(explicit, str) and explicit in RESOURCE_PROFILES:
        return explicit if unit == RESOURCE_PROFILES[explicit].rate_unit else None
    # Exact canonical identity; no guesses from raw tag names or dimension alone.
    if (
        metadata.get("canonical_signal_name") == "electrical.active_power"
        and unit == "kW"
    ):
        return "electricity_kw"
    resource = metadata.get("resource_type")
    for key, profile in RESOURCE_PROFILES.items():
        if resource == profile.resource_type and unit == profile.rate_unit:
            return key
    return None


def build_measurable_consequence(
    finding: dict[str, Any],
    *,
    expected_behavior: dict[str, Any] | None = None,
    signal_catalog: dict[str, Any] | None = None,
    analysis_run_id: str | None = None,
) -> dict[str, Any]:
    relationship_ids = _relationship_ids(finding)
    finding_id = (
        finding.get("condition_id") or finding.get("id") or finding.get("finding_id")
    )
    kwargs = dict(
        source_relationship_ids=relationship_ids,
        source_tag_ids=_strings(
            finding.get("source_tag_ids") or finding.get("source_tags")
        ),
        finding_id=finding_id if isinstance(finding_id, str) else None,
        analysis_run_id=analysis_run_id,
        evidence_id=finding.get("evidence_id")
        if isinstance(finding.get("evidence_id"), str)
        else None,
        support_level=finding.get("support_level")
        if isinstance(finding.get("support_level"), str)
        else None,
    )

    def refuse(reason: str) -> dict[str, Any]:
        result = dict(quantify_consequence([], profile_key="unmapped", **kwargs))
        result.update(reason=reason, limitations=[reason])
        return result

    persistence = _mapping(finding.get("persistence"))
    if not (
        persistence.get("persistent") is True
        or str(persistence.get("status", "")).lower() == "persistent"
    ):
        return refuse(
            "Persistent relationship change is not established for this finding."
        )
    mode = _mapping(finding.get("operating_mode"))
    comparable = _mapping(finding.get("comparable_operation"))
    confidence_context = _mapping(
        _mapping(finding.get("finding_confidence_v1")).get("operating_context")
    )
    context_status = (
        mode.get("match")
        or comparable.get("status")
        or confidence_context.get("status")
    )
    if str(context_status or "").lower() not in {"strong", "supported", "comparable"}:
        return refuse(
            "Comparable operating context is not established for this finding."
        )
    window = _window(finding)
    if window is None:
        return refuse("An exact finding-owned calculation window is unavailable.")
    catalog = signal_catalog or {}
    candidates = []
    values = (expected_behavior or {}).get("expected_values")
    for expected in values if isinstance(values, list) else []:
        if not isinstance(expected, dict) or expected.get("status") != "complete":
            continue
        source_ids = _strings(expected.get("source_relationships"))
        if (
            not source_ids
            or source_ids != expected.get("source_relationships")
            or not set(source_ids).issubset(relationship_ids)
        ):
            continue
        target = expected.get("target_signal")
        if not isinstance(target, str):
            continue
        profile_key = _profile(_mapping(catalog.get(target)))
        if profile_key:
            candidates.append((expected, profile_key, source_ids))
    if len(candidates) != 1:
        return refuse(
            "Exactly one mapped, finding-owned resource rate series is required."
        )
    expected, profile_key, source_ids = candidates[0]
    observations = deepcopy(expected.get("observations") or [])
    if not isinstance(observations, list):
        return refuse("Aligned observed-versus-expected observations are unavailable.")
    for row in observations:
        if not isinstance(row, dict):
            continue
        try:
            timestamp = timestamp_seconds(row.get("timestamp"))
            if not window[0] <= timestamp <= window[1]:
                row["valid"] = False
        except (TypeError, ValueError, OverflowError, OSError):
            pass  # The package refuses unplaceable timestamps.
    kwargs["source_relationship_ids"] = source_ids
    kwargs["source_tag_ids"] = [
        expected["target_signal"],
        *_strings(expected.get("predictor_signals")),
    ]
    result = dict(
        quantify_consequence(
            observations,
            profile_key=profile_key,
            max_gap_seconds=expected.get("max_gap_seconds"),
            **kwargs,
        )
    )
    result["provenance"]["expected_behavior"] = snapshot(expected)
    result["provenance"]["signal_metadata"] = snapshot(
        catalog.get(expected["target_signal"])
    )
    result["provenance"]["finding_window"] = list(window)
    result["provenance"]["operating_context"] = snapshot(
        {
            "operating_mode": mode,
            "comparable_operation": comparable,
            "confidence_context": confidence_context,
        }
    )
    result["limitations"].extend(_strings(expected.get("limitations")))
    return result


def attach_measurable_consequences(
    analysis: dict[str, Any],
    *,
    source: dict[str, Any],
    original_findings: list[dict[str, Any]],
) -> None:
    originals = {
        str(item.get("condition_id") or item.get("id") or item.get("finding_id")): item
        for item in original_findings
        if isinstance(item, dict)
    }
    expected = _mapping(_mapping(source.get("sii_result")).get("expected_behavior"))
    catalog = _mapping(source.get("telemetry_signal_catalog"))
    run_id = (
        source.get("run_id")
        or source.get("analysis_run_id")
        or analysis.get("analysis_id")
    )
    for field in ("conditions", "insights"):
        for finding in analysis.get(field, []):
            identity = str(finding.get("condition_id") or finding.get("id"))
            finding["measurable_consequence"] = build_measurable_consequence(
                originals.get(identity, finding),
                expected_behavior=expected,
                signal_catalog=catalog,
                analysis_run_id=run_id if isinstance(run_id, str) else None,
            )


def recorded_measurable_consequence(
    finding: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    identity = (
        finding.get("condition_id") or finding.get("id") or finding.get("finding_id")
    )
    analysis = _mapping(result.get("analysis_result"))
    for field in ("conditions", "insights"):
        for item in analysis.get(field, []):
            if not isinstance(item, dict):
                continue
            candidate = (
                item.get("condition_id") or item.get("id") or item.get("finding_id")
            )
            if (
                identity
                and candidate == identity
                and isinstance(item.get("measurable_consequence"), dict)
            ):
                return deepcopy(item["measurable_consequence"])
    value = finding.get("measurable_consequence")
    return deepcopy(value) if isinstance(value, dict) else unavailable_consequence()
