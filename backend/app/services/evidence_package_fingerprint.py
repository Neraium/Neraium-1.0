from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "evidence-package-fingerprint-v1"
ALGORITHM_VERSION = "evidence-package-canonical-sha256-v1"
MATCH_SCHEMA_VERSION = "evidence-package-exact-match-v1"
ROUNDING_PLACES = 8


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FingerprintStatus(str, Enum):
    available = "available"
    unavailable = "unavailable"


class ExactMatchStatus(str, Enum):
    not_evaluated = "not_evaluated"
    insufficient_history = "insufficient_history"
    unavailable = "unavailable"
    no_exact_match = "no_exact_match"
    exact_match = "exact_match"


class FingerprintScope(StrictModel):
    organization_id: str
    workspace_id: str
    system_id: str | None = None


class FingerprintProvenance(StrictModel):
    source_schema_version: str
    package_revision: int
    source: str
    calculation_versions: list[str]


class EvidencePackageFingerprint(StrictModel):
    schema_version: str = SCHEMA_VERSION
    algorithm_version: str = ALGORITHM_VERSION
    status: FingerprintStatus
    package_id: str
    fingerprint_id: str | None = None
    canonical_digest: str | None = None
    scope: FingerprintScope
    features: dict[str, Any]
    available_dimensions: list[str]
    unavailable_dimensions: list[str]
    evidence_refs: list[str]
    limitations: list[str]
    provenance: FingerprintProvenance


class ExactMatchObservation(StrictModel):
    observation_id: str
    evaluated_package_id: str
    evaluated_fingerprint_id: str
    prior_package_id: str
    prior_fingerprint_id: str
    canonical_digest: str
    algorithm_version: str
    eligibility_basis: str
    scope_basis: str
    temporal_basis: str
    evidence_refs: list[str]
    limitations: list[str]


class ExactMatchResult(StrictModel):
    schema_version: str = MATCH_SCHEMA_VERSION
    status: ExactMatchStatus
    evaluated_package_id: str
    evaluated_fingerprint_id: str | None = None
    algorithm_version: str = ALGORITHM_VERSION
    matches: list[ExactMatchObservation] = Field(default_factory=list)
    eligible_history_count: int = 0
    limitations: list[str] = Field(default_factory=list)


