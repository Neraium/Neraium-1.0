"""Bounded product transport for a verified canonical connector result.

The immutable artifact remains authoritative.  This module only selects exact
facts for the existing progressive-disclosure product surfaces; it never runs
analysis or derives new analytical claims.
"""

from __future__ import annotations

from app.services.product_evidence_contract import product_evidence

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
import re
import time
from typing import Any


PRODUCT_PROJECTION_CONTRACT_VERSION = "telemetry-canonical-result-product.v1"
MAX_SHARED_ENVELOPE_BYTES = 1 * 1024 * 1024
MAX_SHARED_ANALYSIS_BYTES = MAX_SHARED_ENVELOPE_BYTES - (64 * 1024)
MAX_TECHNICAL_CHANNEL_BYTES = 256 * 1024
MAX_TECHNICAL_CHANNELS_BYTES = 2 * 1024 * 1024
MAX_EVIDENCE_AUDIT_BYTES = 256 * 1024
MAX_COLLECTION_ITEMS = 32
MAX_MAPPING_ENTRIES = 128
MAX_SIGNAL_CATALOG_ITEMS = 64
MAX_INDEXED_IDS = 256
MAX_STRING_BYTES = 4 * 1024
MAX_JSON_DEPTH = 16

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OMIT = object()

# These are the direct SII paths consumed by Investigation/Evidence Record.
# A missing channel remains missing; no compatibility evidence is fabricated.
_TECHNICAL_CHANNELS = (
    "engine",
    "relationship_analysis",
    "relationship_graph",
    "covariance_analysis",
    "temporal_analysis",
    "multiscale_analysis",
    "persistence_analysis",
    "operating_modes",
    "uncertainty",
    "data_conditions",
    "sensor_health",
    "evidence_fusion",
    "behavioral_model",
    "expected_behavior",
    "behavioral_evolution",
    "behavioral_snapshots",
    "event_memory",
    "spectral_analysis",
    "dynamical_stability",
    "network_stability",
    "bayesian_evidence",
    "propagation_analysis",
    "physics_reasoning",
    "physics_evidence",
    "processing_trace",
    "provenance",
)

_SHARED_ANALYSIS_FIELDS = (
    "schema_version",
    "status",
    "analysis_id",
    "upload_id",
    "source_file",
    "generated_at",
    "change_onset",
    "stable_window",
    "deviation_window",
    "current_state_window",
    "data_quality",
    "executive_summary",
    "systems",
    "conditions",
    "primary_object",
    "relationships",
    "fingerprint",
    "insights",
    "recommendations",
    "evidence_index",
    "warnings",
    "errors",
    "telemetry_signals",
    "analysis_metadata",
    "sii_evidence",
    "telemetry_lineage",
    "normalized_telemetry",
)

_FINDING_AUDIT_FIELDS = frozenset(
    {
        "measurable_consequence",
        "id",
        "finding_id",
        "finding_key",
        "status",
        "tier",
        "title",
        "generated_at",
        "generatedAt",
        "first_detected_at",
        "firstDetectedAt",
        "system_id",
        "asset_id",
        "equipment_id",
        "metrics",
        "relationships",
        "classification",
        "classificationPresentation",
        "confidence_contract",
        "confidenceContract",
        "confidenceDimensions",
        "limitations",
        "primaryLimitation",
        "technicalLimitations",
        "dataLimitations",
        "contradictions",
        "evidence_refs",
        "sourceTimeRanges",
        "rawVariables",
        "variables",
        "provenance",
    }
)


class CanonicalResultProjectionError(ValueError):
    """A verified artifact cannot be represented within product bounds."""


@dataclass(frozen=True, slots=True)
class CanonicalResultProjection:
    """A product result plus measured bounded transport costs."""

    product_result: dict[str, Any]
    projection_bytes: int
    shared_envelope_bytes: int
    technical_channels_bytes: int
    evidence_audit_bytes: int
    serialization_ms: float


@dataclass(slots=True)
class _Selection:
    omitted_values: int = 0
    original_items: int = 0
    selected_items: int = 0
    depth_limited: bool = False
    string_limited: bool = False

    @property
    def truncated(self) -> bool:
        return self.omitted_values > 0 or self.depth_limited or self.string_limited


