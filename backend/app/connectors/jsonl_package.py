"""Read-only adapter for Neraium's vendor-neutral telemetry JSONL package.

This module only translates the transport contract into connector boundary
objects. It does not fetch files, resolve mappings, normalize timestamps or
units, persist observations, or invoke analysis.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
import json
import math
import re
from typing import Any, TextIO

from app.connectors.base import ConnectorPage, ConnectorRecordIssue, RawObservationEnvelope
from app.services.telemetry_domain import is_sensitive_telemetry_key


_REQUIRED_FIELDS = ("source", "partition_id", "asset_id", "point_id", "timestamp", "value", "metadata")
_MAX_LINE_BYTES = 256 * 1024
_MAX_METADATA_KEYS = 32
_MAX_METADATA_DEPTH = 4
_MAX_METADATA_VALUE_LENGTH = 2_048
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_PRIVATE_KEY_VALUE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


class JsonlPackageError(ValueError):
    """Deterministic, safe error code for one JSONL record."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _reject_constant(value: str) -> None:
    raise JsonlPackageError(f"nonfinite_json_number:{value.lower()}")


def _text(record: Mapping[str, Any], field: str, *, optional: bool = False) -> str | None:
    value = record.get(field)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 512:
        raise JsonlPackageError(f"{field}_invalid")
    return value.strip()


def _safe_metadata(value: Any, *, depth: int = 0, keys: list[int] | None = None) -> Any:
    if keys is None:
        keys = [0]
    if depth > _MAX_METADATA_DEPTH:
        raise JsonlPackageError("metadata_too_deep")
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if not key or len(key) > 128 or is_sensitive_telemetry_key(key):
                raise JsonlPackageError("metadata_sensitive_or_invalid_key")
            keys[0] += 1
            if keys[0] > _MAX_METADATA_KEYS:
                raise JsonlPackageError("metadata_too_many_keys")
            result[key] = _safe_metadata(item, depth=depth + 1, keys=keys)
        return result
    if isinstance(value, list):
        if len(value) > 64:
            raise JsonlPackageError("metadata_list_too_large")
        return [_safe_metadata(item, depth=depth + 1, keys=keys) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and (
            len(value) > _MAX_METADATA_VALUE_LENGTH
            or _BEARER_VALUE.search(value)
            or _PRIVATE_KEY_VALUE.search(value)
        ):
            raise JsonlPackageError("metadata_sensitive_or_invalid_value")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JsonlPackageError("metadata_nonfinite")
        return value
    raise JsonlPackageError("metadata_value_invalid")


def _observation(record: Mapping[str, Any]) -> RawObservationEnvelope:
    for field in _REQUIRED_FIELDS:
        if field not in record:
            raise JsonlPackageError(f"missing_{field}")
    source = _text(record, "source")
    partition_id = _text(record, "partition_id")
    asset_id = _text(record, "asset_id")
    point_id = _text(record, "point_id")
    timestamp = record["timestamp"]
    if not isinstance(timestamp, str) or not timestamp.strip() or len(timestamp) > 512:
        raise JsonlPackageError("timestamp_invalid")
    value = record["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise JsonlPackageError("unsupported_value_type")
    metadata = _safe_metadata(record["metadata"])
    if not isinstance(metadata, Mapping):
        raise JsonlPackageError("metadata_invalid")

    source_metadata: dict[str, Any] = {
        "source": source,
        "partition_id": partition_id,
        "asset_id": asset_id,
        "asset_name": _text(record, "asset_name", optional=True),
        "location_id": _text(record, "location_id", optional=True),
        "point_type": _text(record, "point_type", optional=True),
        "point_category": _text(record, "point_category", optional=True),
        "metadata": metadata,
    }
    unit = _text(record, "unit", optional=True)
    quality = _text(record, "quality", optional=True)
    return RawObservationEnvelope(
        external_tag_id=point_id or "",
        external_tag_name=_text(record, "point_name", optional=True) or point_id or "",
        source_timestamp=timestamp,
        raw_value=value,
        reported_unit=unit,
        reported_quality=quality,
        metadata=source_metadata,
    )


def _records(source: str | Path | TextIO) -> tuple[Iterable[str], int]:
    if isinstance(source, (str, Path)):
        # Opening a caller-supplied local path is the only I/O this parser does.
        handle = Path(source).open("r", encoding="utf-8")
        return handle, -1
    if not hasattr(source, "read"):
        raise TypeError("jsonl_source_must_be_path_or_text_stream")
    return source, -1


def load_jsonl_connector_page(source: str | Path | TextIO) -> ConnectorPage:
    """Load one local JSONL package into a single immutable connector page.

    Invalid lines are represented as bounded connector issues so valid sibling
    records remain inspectable. No source-provided path, URL, or command is
    followed or executed.
    """

    stream, _ = _records(source)
    observations: list[RawObservationEnvelope] = []
    issues: list[ConnectorRecordIssue] = []
    response_bytes = 0
    try:
        for index, line in enumerate(stream):
            encoded = line.encode("utf-8")
            response_bytes += len(encoded)
            if len(encoded) > _MAX_LINE_BYTES:
                issues.append(ConnectorRecordIssue(index, "line_too_large"))
                continue
            try:
                record = json.loads(line, parse_constant=_reject_constant)
                if not isinstance(record, dict):
                    raise JsonlPackageError("record_must_be_object")
                observations.append(_observation(record))
            except (json.JSONDecodeError, UnicodeEncodeError):
                issues.append(ConnectorRecordIssue(index, "malformed_json"))
            except (JsonlPackageError, ValueError) as error:
                code = getattr(error, "code", str(error))
                issues.append(ConnectorRecordIssue(index, code[:128]))
    finally:
        if isinstance(source, (str, Path)):
            stream.close()
    return ConnectorPage(
        observations=tuple(observations),
        issues=tuple(issues),
        pages_read=1,
        response_bytes=response_bytes,
    )


__all__ = ["JsonlPackageError", "load_jsonl_connector_page"]