def _number(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("fingerprint_numeric_value_invalid")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("fingerprint_numeric_value_invalid") from exc
    if not math.isfinite(number):
        raise ValueError("fingerprint_numeric_value_not_finite")
    quantum = Decimal(1).scaleb(-ROUNDING_PLACES)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_EVEN)
    return format(rounded, "f").rstrip("0").rstrip(".") or "0"


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build_fingerprint(package: dict[str, Any], *, algorithm_version: str = ALGORITHM_VERSION) -> EvidencePackageFingerprint:
    relationship = package.get("primary_relationship") if isinstance(package.get("primary_relationship"), dict) else {}
    scope = FingerprintScope(
        organization_id=str(package.get("organization_id") or ""),
        workspace_id=str(package.get("portfolio_id") or ""),
        system_id=str(package.get("system_id") or "") or None,
    )
    evidence_ids = {str(item.get("id")) for item in package.get("supporting_evidence", []) if isinstance(item, dict)}
    required_refs = {
        "baseline_strength": "ev-baseline-strength",
        "comparison_strength": "ev-comparison-strength",
        "absolute_change": "ev-absolute-change",
    }
    required: dict[str, Any] = {
        "organization_id": scope.organization_id,
        "workspace_id": scope.workspace_id,
        "system_id": scope.system_id,
        "condition_type": package.get("condition_type"),
        "left_signal_id": relationship.get("left_variable"),
        "right_signal_id": relationship.get("right_variable"),
        "relationship_type": relationship.get("relationship_type"),
        "baseline_strength": relationship.get("baseline_strength"),
        "comparison_strength": relationship.get("comparison_strength"),
        "signed_change": relationship.get("signed_change"),
        "absolute_change": relationship.get("absolute_change"),
    }
    missing = sorted(key for key, value in required.items() if value is None or value == "")
    missing.extend(sorted(key for key, ref in required_refs.items() if ref not in evidence_ids and key not in missing))
    numeric: dict[str, str] = {}
    try:
        for key in ("baseline_strength", "comparison_strength", "signed_change", "absolute_change"):
            if key not in missing:
                numeric[key] = _number(required[key])
    except ValueError:
        raise

    relationship_type = str(required.get("relationship_type") or "").lower()
    symmetric = relationship_type in {"correlation", "pearson_correlation", "spearman_correlation"}
    signals = [str(required.get("left_signal_id") or ""), str(required.get("right_signal_id") or "")]
    if symmetric:
        signals.sort()

    context_features: list[dict[str, Any]] = []
    context = package.get("operating_context") if isinstance(package.get("operating_context"), dict) else {}
    metrics: list[dict[str, Any]] = []
    if isinstance(context.get("load_context"), dict):
        metrics.append(context["load_context"])
    for group in ("equipment_configuration", "control_context", "environmental_context"):
        metrics.extend(item for item in context.get(group, []) if isinstance(item, dict))
    for metric in metrics:
        values = {}
        for key in ("baseline_mean", "comparison_mean"):
            if metric.get(key) is not None:
                values[key] = _number(metric[key])
        if values:
            context_features.append({"canonical_role": str(metric.get("canonical_role") or ""), **values})
    context_features.sort(key=lambda item: (item["canonical_role"], canonical_bytes(item)))

    persistence = relationship.get("persistence_score")
    optional_unavailable = []
    if persistence is None:
        optional_unavailable.append("quantified_persistence")
    if not context_features:
        optional_unavailable.append("operating_context")
    selected_ref_ids = set(required_refs.values())
    if persistence is not None:
        selected_ref_ids.add("ev-persistence")
    if context_features:
        selected_ref_ids.update(item for item in evidence_ids if item.startswith("ev-context-"))
    selected_evidence = [
        item for item in package.get("supporting_evidence", [])
        if isinstance(item, dict) and item.get("id") in selected_ref_ids
    ]
    calculation_versions = sorted({str(item.get("calculation_version")) for item in selected_evidence if item.get("calculation_version")})
    features: dict[str, Any] = {}
    refs = sorted(item for item in evidence_ids if item in selected_ref_ids)
    if not missing:
        features = {
            "scope": scope.model_dump(mode="json"),
            "condition_type": str(required["condition_type"]),
            "relationship": {
                "signal_ids": signals,
                "relationship_type": str(required["relationship_type"]),
                "directionality": "symmetric" if symmetric else "directed",
                **numeric,
                **({"persistence": _number(persistence)} if persistence is not None else {}),
            },
            "operating_context": context_features,
            "calculation_versions": calculation_versions,
            "evidence": sorted(
                ({"id": item["id"], "quality_status": item.get("quality_status"), "calculation_version": item.get("calculation_version")} for item in selected_evidence),
                key=lambda item: item["id"],
            ),
        }
    digest = None
    fingerprint_id = None
    if not missing:
        digest = hashlib.sha256(canonical_bytes({"algorithm_version": algorithm_version, "features": features})).hexdigest()
        fingerprint_id = f"sha256:{digest}"
    unavailable = sorted(set(missing + optional_unavailable))
    available = sorted(set(required) - set(missing))
    if persistence is not None:
        available.append("quantified_persistence")
    if context_features:
        available.append("operating_context")
    return EvidencePackageFingerprint(
        algorithm_version=algorithm_version,
        status=FingerprintStatus.available if digest else FingerprintStatus.unavailable,
        package_id=str(package.get("id") or ""), fingerprint_id=fingerprint_id, canonical_digest=digest,
        scope=scope, features=features, available_dimensions=sorted(available), unavailable_dimensions=unavailable,
        evidence_refs=refs, limitations=[f"Unavailable dimension: {item}." for item in unavailable],
        provenance=FingerprintProvenance(source_schema_version=str(package.get("schema_version") or ""), package_revision=int(package.get("revision") or 0), source="completed_analysis_persistence", calculation_versions=calculation_versions),
    )


def parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def observation_id(evaluated_package_id: str, prior_package_id: str, algorithm_version: str, basis: str) -> str:
    payload = {"evaluated_package_id": evaluated_package_id, "prior_package_id": prior_package_id, "algorithm_version": algorithm_version, "basis": basis}
    return f"sha256:{hashlib.sha256(canonical_bytes(payload)).hexdigest()}"