def build_canonical_result_projection(
    execution: Mapping[str, Any],
    *,
    artifact_metadata: Mapping[str, Any],
    scope: Mapping[str, Any],
    lineage_verified: bool = False,
) -> CanonicalResultProjection:
    """Build one bounded transport from an already decoded, verified artifact.

    ``artifact_metadata`` and ``scope`` are the indexed values loaded under the
    request's full authorization predicate.  Their agreement with the decoded
    execution is checked again before any product content is returned.
    """

    started = time.perf_counter()
    execution_map = _required_mapping(
        execution, "canonical_result_projection_execution_required"
    )
    metadata = _required_mapping(
        artifact_metadata, "canonical_result_projection_metadata_required"
    )
    scoped = _required_mapping(scope, "canonical_result_projection_scope_required")
    identity = _validated_identity(execution_map, metadata, scoped)

    analysis_result = _required_mapping(
        execution_map.get("analysis_result"),
        "canonical_result_projection_analysis_result_required",
    )
    sii_result = _required_mapping(
        execution_map.get("sii_result"),
        "canonical_result_projection_sii_result_required",
    )

    analysis_result = product_evidence(analysis_result)
    sii_result = product_evidence(sii_result)
    shared_analysis, shared_selection = _build_shared_analysis(analysis_result)
    shared_envelope = {
        "identity": identity,
        "analysis_result": shared_analysis,
        "source_type": "telemetry_connector",
        "status": str(execution_map.get("status")),
        "availability": "available",
        "product_boundary": {"mode": "read_only", "control_actions": []},
        "lineage": {
            "analysis_window_id": identity["analysis_window_id"],
            "observation_count": identity["observation_count"],
            "digest": identity["observation_lineage_digest"],
            "verified": bool(lineage_verified),
            "detail_source": "analysis_window_observations",
        },
    }
    shared_bytes = _json_size(shared_envelope)
    if shared_bytes > MAX_SHARED_ENVELOPE_BYTES:
        raise CanonicalResultProjectionError(
            "canonical_result_projection_shared_envelope_too_large"
        )

    projected_sii, channel_metadata, technical_bytes = _build_technical_channels(
        sii_result,
        result_id=identity["result_id"],
        payload_digest=identity["payload_digest"],
    )
    audit, audit_selection = _build_evidence_audit(
        analysis_result,
        identity=identity,
        metadata=metadata,
        scope=scoped,
    )
    audit_bytes = _json_size(audit)
    if audit_bytes > MAX_EVIDENCE_AUDIT_BYTES:
        raise CanonicalResultProjectionError(
            "canonical_result_projection_evidence_audit_too_large"
        )

    projection_metadata = {
        "contract_version": PRODUCT_PROJECTION_CONTRACT_VERSION,
        "canonical_result_id": identity["result_id"],
        "canonical_payload_digest": identity["payload_digest"],
        "shared": {
            "source_path": "analysis_result",
            "bytes": shared_bytes,
            "truncated": shared_selection.truncated,
            "omitted_values": shared_selection.omitted_values,
        },
        "technical_channels": channel_metadata,
        "technical_channels_bytes": technical_bytes,
        "evidence_audit": {
            "source_path": "analysis_result.conditions|analysis_result.insights",
            "bytes": audit_bytes,
            "truncated": audit_selection.truncated,
            "omitted_values": audit_selection.omitted_values,
        },
    }
    product_result = {
        **shared_envelope,
        # Keep the existing engineering view-model input path.
        "analysis_result": shared_analysis,
        "sii_result": projected_sii,
        "canonical_result": {
            "identity": identity,
            "reference_metadata": _json_value(metadata.get("reference_metadata", {})),
            "finding_ids": _json_value(metadata.get("finding_ids", {})),
            "evidence_ids": _json_value(metadata.get("evidence_ids", {})),
            "evidence_audit": audit,
        },
        "projection": projection_metadata,
        # Existing consumers look for these top-level aliases.
        "result_id": identity["result_id"],
        "analysis_id": identity["analysis_id"],
        "analysis_window_id": identity["analysis_window_id"],
        "connection_id": identity["connection_id"],
        "source_run_id": identity["source_ingestion_run_id"],
        "analysis_run_id": identity["source_ingestion_run_id"],
        "run_id": identity["source_ingestion_run_id"],
        "source_kind": str(execution_map.get("source_kind")),
        "facility_id": identity["facility_id"],
        "system_id": identity["system_id"],
        "asset_id": identity["asset_id"],
        "window_start": identity["window_start"],
        "window_end": identity["window_end"],
        "data_quality": shared_analysis.get("data_quality", {}),
        "warnings": shared_analysis.get("warnings", []),
        "data_conditions": projected_sii.get("data_conditions", {}),
        "sensor_health": projected_sii.get("sensor_health", {}),
        "processing_trace": projected_sii.get("processing_trace", {}),
        "engine": {
            "name": identity["engine_name"],
            "version": identity["engine_version"],
        },
        "engine_name": identity["engine_name"],
        "engine_version": identity["engine_version"],
        "schema_version": identity["analysis_schema_version"],
        "payload_digest": identity["payload_digest"],
        "result_hash": identity["payload_digest"],
        "lineage_verified": bool(lineage_verified),
    }
    projection_bytes = _json_size(product_result)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return CanonicalResultProjection(
        product_result=product_result,
        projection_bytes=projection_bytes,
        shared_envelope_bytes=shared_bytes,
        technical_channels_bytes=technical_bytes,
        evidence_audit_bytes=audit_bytes,
        serialization_ms=elapsed_ms,
    )


