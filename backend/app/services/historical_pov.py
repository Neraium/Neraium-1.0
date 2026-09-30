"""Read-only, declaration-driven historical PoV adapter. No event/label interface.

The owner attests acquisition facts; this module checks consistency, not their
truth. No independence, bounds, context, or sampling assumptions are inferred.
The first version supports one pair in a declared homogeneous global context.
"""
from __future__ import annotations

import csv
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import io
import json
import math
from typing import Any

from app.engine.relationship_qualification import clock, digest, scheduled
from app.engine.supplied_reference import prepare_supplied_reference

VERSION = "historical-pov.v1"
DEPENDENCE = "independent_groups_conditional_on_context_and_schedule"
LIMITATIONS = [
    "Independence and acquisition facts are owner declarations, not statistically verified facts.",
    "Qualification is conditional bounded relationship evidence, not fault probability or event detection accuracy.",
    "The adapter accepts one pair in a declared homogeneous global context; it does not infer operating context.",
    "Source and plan must be selected independently of event identity, timing and outcomes before analysis.",
    "Hashes bind supplied content; they do not authenticate declarations or recover missing source data.",
]


class PoVAdmissionError(ValueError):
    """No engine call is permitted after admission fails."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason_code = reason
        self.not_quantifiable = True


def _require(condition, reason):
    if not condition:
        raise PoVAdmissionError(reason)


def _keys(value, names, label):
    _require(isinstance(value, dict) and set(value) == set(names.split()),
             f"invalid_{label}_fields")


def _text(value, label):
    _require(isinstance(value, str) and bool(value.strip()), f"missing_{label}")
    return value


def _basis(value, label):
    _text(value, label)
    _require(value.strip().lower().rstrip(".") not in {
        "unknown", "unavailable", "n/a", "none", "not supplied", "not established", "unjustified",
    }, f"unjustified_{label}")
    return value


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, OverflowError) as exc:
        raise PoVAdmissionError("non_json_or_nonfinite_input") from exc


@dataclass(frozen=True)
class PreparedPoV:
    """Detached immutable serialized bundle; inspect() returns a disposable copy."""

    _serialized: str
    identity: str

    def inspect(self) -> dict[str, Any]:
        value = json.loads(self._serialized)
        _require(digest(value) == self.identity, "prepared_bundle_changed")
        return value


def prepare_historical_pov(*, metadata: dict, rows: list[dict] | None = None,
                           csv_bytes: bytes | None = None) -> PreparedPoV:
    """Validate declarations and freeze the source, row plan and acquisition profile.

    Supply exactly one of UTF-8 comma-delimited CSV bytes or JSON-compatible rows.
    Unknown fields/columns are rejected, including event labels. No sorting,
    deduplication, imputation, conversion, sampling or silent exclusion occurs.
    See docs/historical_pov_adapter.md for the explicit metadata contract.
    """
    _require((rows is None) != (csv_bytes is None), "provide_rows_or_csv_bytes")
    metadata = json.loads(_json(metadata))
    _keys(metadata, "signals timestamp acquisition grouping dependence_assumption independence_basis "
          "schedule context coverage_period_seconds plan", "metadata")
    _basis(metadata["independence_basis"], "independence_basis")
    _require(metadata["dependence_assumption"] == DEPENDENCE, "unjustified_dependence_assumption")
    signals = metadata["signals"]
    _require(isinstance(signals, dict) and len(signals) == 2, "requires_exactly_two_signals")
    columns = sorted(signals)
    units, bounds = {}, {}
    for column, spec in signals.items():
        _require(bool(column.strip()) and not column.startswith("__"), "invalid_signal_name")
        _keys(spec, "unit bounds bounds_unit bounds_basis", "signal")
        units[column] = _basis(spec["unit"], "unit")
        _require(spec["bounds_unit"] == spec["unit"], "bounds_unit_mismatch")
        _basis(spec["bounds_basis"], "bounds_basis")
        limits = spec["bounds"]
        _require(isinstance(limits, list) and len(limits) == 2
                 and all(type(v) in (int, float) and math.isfinite(v) for v in limits)
                 and limits[0] < limits[1] and math.isfinite(limits[1] - limits[0])
                 and math.nextafter(limits[1] - limits[0], -math.inf) > 0, "invalid_signal_bounds")
        bounds[column] = limits

    timestamp = metadata["timestamp"]
    _keys(timestamp, "column mode basis", "timestamp")
    timestamp_column = _text(timestamp["column"], "timestamp_column")
    _basis(timestamp["basis"], "timestamp_semantics")
    _require(isinstance(timestamp["mode"], str) and timestamp["mode"] in {
        "timezone_aware", "naive_historical_source_clock"}, "unsupported_timestamp_mode")
    acquisition = metadata["acquisition"]
    _keys(acquisition, "namespace identity basis", "acquisition")
    namespace = _text(acquisition["namespace"], "acquisition_namespace")
    _basis(acquisition["basis"], "acquisition_basis")
    identity = acquisition["identity"]
    _require(isinstance(identity, dict), "invalid_acquisition_identity")
    if identity.get("kind") == "column":
        _keys(identity, "kind column", "acquisition_identity")
        acquisition_column = _text(identity["column"], "acquisition_column")
    else:
        _keys(identity, "kind fresh_nonreplayed_rows", "acquisition_identity")
        _require(identity["kind"] == "source_row" and identity["fresh_nonreplayed_rows"] is True,
                 "unjustified_acquisition_identity")
        acquisition_column = None
    grouping = metadata["grouping"]
    _require(isinstance(grouping, dict), "invalid_grouping_fields")
    group_column = None
    if grouping.get("kind") == "column":
        _keys(grouping, "kind column basis justified", "grouping")
        group_column = _text(grouping["column"], "group_column")
    else:
        _keys(grouping, "kind basis justified", "grouping")
        _require(grouping["kind"] == "independent_acquisitions", "unsupported_grouping_rule")
    _require(grouping["justified"] is True, "unjustified_grouping")
    _basis(grouping["basis"], "grouping_basis")
    schedule = metadata["schedule"]
    _keys(schedule, "assumption basis", "schedule")
    _require(schedule["assumption"] == "predeclared_noninformative", "unjustified_schedule")
    _basis(schedule["basis"], "schedule_basis")
    context = metadata["context"]
    _keys(context, "basis selection", "context")
    _basis(context["basis"], "context_basis")
    _require(context["selection"] == {}, "only_declared_homogeneous_global_context_supported")
    coverage = metadata["coverage_period_seconds"]
    _require(type(coverage) in (int, float) and math.isfinite(coverage) and coverage > 0,
             "invalid_coverage_period")
    plan = metadata["plan"]
    _keys(plan, "reference_epoch_rows comparison_rows basis declared_before_analysis event_independent", "plan")
    _basis(plan["basis"], "plan_basis")
    _require(plan["declared_before_analysis"] is True and plan["event_independent"] is True,
             "informative_or_undeclared_plan")
    epochs, slots = plan["reference_epoch_rows"], plan["comparison_rows"]
    _require(isinstance(epochs, list) and len(epochs) >= 2
             and all(type(n) is int and n >= 3 for n in epochs), "invalid_reference_epochs")
    _require(isinstance(slots, list) and bool(slots)
             and all(type(n) is int and 16 <= n <= 12000 for n in slots), "invalid_comparison_sizes")
    _require(16 <= sum(epochs) <= 12000, "invalid_reference_size")

    allowed = [timestamp_column, *columns]
    for c in (acquisition_column, group_column):
        if c is not None:
            _require(c not in [timestamp_column, *columns], "identity_column_is_measurement_or_clock")
            if c not in allowed:
                allowed.append(c)
    _require(len({timestamp_column, *columns}) == 3, "timestamp_signal_collision")
    if csv_bytes is not None:
        _require(isinstance(csv_bytes, bytes), "csv_bytes_required")
        try:
            source_text = csv_bytes.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(source_text, newline=""), strict=True)
            _require(reader.fieldnames is not None and len(set(reader.fieldnames)) == len(reader.fieldnames)
                     and set(reader.fieldnames) == set(allowed), "unexpected_source_columns")
            source_rows = list(reader)
        except (UnicodeError, csv.Error) as exc:
            raise PoVAdmissionError("invalid_utf8_csv") from exc
        source_hash = sha256(csv_bytes).hexdigest()
        # Retain the exact decoded bytes, including a possible BOM, for recovery.
        source = {"kind": "csv", "sha256": source_hash, "text": csv_bytes.decode("utf-8")}
    else:
        _require(isinstance(rows, list), "rows_must_be_list")
        serialized = _json(rows)
        source_rows = json.loads(serialized)
        source_hash = sha256(serialized.encode()).hexdigest()
        source = {"kind": "canonical_json_rows", "sha256": source_hash, "rows": source_rows}
    _require(len(source_rows) == sum(epochs) + sum(slots), "source_plan_row_count_mismatch")
    projected, events = [], []
    seen_acquisitions = set()
    prior_time = None
    for ordinal, row in enumerate(source_rows, 1):
        _require(isinstance(row, dict) and set(row) == set(allowed), "unexpected_source_columns")
        raw_time = _text(row[timestamp_column], "timestamp")
        try:
            at = clock(raw_time)
            _require((at.tzinfo is not None) == (timestamp["mode"] == "timezone_aware"), "timestamp_mode_mismatch")
            _require(prior_time is None or at > prior_time, "unordered_or_overlapping_source_clock")
        except (ValueError, TypeError) as exc:
            if isinstance(exc, PoVAdmissionError):
                raise
            raise PoVAdmissionError("invalid_source_clock") from exc
        prior_time = at
        selected = {timestamp_column: raw_time}
        for c in columns:
            value = row[c]
            _require(type(value) in (int, float, str), "invalid_numeric_value")
            try:
                value = float(value)
            except (ValueError, OverflowError) as exc:
                raise PoVAdmissionError("invalid_numeric_value") from exc
            _require(math.isfinite(value) and bounds[c][0] <= value <= bounds[c][1], "measurement_out_of_bounds")
            selected[c] = value
        native = _text(row[acquisition_column], "acquisition_key") if acquisition_column else f"{source_hash}:{ordinal}"
        acquisition_id = "acq:" + digest([namespace, identity["kind"], native])
        _require(acquisition_id not in seen_acquisitions, "replayed_acquisition")
        seen_acquisitions.add(acquisition_id)
        group_key = _text(row[group_column], "group_key") if group_column else acquisition_id
        group_id = "group:" + digest([namespace, grouping["kind"], group_key])
        projected.append(selected)
        events.append({"timestamp": raw_time, "acquisition_id": acquisition_id, "group_id": group_id})

    locator = f"sha256:{source_hash}"
    def window(start, count):
        end = start + count
        return {"start": events[start]["timestamp"], "end": events[end-1]["timestamp"],
                "source_locator": f"{locator}#records={start+1}:{end}",
                "observations": deepcopy(events[start:end])}

    reference_count = sum(epochs)
    reference = window(0, reference_count)
    reference["epochs"] = []
    offset = 0
    for number, count in enumerate(epochs, 1):
        epoch_id = f"epoch-{number:04d}"
        epoch = window(offset, count)
        try:
            scheduled(epoch, coverage)
        except (ValueError, TypeError) as exc:
            raise PoVAdmissionError(str(exc)) from exc
        reference["epochs"].append({"epoch_id": epoch_id, "start": epoch["start"], "end": epoch["end"]})
        for event in reference["observations"][offset:offset+count]:
            event["epoch_id"] = epoch_id
        offset += count
    comparisons, mappings = [], []
    seen_groups = {e["group_id"] for e in reference["observations"]}
    try:
        scheduled(reference, 2 * coverage)
        for number, count in enumerate(slots, 1):
            comparison = window(offset, count)
            comparison["slot_id"] = f"slot-{number:04d}"
            scheduled(comparison, coverage)
            groups = {e["group_id"] for e in comparison["observations"]}
            _require(not groups & seen_groups, "reused_or_overlapping_groups")
            seen_groups.update(groups)
            comparisons.append(comparison)
            mappings.append(list(range(offset+1, offset+count+1)))
            offset += count
    except (ValueError, TypeError) as exc:
        if isinstance(exc, PoVAdmissionError):
            raise
        raise PoVAdmissionError(str(exc)) from exc

    seed = digest({"source_hash": source_hash, "metadata": metadata, "adapter": VERSION})
    profile = {
        "version": "relationship-acquisition.v1", "assessment_id": f"assessment:{seed}",
        "acquisition_profile_id": f"profile:{seed}",
        "independence_basis": metadata["independence_basis"], "dependence_assumption": DEPENDENCE,
        "schedule_assumption": schedule["assumption"], "coverage_period_seconds": coverage,
        "pairs": [{"columns": columns, "signal_units": units, "signal_bounds": bounds,
                   "bounds_basis": _json({c: signals[c]["bounds_basis"] for c in columns}),
                   "context": {**context, "context_id": "context:" + digest(context)},
                   "reference": reference, "comparisons": comparisons}],
    }
    engine_columns = [timestamp_column, *columns]
    # Preflight the unchanged paired boundary for EVERY slot before any evaluation.
    for mapping in mappings:
        try:
            prepare_supplied_reference(columns=engine_columns, reference_rows=projected[:reference_count],
                comparison_rows=[projected[i-1] for i in mapping], numeric_profiles=[{"column": c} for c in columns],
                timestamp_column=timestamp_column, signal_units=units, config={})
        except ValueError as exc:
            raise PoVAdmissionError(str(exc)) from exc
    bundle = {"version": VERSION, "source": source, "metadata": metadata, "profile": profile,
              "profile_hash": digest(profile), "columns": engine_columns, "rows": projected,
              "row_mapping": {"numbering": "one-based data records, excluding CSV header; not physical lines",
                              "reference": list(range(1, reference_count+1)), "comparisons": mappings}}
    return PreparedPoV(_json(bundle), digest(bundle))


def run_historical_pov(prepared: PreparedPoV, *, checkpoint: dict | None = None,
                       stop_after_slots: int | None = None) -> dict:
    """Evaluate chronological slots with one frozen profile/reference and state.

    Checkpoints bind the complete prepared bundle and ledger, detecting accidental
    mutation/mismatched continuation; they are not authentication tokens. Outputs
    contain deterministic relationship evidence, not engine performance timings.
    """
    from app.engine.sii_engine import evaluate_sii

    bundle = prepared.inspect()
    mappings = bundle["row_mapping"]["comparisons"]
    state, start = {}, 0
    if checkpoint is not None:
        _keys(checkpoint, "prepared_identity completed_slots relationship_persistence_state digest", "checkpoint")
        payload = {k: v for k, v in checkpoint.items() if k != "digest"}
        _require(payload["prepared_identity"] == prepared.identity, "reference_or_profile_changed")
        _require(digest(payload) == checkpoint["digest"], "checkpoint_changed")
        start = payload["completed_slots"]
        _require(type(start) is int and 0 <= start <= len(mappings), "invalid_checkpoint_position")
        state = deepcopy(payload["relationship_persistence_state"])
        _require(isinstance(state, dict), "continuation_state_missing")
    end = len(mappings) if stop_after_slots is None else stop_after_slots
    _require(type(end) is int and start < end <= len(mappings), "invalid_stop_position")
    profile = bundle["profile"]
    pair = profile["pairs"][0]
    source_rows = bundle["rows"]
    reference = [source_rows[i-1] for i in bundle["row_mapping"]["reference"]]
    outputs = []
    for index in range(start, end):
        result = evaluate_sii(columns=bundle["columns"], reference_rows=deepcopy(reference),
            comparison_rows=[deepcopy(source_rows[i-1]) for i in mappings[index]],
            signal_units=deepcopy(pair["signal_units"]),
            numeric_profiles=[{"column": c} for c in pair["columns"]],
            timestamp_column=bundle["metadata"]["timestamp"]["column"],
            relationship_acquisition_profile=deepcopy(profile), relationship_persistence_state=deepcopy(state))
        graph = result.get("relationship_graph") or {}
        edges = graph.get("edges") or []
        next_state = graph.get("relationship_persistence_state") or {}
        failed = result.get("processing_trace", {}).get("modules_failed", [])
        _require(not failed, "engine_modules_failed:" + ",".join(failed))
        _require(bool(next_state) == bool(edges), "relationship_evidence_state_mismatch")
        if state and next_state:
            _require(set(next_state) == set(state), "continuation_relationship_changed")
        if next_state:
            state = deepcopy(next_state)
        limitations = [*LIMITATIONS, *result.get("supplied_reference", {}).get("limitations", [])]
        assessments = []
        for edge in edges:
            qualification = deepcopy(edge.get("qualified_persistence") or {})
            status = edge.get("qualification_status", "limited")
            assessments.append({
                "columns": edge["columns"], "qualification_status": status,
                "qualification": qualification,
                "not_quantifiable": status != "sufficient",
                "directional_persistence_supported": bool(edge.get("directional_persistence_supported")),
                "qualified_persistence_supported": bool(edge.get("qualified_persistence_supported")),
                "persistent_relationship_change": bool(edge.get("persistent_relationship_change")),
                "persistence_factor": edge.get("persistence_factor"),
                "baseline_correlation": edge.get("baseline_correlation"),
                "current_correlation": edge.get("current_correlation"),
                "signed_correlation_delta": edge.get("signed_correlation_delta"),
                "reference_qualification_id": edge.get("reference_qualification_id"),
            })
        if not edges:
            # A constant or structurally ineligible pair has no Pearson edge.
            # Preserve prior evidence, grant no vote, and leave this planned slot
            # absent; the existing qualifier counts missing slots as neutral.
            assessments.append({"columns": pair["columns"], "qualification_status": "insufficient",
                "qualification": {"status": "insufficient", "reason_codes": ["relationship_evidence_unavailable"]},
                "not_quantifiable": True, "directional_persistence_supported": False,
                "qualified_persistence_supported": False, "persistent_relationship_change": False,
                "persistence_factor": None, "baseline_correlation": None, "current_correlation": None,
                "signed_correlation_delta": None, "reference_qualification_id": None})
        outputs.append({"slot_id": pair["comparisons"][index]["slot_id"], "assessments": assessments,
                        "evidence_limitations": limitations,
                        "evidence_registry": deepcopy(result.get("relationship_evidence_registry", {})),
                        "supplied_reference": deepcopy(result.get("supplied_reference", {}))})
    payload = {"prepared_identity": prepared.identity, "completed_slots": end,
               "relationship_persistence_state": state}
    return {"version": VERSION, "prepared_identity": prepared.identity,
            "profile": deepcopy(profile), "profile_hash": bundle["profile_hash"],
            "provenance": {"source": bundle["source"], "metadata": bundle["metadata"],
                           "row_mapping": bundle["row_mapping"]},
            "slots": outputs, "checkpoint": {**payload, "digest": digest(payload)},
            "not_quantifiable": any(a["not_quantifiable"] for o in outputs for a in o["assessments"])}
