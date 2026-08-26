"""Durable, source-neutral lineage for telemetry analysis windows.

The complete lineage remains a persistence contract.  Result and evidence
projections expose only a bounded sample plus a digest, so a large analysis
window cannot make API payloads grow without limit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Any


LINEAGE_CONTRACT_VERSION = "telemetry-observation-lineage.v1"
LINEAGE_SUMMARY_VERSION = "telemetry-window-lineage-summary.v1"
DURABLE_RESULT_LINEAGE_VERSION = "telemetry-analysis-result-lineage.v1"
DEFAULT_LINEAGE_SAMPLE_LIMIT = 8
MAX_LINEAGE_SAMPLE_LIMIT = 32
MAX_LINEAGE_RECORDS = 5_000
MAX_RESULT_REFERENCE_IDS = 256
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LINEAGE_PUBLIC_FIELDS = frozenset(
    {
        "asset_id",
        "canonical_signal_id",
        "canonical_signal_name",
        "canonical_unit",
        "connection_id",
        "contract_version",
        "conversion_id",
        "conversion_version",
        "external_signal_id",
        "external_tag_id",
        "ingestion_run_id",
        "mapping_authority_digest",
        "mapping_id",
        "mapping_revision",
        "observation_id",
        "observed_at_utc",
        "original_unit",
        "source_offset",
        "source_record_digest",
        "source_timestamp_raw",
        "source_timezone",
        "system_id",
        "timestamp_normalization_version",
    }
)


def _required_text(value: Any, code: str, *, maximum: int = 2_048) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(code)
    return normalized


def _optional_text(value: Any, *, maximum: int = 2_048) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise ValueError("telemetry_lineage_text_too_long")
    return normalized


def _aware_utc(value: Any, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(code)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ObservationLineage:
    """One immutable observation-to-source lineage record.

    The original value is intentionally excluded.  Canonical values belong in
    the analysis window; lineage retains identities, units, timestamps,
    conversion provenance and the source-record digest needed for audit.
    """

    observation_id: str
    connection_id: str
    ingestion_run_id: str
    external_signal_id: str
    mapping_id: str
    mapping_revision: int
    canonical_signal_id: str
    canonical_signal_name: str
    system_id: str
    asset_id: str | None
    external_tag_id: str
    source_timestamp_raw: str
    source_timezone: str
    source_offset: str | None
    timestamp_normalization_version: str
    observed_at_utc: datetime
    original_unit: str | None
    canonical_unit: str
    conversion_id: str
    conversion_version: str
    source_record_digest: str
    mapping_authority_digest: str
    contract_version: str = LINEAGE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != LINEAGE_CONTRACT_VERSION:
            raise ValueError("telemetry_lineage_contract_version_invalid")
        for field_name in (
            "observation_id",
            "connection_id",
            "ingestion_run_id",
            "external_signal_id",
            "mapping_id",
            "canonical_signal_id",
            "canonical_signal_name",
            "system_id",
            "external_tag_id",
            "source_timestamp_raw",
            "source_timezone",
            "timestamp_normalization_version",
            "canonical_unit",
            "conversion_id",
            "conversion_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(
                    getattr(self, field_name), f"telemetry_lineage_{field_name}_invalid"
                ),
            )
        object.__setattr__(self, "asset_id", _optional_text(self.asset_id))
        object.__setattr__(self, "source_offset", _optional_text(self.source_offset))
        object.__setattr__(self, "original_unit", _optional_text(self.original_unit))
        if int(self.mapping_revision) < 1:
            raise ValueError("telemetry_lineage_mapping_revision_invalid")
        object.__setattr__(self, "mapping_revision", int(self.mapping_revision))
        object.__setattr__(
            self,
            "observed_at_utc",
            _aware_utc(self.observed_at_utc, "telemetry_lineage_timestamp_invalid"),
        )
        for field_name in ("source_record_digest", "mapping_authority_digest"):
            digest = str(getattr(self, field_name) or "").strip().lower()
            if not _SHA256.fullmatch(digest):
                raise ValueError(f"telemetry_lineage_{field_name}_invalid")
            object.__setattr__(self, field_name, digest)

    @classmethod
    def from_observation(cls, observation: Mapping[str, Any]) -> "ObservationLineage":
        if not isinstance(observation, Mapping):
            raise TypeError("telemetry_lineage_observation_mapping_required")
        return cls(
            observation_id=observation.get("observation_id") or observation.get("id"),
            connection_id=observation.get("connection_id"),
            ingestion_run_id=observation.get("ingestion_run_id"),
            external_signal_id=observation.get("external_signal_id"),
            mapping_id=observation.get("mapping_id"),
            mapping_revision=observation.get("mapping_revision"),
            canonical_signal_id=(
                observation.get("canonical_signal_id")
                or observation.get("canonical_concept_id")
            ),
            canonical_signal_name=observation.get("canonical_signal_name"),
            system_id=observation.get("system_id"),
            asset_id=observation.get("asset_id"),
            external_tag_id=observation.get("external_tag_id"),
            source_timestamp_raw=observation.get("source_timestamp_raw"),
            source_timezone=observation.get("source_timezone"),
            source_offset=observation.get("source_offset"),
            timestamp_normalization_version=observation.get(
                "timestamp_normalization_version"
            ),
            observed_at_utc=observation.get("observed_at_utc"),
            original_unit=observation.get("original_unit"),
            canonical_unit=observation.get("canonical_unit"),
            conversion_id=observation.get("conversion_id"),
            conversion_version=observation.get("conversion_version"),
            source_record_digest=observation.get("source_record_digest"),
            mapping_authority_digest=observation.get("mapping_authority_digest"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "observation_id": self.observation_id,
            "connection_id": self.connection_id,
            "ingestion_run_id": self.ingestion_run_id,
            "external_signal_id": self.external_signal_id,
            "mapping_id": self.mapping_id,
            "mapping_revision": self.mapping_revision,
            "canonical_signal_id": self.canonical_signal_id,
            "canonical_signal_name": self.canonical_signal_name,
            "system_id": self.system_id,
            "asset_id": self.asset_id,
            "external_tag_id": self.external_tag_id,
            "source_timestamp_raw": self.source_timestamp_raw,
            "source_timezone": self.source_timezone,
            "source_offset": self.source_offset,
            "timestamp_normalization_version": self.timestamp_normalization_version,
            "observed_at_utc": self.observed_at_utc.isoformat(),
            "original_unit": self.original_unit,
            "canonical_unit": self.canonical_unit,
            "conversion_id": self.conversion_id,
            "conversion_version": self.conversion_version,
            "source_record_digest": self.source_record_digest,
            "mapping_authority_digest": self.mapping_authority_digest,
        }


def build_observation_lineage(
    observations: Sequence[Mapping[str, Any] | ObservationLineage],
) -> tuple[ObservationLineage, ...]:
    if len(observations) > MAX_LINEAGE_RECORDS:
        raise ValueError("telemetry_analysis_window_observation_limit_exceeded")
    records = tuple(
        item if isinstance(item, ObservationLineage) else ObservationLineage.from_observation(item)
        for item in observations
    )
    observation_ids = [item.observation_id for item in records]
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("telemetry_lineage_observation_id_duplicate")
    return records


def observation_lineage_digest(lineage: Sequence[ObservationLineage]) -> str:
    canonical = [item.as_dict() for item in sorted(lineage, key=lambda item: item.observation_id)]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_lineage_summary(
    lineage: Sequence[ObservationLineage],
    *,
    sample_limit: int = DEFAULT_LINEAGE_SAMPLE_LIMIT,
) -> dict[str, Any]:
    bounded_limit = min(max(int(sample_limit), 0), MAX_LINEAGE_SAMPLE_LIMIT)
    ordered = sorted(lineage, key=lambda item: (item.observed_at_utc, item.observation_id))
    return {
        "contract_version": LINEAGE_SUMMARY_VERSION,
        "observation_count": len(lineage),
        "lineage_digest": observation_lineage_digest(lineage),
        "sample_limit": bounded_limit,
        "sample_truncated": len(lineage) > bounded_limit,
        "observation_sample": [item.as_dict() for item in ordered[:bounded_limit]],
        "contributing_ingestion_run_ids": sorted(
            {item.ingestion_run_id for item in lineage}
        ),
    }


def _bounded_reference_ids(
    value: Any,
    *,
    keys: frozenset[str],
) -> tuple[list[str], int]:
    """Extract identifier fields only, without retaining result payloads."""
    identifiers: set[str] = set()
    stack: list[Any] = [value]
    visited = 0
    while stack and visited < 20_000:
        current = stack.pop()
        visited += 1
        if isinstance(current, Mapping):
            for raw_key, nested in current.items():
                key = str(raw_key)
                if key in keys:
                    candidates = nested if isinstance(nested, (list, tuple, set)) else (nested,)
                    for candidate in candidates:
                        text = str(candidate or "").strip()
                        if text and len(text) <= 512:
                            identifiers.add(text)
                elif isinstance(nested, (Mapping, list, tuple)):
                    stack.append(nested)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
    ordered = sorted(identifiers)
    return ordered[:MAX_RESULT_REFERENCE_IDS], len(ordered)


def build_durable_result_lineage(
    *,
    window_id: str,
    source_run_id: str,
    lineage: Sequence[ObservationLineage],
    sii_result: Mapping[str, Any],
    analysis_result: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Build bounded completion metadata and deterministic evidence references.

    Only counts, contract/status metadata, identifiers and digests survive. Raw
    provider payloads, uploaded bytes, rows, configs and full SII output do not.
    """
    summary = build_lineage_summary(lineage, sample_limit=0)
    evidence_ids, evidence_total = _bounded_reference_ids(
        (sii_result, analysis_result),
        keys=frozenset(
            {
                "evidence_id",
                "evidence_ids",
                "supporting_evidence_ids",
                "limiting_evidence_ids",
                "contradictory_evidence_ids",
            }
        ),
    )
    finding_ids, finding_total = _bounded_reference_ids(
        (sii_result, analysis_result),
        keys=frozenset({"finding_id", "finding_ids", "sii_finding_id"}),
    )
    generated_finding_ids = {
        str(item.get("id") or "").strip()
        for collection_name in ("conditions", "insights")
        for item in (
            analysis_result.get(collection_name)
            if isinstance(analysis_result.get(collection_name), list)
            else []
        )
        if isinstance(item, Mapping) and str(item.get("id") or "").strip()
    }
    all_finding_ids = sorted({*finding_ids, *generated_finding_ids})
    finding_total = max(finding_total, len(all_finding_ids))
    finding_ids = all_finding_ids[:MAX_RESULT_REFERENCE_IDS]
    evidence_lineage = {
        "contract_version": DURABLE_RESULT_LINEAGE_VERSION,
        "window_id": _required_text(window_id, "telemetry_analysis_window_id_invalid"),
        "source_run_id": _required_text(
            source_run_id, "telemetry_lineage_run_invalid"
        ),
        "observation_count": summary["observation_count"],
        "observation_lineage_digest": summary["lineage_digest"],
        "contributing_ingestion_run_ids": summary[
            "contributing_ingestion_run_ids"
        ],
        "evidence_ids": evidence_ids,
        "evidence_id_count": evidence_total,
        "evidence_ids_truncated": evidence_total > len(evidence_ids),
        "finding_ids": finding_ids,
        "finding_id_count": finding_total,
        "finding_ids_truncated": finding_total > len(finding_ids),
    }
    reference_encoded = json.dumps(
        evidence_lineage, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    evidence_lineage["reference_digest"] = hashlib.sha256(
        reference_encoded.encode("utf-8")
    ).hexdigest()
    analysis_metadata = analysis_result.get("analysis_metadata")
    if not isinstance(analysis_metadata, Mapping):
        analysis_metadata = {}
    result_metadata = {
        "contract_version": DURABLE_RESULT_LINEAGE_VERSION,
        "status": str(sii_result.get("status") or "completed")[:64],
        # The product result's top-level identity is a schema version.  Keep it
        # distinct from the nested analysis contract instead of silently
        # reading the non-existent top-level ``contract_version`` field.
        "analysis_schema_version": str(
            analysis_result.get("schema_version") or ""
        )[:128],
        "analysis_contract_version": str(
            analysis_metadata.get("contract_version") or ""
        )[:128],
        "observation_count": summary["observation_count"],
        "contributing_run_count": len(summary["contributing_ingestion_run_ids"]),
        "evidence_id_count": evidence_total,
        "finding_id_count": finding_total,
        "reference_digest": evidence_lineage["reference_digest"],
    }
    result_digest = hashlib.sha256(
        json.dumps(
            {"metadata": result_metadata, "lineage": evidence_lineage},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return result_metadata, evidence_lineage, result_digest


def project_analysis_window_persistence(
    *,
    window_id: str,
    tenant_scope_id: str,
    workspace_id: str,
    resource_scope_id: str,
    facility_id: str,
    system_id: str,
    asset_id: str | None,
    source_run_id: str,
    window_start: datetime,
    window_end: datetime,
    authority_digest: str,
    quality_summary: Mapping[str, Any],
    status: str = "eligible",
) -> dict[str, Any]:
    """Project the server-owned row for ``telemetry.analysis_windows``."""
    if status not in {"pending", "eligible", "running", "completed", "failed", "ineligible"}:
        raise ValueError("telemetry_analysis_window_status_invalid")
    start = _aware_utc(window_start, "telemetry_analysis_window_start_invalid")
    end = _aware_utc(window_end, "telemetry_analysis_window_end_invalid")
    if end <= start:
        raise ValueError("telemetry_analysis_window_range_invalid")
    digest = str(authority_digest or "").strip().lower()
    if not _SHA256.fullmatch(digest):
        raise ValueError("telemetry_analysis_window_authority_digest_invalid")
    return {
        "id": _required_text(window_id, "telemetry_analysis_window_id_invalid"),
        "tenant_scope_id": _required_text(tenant_scope_id, "telemetry_lineage_tenant_invalid"),
        "workspace_id": _required_text(workspace_id, "telemetry_lineage_workspace_invalid"),
        "resource_scope_id": _required_text(resource_scope_id, "telemetry_lineage_scope_invalid"),
        "facility_id": _required_text(facility_id, "telemetry_lineage_facility_invalid"),
        "system_id": _required_text(system_id, "telemetry_lineage_system_invalid"),
        "asset_id": _optional_text(asset_id),
        "source_ingestion_run_id": _required_text(source_run_id, "telemetry_lineage_run_invalid"),
        "window_start": start,
        "window_end": end,
        "status": status,
        "authority_digest": digest,
        "quality_summary": dict(quality_summary),
    }


def project_analysis_window_observations(
    *,
    window_id: str,
    tenant_scope_id: str,
    workspace_id: str,
    resource_scope_id: str,
    facility_id: str,
    lineage: Sequence[ObservationLineage],
) -> tuple[dict[str, str], ...]:
    """Project complete join rows for durable window/observation lineage."""
    common = {
        "tenant_scope_id": _required_text(tenant_scope_id, "telemetry_lineage_tenant_invalid"),
        "workspace_id": _required_text(workspace_id, "telemetry_lineage_workspace_invalid"),
        "resource_scope_id": _required_text(resource_scope_id, "telemetry_lineage_scope_invalid"),
        "facility_id": _required_text(facility_id, "telemetry_lineage_facility_invalid"),
        "analysis_window_id": _required_text(window_id, "telemetry_analysis_window_id_invalid"),
    }
    return tuple({**common, "observation_id": item.observation_id} for item in lineage)


def bounded_lineage_bundle(value: Any) -> dict[str, Any] | None:
    """Accept only the bounded public summary shape for evidence transport."""
    if not isinstance(value, Mapping):
        return None
    digest = str(value.get("lineage_digest") or "").strip().lower()
    count = value.get("observation_count")
    sample = value.get("observation_sample")
    if not _SHA256.fullmatch(digest) or not isinstance(count, int) or count < 0:
        return None
    if not isinstance(sample, list) or len(sample) > MAX_LINEAGE_SAMPLE_LIMIT:
        return None
    safe_sample = [
        dict(item)
        for item in sample
        if isinstance(item, Mapping) and set(item).issubset(_LINEAGE_PUBLIC_FIELDS)
    ]
    if len(safe_sample) != len(sample):
        return None
    return {
        "contract_version": str(value.get("contract_version") or LINEAGE_SUMMARY_VERSION),
        "window_id": _optional_text(value.get("window_id")),
        "source_kind": _optional_text(value.get("source_kind")),
        "source_run_id": _optional_text(value.get("source_run_id")),
        "observation_count": count,
        "lineage_digest": digest,
        "sample_limit": min(max(int(value.get("sample_limit") or 0), 0), MAX_LINEAGE_SAMPLE_LIMIT),
        "sample_truncated": bool(value.get("sample_truncated")),
        "observation_sample": safe_sample,
        "contributing_ingestion_run_ids": [
            str(item)
            for item in value.get("contributing_ingestion_run_ids", [])
            if str(item).strip()
        ][:MAX_RESULT_REFERENCE_IDS],
    }


__all__ = [
    "DEFAULT_LINEAGE_SAMPLE_LIMIT",
    "DURABLE_RESULT_LINEAGE_VERSION",
    "LINEAGE_CONTRACT_VERSION",
    "LINEAGE_SUMMARY_VERSION",
    "MAX_LINEAGE_RECORDS",
    "MAX_LINEAGE_SAMPLE_LIMIT",
    "MAX_RESULT_REFERENCE_IDS",
    "ObservationLineage",
    "bounded_lineage_bundle",
    "build_lineage_summary",
    "build_durable_result_lineage",
    "build_observation_lineage",
    "observation_lineage_digest",
    "project_analysis_window_observations",
    "project_analysis_window_persistence",
]
