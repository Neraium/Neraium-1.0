from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import resource
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable

from app.services.dataset_scope import attach_dataset_scope, current_dataset_scope
from app.services.telemetry_classification import build_telemetry_signal_catalog
from app.services.upload_state_repository import (
    read_local_json,
    read_shared_state_pure,
    persist_immutable_derived_artifact,
    restore_immutable_derived_artifact,
    restore_upload_source,
    runtime_state,
    write_local_json,
    write_shared_state,
)
from app.services.upload_parser import json_payload_to_csv_text
from app.services.upload_validator import detect_delimiter, looks_like_header, normalized_columns, row_tokens


CONTRACT_VERSION = "historical-ingestion-trust/v1"
CANONICAL_VERSION = "historical-canonical-dataset/v1"
PARSER_VERSION = "historical-delimited-parser/v1"
MAPPING_VERSION = "industrial-semantic-rules/v1"
UNIT_VERSION = "industrial-units/v1"
QUALITY_VERSION = "historical-signal-quality/v1"
CONFIGURATION_VERSION = "configuration-boundaries/v1"
IDENTITY_VERSION = "historical-dataset-identity/v1"
MAX_PROFILE_SAMPLES = 4096
MAX_DISTINCT_VALUES_PER_SIGNAL = 4097
MAX_REVIEW_HISTORY = 500
MAX_NEAR_DUPLICATE_COMPARISONS = 4000
MAX_CORRELATION_MAPPING_COMPARISONS = 2000
MAX_ANALYSIS_CELLS = 2_000_000
JSON_TABULARIZATION_VERSION = "historical-json-tabularization/v1"

SUPPORTED_ROLES = (
    "process_variable",
    "process_rate",
    "flow",
    "pressure",
    "differential_pressure",
    "temperature",
    "return_temperature",
    "supply_temperature",
    "environmental_temperature",
    "power",
    "energy",
    "valve_command",
    "valve_position",
    "pump_status",
    "equipment_state",
    "speed",
    "frequency",
    "setpoint",
    "demand",
    "load",
    "control_command",
)

CANONICAL_UNITS = {
    "degF": "degC",
    "degC": "degC",
    "psi": "kPa",
    "kPa": "kPa",
    "bar": "kPa",
    "gpm": "L/s",
    "L/s": "L/s",
    "L/min": "L/s",
    "m3/h": "L/s",
    "W": "kW",
    "kW": "kW",
    "MW": "kW",
    "kWh": "kWh",
    "%": "%",
    "fraction": "%",
    "RPM": "RPM",
    "Hz": "Hz",
}

ROLE_UNIT_FAMILIES = {
    "temperature": "temperature",
    "return_temperature": "temperature",
    "supply_temperature": "temperature",
    "environmental_temperature": "temperature",
    "pressure": "pressure",
    "differential_pressure": "pressure",
    "flow": "flow",
    "power": "power",
    "energy": "energy",
    "valve_command": "percentage",
    "valve_position": "percentage",
    "load": "percentage",
    "demand": "percentage_or_power",
    "speed": "speed",
    "frequency": "frequency",
    "control_command": "percentage",
}

UNIT_FAMILIES = {
    "degF": "temperature",
    "degC": "temperature",
    "psi": "pressure",
    "kPa": "pressure",
    "bar": "pressure",
    "gpm": "flow",
    "L/s": "flow",
    "L/min": "flow",
    "m3/h": "flow",
    "W": "power",
    "kW": "power",
    "MW": "power",
    "kWh": "energy",
    "%": "percentage",
    "fraction": "percentage",
    "RPM": "speed",
    "Hz": "frequency",
}

UNIT_PATTERNS = (
    ("degF", re.compile(r"(?:°\s*f\b|\bdeg\s*f\b|\bfahrenheit\b|(?:^|[_\s(\[])f(?:$|[_\s)\]]))", re.I)),
    ("degC", re.compile(r"(?:°\s*c\b|\bdeg\s*c\b|\bcelsius\b|(?:^|[_\s(\[])c(?:$|[_\s)\]]))", re.I)),
    ("kPa", re.compile(r"\bkpa\b", re.I)),
    ("psi", re.compile(r"\bpsi\b", re.I)),
    ("bar", re.compile(r"\bbar\b", re.I)),
    ("gpm", re.compile(r"\bgpm\b", re.I)),
    ("L/s", re.compile(r"\b(?:l/s|lps|lit(?:er|re)s?\s*/\s*s)\b", re.I)),
    ("L/min", re.compile(r"\b(?:l/min|lpm)\b", re.I)),
    ("m3/h", re.compile(r"\b(?:m3/h|m\^3/h|m³/h)\b", re.I)),
    ("MW", re.compile(r"\bmw\b", re.I)),
    ("kW", re.compile(r"\bkw\b", re.I)),
    ("W", re.compile(r"(?:^|[_\s(\[])w(?:$|[_\s)\]])", re.I)),
    ("kWh", re.compile(r"\bkwh\b", re.I)),
    ("%", re.compile(r"%|\bpct\b|\bpercent(?:age)?\b", re.I)),
    ("fraction", re.compile(r"\bfraction\b|\bratio_0_1\b", re.I)),
    ("RPM", re.compile(r"\brpm\b", re.I)),
    ("Hz", re.compile(r"\bhz\b", re.I)),
)

TIMESTAMP_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)

TIMESTAMP_NAME_TOKENS = {"timestamp", "time", "datetime", "date", "logged", "recorded", "created"}
IDENTITY_NAME_TOKENS = {"asset", "equipment", "device", "system", "zone", "room", "location", "id"}
MISSING_TOKENS = {"", "null", "none", "n/a", "na", "-", "missing"}
NONFINITE_TOKENS = {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return text[:48] or "signal"


def _tokens(value: str) -> set[str]:
    return {item for item in re.split(r"[^a-z0-9]+", str(value or "").lower()) if item}


def _canonical_signal_id(column: str, index: int, role: str | None) -> str:
    seed = {"column": str(column).strip().lower(), "index": index, "role": role or "unresolved"}
    return f"sig_{_slug(column)}_{_digest(seed)[:8]}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scope_root(*, create: bool = True) -> Path:
    scope = current_dataset_scope()
    root = runtime_state().runtime_dir / "historical_ingestion" / "scopes" / scope.storage_id
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def preserve_raw_source(path: Path, *, source_sha256: str) -> dict[str, Any]:
    target_dir = _scope_root() / "raw"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source_sha256}.source"
    if not target.exists():
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(delete=False, dir=target_dir) as output, path.open("rb") as source:
                temporary = Path(output.name)
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    if file_sha256(target) != source_sha256:
        raise RuntimeError("immutable_raw_source_digest_mismatch")
    try:
        target.chmod(0o440)
    except OSError:
        pass
    return {
        "backend": "scoped_local_immutable",
        "artifact_id": source_sha256,
        "sha256": source_sha256,
        "byte_count": path.stat().st_size,
        "immutable": True,
    }


def _raw_artifact_path(reference: dict[str, Any]) -> Path:
    artifact_id = str(reference.get("artifact_id") or "")
    if not re.fullmatch(r"[a-f0-9]{64}", artifact_id):
        raise ValueError("invalid_raw_artifact_reference")
    path = _scope_root(create=False) / "raw" / f"{artifact_id}.source"
    if not path.is_file():
        raise FileNotFoundError("raw_source_not_available")
    return path


def prepare_tabular_source(
    path: str | os.PathLike[str],
    *,
    filename: str,
    source_sha256: str | None = None,
) -> tuple[Path, dict[str, Any] | None]:
    """Return a deterministic tabular derivative while leaving the source untouched."""
    source_path = Path(path)
    if Path(filename).suffix.lower() != ".json" and source_path.suffix.lower() != ".json":
        return source_path, None
    raw_sha256 = source_sha256 or file_sha256(source_path)
    csv_bytes = json_payload_to_csv_text(source_path.read_bytes()).encode("utf-8")
    derivative_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    target_dir = _scope_root() / "prepared_sources"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{raw_sha256}-{derivative_sha256}.csv"
    if not target.exists():
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(delete=False, dir=target_dir) as output:
                temporary = Path(output.name)
                output.write(csv_bytes)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    if file_sha256(target) != derivative_sha256:
        raise RuntimeError("prepared_source_digest_mismatch")
    return target, {
        "type": "json_to_tabular_csv",
        "version": JSON_TABULARIZATION_VERSION,
        "input_sha256": raw_sha256,
        "output_sha256": derivative_sha256,
        "lossless_raw_source_preserved": True,
        "limitations": [
            "The canonical table is a derived projection of JSON records; the immutable raw JSON remains authoritative."
        ],
    }


def _canonical_artifact_path(dataset_identity: str, *, create: bool = True) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", dataset_identity):
        raise ValueError("invalid_canonical_dataset_identity")
    directory = _scope_root(create=create) / "canonical"
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{dataset_identity}.jsonl"


