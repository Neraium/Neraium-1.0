from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.services.health_relevance import (
    DEFAULT_THRESHOLDS,
    evaluate_evidence_state,
    freshness_status,
    summarize_manifest,
)
from app.services.health_relevance_methods import (
    BAYESIAN_METHOD_ID,
    INFORMATION_METHOD_ID,
    METHOD_REGISTRY,
    evaluate_health_relevance_method,
)


BENCHMARK_SCHEMA_VERSION = "health-relevance-benchmark.v1"
_CASE_IDS = tuple("ABCDEFGHIJKLMNOP")
_METHOD_IDS = (BAYESIAN_METHOD_ID, INFORMATION_METHOD_ID)
_DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "health_relevance_benchmark.json"
)
_CAUSAL_TERMS = (" caused ", " causes ", " proved ", " proves ", " because of ")


class BenchmarkFixtureError(ValueError):
    """Raised when the frozen synthetic benchmark contract is malformed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def load_benchmark_fixture(path: str | Path | None = None) -> dict[str, Any]:
    fixture_path = Path(path) if path is not None else _DEFAULT_FIXTURE
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise BenchmarkFixtureError("benchmark_schema_version_invalid")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or tuple(case.get("id") for case in cases) != _CASE_IDS:
        raise BenchmarkFixtureError("benchmark_cases_must_be_exactly_A_through_P")
    if set(METHOD_REGISTRY) != set(_METHOD_IDS) or len(METHOD_REGISTRY) != 2:
        raise BenchmarkFixtureError("benchmark_requires_exactly_two_approved_methods")
    return fixture


def _expand_group(
    case_id: str,
    variant_id: str,
    group: Mapping[str, Any],
    *,
    group_index: int,
) -> list[dict[str, Any]]:
    count = int(group.get("count", 0))
    if count < 0:
        raise BenchmarkFixtureError("benchmark_group_count_invalid")
    treatment = str(group.get("treatment") or "neutral")
    eligible = bool(group.get("eligible", treatment not in {"excluded", "duplicate_suppressed"}))
    information_cell = group.get("information_cell")
    authority_tiers = group.get("authority_tiers") or [group.get("authority_tier", "A")]
    families = group.get("outcome_families") or [
        group.get("outcome_family", "degradation_or_fault")
    ]
    incident_count = max(1, int(group.get("incident_count", count or 1)))
    episode_count = max(1, int(group.get("episode_count", 2)))
    context_complete_count = int(group.get("context_complete_count", count))
    rows: list[dict[str, Any]] = []
    for index in range(count):
        row_id = f"{case_id}-{variant_id}-g{group_index + 1}-r{index + 1}"
        cell = (
            str(information_cell)
            if information_cell is not None
            else {"positive": "a", "negative": "b"}.get(treatment)
        )
        outcome_class = None
        subject_state = "active_changed"
        if cell in {"a", "c"}:
            outcome_class = "validated_health_outcome"
        elif cell in {"b", "d"}:
            outcome_class = "explicit_comparison"
        if cell in {"c", "d"}:
            subject_state = "present_aligned"
        row_eligible = eligible
        exclusion_reason = group.get("exclusion_reason")
        rows.append(
            {
                "contribution_id": row_id,
                "eligible": row_eligible,
                "evidence_treatment": treatment,
                "treatment": treatment,
                "exclusion_reason": exclusion_reason,
                "reason_code": exclusion_reason or f"eligible_{treatment}",
                "information_cell": cell,
                "outcome_class": outcome_class,
                "authority_tier": str(authority_tiers[index % len(authority_tiers)]),
                "provenance_categories": [
                    "operator_confirmed_after_neraium_review"
                    if str(authority_tiers[index % len(authority_tiers)]) == "D"
                    else "independently_documented_outcome"
                ],
                "outcome_id": f"outcome-{row_id}",
                "outcome_revision_id": f"outcome-revision-{row_id}",
                "link_id": f"link-{row_id}",
                "link_revision_id": f"link-revision-{row_id}",
                "canonical_incident_key": (
                    None
                    if group.get("canonical_incident_missing")
                    else f"{case_id}-{variant_id}-incident-{(index % incident_count) + 1}"
                ),
                "outcome_family": str(families[index % len(families)]),
                "health_disposition": str(group.get("health_disposition") or "degraded"),
                "outcome_type": str(group.get("outcome_type") or "confirmed_degraded_condition"),
                "subject_state": subject_state,
                "temporal_role": str(group.get("temporal_role") or "outcome_period"),
                "context_episode_id": (
                    f"{case_id}-{variant_id}-episode-{(index % episode_count) + 1}"
                ),
                "context_complete": index < context_complete_count,
                "same_actor_validation": bool(group.get("same_actor_validation", False)),
                "window_start_at": f"2026-01-{(index % 20) + 1:02d}T00:00:00+00:00",
                "window_end_at": f"2026-01-{(index % 20) + 1:02d}T01:00:00+00:00",
                "occurred_start_at": f"2026-01-{(index % 20) + 1:02d}T00:00:00+00:00",
                "occurred_end_at": f"2026-01-{(index % 20) + 1:02d}T01:00:00+00:00",
                "behavioral_model_id": str(group.get("behavioral_model_id") or "model-synthetic"),
                "behavioral_model_version": str(group.get("behavioral_model_version") or "1"),
                "baseline_reference_id": str(
                    group.get("baseline_reference_id") or "reference-synthetic"
                ),
                "baseline_reference_version": str(group.get("baseline_reference_version") or "1"),
                "telemetry_schema_fingerprint": str(
                    group.get("telemetry_schema_fingerprint") or "telemetry-synthetic-v1"
                ),
                "system_configuration_fingerprint": str(
                    group.get("system_configuration_fingerprint") or "configuration-synthetic-v1"
                ),
            }
        )
    return rows


def _suppress_repeated_method_units(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Mirror persisted incident/cell suppression in synthetic frozen manifests."""

    seen_method_units: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        row["state_eligible"] = row.get("eligible") is True
        row["state_evidence_treatment"] = row.get("evidence_treatment")
        if row["state_eligible"]:
            method_unit = (
                str(row.get("canonical_incident_key") or row.get("outcome_id")),
                str(row.get("information_cell") or row.get("evidence_treatment")),
            )
            if method_unit in seen_method_units:
                row.update(
                    eligible=False,
                    evidence_treatment="duplicate_suppressed",
                    treatment="duplicate_suppressed",
                    exclusion_reason="same_incident_method_unit_suppressed",
                    reason_code="same_incident_method_unit_suppressed",
                )
            else:
                seen_method_units.add(method_unit)
        normalized.append(row)
    return normalized


