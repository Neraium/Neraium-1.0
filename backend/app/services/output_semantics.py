"""Versioned semantic encoding, separate from immutable artifact serialization.

Current v2 identities are classified by producer responsibility. Only declared
execution envelopes and producer-owned aliases are omitted. Historical v1
readers retain their original rules; artifact serialization remains separate.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

SEMANTICS_VERSION = "governed-output-semantics.v2"
LEGACY_SEMANTICS_VERSION = "governed-output-semantics.v1"
RUNTIME_VERSION = "execution-metadata.v1"


def runtime_metadata(**values: Any) -> dict[str, Any]:
    """An explicit execution envelope; source fields with this name stay semantic."""
    return {**values, "contract_version": RUNTIME_VERSION}


def canonical_json(value: Any) -> str:
    """Canonical semantic encoding; never used to rewrite canonical artifacts."""
    def plain(item: Any) -> Any:
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("Canonical mappings require string keys")
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (set, frozenset)):
            return sorted((plain(child) for child in item), key=canonical_json)
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, date):
            return item.isoformat()
        return item
    # Current semantic JSON and immutable artifacts both reject nonfinite values.
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _legacy_reader(value: Any, legacy_contract: str | None = None):
    """The two historical v1 populations share a label, but not an encoder.

    Complete-upload v2 and marked execution envelopes identify the source
    producer. Ambiguous standalone historical values can name their origin.
    Stored bytes and version strings are never modified to select a reader.
    """
    if legacy_contract not in (None, "source-v1", "target-v1"):
        raise ValueError("Unknown historical semantic contract")
    if legacy_contract == "source-v1" or (legacy_contract is None and isinstance(value, Mapping) and (
        value.get("upload_evidence_contract") == "complete-upload-evidence.v2"
        or isinstance(value.get("runtime_metadata"), Mapping) and value["runtime_metadata"].get("contract_version") == RUNTIME_VERSION
    )):
        from app.services import output_semantics_legacy_source as reader
    else:
        from app.services import output_semantics_legacy_target as reader
    return reader


def semantic_content(value: Any, *, legacy_contract: str | None = None) -> Any:
    if legacy_contract:
        return _legacy_reader(value, legacy_contract).semantic_content(value)
    if isinstance(value, Mapping):
        if value.get("output_semantics") == LEGACY_SEMANTICS_VERSION:
            return _legacy_reader(value).semantic_content(value)
        runtime = value.get("runtime_metadata")
        marked = isinstance(runtime, Mapping) and runtime.get("contract_version") == RUNTIME_VERSION
        # Semantic responsibility comes from the versioned producer contract,
        # never from mutable execution metadata describing compatibility aliases.
        aliases = {"generated_at"} if value.get("output_semantics") == SEMANTICS_VERSION else set()
        if value.get("output_semantics") == SEMANTICS_VERSION and value.get("identity_contract") == "execution.v1":
            aliases.update({"analysis_id", "upload_id"})
        return {key: semantic_content(child) for key, child in value.items()
                if not (key == "runtime_metadata" and marked) and key not in aliases}
    if isinstance(value, (list, tuple)):
        return [semantic_content(child) for child in value]
    if isinstance(value, (set, frozenset)):
        return sorted((semantic_content(child) for child in value), key=canonical_json)
    return value


def semantic_digest(value: Any, *, legacy_contract: str | None = None) -> str:
    if legacy_contract or (isinstance(value, Mapping) and
                           value.get("output_semantics") == LEGACY_SEMANTICS_VERSION):
        return _legacy_reader(value, legacy_contract).semantic_digest(value)
    return hashlib.sha256(canonical_json(semantic_content(value)).encode("utf-8")).hexdigest()


def evidence_identifier(seed: str, evidence: dict[str, Any]) -> str:
    """Analysis-local evidence references; source identity is retained separately."""
    return "ev-" + semantic_digest({"seed": seed, "evidence": evidence})[:24]


def runtime_value(record: dict[str, Any], key: str) -> Any:
    """Read current runtime fields or the legacy top-level representation."""
    runtime = record.get("runtime_metadata") or {}
    return runtime[key] if key in runtime else record.get(key)


def separate_generation_events(record: dict[str, Any]) -> dict[str, Any]:
    """Preserve execution events without labelling them source chronology."""
    for key in ("timeline", "activity_timeline"):
        timeline = record.get(key)
        if not isinstance(timeline, list):
            continue
        events = [dict(item, precision="runtime_timestamp", time_basis="execution_clock")
                  for item in timeline if isinstance(item, dict)
                  and item.get("event_type") in {"condition_generated", "finding_generated"}]
        if events:
            runtime = record.setdefault("runtime_metadata", {})
            runtime["contract_version"] = RUNTIME_VERSION
            runtime[key] = events
            record[key] = [item for item in timeline if not (
                isinstance(item, dict) and item.get("event_type") in
                {"condition_generated", "finding_generated"})]
    return record


def govern_runtime(payload: dict[str, Any], *, identity_contract: str = "execution.v1") -> dict[str, Any]:
    """Encode newly produced v2 output; never call this to replay old records.

    Connector-window v1 and complete-upload v2 establish durable source ownership.
    Other engine invocations own execution correlation, not source identity.
    """
    if identity_contract not in {"execution.v1", "connector-window.v1", "paired-reference.v1", "complete-upload-evidence.v2"}:
        raise ValueError("Unknown identity producer contract")
    source_owned = identity_contract != "execution.v1"
    payload["output_semantics"] = SEMANTICS_VERSION
    payload["identity_contract"] = identity_contract
    runtime = payload.setdefault("runtime_metadata", {})
    runtime["contract_version"] = RUNTIME_VERSION
    aliases = ["generated_at"]
    if not source_owned:
        aliases.extend(["analysis_id", "upload_id"])
    runtime["legacy_root_aliases"] = aliases
    for key in aliases:
        if key in payload:
            runtime[key] = payload[key]
    metadata = payload.get("analysis_metadata", {})
    fields = ["processing_time_seconds"] + ([] if source_owned else ["run_id", "job_id", "upload_id"])
    for key in fields:
        if key in metadata:
            runtime[key] = metadata.pop(key)
    provenance = payload.get("sii_evidence", {}).get("provenance", {})
    if not source_owned:
        for key in ("analysis_run_id", "upload_id"):
            if key in provenance:
                provenance.setdefault("runtime_metadata", runtime_metadata())[key] = provenance.pop(key)
    for field in ("conditions", "insights"):
        for record in payload.get(field, []):
            if isinstance(record, dict):
                separate_generation_events(record)
                consequence = record.get("measurable_consequence")
                if not source_owned and isinstance(consequence, dict) and "analysis_run_id" in consequence:
                    consequence.setdefault("runtime_metadata", runtime_metadata())["analysis_run_id"] = consequence.pop("analysis_run_id")
    return payload