def _ingestion_state_name(dataset_id: str) -> str:
    clean_dataset_id = str(dataset_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", clean_dataset_id):
        raise ValueError("invalid_historical_ingestion_dataset_id")
    return f"scopes/{current_dataset_scope().storage_id}/historical-ingestion/v1/{clean_dataset_id}"


def persist_ingestion_record(record: dict[str, Any]) -> dict[str, Any]:
    dataset_id = str(record.get("dataset_id") or "")
    if not dataset_id:
        raise ValueError("dataset_id_required")
    normalized = attach_dataset_scope(dict(record), dataset_id=dataset_id)
    name = _ingestion_state_name(dataset_id)
    write_local_json(f"{name}.json", normalized)
    write_shared_state(name, normalized)
    return normalized


def read_ingestion_record(dataset_id: str) -> dict[str, Any] | None:
    name = _ingestion_state_name(dataset_id)
    payload = read_shared_state_pure(name) or read_local_json(f"{name}.json")
    if not isinstance(payload, dict):
        return None
    scope = payload.get("dataset_scope") if isinstance(payload.get("dataset_scope"), dict) else {}
    current = current_dataset_scope().as_dict()
    if any(scope.get(key) != current.get(key) for key in ("tenant_id", "user_id", "workspace_id")):
        return None
    return payload if str(payload.get("dataset_id") or "") == str(dataset_id) else None


def _read_delimited_header(path: Path) -> tuple[str, bool, list[str], int]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample_lines: list[str] = []
        while len(sample_lines) < 20 and sum(len(item) for item in sample_lines) < 65536:
            line = handle.readline()
            if line == "":
                break
            if line.strip():
                sample_lines.append(line.rstrip("\r\n"))
    if not sample_lines:
        raise ValueError("Historical source is empty.")
    delimiter = detect_delimiter("\n".join(sample_lines))
    if delimiter == "whitespace":
        explicit_counts = {candidate: sample_lines[0].count(candidate) for candidate in (",", "\t", ";", "|")}
        candidate, count = max(explicit_counts.items(), key=lambda item: item[1])
        if count > 0:
            delimiter = candidate
    first = row_tokens(sample_lines[0], delimiter)
    header_present = looks_like_header(first)
    if not header_present and len(sample_lines) > 1:
        second = row_tokens(sample_lines[1], delimiter)
        first_data_like = sum(
            1 for value in first
            if _parse_number(value)[1] == "numeric" or _parse_timestamp(value)[0] is not None
        )
        second_data_like = sum(
            1 for value in second
            if _parse_number(value)[1] == "numeric" or _parse_timestamp(value)[0] is not None
        )
        alphabetic_headers = sum(1 for value in first if re.search(r"[A-Za-z]", value))
        explicit_timestamp_header = any(_tokens(value) & TIMESTAMP_NAME_TOKENS for value in first)
        header_present = bool(
            (explicit_timestamp_header and second_data_like >= 1)
            or (
                alphabetic_headers >= max(1, len(first) // 2)
                and second_data_like > first_data_like
                and len(second) == len(first)
            )
        )
    return delimiter, header_present, normalized_columns(first, header_present=header_present), len(first)


def _iter_source_rows(
    path: Path,
    *,
    delimiter: str,
    header_present: bool,
    column_count: int,
) -> Iterable[tuple[int, list[str] | None, str | None]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        if delimiter == "whitespace":
            source_number = 0
            header_skipped = not header_present
            for line in handle:
                if not header_skipped:
                    header_skipped = True
                    continue
                source_number += 1
                if not line.strip():
                    yield source_number, None, "blank_row"
                    continue
                values = line.strip().split()
                yield source_number, values if len(values) == column_count else None, None if len(values) == column_count else "column_count_mismatch"
            return

        reader = csv.reader(handle, delimiter=delimiter)
        if header_present:
            next(reader, None)
        for source_number, values in enumerate(reader, start=1):
            if not values or all(not str(value).strip() for value in values):
                yield source_number, None, "blank_row"
            elif len(values) != column_count:
                yield source_number, None, "column_count_mismatch"
            else:
                yield source_number, [str(value).strip() for value in values], None


def _parse_timestamp(value: str) -> tuple[datetime | None, str | None, bool]:
    text = str(value or "").strip()
    if not text:
        return None, None, False
    normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed, "iso8601", parsed.tzinfo is not None
    except ValueError:
        pass
    matches: list[tuple[datetime, str]] = []
    for format_string in TIMESTAMP_FORMATS:
        try:
            matches.append((datetime.strptime(text, format_string), format_string))
        except ValueError:
            continue
    if not matches:
        return None, None, False
    unique = {(item[0].year, item[0].month, item[0].day, item[0].hour, item[0].minute, item[0].second) for item in matches}
    if len(unique) > 1 and "/" in text:
        return None, "ambiguous_day_month", False
    parsed, format_string = matches[0]
    return parsed, format_string, parsed.tzinfo is not None


def _canonical_timestamp(parsed: datetime | None) -> str | None:
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.isoformat()
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_sort_key(parsed: datetime | None) -> tuple[int, str]:
    if parsed is None:
        return (1, "")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return (0, parsed.isoformat())


def _timestamp_candidates(columns: list[str], sample_rows: list[list[str]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, column in enumerate(columns):
        name_tokens = _tokens(column)
        name_strength = 1.0 if "timestamp" in name_tokens or "datetime" in name_tokens else 0.75 if name_tokens & TIMESTAMP_NAME_TOKENS else 0.0
        if not name_strength and not any(
            any(character.isdigit() for character in value) and any(marker in value for marker in ("-", "/", ":", "T"))
            for value in (row[index].strip() for row in sample_rows[:24] if index < len(row))
        ):
            continue
        observed = 0
        parsed_count = 0
        aware_count = 0
        formats: Counter[str] = Counter()
        for row in sample_rows:
            value = row[index].strip() if index < len(row) else ""
            if not value:
                continue
            observed += 1
            parsed, detected_format, aware = _parse_timestamp(value)
            if parsed is not None:
                parsed_count += 1
                aware_count += int(aware)
                formats[detected_format or "unknown"] += 1
        parse_ratio = parsed_count / max(1, observed)
        score = round(parse_ratio * 0.8 + name_strength * 0.2, 6)
        if parse_ratio >= 0.5 or name_strength:
            candidates.append({
                "source_column": column,
                "source_column_index": index,
                "score": score,
                "parse_ratio": round(parse_ratio, 6),
                "observed_count": observed,
                "parsed_count": parsed_count,
                "timezone_aware_count": aware_count,
                "timezone_absent_count": max(0, parsed_count - aware_count),
                "formats": [{"format": key, "count": value} for key, value in sorted(formats.items())],
                "name_evidence": sorted(name_tokens & TIMESTAMP_NAME_TOKENS),
            })
    return sorted(candidates, key=lambda item: (-item["score"], item["source_column_index"]))


def _select_timestamp(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    if not candidates or candidates[0]["parse_ratio"] < 0.6:
        return None, ["No column had enough defensible timestamp evidence."]
    top = candidates[0]
    if len(candidates) > 1:
        second = candidates[1]
        if second["parse_ratio"] >= 0.8 and abs(float(top["score"]) - float(second["score"])) < 0.08:
            return None, [f"Multiple timestamp columns are plausible: {top['source_column']} and {second['source_column']}. Review is required."]
    return top, [f"Selected {top['source_column']} from parse success and timestamp-specific name evidence."]


def _header_unit(column: str) -> tuple[str | None, list[str]]:
    matches = [unit for unit, pattern in UNIT_PATTERNS if pattern.search(str(column or ""))]
    matches = list(dict.fromkeys(matches))
    return (matches[0] if len(matches) == 1 else None), matches


def _value_unit(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for unit, pattern in UNIT_PATTERNS:
        if pattern.search(text):
            return unit
    return None


def _parse_number(value: Any) -> tuple[float | None, str]:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered in MISSING_TOKENS:
        return None, "missing"
    if lowered in NONFINITE_TOKENS:
        return None, "nonfinite"
    cleaned = text.replace(",", "").strip()
    try:
        direct = float(cleaned)
    except ValueError:
        direct = None
    if direct is not None:
        return (direct, "numeric") if math.isfinite(direct) else (None, "nonfinite")
    for _, pattern in UNIT_PATTERNS:
        cleaned = pattern.sub("", cleaned).strip()
    cleaned = cleaned.replace("°", "").strip()
    if not re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", cleaned):
        return None, "nonnumeric"
    try:
        number = float(cleaned)
    except ValueError:
        return None, "nonnumeric"
    return (number, "numeric") if math.isfinite(number) else (None, "nonfinite")


def _semantic_mapping(column: str, profile: dict[str, Any], unit: str | None, *, header_present: bool) -> dict[str, Any]:
    tokens = _tokens(column)
    reasons: list[str] = []
    conflicts: list[str] = []
    alternatives: list[dict[str, Any]] = []
    role: str | None = None
    confidence = "low"
    state = "unresolved"

    def contains(*values: str) -> bool:
        return any(value in tokens for value in values)

    temperature = contains("temp", "temperature", "sat", "rat", "oat") or unit in {"degF", "degC"}
    if temperature and contains("supply", "leaving", "discharge", "sat"):
        role, confidence = "supply_temperature", "high"
        reasons.append("The name combines explicit supply/leaving/discharge and temperature evidence.")
    elif temperature and contains("return", "entering", "rat"):
        role, confidence = "return_temperature", "high"
        reasons.append("The name combines explicit return/entering and temperature evidence.")
    elif temperature and contains("outside", "outdoor", "ambient", "weather", "oat"):
        role, confidence = "environmental_temperature", "high"
        reasons.append("The name combines explicit environmental and temperature evidence.")
    elif temperature:
        role, confidence = "temperature", "high" if contains("temp", "temperature") else "medium"
        reasons.append("Temperature is supported by an explicit name or unit token.")
    elif contains("differential", "diff", "delta", "dp") and contains("pressure", "press", "dp"):
        role, confidence = "differential_pressure", "high"
        reasons.append("The name explicitly describes differential pressure.")
    elif contains("pressure", "press") or unit in {"psi", "kPa", "bar"}:
        role, confidence = "pressure", "high" if contains("pressure", "press") else "medium"
        reasons.append("Pressure is supported by an explicit name or unit token.")
    elif contains("flow", "gpm", "lps") or unit in {"gpm", "L/s", "L/min", "m3/h"}:
        role, confidence = "flow", "high" if contains("flow") else "medium"
        reasons.append("Flow is supported by an explicit name or unit token.")
    elif contains("energy", "kwh") or unit == "kWh":
        role, confidence = "energy", "high"
        reasons.append("Energy is explicitly named or unit-qualified.")
    elif contains("power", "kw", "watt") or unit in {"W", "kW", "MW"}:
        role, confidence = "power", "high" if contains("power") else "medium"
        reasons.append("Power is supported by an explicit name or unit token.")
    elif contains("valve") and contains("command", "cmd", "output", "ao"):
        role, confidence = "valve_command", "high"
        reasons.append("The tag explicitly combines valve and command/output evidence.")
    elif contains("valve") and contains("position", "feedback", "pos"):
        role, confidence = "valve_position", "high"
        reasons.append("The tag explicitly combines valve and position/feedback evidence.")
    elif contains("pump") and contains("status", "running", "run", "proof", "enable"):
        role, confidence = "pump_status", "high"
        reasons.append("The tag explicitly combines pump and state/status evidence.")
    elif tokens & IDENTITY_NAME_TOKENS and int(profile.get("distinct_count") or 0) <= 32:
        role, confidence = "equipment_state", "high"
        reasons.append("The explicit equipment/asset identifier and bounded cardinality support configuration context only.")
    elif contains("state", "status", "mode", "stage", "staging", "lead", "lag", "configuration", "config", "enabled", "enable") and int(profile.get("distinct_count") or 0) <= 32:
        role, confidence = "equipment_state", "high" if contains("state", "status", "mode", "stage", "staging", "lead", "lag", "configuration", "config") else "medium"
        reasons.append("The name and low cardinality support an equipment-state interpretation.")
    elif contains("setpoint", "set", "sp"):
        role, confidence = "setpoint", "high" if contains("setpoint") else "medium"
        reasons.append("The name contains setpoint evidence.")
    elif contains("frequency", "freq") or unit == "Hz":
        role, confidence = "frequency", "high"
        reasons.append("Frequency is explicitly named or unit-qualified.")
    elif contains("speed", "rpm") or unit == "RPM":
        role, confidence = "speed", "high"
        reasons.append("Speed is explicitly named or unit-qualified.")
    elif contains("demand"):
        role, confidence = "demand", "high"
        reasons.append("Demand is explicitly named.")
    elif contains("load"):
        role, confidence = "load", "high"
        reasons.append("Load is explicitly named.")
    elif contains("command", "cmd", "output"):
        role, confidence = "control_command", "medium"
        reasons.append("The name indicates a control command but does not identify a specific actuator.")
    elif profile.get("numeric_count", 0) >= 3 and not header_present:
        role, confidence = "process_variable", "low"
        reasons.append("Headerless numeric data is retained only as a generic process variable; no physical meaning is claimed.")
    elif profile.get("numeric_count", 0) >= 3 and re.fullmatch(r"(?:column|tag|point|signal)[_\s-]*\d+", column, re.I):
        role, confidence = "process_variable", "low"
        reasons.append("The generated numeric column is retained only as a generic process variable.")
    elif profile.get("numeric_count", 0) >= 3:
        role, confidence = "process_variable", "medium"
        reasons.append("The column is consistently numeric, so it can support unit-independent relationship analysis without a physical claim.")
        alternatives.append({"role": None, "reason": "The physical signal meaning remains unresolved."})

    expected_family = ROLE_UNIT_FAMILIES.get(role or "")
    actual_family = UNIT_FAMILIES.get(unit or "")
    if expected_family and actual_family and expected_family != actual_family and not (
        expected_family == "percentage_or_power" and actual_family in {"percentage", "power"}
    ):
        conflicts.append(f"The proposed {role} role conflicts with the explicit {unit} unit.")
        alternatives.append({"role": None, "reason": "Resolve the role/unit dimensional conflict."})
        confidence = "low"
        state = "ambiguous"
    elif role and confidence == "high":
        state = "confidently_mapped"
    elif role:
        state = "provisionally_mapped"
    else:
        alternatives.extend({"role": candidate, "reason": "Supported role available for human review."} for candidate in ("process_variable", "equipment_state"))

    return {
        "proposed_canonical_role": role,
        "mapping_confidence": confidence,
        "mapping_state": state,
        "supporting_reasons": reasons,
        "conflicting_evidence": conflicts,
        "alternatives": alternatives[:5],
        "review_required": state in {"ambiguous", "unresolved"},
        "mapping_rule_version": MAPPING_VERSION,
    }


def _unit_profile(column: str, observed_units: Counter[str], mapping: dict[str, Any]) -> dict[str, Any]:
    header_unit, header_matches = _header_unit(column)
    value_units = sorted(observed_units)
    warnings: list[str] = []
    inferred: str | None = None
    confidence = "unavailable"
    status = "unresolved"
    if len(header_matches) > 1:
        warnings.append(f"Multiple unit tokens were found in the source header: {', '.join(header_matches)}.")
    elif header_unit and value_units and any(unit != header_unit for unit in value_units):
        warnings.append(f"Header unit {header_unit} conflicts with value suffixes: {', '.join(value_units)}.")
        status = "conflict"
    elif header_unit:
        inferred, confidence, status = header_unit, "high", "identified"
    elif len(value_units) == 1:
        inferred, confidence, status = value_units[0], "high", "identified"
    elif len(value_units) > 1:
        warnings.append(f"Values contain inconsistent unit suffixes: {', '.join(value_units)}.")
        status = "conflict"

    role = mapping.get("proposed_canonical_role")
    expected_family = ROLE_UNIT_FAMILIES.get(str(role or ""))
    actual_family = UNIT_FAMILIES.get(str(inferred or ""))
    if expected_family and actual_family and expected_family != actual_family and not (
        expected_family == "percentage_or_power" and actual_family in {"percentage", "power"}
    ):
        warnings.append(f"Unit {inferred} is dimensionally inconsistent with role {role}.")
        status = "conflict"
        confidence = "low"
    canonical = CANONICAL_UNITS.get(inferred or "") if status == "identified" else None
    formula = _conversion_formula(inferred, canonical) if inferred and canonical else None
    return {
        "original_unit": header_unit,
        "observed_value_units": value_units,
        "inferred_unit": inferred,
        "normalized_unit": canonical,
        "unit_status": status,
        "unit_confidence": confidence,
        "conversion_formula": formula,
        "conversion_version": UNIT_VERSION if formula else None,
        "warnings": warnings,
        "review_required": status in {"conflict", "unresolved"} and expected_family is not None,
    }


def _conversion_formula(source: str | None, target: str | None) -> str | None:
    formulas = {
        ("degF", "degC"): "(x - 32) * 5 / 9",
        ("psi", "kPa"): "x * 6.894757293168",
        ("bar", "kPa"): "x * 100",
        ("gpm", "L/s"): "x * 0.0630901964",
        ("L/min", "L/s"): "x / 60",
        ("m3/h", "L/s"): "x / 3.6",
        ("W", "kW"): "x / 1000",
        ("MW", "kW"): "x * 1000",
        ("fraction", "%"): "x * 100",
    }
    if source == target:
        return "x"
    return formulas.get((source or "", target or ""))


def _unit_matches_role(role: str | None, unit: str | None) -> bool:
    expected_family = ROLE_UNIT_FAMILIES.get(str(role or ""))
    actual_family = UNIT_FAMILIES.get(str(unit or ""))
    if not expected_family or not actual_family:
        return True
    return expected_family == actual_family or (
        expected_family == "percentage_or_power" and actual_family in {"percentage", "power"}
    )


def _convert_value(value: float, source: str | None, target: str | None) -> float:
    if source == target or not source or not target:
        return value
    converters = {
        ("degF", "degC"): lambda x: (x - 32.0) * 5.0 / 9.0,
        ("psi", "kPa"): lambda x: x * 6.894757293168,
        ("bar", "kPa"): lambda x: x * 100.0,
        ("gpm", "L/s"): lambda x: x * 0.0630901964,
        ("L/min", "L/s"): lambda x: x / 60.0,
        ("m3/h", "L/s"): lambda x: x / 3.6,
        ("W", "kW"): lambda x: x / 1000.0,
        ("MW", "kW"): lambda x: x * 1000.0,
        ("fraction", "%"): lambda x: x * 100.0,
    }
    converter = converters.get((source, target))
    return round(converter(value) if converter else value, 12)


@dataclass
class SignalAccumulator:
    source_column: str
    source_column_index: int
    total_count: int = 0
    missing_count: int = 0
    numeric_count: int = 0
    invalid_numeric_count: int = 0
    nonfinite_count: int = 0
    unexpected_states: Counter[str] = field(default_factory=Counter)
    observed_units: Counter[str] = field(default_factory=Counter)
    values: list[float] = field(default_factory=list)
    sample_positions: list[int] = field(default_factory=list)
    distinct: set[str] = field(default_factory=set)
    distinct_count_bounded: bool = False
    longest_missing_run: int = 0
    current_missing_run: int = 0
    longest_constant_run: int = 0
    current_constant_run: int = 0
    previous_value: float | None = None
    negative_jumps: int = 0
    discontinuities: int = 0
    full_value_hasher: Any = field(default_factory=hashlib.sha256, repr=False)

    def add(self, raw: str, row_index: int, *, sample_stride: int) -> None:
        self.total_count += 1
        encoded = str(raw).encode("utf-8", errors="replace")
        self.full_value_hasher.update(len(encoded).to_bytes(8, "big"))
        self.full_value_hasher.update(encoded)
        value, kind = _parse_number(raw)
        if any(character.isalpha() or character in "%°" for character in str(raw)):
            unit = _value_unit(raw)
            if unit:
                self.observed_units[unit] += 1
        if kind == "missing":
            self.missing_count += 1
            self.current_missing_run += 1
            self.longest_missing_run = max(self.longest_missing_run, self.current_missing_run)
            self.current_constant_run = 0
            return
        self.current_missing_run = 0
        if kind == "nonfinite":
            self.nonfinite_count += 1
            return
        if kind != "numeric" or value is None:
            self.invalid_numeric_count += 1
            self.unexpected_states[str(raw)[:80]] += 1
            if len(self.distinct) < MAX_DISTINCT_VALUES_PER_SIGNAL:
                self.distinct.add(f"s:{str(raw)[:80]}")
            else:
                self.distinct_count_bounded = True
            return
        self.numeric_count += 1
        if len(self.distinct) < MAX_DISTINCT_VALUES_PER_SIGNAL:
            self.distinct.add(f"n:{value:.12g}")
        else:
            self.distinct_count_bounded = True
        if len(self.values) < MAX_PROFILE_SAMPLES and (row_index % max(1, sample_stride) == 0 or not self.values):
            self.values.append(value)
            self.sample_positions.append(row_index)
        if self.previous_value is not None:
            if value == self.previous_value:
                self.current_constant_run += 1
            else:
                self.current_constant_run = 1
            self.longest_constant_run = max(self.longest_constant_run, self.current_constant_run)
            if value < self.previous_value:
                self.negative_jumps += 1
        else:
            self.current_constant_run = 1
            self.longest_constant_run = 1
        self.previous_value = value

    def preliminary(self) -> dict[str, Any]:
        return {
            "numeric_count": self.numeric_count,
            "distinct_count": len(self.distinct),
            "distinct_count_bounded": self.distinct_count_bounded,
            "missing_count": self.missing_count,
        }

    def full_value_digest(self) -> str:
        return self.full_value_hasher.hexdigest()

    def profile(self, *, role: str | None, timestamp_coverage_seconds: float | None) -> dict[str, Any]:
        values = self.values
        minimum = min(values) if values else None
        maximum = max(values) if values else None
        average = statistics.fmean(values) if values else None
        std = statistics.pstdev(values) if len(values) > 1 else 0.0 if values else None
        missing_ratio = self.missing_count / max(1, self.total_count)
        invalid_ratio = (self.invalid_numeric_count + self.nonfinite_count) / max(1, self.total_count - self.missing_count)
        near_constant = bool(values and minimum is not None and maximum is not None and (maximum == minimum or float(std or 0) <= max(abs(float(average or 0)) * 1e-6, 1e-9)))
        # A durable operating plateau is not, by itself, a stuck sensor. Require
        # an unchanged run across almost the whole usable sequence; shorter
        # plateaus remain explainable quality observations/configuration evidence.
        stuck = self.longest_constant_run >= max(12, math.ceil(self.numeric_count * 0.9)) and role not in {"equipment_state", "pump_status"}
        endpoint_counts = Counter(values)
        clipping = False
        saturation = False
        if len(values) >= 20 and minimum is not None and maximum is not None and minimum != maximum:
            minimum_fraction = endpoint_counts[minimum] / len(values)
            maximum_fraction = endpoint_counts[maximum] / len(values)
            clipping = minimum_fraction >= 0.1 or maximum_fraction >= 0.1
            saturation = minimum_fraction >= 0.25 or maximum_fraction >= 0.25
        diffs = [abs(current - previous) for previous, current in zip(values, values[1:])]
        median_diff = statistics.median(diffs) if diffs else 0.0
        large_discontinuities = sum(1 for diff in diffs if median_diff > 0 and diff > median_diff * 20)
        spread = (maximum - minimum) if minimum is not None and maximum is not None else 0.0
        noise_ratio = (median_diff / spread) if spread else 0.0
        excessive_noise = len(values) >= 30 and noise_ratio > 0.35
        reset_behavior = role == "energy" and self.negative_jumps >= 1
        unusual = _physical_range_findings(role, minimum, maximum)
        insufficient_reasons: list[str] = []
        if self.numeric_count < 6 and role not in {"equipment_state", "pump_status"}:
            insufficient_reasons.append("Fewer than 6 usable numeric samples were present.")
        if missing_ratio >= 0.8:
            insufficient_reasons.append("At least 80% of source values were missing.")
        if invalid_ratio >= 0.25 and role not in {"equipment_state", "pump_status"}:
            insufficient_reasons.append("At least 25% of populated values were invalid or non-finite.")
        if stuck:
            insufficient_reasons.append("A numeric value remained unchanged for most of the observed series.")
        if timestamp_coverage_seconds is not None and timestamp_coverage_seconds < 300 and self.numeric_count < 12:
            insufficient_reasons.append("Temporal coverage and sample volume are both too limited for relationship analysis.")
        findings: list[dict[str, Any]] = []
        for code, active, detail, interpretation in (
            ("sparse_signal", missing_ratio >= 0.5, f"{missing_ratio:.1%} missing", "quality_limitation"),
            ("long_dropout", self.longest_missing_run >= 6, f"Longest consecutive missing run: {self.longest_missing_run} rows", "quality_limitation"),
            ("stuck_sensor", stuck, f"Longest repeated-value run: {self.longest_constant_run} samples", "quality_limitation"),
            ("near_constant", near_constant, "Observed numeric variability was negligible.", "quality_observation"),
            ("clipping", clipping, "At least one observed endpoint recurred in 10% or more samples.", "quality_observation"),
            ("saturation", saturation, "At least one observed endpoint recurred in 25% or more samples.", "quality_observation"),
            ("reset_behavior", reset_behavior, f"Observed {self.negative_jumps} decrease(s) in an energy-like series.", "quality_observation"),
            ("excessive_noise", excessive_noise, f"Median step/range ratio was {noise_ratio:.3f}.", "quality_observation"),
            ("sudden_discontinuities", large_discontinuities > 0, f"Observed {large_discontinuities} steps above 20 times the median step.", "quality_observation"),
        ):
            if active:
                findings.append({"code": code, "detail": detail, "interpretation": interpretation, "rule_version": QUALITY_VERSION})
        findings.extend(unusual)
        return {
            "total_count": self.total_count,
            "valid_numeric_count": self.numeric_count,
            "missing_count": self.missing_count,
            "missing_fraction": round(missing_ratio, 6),
            "longest_dropout_rows": self.longest_missing_run,
            "invalid_numeric_count": self.invalid_numeric_count,
            "nonfinite_count": self.nonfinite_count,
            "unexpected_string_states": [
                {"value": value, "count": count}
                for value, count in sorted(self.unexpected_states.items(), key=lambda item: (-item[1], item[0]))[:12]
            ],
            "distinct_count": len(self.distinct),
            "distinct_count_bounded": self.distinct_count_bounded,
            "temporal_coverage_seconds": round(timestamp_coverage_seconds, 6) if timestamp_coverage_seconds is not None else None,
            "sufficient_temporal_coverage": timestamp_coverage_seconds is not None and timestamp_coverage_seconds >= 300,
            "minimum": round(minimum, 8) if minimum is not None else None,
            "maximum": round(maximum, 8) if maximum is not None else None,
            "mean": round(average, 8) if average is not None else None,
            "standard_deviation": round(std, 8) if std is not None else None,
            "longest_constant_run": self.longest_constant_run,
            "near_constant": near_constant,
            "stuck": stuck,
            "clipping": clipping,
            "saturation": saturation,
            "reset_behavior": reset_behavior,
            "excessive_noise": excessive_noise,
            "sudden_discontinuity_count": large_discontinuities,
            "findings": findings,
            "relationship_fitness": "insufficient" if insufficient_reasons else "context_only" if role in {"equipment_state", "pump_status"} else "fit_with_limitations" if findings else "fit",
            "relationship_fitness_reasons": insufficient_reasons,
            "quality_rule_version": QUALITY_VERSION,
        }


def _add_correlation_alternatives(
    signal_profiles: list[dict[str, Any]],
    accumulators: list[SignalAccumulator],
) -> None:
    """Add bounded advisory alternatives without promoting a semantic mapping."""

    anchors = [
        index
        for index, signal in enumerate(signal_profiles)
        if signal.get("mapping_state") == "confidently_mapped"
        and signal.get("proposed_canonical_role") not in {None, "equipment_state", "pump_status"}
        and len(accumulators[index].values) >= 12
    ][:8]
    comparisons = 0
    for candidate_index, signal in enumerate(signal_profiles):
        if signal.get("mapping_state") == "confidently_mapped" or int((signal.get("quality") or {}).get("valid_numeric_count") or 0) < 12:
            continue
        candidate = accumulators[candidate_index]
        candidate_values = dict(zip(candidate.sample_positions, candidate.values))
        suggestions: list[tuple[float, int]] = []
        for anchor_index in anchors:
            if comparisons >= MAX_CORRELATION_MAPPING_COMPARISONS:
                break
            comparisons += 1
            if anchor_index == candidate_index:
                continue
            anchor = accumulators[anchor_index]
            anchor_values = dict(zip(anchor.sample_positions, anchor.values))
            positions = sorted(candidate_values.keys() & anchor_values.keys())
            if len(positions) < 12:
                continue
            left = [candidate_values[position] for position in positions]
            right = [anchor_values[position] for position in positions]
            left_mean = statistics.fmean(left)
            right_mean = statistics.fmean(right)
            covariance = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
            denominator = math.sqrt(
                sum((x - left_mean) ** 2 for x in left)
                * sum((y - right_mean) ** 2 for y in right)
            )
            if denominator <= 1e-12:
                continue
            correlation = covariance / denominator
            if abs(correlation) >= 0.98:
                suggestions.append((abs(correlation), anchor_index))
        alternatives = list(signal.get("alternatives") or [])
        existing_roles = {item.get("role") for item in alternatives if isinstance(item, dict)}
        for strength, anchor_index in sorted(suggestions, key=lambda item: (-item[0], item[1])):
            anchor_signal = signal_profiles[anchor_index]
            role = anchor_signal.get("proposed_canonical_role")
            if role in existing_roles:
                continue
            alternatives.append({
                "role": role,
                "confidence": "advisory_only",
                "reason": (
                    f"Observed values correlate at {strength:.3f} with strongly mapped "
                    f"{anchor_signal['source_column']}; correlation does not establish physical identity."
                ),
            })
            existing_roles.add(role)
            if len(alternatives) >= 5:
                break
        signal["alternatives"] = alternatives[:5]
        if comparisons >= MAX_CORRELATION_MAPPING_COMPARISONS:
            break


def _physical_range_findings(role: str | None, minimum: float | None, maximum: float | None) -> list[dict[str, Any]]:
    if minimum is None or maximum is None:
        return []
    ranges = {
        "temperature": (-150, 1000),
        "supply_temperature": (-150, 1000),
        "return_temperature": (-150, 1000),
        "environmental_temperature": (-150, 200),
        "pressure": (-100, 100000),
        "differential_pressure": (-10000, 10000),
        "flow": (0, 1e9),
        "power": (-1e7, 1e9),
        "valve_position": (0, 100),
        "valve_command": (0, 100),
    }
    bounds = ranges.get(str(role or ""))
    if not bounds or (minimum >= bounds[0] and maximum <= bounds[1]):
        return []
    return [{
        "code": "physically_unusual_range",
        "detail": f"Observed range {minimum:g} to {maximum:g} is outside the broad plausibility bound {bounds[0]:g} to {bounds[1]:g} for {role}.",
        "interpretation": "physically_unusual_not_automatically_bad_data",
        "rule_version": QUALITY_VERSION,
    }]


def _timestamp_profile(
    candidates: list[dict[str, Any]],
    selected: dict[str, Any] | None,
    selection_reasons: list[str],
    timestamps: list[tuple[int, datetime, bool, str]],
    *,
    missing_count: int,
    invalid_count: int,
    ambiguous_count: int,
    duplicate_count: int,
    repeated_timestamp_blocks: int,
) -> dict[str, Any]:
    if selected is None:
        return {
            "integrity": "unavailable",
            "selected_column": None,
            "selected_column_index": None,
            "candidates": candidates,
            "selection_reasons": selection_reasons,
            "formats": [],
            "timezone_status": "unavailable",
            "timezone_aware_count": 0,
            "timezone_absent_count": 0,
            "missing_count": missing_count,
            "malformed_or_impossible_count": invalid_count,
            "ambiguous_format_count": ambiguous_count,
            "duplicate_timestamp_count": duplicate_count,
            "out_of_order_count": 0,
            "clock_jump_count": 0,
            "repeated_timestamp_blocks": repeated_timestamp_blocks,
            "monotonic_in_source_order": None,
            "irregular_sampling": None,
            "sampling_interval_distribution": [],
            "median_sampling_interval_seconds": None,
            "large_gap_threshold_seconds": None,
            "large_gaps": [],
            "large_gap_count": 0,
            "dataset_start": None,
            "dataset_end": None,
            "gross_coverage_seconds": None,
            "effective_usable_coverage_seconds": None,
            "warnings": selection_reasons,
            "review_required": bool(candidates),
            "timestamp_rule_version": PARSER_VERSION,
        }
    aware_count = sum(int(item[2]) for item in timestamps)
    naive_count = len(timestamps) - aware_count
    timezone_status = "explicit" if aware_count and not naive_count else "absent" if naive_count and not aware_count else "mixed"
    normalized = [
        item[1].astimezone(timezone.utc).replace(tzinfo=None) if item[1].tzinfo is not None else item[1]
        for item in timestamps
    ]
    source_deltas = [(current - previous).total_seconds() for previous, current in zip(normalized, normalized[1:])]
    positive = [value for value in source_deltas if value > 0]
    interval_counts = Counter(round(value, 6) for value in positive)
    median_interval = statistics.median(positive) if positive else None
    negative_jumps = sum(1 for value in source_deltas if value < 0)
    out_of_order = negative_jumps
    large_gap_threshold = max(3600.0, float(median_interval or 0) * 5.0)
    large_gaps = [
        {"after_source_row": timestamps[index][0], "before_source_row": timestamps[index + 1][0], "seconds": round(delta, 6)}
        for index, delta in enumerate(source_deltas)
        if delta > large_gap_threshold
    ]
    irregular = False
    if positive and median_interval:
        irregular = sum(1 for value in positive if abs(value - median_interval) > max(1.0, median_interval * 0.1)) / len(positive) > 0.1
    ordered = sorted(normalized)
    first = ordered[0] if ordered else None
    last = ordered[-1] if ordered else None
    gross = (last - first).total_seconds() if first and last else 0.0
    gap_seconds = sum(max(0.0, item["seconds"] - float(median_interval or 0)) for item in large_gaps)
    effective = max(0.0, gross - gap_seconds)
    reasons: list[str] = []
    integrity = "high"
    if timezone_status in {"absent", "mixed"}:
        reasons.append("Timestamp timezone is absent or inconsistent; v1 did not assume a site timezone.")
        integrity = "medium"
    if invalid_count or missing_count or duplicate_count or out_of_order or irregular or large_gaps:
        reasons.append("Timestamp defects or irregular sampling were observed and preserved as explicit evidence.")
        integrity = "medium" if (invalid_count + missing_count) / max(1, len(timestamps) + invalid_count + missing_count) < 0.05 and negative_jumps <= 1 else "low"
    return {
        "integrity": integrity,
        "selected_column": selected["source_column"],
        "selected_column_index": selected["source_column_index"],
        "candidates": candidates,
        "selection_reasons": selection_reasons,
        "formats": selected.get("formats", []),
        "timezone_status": timezone_status,
        "timezone_aware_count": aware_count,
        "timezone_absent_count": naive_count,
        "missing_count": missing_count,
        "malformed_or_impossible_count": invalid_count,
        "ambiguous_format_count": ambiguous_count,
        "duplicate_timestamp_count": duplicate_count,
        "out_of_order_count": out_of_order,
        "clock_jump_count": negative_jumps,
        "repeated_timestamp_blocks": repeated_timestamp_blocks,
        "monotonic_in_source_order": out_of_order == 0,
        "irregular_sampling": irregular,
        "sampling_interval_distribution": [
            {"seconds": seconds, "count": count}
            for seconds, count in sorted(interval_counts.items(), key=lambda item: item[0])[:30]
        ],
        "median_sampling_interval_seconds": round(median_interval, 6) if median_interval is not None else None,
        "large_gap_threshold_seconds": round(large_gap_threshold, 6),
        "large_gaps": large_gaps[:200],
        "large_gap_count": len(large_gaps),
        "dataset_start": _canonical_timestamp(first),
        "dataset_end": _canonical_timestamp(last),
        "gross_coverage_seconds": round(gross, 6),
        "effective_usable_coverage_seconds": round(effective, 6),
        "warnings": reasons,
        "review_required": integrity == "low" or timezone_status == "mixed",
        "timestamp_rule_version": PARSER_VERSION,
    }


def _apply_decision(signal: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
    if not decision:
        return signal
    updated = dict(signal)
    action = str(decision.get("mapping_action") or "").strip()
    role = decision.get("canonical_role")
    if action == "exclude":
        updated["mapping_state"] = "excluded"
        updated["included_for_analysis"] = False
        updated["exclusion_reasons"] = ["Excluded by a recorded human review decision."]
        updated["review_required"] = False
    elif action == "leave_unresolved":
        updated["proposed_canonical_role"] = None
        updated["mapping_state"] = "unresolved"
        updated["included_for_analysis"] = False
        updated["review_required"] = False
    elif action in {"accept", "choose_role"}:
        selected_role = updated.get("proposed_canonical_role") if action == "accept" else role
        if selected_role not in SUPPORTED_ROLES:
            raise ValueError(f"Unsupported canonical role: {selected_role}")
        updated["proposed_canonical_role"] = selected_role
        updated["mapping_state"] = "confidently_mapped"
        updated["mapping_confidence"] = "human_confirmed"
        updated["review_required"] = False
        updated["supporting_reasons"] = [*updated.get("supporting_reasons", []), "Confirmed by human review."]
    selected_unit = decision.get("unit")
    if selected_unit is not None:
        if selected_unit not in CANONICAL_UNITS:
            raise ValueError(f"Unsupported unit: {selected_unit}")
        if not _unit_matches_role(updated.get("proposed_canonical_role"), selected_unit):
            raise ValueError(
                f"Unit {selected_unit} is dimensionally inconsistent with role {updated.get('proposed_canonical_role')}."
            )
        unit = dict(updated.get("unit") or {})
        unit.update({
            "inferred_unit": selected_unit,
            "normalized_unit": CANONICAL_UNITS[selected_unit],
            "unit_status": "identified",
            "unit_confidence": "human_confirmed",
            "conversion_formula": _conversion_formula(selected_unit, CANONICAL_UNITS[selected_unit]),
            "conversion_version": UNIT_VERSION,
            "review_required": False,
        })
        updated["unit"] = unit
    updated["canonical_signal_id"] = _canonical_signal_id(
        updated["source_column"], int(updated["source_column_index"]), updated.get("proposed_canonical_role")
    )
    return updated


def _configuration_profile(signal_profiles: list[dict[str, Any]], sample_rows: list[dict[str, Any]], timestamp_column: str | None) -> dict[str, Any]:
    if len(sample_rows) < 12:
        return {
            "status": "insufficient_evidence",
            "boundaries": [],
            "reasons": ["At least 12 ordered rows are required to assess durable configuration changes."],
            "rule_version": CONFIGURATION_VERSION,
        }
    candidates = [
        item for item in signal_profiles
        if item.get("proposed_canonical_role") in {"equipment_state", "pump_status", "setpoint"}
        and item.get("included_for_analysis")
    ]
    if not candidates:
        return {
            "status": "insufficient_evidence",
            "boundaries": [],
            "reasons": ["No included equipment-state, staging, mode, or setpoint signal was available to assess configuration consistency."],
            "evaluated_signal_ids": [],
            "rule_version": CONFIGURATION_VERSION,
        }
    boundaries: list[dict[str, Any]] = []
    persistence = max(3, min(12, len(sample_rows) // 20))
    for signal in candidates:
        column = signal["source_column"]
        values = [str(row.get(column, "")).strip() for row in sample_rows]
        change_count = sum(
            1 for previous, current in zip(values, values[1:])
            if previous and current and previous != current
        )
        if signal.get("proposed_canonical_role") == "pump_status" and change_count > 2:
            # Repeated on/off cycling is operating-state coverage, not by
            # itself evidence of a durable configuration change.
            continue
        for index in range(1, len(values) - persistence):
            previous = values[index - 1]
            current = values[index]
            if not previous or not current or current == previous:
                continue
            following = values[index : index + persistence]
            if sum(value == current for value in following) < persistence:
                continue
            explicit_tokens = _tokens(column) & {
                "configuration", "config", "lead", "lag", "stage", "staging", "mode",
                "asset", "equipment", "device", "system", "id",
            }
            explicit = bool(explicit_tokens)
            boundaries.append({
                "boundary_id": f"cfg_{_digest({'signal': signal['canonical_signal_id'], 'row': index})[:12]}",
                "classification": "explicit_configuration_boundary" if explicit else "possible_configuration_boundary",
                "source_row": sample_rows[index].get("__source_row_number"),
                "timestamp": sample_rows[index].get(timestamp_column) if timestamp_column else None,
                "signal_id": signal["canonical_signal_id"],
                "source_column": column,
                "before": previous,
                "after": current,
                "evidence": f"The new value persisted for at least {persistence} sampled rows.",
                "downstream_requirement": "Analyze configuration regimes separately or include this boundary as explicit operating context.",
            })
            break
    if boundaries:
        status = "explicit_configuration_boundary" if any(item["classification"] == "explicit_configuration_boundary" for item in boundaries) else "possible_configuration_boundary"
        reasons = ["Durable state or setpoint changes indicate more than one possible operating configuration."]
    else:
        status = "no_configuration_concern_detected"
        reasons = ["No durable explicit state or setpoint boundary was found in the profiled sample."]
    return {
        "status": status,
        "boundaries": boundaries,
        "reasons": reasons,
        "evaluated_signal_ids": [item["canonical_signal_id"] for item in candidates],
        "rule_version": CONFIGURATION_VERSION,
    }


def _duplicate_channels(signal_profiles: list[dict[str, Any]], accumulators: list[SignalAccumulator]) -> list[dict[str, Any]]:
    by_digest: defaultdict[str, list[int]] = defaultdict(list)
    for index, accumulator in enumerate(accumulators):
        if accumulator.total_count:
            by_digest[_digest({
                "full_value_digest": accumulator.full_value_digest(),
                "total_count": accumulator.total_count,
            })].append(index)
    findings: list[dict[str, Any]] = []
    compared: set[tuple[int, int]] = set()
    for indexes in by_digest.values():
        if len(indexes) < 2:
            continue
        kept = indexes[0]
        for duplicate in indexes[1:]:
            compared.add((kept, duplicate))
            findings.append({
                "type": "exact_duplicate",
                "left_signal_id": signal_profiles[kept]["canonical_signal_id"],
                "right_signal_id": signal_profiles[duplicate]["canonical_signal_id"],
                "evidence": "The complete source-value sequence fingerprints are identical.",
                "review_required": False,
            })
            signal_profiles[duplicate]["duplicate_of"] = signal_profiles[kept]["canonical_signal_id"]
            signal_profiles[duplicate]["included_for_analysis"] = False
            signal_profiles[duplicate]["mapping_state"] = "excluded"
            signal_profiles[duplicate]["exclusion_reasons"] = ["Redundant exact duplicate of another included channel."]
    buckets: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    for index, signal in enumerate(signal_profiles):
        key = (str(signal.get("proposed_canonical_role") or ""), str((signal.get("unit") or {}).get("normalized_unit") or ""))
        if key[0]:
            buckets[key].append(index)
    comparisons = 0
    for indexes in buckets.values():
        for position, left_index in enumerate(indexes):
            for right_index in indexes[position + 1 : position + 9]:
                if comparisons >= MAX_NEAR_DUPLICATE_COMPARISONS:
                    break
                comparisons += 1
                if (left_index, right_index) in compared:
                    continue
                left_unit = signal_profiles[left_index].get("unit") or {}
                right_unit = signal_profiles[right_index].get("unit") or {}
                left = [
                    _convert_value(value, left_unit.get("inferred_unit"), left_unit.get("normalized_unit"))
                    for value in accumulators[left_index].values
                ]
                right = [
                    _convert_value(value, right_unit.get("inferred_unit"), right_unit.get("normalized_unit"))
                    for value in accumulators[right_index].values
                ]
                size = min(len(left), len(right))
                if size < 12:
                    continue
                differences = [abs(left[i] - right[i]) for i in range(size)]
                scale = max(max(abs(value) for value in left[:size] + right[:size]), 1.0)
                if statistics.fmean(differences) / scale <= 0.001:
                    findings.append({
                        "type": "nearly_duplicate",
                        "left_signal_id": signal_profiles[left_index]["canonical_signal_id"],
                        "right_signal_id": signal_profiles[right_index]["canonical_signal_id"],
                        "evidence": "Compatible-role sampled values differ by no more than 0.1% of scale on average.",
                        "review_required": True,
                    })
            if comparisons >= MAX_NEAR_DUPLICATE_COMPARISONS:
                break
    return findings


def _trust_dimensions(
    timestamp: dict[str, Any],
    signals: list[dict[str, Any]],
    configuration: dict[str, Any],
    readiness: dict[str, Any],
) -> list[dict[str, Any]]:
    mapped = [item for item in signals if item.get("mapping_state") == "confidently_mapped"]
    provisional = [item for item in signals if item.get("mapping_state") == "provisionally_mapped"]
    unresolved = [
        item
        for item in signals
        if item.get("mapping_state") in {"ambiguous", "unresolved"}
        or item.get("review_required")
    ]
    unit_conflicts = [item for item in signals if (item.get("unit") or {}).get("unit_status") == "conflict"]
    missing_heavy = [item for item in signals if float((item.get("quality") or {}).get("missing_fraction") or 0) >= 0.5]
    unfit = [item for item in signals if (item.get("quality") or {}).get("relationship_fitness") == "insufficient"]
    return [
        _dimension("timestamp_integrity", timestamp.get("integrity", "unavailable"), timestamp.get("warnings", []), ["timestamp_profile"], timestamp.get("review_required", False)),
        _dimension(
            "semantic_mapping_confidence",
            "high" if signals and not unresolved and not provisional else "medium" if mapped or provisional else "low",
            [f"{len(mapped)} confidently mapped; {len(provisional)} provisional; {len(unresolved)} require semantic review."],
            ["signal_profiles.mapping_state", "signal_profiles.supporting_reasons", "signal_profiles.conflicting_evidence"],
            bool(unresolved),
        ),
        _dimension("unit_confidence", "low" if unit_conflicts else "medium" if any((item.get("unit") or {}).get("unit_status") == "unresolved" for item in signals) else "high", [f"{len(unit_conflicts)} unit conflict(s) were found."], ["signal_profiles.unit"], bool(unit_conflicts)),
        _dimension("missing_data_burden", "low" if not missing_heavy else "high", [f"{len(missing_heavy)} signal(s) are at least 50% missing."], ["signal_profiles.quality"], bool(missing_heavy)),
        _dimension("signal_quality_fitness", "low" if unfit else "medium" if any((item.get("quality") or {}).get("findings") for item in signals) else "high", [f"{len(unfit)} signal(s) are insufficient for relationship analysis."], ["signal_profiles.quality"], bool(unfit)),
        _dimension("operating_state_coverage", "medium" if configuration.get("status") != "insufficient_evidence" else "unavailable", configuration.get("reasons", []), ["configuration_profile"], configuration.get("status") == "insufficient_evidence"),
        _dimension("configuration_consistency", "low" if configuration.get("status") == "explicit_configuration_boundary" else "medium" if configuration.get("status") == "possible_configuration_boundary" else "high" if configuration.get("status") == "no_configuration_concern_detected" else "unavailable", configuration.get("reasons", []), ["configuration_profile.boundaries"], configuration.get("status") in {"explicit_configuration_boundary", "possible_configuration_boundary"}),
        _dimension("analysis_readiness", readiness.get("outcome", "review_required"), readiness.get("reasons", []), ["readiness"], readiness.get("outcome") == "review_required"),
    ]


def _dimension(name: str, status: str, reasons: list[str], evidence: list[str], review: bool) -> dict[str, Any]:
    return {
        "dimension": name,
        "status": status,
        "reasons": reasons,
        "evidence_references": evidence,
        "limitations": reasons if review or status in {"unavailable", "review_required", "insufficient_trustworthy_data"} else [],
        "review_requirement": "review_required" if review else "none",
    }


def _readiness(timestamp: dict[str, Any], signals: list[dict[str, Any]], row_count: int, configuration: dict[str, Any]) -> dict[str, Any]:
    included = [item for item in signals if item.get("included_for_analysis")]
    excluded = [item for item in signals if not item.get("included_for_analysis")]
    usable = [item for item in included if (item.get("quality") or {}).get("relationship_fitness") != "insufficient"]
    relationship_usable = [
        item for item in usable
        if int((item.get("quality") or {}).get("valid_numeric_count") or 0) >= 6
        and item.get("proposed_canonical_role") not in {"equipment_state", "pump_status"}
    ]
    unresolved_reviews = [
        item["canonical_signal_id"] for item in signals
        if item.get("review_required") or (item.get("unit") or {}).get("review_required")
    ]
    limitations: list[str] = []
    blocked_methods: list[str] = []
    reasons: list[str] = []
    if timestamp.get("integrity") == "unavailable":
        limitations.append("No canonical timestamp is available; time-dependent and elapsed-time methods are blocked.")
        blocked_methods.extend(["temporal_analysis", "time_shift_analysis", "duration_weighted_persistence"])
    elif timestamp.get("integrity") == "low":
        limitations.append("Low timestamp integrity limits time-dependent interpretation.")
        blocked_methods.extend(["time_shift_analysis", "duration_weighted_persistence"])
    elif timestamp.get("timezone_status") in {"absent", "mixed", "ambiguous"}:
        limitations.append(
            "Timestamp timezone evidence is absent or ambiguous; absolute-time alignment with other datasets is blocked."
        )
        blocked_methods.append("cross_dataset_time_alignment")
    if any(
        item.get("proposed_canonical_role") in ROLE_UNIT_FAMILIES
        and (item.get("unit") or {}).get("unit_status") in {"unresolved", "conflict"}
        for item in usable
    ):
        limitations.append("Some included signals have no converted engineering unit; only unit-independent methods may use them.")
        blocked_methods.append("unit_dependent_physics_reasoning")
    if configuration.get("status") in {"possible_configuration_boundary", "explicit_configuration_boundary"}:
        limitations.append("Possible configuration regimes must be preserved as operating context rather than treated as one homogeneous baseline.")
    elif configuration.get("status") == "insufficient_evidence":
        limitations.append("Operating-state and configuration coverage could not be verified from the included context signals.")
    if unresolved_reviews:
        limitations.append("Unresolved reviews remain excluded from methods that require their meaning or units.")
    if row_count < 6 or not relationship_usable:
        outcome = "review_required" if unresolved_reviews and row_count >= 6 else "insufficient_trustworthy_data"
        reasons.append(f"Only {len(relationship_usable)} relationship-usable signal(s) and {row_count} canonical row(s) are available; relationship analysis needs at least 2 numeric signals and 6 rows.")
    elif len(relationship_usable) < 2:
        outcome = "ready_with_limitations"
        limitations.append("Only one relationship-usable signal is available; single-signal methods may run, but relationship analysis is blocked.")
        blocked_methods.append("relationship_analysis")
        reasons.append("Trustworthy canonical data is available for single-signal methods only.")
    elif limitations:
        outcome = "ready_with_limitations"
        reasons.append("Enough trustworthy canonical data is available for the unblocked analytical methods.")
    else:
        outcome = "ready"
        reasons.append("Enough trustworthy canonical data is available for relationship analysis.")
    return {
        "outcome": outcome,
        "reasons": reasons,
        "included_signal_ids": [item["canonical_signal_id"] for item in included],
        "excluded_signal_ids": [item["canonical_signal_id"] for item in excluded],
        "usable_signal_ids": [item["canonical_signal_id"] for item in usable],
        "limitations": limitations,
        "blocked_methods": sorted(set(blocked_methods)),
        "review_signal_ids": sorted(set(unresolved_reviews)),
        "timestamp_blocking": timestamp.get("integrity") == "unavailable",
        "operating_state_coverage": (
            "multiple_regimes_detected"
            if configuration.get("status") in {"possible_configuration_boundary", "explicit_configuration_boundary"}
            else "represented"
            if configuration.get("status") == "no_configuration_concern_detected"
            else "insufficient_evidence"
        ),
        "configuration_handling_required": configuration.get("status") in {"possible_configuration_boundary", "explicit_configuration_boundary"},
    }


def _review_summary(timestamp: dict[str, Any], signals: list[dict[str, Any]], duplicates: list[dict[str, Any]], configuration: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for signal in signals:
        if signal.get("review_required"):
            items.append({"type": "semantic_mapping", "signal_id": signal["canonical_signal_id"], "source_column": signal["source_column"], "reason": "Semantic mapping needs review."})
        if (signal.get("unit") or {}).get("review_required"):
            items.append({"type": "unit", "signal_id": signal["canonical_signal_id"], "source_column": signal["source_column"], "reason": "Unit evidence needs review."})
    if timestamp.get("review_required"):
        items.append({"type": "timestamp", "signal_id": None, "source_column": timestamp.get("selected_column"), "reason": "Timestamp selection or timezone evidence needs review."})
    for duplicate in duplicates:
        if duplicate.get("review_required"):
            items.append({"type": "duplicate", "signal_id": duplicate.get("right_signal_id"), "source_column": None, "reason": duplicate.get("evidence")})
    for boundary in configuration.get("boundaries", []):
        items.append({"type": "configuration_boundary", "signal_id": boundary.get("signal_id"), "source_column": boundary.get("source_column"), "reason": boundary.get("evidence")})
    return {
        "state": "review_required" if items else "not_required",
        "required_count": len(items),
        "items": items,
        "history": history[-MAX_REVIEW_HISTORY:],
    }


def _public_summary(record: dict[str, Any]) -> dict[str, Any]:
    signals = record.get("signal_profiles", [])
    counts = Counter(str(item.get("mapping_state") or "unresolved") for item in signals)
    review_signal_ids = {
        str(item.get("canonical_signal_id"))
        for item in signals
        if item.get("review_required") or (item.get("unit") or {}).get("review_required")
    }
    unit_conflicts = sum(1 for item in signals if (item.get("unit") or {}).get("unit_status") == "conflict")
    duplicates = record.get("duplicate_channels", [])
    timestamp = record.get("timestamp_profile", {})
    configuration = record.get("configuration_profile", {})
    return {
        "contract_version": CONTRACT_VERSION,
        "dataset_id": record.get("dataset_id"),
        "dataset_identity": record.get("dataset_identity"),
        "revision": record.get("revision"),
        "readiness": record.get("readiness"),
        "signal_counts": {
            "detected": len(signals),
            "confidently_mapped": counts["confidently_mapped"],
            "provisionally_mapped": counts["provisionally_mapped"],
            "need_review": len(review_signal_ids),
            "excluded": sum(1 for item in signals if not item.get("included_for_analysis")),
            "unit_conflicts": unit_conflicts,
            "duplicate_candidates": len(duplicates),
            "timestamp_gaps": int(timestamp.get("large_gap_count") or 0),
            "configuration_boundaries": len(configuration.get("boundaries") or []),
        },
        "review_state": (record.get("review") or {}).get("state"),
        "trust_dimensions": record.get("trust_dimensions", []),
        "analysis_handoff": record.get("analysis_handoff"),
    }


def build_historical_ingestion(
    path: str | os.PathLike[str],
    *,
    dataset_id: str,
    filename: str,
    source_sha256: str | None = None,
    shared_source_key: str | None = None,
    raw_source_path: str | os.PathLike[str] | None = None,
    source_preparation: dict[str, Any] | None = None,
    decisions: dict[str, dict[str, Any]] | None = None,
    review_history: list[dict[str, Any]] | None = None,
    revision: int = 1,
    max_analysis_rows: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    source_path = Path(path)
    raw_path = Path(raw_source_path) if raw_source_path is not None else source_path
    source_sha256 = source_sha256 or file_sha256(raw_path)
    if source_preparation is None:
        source_path, source_preparation = prepare_tabular_source(
            source_path,
            filename=filename,
            source_sha256=source_sha256,
        )
    raw_reference = preserve_raw_source(raw_path, source_sha256=source_sha256)
    shared_raw_reference = persist_immutable_derived_artifact(
        str(dataset_id),
        raw_path,
        artifact_id=source_sha256,
        artifact_kind="raw",
        content_type="application/octet-stream",
    )
    if shared_raw_reference.get("backend") == "s3_immutable":
        raw_reference = {
            **shared_raw_reference,
            "sha256": source_sha256,
            "byte_count": raw_path.stat().st_size,
            "immutable": True,
            "local_artifact_id": raw_reference.get("artifact_id"),
        }
    raw_preservation_seconds = time.perf_counter() - started
    parsing_started = time.perf_counter()
    delimiter, header_present, columns, column_count = _read_delimited_header(source_path)
    parsing_seconds = time.perf_counter() - parsing_started

    schema_started = time.perf_counter()
    sample_rows: list[list[str]] = []
    candidate_rows = 0
    malformed_counts: Counter[str] = Counter()
    for _, values, error in _iter_source_rows(source_path, delimiter=delimiter, header_present=header_present, column_count=column_count):
        if error:
            malformed_counts[error] += 1
            continue
        candidate_rows += 1
        if values is not None and len(sample_rows) < 1000:
            sample_rows.append(values)
    timestamp_candidates = _timestamp_candidates(columns, sample_rows)
    selected_timestamp, selection_reasons = _select_timestamp(timestamp_candidates)
    timestamp_index = int(selected_timestamp["source_column_index"]) if selected_timestamp else None
    timestamp_context_indexes = {
        int(item["source_column_index"])
        for item in timestamp_candidates
        if item.get("parse_ratio", 0) >= 0.8 and item.get("name_evidence")
    }
    identity_index = next((index for index, column in enumerate(columns) if _tokens(column) & IDENTITY_NAME_TOKENS and index != timestamp_index), None)
    schema_seconds = time.perf_counter() - schema_started

    quality_started = time.perf_counter()
    sample_stride = max(1, math.ceil(candidate_rows / MAX_PROFILE_SAMPLES))
    accumulators = [SignalAccumulator(column, index) for index, column in enumerate(columns) if index not in timestamp_context_indexes]
    accumulator_by_index = {item.source_column_index: item for item in accumulators}
    timestamp_rows: list[tuple[int, datetime, bool, str]] = []
    timestamp_missing = 0
    timestamp_invalid = 0
    timestamp_ambiguous = 0
    duplicate_timestamps = 0
    seen_timestamp_keys: set[str] = set()
    seen_exact_rows: set[str] = set()
    timestamp_key_sequence: list[str] = []
    exclusion_counts: Counter[str] = Counter(malformed_counts)
    for source_row, values, error in _iter_source_rows(source_path, delimiter=delimiter, header_present=header_present, column_count=column_count):
        if error or values is None:
            continue
        for index, accumulator in accumulator_by_index.items():
            accumulator.add(values[index], source_row, sample_stride=sample_stride)
        exact_digest = _digest(values)
        if exact_digest in seen_exact_rows:
            exclusion_counts["exact_duplicate_row"] += 1
        elif len(seen_exact_rows) < 200_000:
            seen_exact_rows.add(exact_digest)
        if timestamp_index is not None:
            raw_timestamp = values[timestamp_index]
            if not raw_timestamp:
                timestamp_missing += 1
            else:
                parsed, detected_format, aware = _parse_timestamp(raw_timestamp)
                if parsed is None:
                    timestamp_invalid += 1
                    timestamp_ambiguous += int(detected_format == "ambiguous_day_month")
                else:
                    timestamp_rows.append((source_row, parsed, aware, detected_format or "unknown"))
                    identity = values[identity_index] if identity_index is not None else ""
                    key = f"{identity}\x1f{_canonical_timestamp(parsed)}"
                    if len(timestamp_key_sequence) < 200_000:
                        timestamp_key_sequence.append(key)
                    if key in seen_timestamp_keys:
                        duplicate_timestamps += 1
                    elif len(seen_timestamp_keys) < 200_000:
                        seen_timestamp_keys.add(key)
    repeated_windows = Counter(
        tuple(timestamp_key_sequence[index : index + 3])
        for index in range(max(0, len(timestamp_key_sequence) - 2))
    )
    repeated_timestamp_blocks = sum(count - 1 for count in repeated_windows.values() if count > 1)
    exclusion_counts.update({
        key: count
        for key, count in {
            "missing_timestamp": timestamp_missing,
            "invalid_or_ambiguous_timestamp": timestamp_invalid,
            "duplicate_timestamp_record": duplicate_timestamps,
        }.items()
        if count
    })
    timestamp_profile = _timestamp_profile(
        timestamp_candidates,
        selected_timestamp,
        selection_reasons,
        timestamp_rows,
        missing_count=timestamp_missing,
        invalid_count=timestamp_invalid,
        ambiguous_count=timestamp_ambiguous,
        duplicate_count=duplicate_timestamps,
        repeated_timestamp_blocks=repeated_timestamp_blocks,
    )
    timestamp_coverage = timestamp_profile.get("effective_usable_coverage_seconds")

    mapping_started = time.perf_counter()
    signal_profiles: list[dict[str, Any]] = []
    decisions = decisions or {}
    for accumulator in accumulators:
        header_unit, _ = _header_unit(accumulator.source_column)
        preliminary = accumulator.preliminary()
        provisional_mapping = _semantic_mapping(accumulator.source_column, preliminary, header_unit or (next(iter(accumulator.observed_units), None)), header_present=header_present)
        unit = _unit_profile(accumulator.source_column, accumulator.observed_units, provisional_mapping)
        mapping = _semantic_mapping(accumulator.source_column, preliminary, unit.get("inferred_unit"), header_present=header_present)
        signal_id = _canonical_signal_id(accumulator.source_column, accumulator.source_column_index, mapping.get("proposed_canonical_role"))
        quality = accumulator.profile(role=mapping.get("proposed_canonical_role"), timestamp_coverage_seconds=timestamp_coverage)
        included = bool(mapping.get("proposed_canonical_role")) and mapping.get("mapping_state") not in {"ambiguous", "unresolved", "excluded"} and quality.get("relationship_fitness") != "insufficient"
        signal = {
            "canonical_signal_id": signal_id,
            "source_column": accumulator.source_column,
            "source_column_index": accumulator.source_column_index,
            **mapping,
            "unit": unit,
            "quality": quality,
            "included_for_analysis": included,
            "exclusion_reasons": quality.get("relationship_fitness_reasons", []) if not included else [],
        }
        decision = decisions.get(signal_id) or decisions.get(accumulator.source_column)
        signal_profiles.append(_apply_decision(signal, decision))
    _add_correlation_alternatives(signal_profiles, accumulators)
    mapping_seconds = time.perf_counter() - mapping_started

    duplicate_findings = _duplicate_channels(signal_profiles, accumulators)
    included_columns = [item["source_column"] for item in signal_profiles if item.get("included_for_analysis")]
    signal_by_column = {item["source_column"]: item for item in signal_profiles}
    timestamp_column = str(selected_timestamp["source_column"]) if selected_timestamp else None

    canonical_started = time.perf_counter()
    source_was_reordered = bool(timestamp_profile.get("out_of_order_count"))

    identity_payload = {
        "identity_version": IDENTITY_VERSION,
        "raw_sha256": source_sha256,
        "canonical_version": CANONICAL_VERSION,
        "parser_version": PARSER_VERSION,
        "mapping_version": MAPPING_VERSION,
        "unit_version": UNIT_VERSION,
        "quality_version": QUALITY_VERSION,
        "decisions": {key: decisions[key] for key in sorted(decisions)},
    }
    dataset_identity = _digest(identity_payload)
    canonical_path = _canonical_artifact_path(dataset_identity)
    requested_analysis_rows = max_analysis_rows if max_analysis_rows and max_analysis_rows > 0 else max(1, candidate_rows)
    analysis_limit = min(
        requested_analysis_rows,
        max(6, MAX_ANALYSIS_CELLS // max(1, len(included_columns))),
    )
    analysis_stride = max(1, math.ceil(candidate_rows / max(1, analysis_limit)))
    analysis_rows: list[dict[str, Any]] = []
    canonical_row_count = 0
    included_row_count = 0
    temp_artifact: Path | None = None
    transformations: list[dict[str, Any]] = []
    if source_preparation:
        transformations.append({
            "transformation_id": f"tr_{_digest({'dataset': dataset_identity, 'type': source_preparation.get('type'), 'output': source_preparation.get('output_sha256')})[:12]}",
            **source_preparation,
            "reason": "The accepted JSON telemetry shape was deterministically projected into rows and columns for profiling.",
        })
    if timestamp_column:
        timezone_status = str(timestamp_profile.get("timezone_status") or "unavailable")
        transformations.append({
            "transformation_id": f"tr_{_digest({'dataset': dataset_identity, 'type': 'canonical_timestamp', 'column': timestamp_column})[:12]}",
            "type": "canonical_timestamp_projection",
            "source_column": timestamp_column,
            "rule_version": PARSER_VERSION,
            "reason": (
                "Parsed timestamps with explicit offsets were represented in UTC for the canonical analysis view."
                if timezone_status == "explicit"
                else "Parsed timezone-naive timestamps were preserved without assuming a site timezone."
            ),
            "timezone_policy": "explicit_offset_to_utc" if timezone_status == "explicit" else "preserve_timezone_naive",
            "affected_rows": len(timestamp_rows),
        })
    canonical_seen_exact: set[str] = set()
    canonical_seen_timestamps: set[str] = set()
    try:
        with NamedTemporaryFile("w", delete=False, dir=canonical_path.parent, encoding="utf-8") as output:
            temp_artifact = Path(output.name)
            for source_row, source_values, source_error in _iter_source_rows(
                source_path,
                delimiter=delimiter,
                header_present=header_present,
                column_count=column_count,
            ):
                if source_error or source_values is None:
                    continue
                row = {column: source_values[index] for index, column in enumerate(columns)}
                row_exclusions: list[str] = []
                exact_digest = _digest(source_values)
                if exact_digest in canonical_seen_exact:
                    row_exclusions.append("exact_duplicate_row")
                elif len(canonical_seen_exact) < 200_000:
                    canonical_seen_exact.add(exact_digest)
                parsed: datetime | None = None
                canonical_timestamp = None
                if timestamp_index is not None:
                    raw_timestamp = source_values[timestamp_index]
                    if not raw_timestamp:
                        row_exclusions.append("missing_timestamp")
                    else:
                        parsed, _, _ = _parse_timestamp(raw_timestamp)
                        canonical_timestamp = _canonical_timestamp(parsed)
                        if parsed is None:
                            row_exclusions.append("invalid_or_ambiguous_timestamp")
                        else:
                            identity = source_values[identity_index] if identity_index is not None else ""
                            timestamp_key = f"{identity}\x1f{canonical_timestamp}"
                            if timestamp_key in canonical_seen_timestamps:
                                row_exclusions.append("duplicate_timestamp_record")
                            elif len(canonical_seen_timestamps) < 200_000:
                                canonical_seen_timestamps.add(timestamp_key)
                values_payload: dict[str, Any] = {}
                analysis_row: dict[str, Any] = {}
                usable_value_count = 0
                if timestamp_column:
                    analysis_row[timestamp_column] = canonical_timestamp
                    analysis_row["__source_timestamp"] = canonical_timestamp
                for column, signal in signal_by_column.items():
                    raw = row.get(column, "")
                    number, kind = _parse_number(raw)
                    unit = signal.get("unit") or {}
                    normalized = None
                    if kind == "numeric" and number is not None:
                        normalized = _convert_value(number, unit.get("inferred_unit"), unit.get("normalized_unit"))
                        if signal.get("included_for_analysis"):
                            analysis_row[column] = normalized
                            usable_value_count += 1
                    elif signal.get("proposed_canonical_role") in {"equipment_state", "pump_status"} and str(raw).strip():
                        normalized = str(raw).strip()
                        if signal.get("included_for_analysis"):
                            analysis_row[column] = normalized
                            usable_value_count += 1
                    elif signal.get("included_for_analysis"):
                        analysis_row[column] = None
                    values_payload[signal["canonical_signal_id"]] = {
                        "source_column": column,
                        "original_value": raw,
                        "normalized_value": normalized,
                        "original_unit": unit.get("inferred_unit"),
                        "normalized_unit": unit.get("normalized_unit"),
                        "included_for_analysis": bool(signal.get("included_for_analysis")),
                    }
                if included_columns and usable_value_count == 0:
                    row_exclusions.append("no_usable_included_signal_values")
                    exclusion_counts["no_usable_included_signal_values"] += 1
                excluded = bool(row_exclusions)
                canonical_row = {
                    "source_row_number": source_row,
                    "original_timestamp": row.get(timestamp_column) if timestamp_column else None,
                    "canonical_timestamp": canonical_timestamp,
                    "included_for_analysis": not excluded,
                    "exclusion_reasons": sorted(set(row_exclusions)),
                    "source_values": row,
                    "values": values_payload,
                }
                output.write(_stable_json(canonical_row) + "\n")
                canonical_row_count += 1
                if not excluded:
                    if included_row_count % analysis_stride == 0 and len(analysis_rows) < analysis_limit:
                        analysis_row["__source_row_number"] = source_row
                        analysis_rows.append(analysis_row)
                    included_row_count += 1
            output.flush()
            os.fsync(output.fileno())
        if not canonical_path.exists():
            try:
                os.link(temp_artifact, canonical_path)
            except FileExistsError:
                pass
    finally:
        if temp_artifact is not None:
            temp_artifact.unlink(missing_ok=True)
    if source_was_reordered and timestamp_column:
        analysis_rows.sort(
            key=lambda row: (
                _timestamp_sort_key(_parse_timestamp(str(row.get(timestamp_column) or ""))[0]),
                int(row.get("__source_row_number") or 0),
            )
        )
    canonical_persistence_started = time.perf_counter()
    canonical_sha256 = file_sha256(canonical_path)
    canonical_storage = persist_immutable_derived_artifact(
        str(dataset_id),
        canonical_path,
        artifact_id=canonical_sha256,
        artifact_kind="canonical",
        content_type="application/x-ndjson",
    )
    canonical_persistence_seconds = time.perf_counter() - canonical_persistence_started
    if source_was_reordered:
        transformations.append({
            "transformation_id": f"tr_{_digest({'dataset': dataset_identity, 'type': 'row_order'})[:12]}",
            "type": "deterministic_analysis_order",
            "rule_version": PARSER_VERSION,
            "reason": "Canonical analysis rows were ordered by parsed timestamp; source row numbers preserve original order.",
            "affected_rows": included_row_count,
        })
    for signal in signal_profiles:
        unit = signal.get("unit") or {}
        if unit.get("conversion_formula") and unit.get("conversion_formula") != "x":
            transformations.append({
                "transformation_id": f"tr_{_digest({'dataset': dataset_identity, 'signal': signal['canonical_signal_id'], 'unit': unit.get('inferred_unit')})[:12]}",
                "type": "unit_conversion",
                "signal_id": signal["canonical_signal_id"],
                "source_column": signal["source_column"],
                "original_unit": unit.get("inferred_unit"),
                "normalized_unit": unit.get("normalized_unit"),
                "formula": unit.get("conversion_formula"),
                "rule_version": UNIT_VERSION,
            })
    canonical_seconds = time.perf_counter() - canonical_started

    configuration = _configuration_profile(signal_profiles, analysis_rows, timestamp_column)
    readiness = _readiness(timestamp_profile, signal_profiles, included_row_count, configuration)
    history = list(review_history or [])
    review = _review_summary(timestamp_profile, signal_profiles, duplicate_findings, configuration, history)
    trust_dimensions = _trust_dimensions(timestamp_profile, signal_profiles, configuration, readiness)
    total_seconds = time.perf_counter() - started
    record = {
        "contract_version": CONTRACT_VERSION,
        "canonical_contract_version": CANONICAL_VERSION,
        "dataset_id": str(dataset_id),
        "dataset_identity": dataset_identity,
        "revision": int(revision),
        "created_at": _utc_now(),
        "raw_source": {
            "filename": filename,
            "sha256": source_sha256,
            "byte_count": raw_path.stat().st_size,
            "immutable": True,
            "storage": raw_reference,
            "shared_source_key_present": bool(shared_source_key),
        },
        "source_schema": {
            "columns": columns,
            "column_count": len(columns),
            "header_present": header_present,
            "delimiter": delimiter,
            "candidate_row_count": candidate_rows,
            "malformed_row_counts": dict(sorted(malformed_counts.items())),
            "parser_version": PARSER_VERSION,
            "source_preparation": source_preparation,
        },
        "timestamp_profile": timestamp_profile,
        "signal_profiles": signal_profiles,
        "duplicate_channels": duplicate_findings,
        "configuration_profile": configuration,
        "trust_dimensions": trust_dimensions,
        "review": review,
        "readiness": readiness,
        "canonical_dataset": {
            "contract_version": CANONICAL_VERSION,
            "dataset_identity": dataset_identity,
            "artifact_id": dataset_identity,
            "sha256": canonical_sha256,
            "storage": canonical_storage,
            "row_count": canonical_row_count,
            "included_row_count": included_row_count,
            "excluded_row_count": canonical_row_count - included_row_count,
            "row_exclusion_counts": dict(sorted(exclusion_counts.items())),
            "analysis_sample_rows": len(analysis_rows),
            "analysis_population_rows": included_row_count,
            "analysis_sample_stride": analysis_stride,
            "analysis_sampling_applied": len(analysis_rows) < included_row_count,
            "analysis_cell_limit": MAX_ANALYSIS_CELLS,
            "timestamp_column": timestamp_column,
            "included_signal_ids": readiness["included_signal_ids"],
            "excluded_signal_ids": readiness["excluded_signal_ids"],
            "original_values_preserved": True,
            "major_gaps_interpolated": False,
        },
        "provenance": {
            "identity_inputs": identity_payload,
            "transformations": transformations,
            "mapping_rule_version": MAPPING_VERSION,
            "unit_rule_version": UNIT_VERSION,
            "quality_rule_version": QUALITY_VERSION,
            "configuration_rule_version": CONFIGURATION_VERSION,
            "no_silent_repairs": True,
        },
        "performance": {
            "raw_preservation_seconds": round(raw_preservation_seconds, 6),
            "parsing_seconds": round(parsing_seconds, 6),
            "schema_and_timestamp_profiling_seconds": round(schema_seconds, 6),
            "mapping_seconds": round(mapping_seconds, 6),
            "quality_profiling_seconds": round(max(0.0, mapping_started - quality_started), 6),
            "canonical_normalization_seconds": round(canonical_seconds, 6),
            "canonical_persistence_seconds": round(canonical_persistence_seconds, 6),
            "total_ingestion_to_readiness_seconds": round(total_seconds, 6),
            "peak_process_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
            "profile_sample_limit_per_signal": MAX_PROFILE_SAMPLES,
            "near_duplicate_comparison_limit": MAX_NEAR_DUPLICATE_COMPARISONS,
        },
    }
    record["summary"] = _public_summary(record)
    record = persist_ingestion_record(record)
    compatibility_profiles = []
    for item in signal_profiles:
        quality = item.get("quality") or {}
        compatibility_profiles.append({
            "column": item["source_column"],
            "min": quality.get("minimum"),
            "max": quality.get("maximum"),
            "average": quality.get("mean"),
            "missing_count": quality.get("missing_count", 0),
            "valid_numeric_count": quality.get("valid_numeric_count", 0),
            "constant_or_stuck": bool(quality.get("stuck")),
            "distinct_count": quality.get("distinct_count", 0),
        })
    compatibility_catalog = build_telemetry_signal_catalog(
        columns,
        numeric_profiles=compatibility_profiles,
        timestamp_column=timestamp_column,
        header_present=header_present,
    )
    handoff_catalog: dict[str, dict[str, Any]] = {}
    for item in signal_profiles:
        if not item.get("included_for_analysis"):
            continue
        column = item["source_column"]
        unit = item.get("unit") or {}
        compatibility_metadata = compatibility_catalog.get(column, {})
        downstream_role = compatibility_metadata.get("canonical_role") or item.get("proposed_canonical_role")
        # Preserve the mature downstream structural classification while adding
        # the trust layer's canonical identity and unit provenance. In
        # particular, state, cumulative, and validation-label classifications
        # must not be flattened into generic process metrics at this boundary.
        handoff_catalog[column] = {
            **compatibility_metadata,
            "source_column": column,
            "source_column_index": item["source_column_index"],
            "canonical_signal_id": item["canonical_signal_id"],
            "canonical_role": downstream_role,
            "ingestion_semantic_role": item.get("proposed_canonical_role"),
            "engineering_units": unit.get("normalized_unit") or compatibility_metadata.get("engineering_units"),
            "original_engineering_units": unit.get("inferred_unit"),
            "normalized_engineering_units": unit.get("normalized_unit"),
            "mapping_state": item.get("mapping_state"),
            "review_required": item.get("review_required"),
            "trust_provenance": {
                "dataset_identity": dataset_identity,
                "contract_version": CONTRACT_VERSION,
            },
        }
    handoff_numeric_columns = [
        item["source_column"]
        for item in signal_profiles
        if item.get("included_for_analysis")
        and item.get("proposed_canonical_role") not in {"equipment_state", "pump_status"}
        and int((item.get("quality") or {}).get("valid_numeric_count") or 0) > 0
    ]
    handoff = {
        "rows": analysis_rows,
        "columns": ([timestamp_column] if timestamp_column else []) + included_columns,
        "numeric_columns": handoff_numeric_columns,
        "timestamp_column": timestamp_column,
        "row_count_total": included_row_count,
        "telemetry_signal_catalog": handoff_catalog,
        "readiness": readiness,
        "dataset_identity": dataset_identity,
    }
    return record, handoff


def apply_review(
    dataset_id: str,
    *,
    decisions: list[dict[str, Any]],
    actor: str,
) -> dict[str, Any]:
    current = read_ingestion_record(dataset_id)
    if current is None:
        raise FileNotFoundError("ingestion_profile_not_found")
    decision_map: dict[str, dict[str, Any]] = {}
    history = list((current.get("review") or {}).get("history") or [])
    prior_decisions = ((current.get("provenance") or {}).get("identity_inputs") or {}).get("decisions") or {}
    if isinstance(prior_decisions, dict):
        decision_map.update({str(key): dict(value) for key, value in prior_decisions.items() if isinstance(value, dict)})
    known = {
        str(item.get("canonical_signal_id")): item
        for item in current.get("signal_profiles", []) if isinstance(item, dict)
    }
    for decision in decisions:
        signal_id = str(decision.get("signal_id") or "")
        if signal_id not in known:
            raise ValueError(f"Unknown signal id: {signal_id}")
        normalized = {key: value for key, value in decision.items() if value is not None and key != "signal_id"}
        decision_map[known[signal_id]["source_column"]] = normalized
        history.append({
            "decision_id": f"review_{_digest({'dataset': dataset_id, 'revision': int(current.get('revision') or 1) + 1, 'signal': signal_id, 'decision': normalized})[:16]}",
            "signal_id": signal_id,
            "source_column": known[signal_id]["source_column"],
            "actor": actor,
            "recorded_at": _utc_now(),
            "previous_mapping_state": known[signal_id].get("mapping_state"),
            "decision": normalized,
            "provenance": "human_review",
        })
    raw_storage = (current.get("raw_source") or {}).get("storage") or {}
    temporary_source = False
    try:
        try:
            source_path = _raw_artifact_path(raw_storage)
        except FileNotFoundError:
            if raw_storage.get("backend") == "s3_immutable":
                source_path = restore_immutable_derived_artifact(raw_storage)
            else:
                shared_key = str(raw_storage.get("shared_object_key") or "")
                if not shared_key:
                    raise
                source_path = restore_upload_source(dataset_id, shared_key, filename=(current.get("raw_source") or {}).get("filename"))
            temporary_source = True
        rebuilt, _ = build_historical_ingestion(
            source_path,
            dataset_id=dataset_id,
            filename=str((current.get("raw_source") or {}).get("filename") or "historical-data.csv"),
            source_sha256=str((current.get("raw_source") or {}).get("sha256") or ""),
            shared_source_key=raw_storage.get("shared_object_key"),
            decisions=decision_map,
            review_history=history,
            revision=int(current.get("revision") or 1) + 1,
        )
    finally:
        if temporary_source:
            source_path.unlink(missing_ok=True)
    rebuilt["analysis_handoff"] = {
        "status": "reanalysis_required",
        "reason": "Human review changed the canonical revision; downstream analysis must use the new dataset identity.",
    }
    rebuilt["summary"] = _public_summary(rebuilt)
    return persist_ingestion_record(rebuilt)


def canonical_rows_page(dataset_id: str, *, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    record = read_ingestion_record(dataset_id)
    if record is None:
        raise FileNotFoundError("ingestion_profile_not_found")
    identity = str(record.get("dataset_identity") or "")
    path = _canonical_artifact_path(identity, create=False)
    temporary_path = False
    if not path.is_file():
        storage = (record.get("canonical_dataset") or {}).get("storage") or {}
        if storage.get("backend") != "s3_immutable":
            raise FileNotFoundError("canonical_dataset_not_available")
        path = restore_immutable_derived_artifact(storage)
        temporary_path = True
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index < offset:
                    continue
                if len(rows) >= limit:
                    break
                rows.append(json.loads(line))
    finally:
        if temporary_path:
            path.unlink(missing_ok=True)
    total = int((record.get("canonical_dataset") or {}).get("row_count") or 0)
    return {
        "contract_version": CANONICAL_VERSION,
        "dataset_id": dataset_id,
        "dataset_identity": identity,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + len(rows) < total,
        "rows": rows,
        "provenance": {
            "raw_sha256": (record.get("raw_source") or {}).get("sha256"),
            "transformations": (record.get("provenance") or {}).get("transformations", []),
        },
    }


def ingestion_summary(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    return dict(record.get("summary") or _public_summary(record))