def _build_shared_analysis(
    analysis_result: Mapping[str, Any],
) -> tuple[dict[str, Any], _Selection]:
    list_limits = {
        "systems": MAX_COLLECTION_ITEMS,
        "conditions": MAX_COLLECTION_ITEMS,
        "relationships": MAX_COLLECTION_ITEMS,
        "insights": MAX_COLLECTION_ITEMS,
        "recommendations": MAX_COLLECTION_ITEMS,
        "warnings": MAX_COLLECTION_ITEMS,
        "errors": MAX_COLLECTION_ITEMS,
        "telemetry_signals": MAX_SIGNAL_CATALOG_ITEMS,
    }
    # Rebuild at progressively tighter collection bounds if nested exact facts
    # would otherwise exceed the shared transport ceiling.
    for scale in (1, 2, 4, 8, 16, 32):
        selection = _Selection()
        projected: dict[str, Any] = {}
        for field in _SHARED_ANALYSIS_FIELDS:
            if field not in analysis_result:
                continue
            value = analysis_result[field]
            if field == "normalized_telemetry":
                value = _normalized_summary(value, selection, scale=scale)
            elif field == "data_quality" and isinstance(value, Mapping):
                value = _data_quality_summary(value, selection, scale=scale)
            list_limit = max(1, list_limits.get(field, MAX_COLLECTION_ITEMS) // scale)
            map_limit = max(1, MAX_MAPPING_ENTRIES // scale)
            if field == "evidence_index":
                map_limit = max(1, MAX_MAPPING_ENTRIES // scale)
            copied = _bounded_copy(
                value,
                selection=selection,
                depth=0,
                list_limit=list_limit,
                map_limit=map_limit,
            )
            if copied is not _OMIT:
                projected[field] = copied
        if _json_size(projected) <= MAX_SHARED_ANALYSIS_BYTES:
            return projected, selection
    raise CanonicalResultProjectionError(
        "canonical_result_projection_shared_analysis_too_large"
    )


def _normalized_summary(value: Any, selection: _Selection, *, scale: int) -> Any:
    if not isinstance(value, Mapping):
        return value
    summary: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text == "records":
            selection.omitted_values += len(item) if _is_sequence(item) else 1
            continue
        limit = (
            max(1, MAX_SIGNAL_CATALOG_ITEMS // scale)
            if key_text in {"tags", "signals", "signal_catalog"}
            else max(1, MAX_COLLECTION_ITEMS // scale)
        )
        copied = _bounded_copy(
            item,
            selection=selection,
            depth=1,
            list_limit=limit,
            map_limit=max(1, MAX_MAPPING_ENTRIES // scale),
        )
        if copied is not _OMIT:
            summary[key_text] = copied
    return summary


def _data_quality_summary(
    value: Mapping[str, Any], selection: _Selection, *, scale: int
) -> dict[str, Any]:
    summary = dict(value)
    if "normalized_telemetry" in summary:
        summary["normalized_telemetry"] = _normalized_summary(
            summary["normalized_telemetry"], selection, scale=scale
        )
    return summary


def _build_technical_channels(
    sii_result: Mapping[str, Any],
    *,
    result_id: str,
    payload_digest: str,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    projected: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    for channel in _TECHNICAL_CHANNELS:
        if channel not in sii_result:
            continue
        source = sii_result[channel]
        original_bytes = _json_size(source)
        original_items = _item_count(source)
        selected: Any = _OMIT
        channel_selection = _Selection()
        for scale in (1, 2, 4, 8, 16, 32):
            candidate_selection = _Selection()
            candidate = _bounded_copy(
                source,
                selection=candidate_selection,
                depth=0,
                list_limit=max(1, MAX_COLLECTION_ITEMS // scale),
                map_limit=max(1, MAX_MAPPING_ENTRIES // scale),
            )
            channel_dto = {
                "source_path": f"sii_result.{channel}",
                "payload": None if candidate is _OMIT else candidate,
                "original_items": original_items,
                "original_bytes": original_bytes,
                "truncated": candidate_selection.truncated,
                "canonical_result_id": result_id,
                "canonical_payload_digest": payload_digest,
            }
            if (
                candidate is not _OMIT
                and _json_size(channel_dto) <= MAX_TECHNICAL_CHANNEL_BYTES
            ):
                selected = candidate
                channel_selection = candidate_selection
                break
        channel_meta = {
            "source_path": f"sii_result.{channel}",
            "original_items": original_items,
            "selected_items": _item_count(selected) if selected is not _OMIT else 0,
            "original_bytes": original_bytes,
            "selected_bytes": _json_size(selected) if selected is not _OMIT else 0,
            "truncated": selected is _OMIT or channel_selection.truncated,
            "canonical_result_id": result_id,
            "canonical_payload_digest": payload_digest,
            "transported": selected is not _OMIT,
        }
        proposed_projected = dict(projected)
        if selected is not _OMIT:
            proposed_projected[channel] = selected
        proposed_metadata = {**metadata, channel: channel_meta}
        proposed_bytes = _json_size(
            {"sii_result": proposed_projected, "channels": proposed_metadata}
        )
        if proposed_bytes > MAX_TECHNICAL_CHANNELS_BYTES:
            channel_meta["truncated"] = True
            channel_meta["transported"] = False
            channel_meta["selected_items"] = 0
            metadata[channel] = channel_meta
            continue
        projected = proposed_projected
        metadata = proposed_metadata
    technical_bytes = _json_size({"sii_result": projected, "channels": metadata})
    if technical_bytes > MAX_TECHNICAL_CHANNELS_BYTES:
        raise CanonicalResultProjectionError(
            "canonical_result_projection_technical_channels_too_large"
        )
    return projected, metadata, technical_bytes


def _build_evidence_audit(
    analysis_result: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    metadata: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> tuple[dict[str, Any], _Selection]:
    source_records: list[dict[str, Any]] = []
    for collection in ("conditions", "insights"):
        values = analysis_result.get(collection)
        if not _is_sequence(values):
            continue
        for index, item in enumerate(values):
            if not isinstance(item, Mapping):
                continue
            selected = {
                str(key): value
                for key, value in item.items()
                if str(key) in _FINDING_AUDIT_FIELDS
            }
            source_records.append(
                {"source_path": f"analysis_result.{collection}[{index}]", "facts": selected}
            )

    for scale in (1, 2, 4, 8, 16, 32):
        selection = _Selection()
        copied_records = _bounded_copy(
            source_records,
            selection=selection,
            depth=0,
            list_limit=max(1, MAX_COLLECTION_ITEMS // scale),
            map_limit=max(1, MAX_MAPPING_ENTRIES // scale),
        )
        audit = {
            "identity": dict(identity),
            "window": {
                "start": _json_value(scope.get("window_start")),
                "end": _json_value(scope.get("window_end")),
            },
            "authority_digest": _json_value(scope.get("authority_digest")),
            "reference_metadata": _json_value(metadata.get("reference_metadata", {})),
            "finding_ids": _json_value(metadata.get("finding_ids", {})),
            "evidence_ids": _json_value(metadata.get("evidence_ids", {})),
            "finding_records": [] if copied_records is _OMIT else copied_records,
            "finding_record_count": len(source_records),
            "finding_records_truncated": selection.truncated,
        }
        if _json_size(audit) <= MAX_EVIDENCE_AUDIT_BYTES:
            return audit, selection
    raise CanonicalResultProjectionError(
        "canonical_result_projection_evidence_audit_too_large"
    )


def _bounded_copy(
    value: Any,
    *,
    selection: _Selection,
    depth: int,
    list_limit: int,
    map_limit: int,
) -> Any:
    if depth > MAX_JSON_DEPTH:
        selection.depth_limited = True
        selection.omitted_values += 1
        return _OMIT
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalResultProjectionError(
                "canonical_result_projection_nonfinite_number"
            )
        return value
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_STRING_BYTES:
            selection.string_limited = True
            selection.omitted_values += 1
            return _OMIT
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        entries = list(value.items())
        selection.original_items += len(entries)
        for key, nested in entries[:map_limit]:
            key_text = str(key)
            if len(key_text.encode("utf-8")) > MAX_STRING_BYTES:
                selection.string_limited = True
                selection.omitted_values += 1
                continue
            copied = _bounded_copy(
                nested,
                selection=selection,
                depth=depth + 1,
                list_limit=list_limit,
                map_limit=map_limit,
            )
            if copied is not _OMIT:
                output[key_text] = copied
                selection.selected_items += 1
        selection.omitted_values += max(0, len(entries) - map_limit)
        return output
    if _is_sequence(value):
        values = list(value)
        selection.original_items += len(values)
        output = []
        for item in values[:list_limit]:
            copied = _bounded_copy(
                item,
                selection=selection,
                depth=depth + 1,
                list_limit=list_limit,
                map_limit=map_limit,
            )
            if copied is not _OMIT:
                output.append(copied)
                selection.selected_items += 1
        selection.omitted_values += max(0, len(values) - list_limit)
        return output
    raise CanonicalResultProjectionError("canonical_result_projection_value_invalid")


def _validated_identity(
    execution: Mapping[str, Any],
    metadata: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    analysis = _required_mapping(
        execution.get("analysis_result"),
        "canonical_result_projection_analysis_result_required",
    )
    analysis_metadata = _required_mapping(
        analysis.get("analysis_metadata"),
        "canonical_result_projection_analysis_metadata_required",
    )
    lineage = _required_mapping(
        execution.get("telemetry_lineage"),
        "canonical_result_projection_lineage_required",
    )
    engine = _mapping(_mapping(execution.get("sii_result")).get("engine"))

    result_id = _required_text(
        metadata.get("result_id") or metadata.get("id"),
        "canonical_result_projection_result_id_required",
    )
    payload_digest = _required_text(
        metadata.get("payload_digest"),
        "canonical_result_projection_payload_digest_required",
    ).lower()
    if not _SHA256.fullmatch(payload_digest):
        raise CanonicalResultProjectionError(
            "canonical_result_projection_payload_digest_invalid"
        )
    window_id = _required_text(
        execution.get("window_id"), "canonical_result_projection_window_id_required"
    )
    run_id = _required_text(
        execution.get("source_run_id"),
        "canonical_result_projection_source_run_id_required",
    )
    expected = {
        "analysis_window_id": window_id,
        "source_ingestion_run_id": run_id,
        "execution_contract_version": _required_text(
            execution.get("contract_version"),
            "canonical_result_projection_execution_contract_required",
        ),
        "analysis_schema_version": _required_text(
            analysis.get("schema_version"),
            "canonical_result_projection_analysis_schema_required",
        ),
        "analysis_contract_version": _required_text(
            analysis_metadata.get("contract_version"),
            "canonical_result_projection_analysis_contract_required",
        ),
        "observation_count": lineage.get("observation_count"),
        "observation_lineage_digest": str(lineage.get("lineage_digest") or "").lower(),
    }
    if (
        _required_text(
            analysis.get("analysis_id"),
            "canonical_result_projection_analysis_id_required",
        )
        != window_id
    ):
        raise CanonicalResultProjectionError(
            "canonical_result_projection_analysis_window_mismatch"
        )
    if (
        _required_text(
            analysis_metadata.get("run_id"),
            "canonical_result_projection_analysis_run_required",
        )
        != run_id
    ):
        raise CanonicalResultProjectionError(
            "canonical_result_projection_analysis_run_mismatch"
        )
    if str(execution.get("status") or "") != "completed":
        raise CanonicalResultProjectionError(
            "canonical_result_projection_execution_status_invalid"
        )
    if str(execution.get("source_kind") or "") not in {
        "connector",
        "telemetry_connector",
    }:
        raise CanonicalResultProjectionError(
            "canonical_result_projection_source_kind_invalid"
        )
    if isinstance(expected["observation_count"], bool) or not isinstance(
        expected["observation_count"], int
    ):
        raise CanonicalResultProjectionError(
            "canonical_result_projection_observation_count_invalid"
        )
    if not _SHA256.fullmatch(expected["observation_lineage_digest"]):
        raise CanonicalResultProjectionError(
            "canonical_result_projection_lineage_digest_invalid"
        )

    for key, expected_value in expected.items():
        source = scope if key in {"analysis_window_id", "source_ingestion_run_id"} else metadata
        actual_value = source.get(key)
        matches = (
            actual_value == expected_value
            if isinstance(expected_value, int)
            else str(actual_value or "") == str(expected_value)
        )
        if not matches:
            raise CanonicalResultProjectionError(
                f"canonical_result_projection_{key}_mismatch"
            )
    for key in (
        "tenant_scope_id",
        "workspace_id",
        "resource_scope_id",
        "facility_id",
        "connection_id",
        "system_id",
    ):
        _required_text(scope.get(key), f"canonical_result_projection_{key}_required")
    for key in ("window_start", "window_end", "authority_digest"):
        _required_text(scope.get(key), f"canonical_result_projection_{key}_required")

    indexed_engine_name = metadata.get("engine_name")
    indexed_engine_version = metadata.get("engine_version")
    if (
        indexed_engine_name != engine.get("name")
        or indexed_engine_version != engine.get("version")
    ):
        raise CanonicalResultProjectionError(
            "canonical_result_projection_engine_identity_mismatch"
        )
    return {
        "result_id": result_id,
        "analysis_id": window_id,
        "analysis_window_id": window_id,
        "source_ingestion_run_id": run_id,
        "connection_id": _required_text(
            scope.get("connection_id"),
            "canonical_result_projection_connection_id_required",
        ),
        "tenant_scope_id": _required_text(
            scope.get("tenant_scope_id"),
            "canonical_result_projection_tenant_scope_id_required",
        ),
        "workspace_id": _required_text(
            scope.get("workspace_id"),
            "canonical_result_projection_workspace_id_required",
        ),
        "resource_scope_id": _required_text(
            scope.get("resource_scope_id"),
            "canonical_result_projection_resource_scope_id_required",
        ),
        "facility_id": _required_text(
            scope.get("facility_id"),
            "canonical_result_projection_facility_id_required",
        ),
        "system_id": _required_text(
            scope.get("system_id"),
            "canonical_result_projection_system_id_required",
        ),
        "asset_id": _optional_text(scope.get("asset_id")),
        "window_start": _json_value(scope.get("window_start")),
        "window_end": _json_value(scope.get("window_end")),
        "authority_digest": _json_value(scope.get("authority_digest")),
        "artifact_schema_version": _required_text(
            metadata.get("artifact_schema_version"),
            "canonical_result_projection_artifact_schema_required",
        ),
        "execution_contract_version": expected["execution_contract_version"],
        "analysis_schema_version": expected["analysis_schema_version"],
        "analysis_contract_version": expected["analysis_contract_version"],
        "engine_name": _optional_text(indexed_engine_name),
        "engine_version": _optional_text(indexed_engine_version),
        "observation_count": expected["observation_count"],
        "observation_lineage_digest": expected["observation_lineage_digest"],
        "payload_digest": payload_digest,
        "payload_uncompressed_bytes": metadata.get("payload_uncompressed_bytes"),
        "payload_stored_bytes": metadata.get("payload_stored_bytes"),
    }


def _json_size(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
                default=_json_default,
            ).encode("utf-8")
        )
    except (TypeError, ValueError, RecursionError) as error:
        raise CanonicalResultProjectionError(
            "canonical_result_projection_serialization_failed"
        ) from error


def _json_default(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _json_value(value: Any) -> Any:
    selection = _Selection()
    copied = _bounded_copy(
        value,
        selection=selection,
        depth=0,
        list_limit=MAX_INDEXED_IDS,
        map_limit=MAX_MAPPING_ENTRIES,
    )
    return None if copied is _OMIT else copied


def _required_mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CanonicalResultProjectionError(code)
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _required_text(value: Any, code: str) -> str:
    text = str(value or "").strip()
    if not text or len(text.encode("utf-8")) > MAX_STRING_BYTES:
        raise CanonicalResultProjectionError(code)
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text.encode("utf-8")) > MAX_STRING_BYTES:
        raise CanonicalResultProjectionError(
            "canonical_result_projection_identity_too_long"
        )
    return text


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _item_count(value: Any) -> int:
    if isinstance(value, Mapping) or _is_sequence(value):
        return len(value)
    return 1 if value is not None else 0


def canonical_projection_digest(projection: CanonicalResultProjection) -> str:
    """Return a diagnostic checksum for the rebuildable transport itself."""

    if not isinstance(projection, CanonicalResultProjection):
        raise CanonicalResultProjectionError(
            "canonical_result_projection_required"
        )
    encoded = json.dumps(
        projection.product_result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