def build_fixture_manifest(case_id: str, variant: Mapping[str, Any]) -> dict[str, Any]:
    """Expand one compact fixture variant into a deterministic frozen manifest."""

    variant_id = str(variant["id"])
    scope = {
        "scope_storage_id": str(variant.get("scope_storage_id") or f"scope-{case_id.lower()}"),
        "tenant_id": str(variant.get("tenant_id") or f"tenant-{case_id.lower()}"),
        "facility_id": str(variant.get("facility_id") or "facility-synthetic"),
        "system_id": str(variant.get("system_id") or "system-synthetic"),
    }
    state_key = {
        "subject_type": str(variant.get("subject_type") or "relationship"),
        "subject_id": str(variant.get("subject_id") or "relationship-r"),
        "subject_mapping_version": str(variant.get("subject_mapping_version") or "mapping-v1"),
        "context_fingerprint": str(variant.get("context_fingerprint") or "context-high-load"),
        "compatibility_epoch": str(variant.get("compatibility_epoch") or "epoch-v1"),
    }
    contributions = _suppress_repeated_method_units(
        [
            row
            for group_index, group in enumerate(variant.get("groups") or [])
            for row in _expand_group(case_id, variant_id, group, group_index=group_index)
        ]
    )
    manifest_core = {
        "schema_version": "health-relevance-frozen-manifest.v1",
        "scope": scope,
        "state_key": state_key,
        "required_context_dimensions": ["operating_mode"],
        "protocol_schedules": copy.deepcopy(variant.get("protocol_schedules") or {}),
        "contributions": contributions,
        "outcome_watermark": str(
            variant.get("outcome_watermark") or f"{case_id}-{variant_id}-outcomes"
        ),
        "link_watermark": str(variant.get("link_watermark") or f"{case_id}-{variant_id}-links"),
    }
    manifest_hash = _stable_hash(manifest_core)
    return {
        **manifest_core,
        "input_snapshot_id": f"benchmark-snapshot-{manifest_hash[:24]}",
        "input_manifest_hash": manifest_hash,
    }


