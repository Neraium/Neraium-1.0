"""Canonical durable representation for completed connector analysis results.

This module owns serialization and integrity only. Persistence and product
projection are separate concerns so the immutable payload remains the sole
analytical authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
import time
from types import MappingProxyType
from typing import Any
from uuid import NAMESPACE_URL, uuid5
import zlib

from app.services.telemetry_analysis_window import AnalysisWindowExecution

ARTIFACT_SCHEMA_VERSION = "telemetry-canonical-result-artifact.v1"
PAYLOAD_ENCODING = "zlib+canonical-json.v1"
MAX_CANONICAL_RESULT_BYTES = 256 * 1024 * 1024
MAX_INDEXED_RESULT_IDS = 256
MAX_INDEXED_ID_METADATA_BYTES = 64 * 1024
MAX_REFERENCE_METADATA_BYTES = 32 * 1024

_RESULT_ID_NAMESPACE = uuid5(
    NAMESPACE_URL,
    "https://neraium.com/contracts/telemetry-canonical-result-artifact.v1",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONNECTOR_SOURCE_KINDS = frozenset({"connector", "telemetry_connector"})
_IDENTIFIER_KEYS = {
    "evidence": frozenset(
        {
            "evidence_id",
            "evidence_ids",
            "supporting_evidence_ids",
            "limiting_evidence_ids",
            "contradictory_evidence_ids",
        }
    ),
    "finding": frozenset({"finding_id", "finding_ids", "sii_finding_id"}),
}


class CanonicalResultArtifactError(ValueError):
    """A completed result cannot be represented or verified canonically."""


@dataclass(frozen=True, slots=True)
class CanonicalResultArtifact:
    """One exact compressed result plus bounded database-index metadata."""

    result_id: str
    analysis_window_id: str
    source_run_id: str
    artifact_schema_version: str
    execution_contract_version: str
    analysis_schema_version: str
    analysis_contract_version: str
    engine_name: str | None
    engine_version: str | None
    reference_metadata: Mapping[str, Any]
    observation_count: int
    observation_lineage_digest: str
    finding_ids: Mapping[str, Any]
    evidence_ids: Mapping[str, Any]
    payload_encoding: str
    payload_digest: str
    payload_uncompressed_bytes: int
    payload_stored_bytes: int
    serialization_ms: float
    payload: bytes

    def __deepcopy__(self, memo: dict[int, Any]) -> CanonicalResultArtifact:
        """The frozen value is safe to share across copied service records."""

        memo[id(self)] = self
        return self


def build_canonical_result_artifact(
    execution: AnalysisWindowExecution,
) -> CanonicalResultArtifact:
    """Serialize an exact terminal execution without truncating its payload."""

    if not isinstance(execution, AnalysisWindowExecution):
        raise CanonicalResultArtifactError("canonical_result_execution_required")
    started = time.perf_counter()
    payload_value = execution.as_dict()
    identity = _validate_payload_identity(payload_value)
    canonical = _canonical_json_bytes(payload_value)
    if len(canonical) > MAX_CANONICAL_RESULT_BYTES:
        raise CanonicalResultArtifactError("canonical_result_payload_too_large")

    payload_digest = hashlib.sha256(canonical).hexdigest()
    compressed = zlib.compress(canonical, level=9)
    if len(compressed) > MAX_CANONICAL_RESULT_BYTES:
        raise CanonicalResultArtifactError("canonical_result_payload_too_large")
    reference_metadata = _reference_metadata(payload_value)
    finding_ids = _indexed_ids(payload_value, kind="finding")
    evidence_ids = _indexed_ids(payload_value, kind="evidence")
    if (
        len(_canonical_json_bytes(finding_ids))
        + len(_canonical_json_bytes(evidence_ids))
        > MAX_INDEXED_ID_METADATA_BYTES
    ):
        raise CanonicalResultArtifactError("canonical_result_id_metadata_too_large")

    result_id = canonical_result_id(
        window_id=identity["window_id"],
        execution_contract_version=identity["execution_contract_version"],
    )
    return CanonicalResultArtifact(
        result_id=result_id,
        analysis_window_id=identity["window_id"],
        source_run_id=identity["source_run_id"],
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        execution_contract_version=identity["execution_contract_version"],
        analysis_schema_version=identity["analysis_schema_version"],
        analysis_contract_version=identity["analysis_contract_version"],
        engine_name=identity["engine_name"],
        engine_version=identity["engine_version"],
        reference_metadata=MappingProxyType(reference_metadata),
        observation_count=identity["observation_count"],
        observation_lineage_digest=identity["observation_lineage_digest"],
        finding_ids=MappingProxyType(finding_ids),
        evidence_ids=MappingProxyType(evidence_ids),
        payload_encoding=PAYLOAD_ENCODING,
        payload_digest=payload_digest,
        payload_uncompressed_bytes=len(canonical),
        payload_stored_bytes=len(compressed),
        serialization_ms=round((time.perf_counter() - started) * 1000, 3),
        payload=compressed,
    )


def decode_canonical_result_artifact(
    artifact: CanonicalResultArtifact,
) -> dict[str, Any]:
    """Verify and decode an artifact without consulting analysis runtime state."""

    if not isinstance(artifact, CanonicalResultArtifact):
        raise CanonicalResultArtifactError("canonical_result_artifact_required")
    if artifact.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
        raise CanonicalResultArtifactError("canonical_result_artifact_schema_mismatch")
    if artifact.payload_encoding != PAYLOAD_ENCODING:
        raise CanonicalResultArtifactError("canonical_result_payload_encoding_mismatch")
    if artifact.payload_stored_bytes != len(artifact.payload):
        raise CanonicalResultArtifactError(
            "canonical_result_stored_byte_count_mismatch"
        )
    if (
        artifact.payload_uncompressed_bytes < 0
        or artifact.payload_uncompressed_bytes > MAX_CANONICAL_RESULT_BYTES
    ):
        raise CanonicalResultArtifactError("canonical_result_payload_size_invalid")
    if not _SHA256.fullmatch(artifact.payload_digest):
        raise CanonicalResultArtifactError("canonical_result_payload_digest_invalid")

    canonical = _bounded_decompress(artifact.payload)
    if len(canonical) != artifact.payload_uncompressed_bytes:
        raise CanonicalResultArtifactError(
            "canonical_result_uncompressed_byte_count_mismatch"
        )
    if hashlib.sha256(canonical).hexdigest() != artifact.payload_digest:
        raise CanonicalResultArtifactError("canonical_result_payload_digest_mismatch")
    try:
        payload_value = json.loads(canonical)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CanonicalResultArtifactError(
            "canonical_result_payload_json_invalid"
        ) from error
    if not isinstance(payload_value, dict):
        raise CanonicalResultArtifactError("canonical_result_payload_object_required")
    if _canonical_json_bytes(payload_value) != canonical:
        raise CanonicalResultArtifactError("canonical_result_payload_not_canonical")

    identity = _validate_payload_identity(payload_value)
    if artifact.result_id != canonical_result_id(
        window_id=identity["window_id"],
        execution_contract_version=identity["execution_contract_version"],
    ):
        raise CanonicalResultArtifactError("canonical_result_id_mismatch")
    if artifact.analysis_window_id != identity["window_id"]:
        raise CanonicalResultArtifactError("canonical_result_window_id_mismatch")
    if artifact.source_run_id != identity["source_run_id"]:
        raise CanonicalResultArtifactError("canonical_result_source_run_id_mismatch")
    expected = {
        "execution_contract_version": identity["execution_contract_version"],
        "analysis_schema_version": identity["analysis_schema_version"],
        "analysis_contract_version": identity["analysis_contract_version"],
        "engine_name": identity["engine_name"],
        "engine_version": identity["engine_version"],
        "observation_count": identity["observation_count"],
        "observation_lineage_digest": identity["observation_lineage_digest"],
    }
    for field_name, expected_value in expected.items():
        if getattr(artifact, field_name) != expected_value:
            raise CanonicalResultArtifactError(
                f"canonical_result_{field_name}_mismatch"
            )
    if dict(artifact.reference_metadata) != _reference_metadata(payload_value):
        raise CanonicalResultArtifactError(
            "canonical_result_reference_metadata_mismatch"
        )
    if dict(artifact.finding_ids) != _indexed_ids(payload_value, kind="finding"):
        raise CanonicalResultArtifactError("canonical_result_finding_ids_mismatch")
    if dict(artifact.evidence_ids) != _indexed_ids(payload_value, kind="evidence"):
        raise CanonicalResultArtifactError("canonical_result_evidence_ids_mismatch")
    return payload_value


def _bounded_decompress(payload: bytes) -> bytes:
    try:
        decompressor = zlib.decompressobj()
        canonical = decompressor.decompress(payload, MAX_CANONICAL_RESULT_BYTES + 1)
        if len(canonical) > MAX_CANONICAL_RESULT_BYTES or decompressor.unconsumed_tail:
            raise CanonicalResultArtifactError("canonical_result_payload_too_large")
        canonical += decompressor.flush()
    except zlib.error as error:
        raise CanonicalResultArtifactError(
            "canonical_result_payload_compression_invalid"
        ) from error
    if len(canonical) > MAX_CANONICAL_RESULT_BYTES:
        raise CanonicalResultArtifactError("canonical_result_payload_too_large")
    if not decompressor.eof or decompressor.unused_data:
        raise CanonicalResultArtifactError(
            "canonical_result_payload_compression_invalid"
        )
    return canonical


def _canonical_json_bytes(value: Any) -> bytes:
    def mapping_default(item: Any) -> Any:
        if isinstance(item, Mapping):
            return dict(item)
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        raise TypeError(f"unsupported canonical JSON value: {type(item).__name__}")

    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=mapping_default,
        )
    except (TypeError, ValueError, RecursionError) as error:
        raise CanonicalResultArtifactError(
            "canonical_result_payload_not_json"
        ) from error
    return encoded.encode("utf-8")


def _required_text(value: Any, code: str, *, maximum: int = 512) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        raise CanonicalResultArtifactError(code)
    return text


def _optional_text(value: Any, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > maximum:
        raise CanonicalResultArtifactError("canonical_result_identity_too_long")
    return text


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _validate_payload_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    status = _required_text(payload.get("status"), "canonical_result_status_missing")
    if status != "completed":
        raise CanonicalResultArtifactError("canonical_result_status_not_completed")
    window_id = _required_text(
        payload.get("window_id"), "canonical_result_window_id_missing"
    )
    source_run_id = _required_text(
        payload.get("source_run_id"), "canonical_result_source_run_id_missing"
    )
    source_kind = _required_text(
        payload.get("source_kind"), "canonical_result_source_kind_missing"
    )
    if source_kind not in _CONNECTOR_SOURCE_KINDS:
        raise CanonicalResultArtifactError("canonical_result_source_kind_invalid")
    execution_contract = _required_text(
        payload.get("contract_version"), "canonical_result_execution_contract_missing"
    )
    analysis_result = _mapping(payload.get("analysis_result"))
    analysis_schema = _required_text(
        analysis_result.get("schema_version"),
        "canonical_result_analysis_schema_missing",
    )
    analysis_metadata = _mapping(analysis_result.get("analysis_metadata"))
    analysis_contract = _required_text(
        analysis_metadata.get("contract_version"),
        "canonical_result_analysis_contract_missing",
    )
    if (
        _required_text(
            analysis_result.get("analysis_id"), "canonical_result_analysis_id_missing"
        )
        != window_id
    ):
        raise CanonicalResultArtifactError("canonical_result_analysis_window_mismatch")
    if (
        _required_text(
            analysis_metadata.get("run_id"), "canonical_result_analysis_run_missing"
        )
        != source_run_id
    ):
        raise CanonicalResultArtifactError("canonical_result_analysis_run_mismatch")

    lineage = _mapping(payload.get("telemetry_lineage"))
    if (
        _required_text(
            lineage.get("window_id"), "canonical_result_lineage_window_missing"
        )
        != window_id
    ):
        raise CanonicalResultArtifactError("canonical_result_lineage_window_mismatch")
    if (
        _required_text(
            lineage.get("source_run_id"), "canonical_result_lineage_run_missing"
        )
        != source_run_id
    ):
        raise CanonicalResultArtifactError("canonical_result_lineage_run_mismatch")
    if (
        _required_text(
            lineage.get("source_kind"), "canonical_result_lineage_source_kind_missing"
        )
        != source_kind
    ):
        raise CanonicalResultArtifactError(
            "canonical_result_lineage_source_kind_mismatch"
        )
    observation_count = lineage.get("observation_count")
    if isinstance(observation_count, bool) or not isinstance(observation_count, int):
        raise CanonicalResultArtifactError("canonical_result_observation_count_invalid")
    if observation_count < 1:
        raise CanonicalResultArtifactError("canonical_result_observation_count_invalid")
    lineage_digest = str(lineage.get("lineage_digest") or "").strip().lower()
    if not _SHA256.fullmatch(lineage_digest):
        raise CanonicalResultArtifactError("canonical_result_lineage_digest_invalid")

    engine = _mapping(_mapping(payload.get("sii_result")).get("engine"))
    return {
        "window_id": window_id,
        "source_run_id": source_run_id,
        "execution_contract_version": execution_contract,
        "analysis_schema_version": analysis_schema,
        "analysis_contract_version": analysis_contract,
        "engine_name": _optional_text(engine.get("name")),
        "engine_version": _optional_text(engine.get("version")),
        "observation_count": observation_count,
        "observation_lineage_digest": lineage_digest,
    }


def canonical_result_id(*, window_id: str, execution_contract_version: str) -> str:
    name = "\x1f".join((ARTIFACT_SCHEMA_VERSION, window_id, execution_contract_version))
    return str(uuid5(_RESULT_ID_NAMESPACE, name))


def _indexed_ids(payload: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    keys = _IDENTIFIER_KEYS[kind]
    identifiers: set[str] = set()
    sii_result = _mapping(payload.get("sii_result"))
    analysis_result = _mapping(payload.get("analysis_result"))
    analysis_without_records = {
        key: value
        for key, value in analysis_result.items()
        if key != "normalized_telemetry"
    }
    stack: list[Any] = [sii_result, analysis_without_records]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for raw_key, nested in current.items():
                key = str(raw_key)
                if key in keys:
                    _add_identifier_values(identifiers, nested)
                if isinstance(nested, (Mapping, list, tuple)):
                    stack.append(nested)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)

    if kind == "finding":
        for collection_name in ("conditions", "insights"):
            collection = analysis_result.get(collection_name)
            if isinstance(collection, Sequence) and not isinstance(
                collection, (str, bytes)
            ):
                for item in collection:
                    if isinstance(item, Mapping):
                        _add_identifier_values(identifiers, item.get("id"))
        findings = sii_result.get("findings")
        if isinstance(findings, Sequence) and not isinstance(findings, (str, bytes)):
            for item in findings:
                if isinstance(item, Mapping):
                    _add_identifier_values(identifiers, item.get("id"))
    else:
        evidence_index = analysis_result.get("evidence_index")
        if isinstance(evidence_index, Mapping):
            for evidence_id in evidence_index:
                _add_identifier_values(identifiers, evidence_id)

    ordered = sorted(identifiers)
    selected = ordered[:MAX_INDEXED_RESULT_IDS]
    result = {
        "ids": selected,
        "total": len(ordered),
        "truncated": len(ordered) > len(selected),
    }
    per_kind_limit = MAX_INDEXED_ID_METADATA_BYTES // 2
    while selected and len(_canonical_json_bytes(result)) > per_kind_limit:
        selected.pop()
        result["truncated"] = True
    return result


def _add_identifier_values(output: set[str], value: Any) -> None:
    candidates = value if isinstance(value, (list, tuple, set)) else (value,)
    for candidate in candidates:
        if candidate is None or isinstance(candidate, (Mapping, list, tuple, set)):
            continue
        text = str(candidate).strip()
        if not text:
            continue
        if len(text) > 2_048:
            raise CanonicalResultArtifactError("canonical_result_identifier_too_long")
        output.add(text)


def _reference_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    sii_result = _mapping(payload.get("sii_result"))
    analysis_result = _mapping(payload.get("analysis_result"))
    paths = (
        (
            "sii_result.behavioral_model",
            _mapping(sii_result.get("behavioral_model")),
            ("contract_version", "model_id", "model_version", "snapshot_id"),
        ),
        (
            "sii_result.behavioral_model.identity",
            _mapping(_mapping(sii_result.get("behavioral_model")).get("identity")),
            ("configured_model_id",),
        ),
        (
            "sii_result.behavioral_model.baseline_state",
            _mapping(
                _mapping(sii_result.get("behavioral_model")).get("baseline_state")
            ),
            ("active_version", "baseline_id", "baseline_version", "candidate_version"),
        ),
        (
            "sii_result.behavioral_model.learning_decision",
            _mapping(
                _mapping(sii_result.get("behavioral_model")).get("learning_decision")
            ),
            ("baseline_id", "baseline_version", "model_version"),
        ),
        (
            "sii_result.behavioral_model.processing_trace",
            _mapping(
                _mapping(sii_result.get("behavioral_model")).get("processing_trace")
            ),
            (
                "model_id",
                "model_version_before",
                "model_version_after",
                "baseline_version_before",
                "baseline_version_after",
                "snapshot_id",
                "previous_snapshot_id",
                "rollback_reference",
            ),
        ),
        (
            "sii_result.behavioral_snapshots",
            _mapping(sii_result.get("behavioral_snapshots")),
            (
                "current_snapshot_id",
                "previous_snapshot_id",
                "model_version",
                "rollback_reference",
            ),
        ),
        (
            "analysis_result.sii_evidence.provenance",
            _mapping(_mapping(analysis_result.get("sii_evidence")).get("provenance")),
            ("baseline_id", "baseline_dataset_id", "baseline_version", "baseline_hash"),
        ),
    )
    references: list[dict[str, str]] = []
    for prefix, source, keys in paths:
        for key in keys:
            value = source.get(key)
            values = value if isinstance(value, (list, tuple)) else (value,)
            for index, item in enumerate(values):
                text = _optional_text(item, maximum=2_048)
                if text is None:
                    continue
                suffix = f".{key}" if len(values) == 1 else f".{key}[{index}]"
                references.append(
                    {"kind": key, "source_path": f"{prefix}{suffix}", "value": text}
                )
    references.sort(key=lambda item: (item["source_path"], item["value"]))
    total = len(references)
    result: dict[str, Any] = {
        "references": references,
        "total": total,
        "truncated": False,
    }
    while (
        references and len(_canonical_json_bytes(result)) > MAX_REFERENCE_METADATA_BYTES
    ):
        references.pop()
        result["truncated"] = True
    if len(_canonical_json_bytes(result)) > MAX_REFERENCE_METADATA_BYTES:
        raise CanonicalResultArtifactError(
            "canonical_result_reference_metadata_too_large"
        )
    return result