def _assert_equal(assertions: list[dict[str, Any]], name: str, actual: Any, expected: Any) -> None:
    assertions.append(
        {"name": name, "passed": actual == expected, "actual": actual, "expected": expected}
    )


def _assert_expected(
    expected: Mapping[str, Any],
    summary: Mapping[str, Any],
    method_outputs: Mapping[str, Mapping[str, Any]],
    assertions: list[dict[str, Any]],
) -> None:
    for key, value in (expected.get("summary") or {}).items():
        _assert_equal(assertions, f"summary.{key}", summary.get(key), value)
    states = expected.get("states") or {}
    for method_id in _METHOD_IDS:
        expected_state = states.get(method_id, states.get("all"))
        if expected_state is not None:
            _assert_equal(
                assertions,
                f"{method_id}.evidence_state",
                method_outputs[method_id]["state"]["evidence_state"],
                expected_state,
            )
        for reason in expected.get("reasons_include") or []:
            assertions.append(
                {
                    "name": f"{method_id}.reason.{reason}",
                    "passed": reason in method_outputs[method_id]["state"]["state_reason_codes"],
                    "actual": method_outputs[method_id]["state"]["state_reason_codes"],
                    "expected": f"contains {reason}",
                }
            )
    bayesian_expected = expected.get("bayesian") or {}
    if "primary_directional" in bayesian_expected:
        actual = method_outputs[BAYESIAN_METHOD_ID]["result"]["components"]["primary_view"]["counts"][
            "directional"
        ]
        _assert_equal(
            assertions,
            "bayesian.primary_directional",
            actual,
            bayesian_expected["primary_directional"],
        )
    information_expected = expected.get("information") or {}
    if "table" in information_expected:
        actual = method_outputs[INFORMATION_METHOD_ID]["result"]["components"]["primary_view"][
            "contingency_table"
        ]
        _assert_equal(
            assertions,
            "information.contingency_table",
            actual,
            information_expected["table"],
        )
    if "max_adjusted" in information_expected:
        actual = method_outputs[INFORMATION_METHOD_ID]["result"]["components"]["primary_view"][
            "adjusted_normalized_information"
        ]
        assertions.append(
            {
                "name": "information.adjusted_normalized_information_maximum",
                "passed": actual <= float(information_expected["max_adjusted"]),
                "actual": actual,
                "expected": f"<= {information_expected['max_adjusted']}",
            }
        )


def _language_lint(samples: Sequence[str]) -> dict[str, Any]:
    violations = [
        {"sample": sample, "term": term.strip()}
        for sample in samples
        for term in _CAUSAL_TERMS
        if term in f" {sample.lower()} "
    ]
    return {"passed": not violations, "violations": violations}


def _simulate_idempotency(sequence: Sequence[Mapping[str, Any]]) -> list[str]:
    """Model the approved deterministic key/fingerprint contract without writes."""

    stored: dict[str, str] = {}
    results: list[str] = []
    for delivery in sequence:
        key = str(delivery.get("key") or "")
        fingerprint = str(delivery.get("fingerprint") or "")
        if not key or not fingerprint:
            raise BenchmarkFixtureError("replay_identity_incomplete")
        if key not in stored:
            stored[key] = fingerprint
            results.append("created")
        elif stored[key] == fingerprint:
            results.append("replay")
        else:
            results.append("conflict")
    return results


def _method_dimensions(cases: Mapping[str, Any], method_id: str) -> dict[str, dict[str, Any]]:
    def variant(case_id: str, variant_id: str) -> Mapping[str, Any]:
        return next(item for item in cases[case_id]["variants"] if item["id"] == variant_id)

    sparse = variant("B", "isolated")
    negative = variant("C", "repeated_false_positive")
    irrelevant = variant("G", "balanced_frequency")
    independent = variant("I", "independent")
    influenced = variant("I", "neraium_influenced")
    dimensions = {
        "sparse_data_behavior": sparse["methods"][method_id]["state"][
            "evidence_state"
        ]
        == "insufficient_outcome_evidence",
        "stability": all(
            output["methods"][method_id]["deterministic_repeat_equal"]
            for case in cases.values()
            for output in case["variants"]
        ),
        "contradictory_evidence": all(
            output["methods"][method_id]["state"]["evidence_state"] == "contradictory_evidence"
            for output in cases["E"]["variants"]
        ),
        "negative_evidence": negative["methods"][method_id]["state"][
            "evidence_state"
        ]
        == "not_supported_by_outcomes",
        "context_specificity": len(cases["D"]["variants"]) == 1
        and cases["D"]["variants"][0]["context_fingerprint"] == "context-high-load",
        "authority_weighting": (
            independent["methods"][method_id]["state"]["evidence_state"] == "supported_relevance"
            and influenced["methods"][method_id]["state"]["evidence_state"] != "supported_relevance"
        ),
        "false_positive_resistance": irrelevant["methods"][method_id]["state"][
            "evidence_state"
        ]
        != "supported_relevance",
        "version_stability": len(
            {item["input_manifest_hash"] for item in cases["M"]["variants"]}
        )
        == 3,
        "interpretability": all(
            bool(output["methods"][method_id]["result"].get("components"))
            and bool(output["methods"][method_id]["result"].get("uncertainty"))
            and len(output["methods"][method_id]["result"].get("contributions") or [])
            == len(output["manifest"]["contributions"])
            for case in cases.values()
            for output in case["variants"]
        ),
    }
    return {
        name: {"passed": passed, "score": 1 if passed else 0}
        for name, passed in dimensions.items()
    }


def run_benchmark(path: str | Path | None = None) -> dict[str, Any]:
    """Run Cases A-P twice without persistence, network, or product-state effects."""

    fixture = load_benchmark_fixture(path)
    method_config = fixture.get("method_config") or {}
    rendered_cases: dict[str, Any] = {}
    all_assertions: list[dict[str, Any]] = []
    for case in fixture["cases"]:
        case_id = str(case["id"])
        rendered_variants: list[dict[str, Any]] = []
        language = _language_lint(case.get("language_samples") or [])
        all_assertions.append(
            {
                "name": f"case_{case_id}.non_causal_language",
                "passed": language["passed"],
                "actual": language["violations"],
                "expected": [],
            }
        )
        for fixture_variant in case.get("variants") or []:
            manifest = build_fixture_manifest(case_id, fixture_variant)
            manifest_before = copy.deepcopy(manifest)
            summary = summarize_manifest(manifest)
            methods: dict[str, Any] = {}
            variant_assertions: list[dict[str, Any]] = []
            for method_id in _METHOD_IDS:
                config = method_config.get(method_id) or {}
                first = evaluate_health_relevance_method(method_id, manifest, config)
                second = evaluate_health_relevance_method(method_id, manifest, config)
                state = evaluate_evidence_state(
                    summary, method_id, first, thresholds=DEFAULT_THRESHOLDS
                )
                methods[method_id] = {
                    "state": state,
                    "result": first,
                    "deterministic_repeat_equal": first == second,
                    "shared_input_manifest_hash": first["input_manifest_hash"],
                    "shared_input_snapshot_id": first["input_snapshot_id"],
                }
                _assert_equal(
                    variant_assertions,
                    f"{method_id}.deterministic_repeat",
                    first,
                    second,
                )
                _assert_equal(
                    variant_assertions,
                    f"{method_id}.manifest_not_mutated",
                    manifest,
                    manifest_before,
                )
            _assert_equal(
                variant_assertions,
                "methods.share_frozen_manifest_hash",
                methods[BAYESIAN_METHOD_ID]["shared_input_manifest_hash"],
                methods[INFORMATION_METHOD_ID]["shared_input_manifest_hash"],
            )
            _assert_expected(
                fixture_variant.get("expected") or {},
                summary,
                methods,
                variant_assertions,
            )
            as_of = fixture_variant.get("as_of")
            freshness = None
            if as_of is not None:
                freshness = freshness_status(
                    fixture_variant.get("last_evidence_at"),
                    as_of=datetime.fromisoformat(str(as_of).replace("Z", "+00:00")).astimezone(UTC),
                )
                _assert_equal(
                    variant_assertions,
                    "freshness_status",
                    freshness,
                    (fixture_variant.get("expected") or {}).get("freshness"),
                )
            replay_results = None
            if fixture_variant.get("replay_sequence") is not None:
                replay_results = _simulate_idempotency(fixture_variant["replay_sequence"])
                _assert_equal(
                    variant_assertions,
                    "idempotency_replay_sequence",
                    replay_results,
                    (fixture_variant.get("expected") or {}).get("replay_results"),
                )
            all_assertions.extend(
                {**assertion, "case_id": case_id, "variant_id": fixture_variant["id"]}
                for assertion in variant_assertions
            )
            rendered_variants.append(
                {
                    "id": fixture_variant["id"],
                    "scope": manifest["scope"],
                    **manifest["state_key"],
                    "input_snapshot_id": manifest["input_snapshot_id"],
                    "input_manifest_hash": manifest["input_manifest_hash"],
                    "manifest": manifest,
                    "summary": summary,
                    "freshness_status": freshness,
                    "idempotency_replay_results": replay_results,
                    "methods": methods,
                    "assertions": variant_assertions,
                    "passed": all(item["passed"] for item in variant_assertions),
                }
            )
        rendered_cases[case_id] = {
            "title": case["title"],
            "dimensions": case.get("dimensions") or [],
            "language_lint": language,
            "variants": rendered_variants,
        }

    dimensions = {
        method_id: _method_dimensions(rendered_cases, method_id) for method_id in _METHOD_IDS
    }
    scores = {
        method_id: sum(item["score"] for item in method_dimensions.values())
        for method_id, method_dimensions in dimensions.items()
    }
    comparison = {
        "winner": "neither_clearly_dominates",
        "reason": (
            "Both methods satisfy the deterministic acceptance dimensions; Bayesian shrinkage "
            "makes sparse uncertainty especially direct, while outcome-conditioned information "
            "makes denominator discrimination and frequent-uninformative resistance especially direct."
        ),
        "scores": scores,
        "production_selection_made": False,
    }
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "fixture_id": fixture["fixture_id"],
        "synthetic_only": True,
        "internal_only": True,
        "production_effect": "none",
        "method_ids": list(_METHOD_IDS),
        "cases": rendered_cases,
        "evaluation_dimensions": dimensions,
        "comparison": comparison,
        "assertions": all_assertions,
        "passed": all(item["passed"] for item in all_assertions)
        and all(item["passed"] for method in dimensions.values() for item in method.values()),
    }


def normalized_report_json(report: Mapping[str, Any]) -> str:
    """Return byte-stable machine output for repeat-run validation."""

    return _canonical_json(report)


__all__ = [
    "BENCHMARK_SCHEMA_VERSION",
    "BenchmarkFixtureError",
    "build_fixture_manifest",
    "load_benchmark_fixture",
    "normalized_report_json",
    "run_benchmark",
]
