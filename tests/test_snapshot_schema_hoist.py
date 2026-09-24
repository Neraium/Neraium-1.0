"""Complete snapshots captured before the schema-only hoist; no field exclusions."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from app.services import upload_jobs, upload_validator

FIXTURE = Path(__file__).parent / "fixtures/snapshot_schema_hoist/before.json"


def csv_text(columns, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue()


def stamp(index):
    return f"2026-01-01T00:{index:02d}:00Z"


def cases():
    clean = csv_text(["Timestamp", "Flow GPM"], [[stamp(i), i + 1] for i in range(6)])
    mixed_rows = [[stamp(i), i + 1, i + 10, i + 20, "A"] for i in range(8)]
    for i, value in enumerate(["", "NA", "NaN", "inf", "-inf", "1e999", "bad", "-9999"]):
        mixed_rows.append([stamp(i + 8), value, value, i + 50, "A"])
    mixed = csv_text(["Timestamp", " Flow-GPM ", "FLOW GPM!", "ordinary", "asset"], mixed_rows)
    chilled_columns = ["Timestamp", "CHW Supply Temp F", "chw-return-temp-f", "Flow GPM", "pump_power_kw", "chiller_load_pct", "ordinary"]
    chilled = [[stamp(i), 42 + i, 50 + i, 100 + i, 10 + i, 20 + i, i] for i in range(25)]
    chilled[4][3] = ""
    duplicate_rows = [[stamp(3), 1], [stamp(1), 2], [stamp(2), 3], [stamp(3), 4], [stamp(2), 3], ["invalid", 9], [stamp(4), 5]]
    bounded_rows = [[stamp(i), i + 1] for i in range(5)]
    bounded_rows += [bounded_rows[0], bounded_rows[4], [stamp(1), 99], [stamp(4), 99]]
    result = {
        "empty": {"text": ""},
        "blank": {"text": "\n \n"},
        "header_only": {"text": "Timestamp,Flow GPM\n"},
        "no_usable_rows": {"text": "Timestamp,Flow GPM\nbad,1\nbad,2\nbad,3\n"},
        "one_numeric": {"text": clean},
        "multiple_aliases_and_missing": {"text": mixed},
        "duplicate_headers": {"text": csv_text(["Timestamp", "flow_gpm", "flow_gpm", "FLOW GPM"], [[stamp(i), i, i + 10, i + 20] for i in range(4)] + [[stamp(4), "", "bad", ""]])},
        "sentinels_units": {"text": csv_text(["Timestamp", "flow_gpm", "other"], [[stamp(i), value, i] for i, value in enumerate(["1", "2", "3", "null", "none", "n/a", "-", "nan", "NaN", "+inf", "Infinity", "-Infinity", "1e999", "42 gpm", "12%", "1,234", "???", "-9999", "9999"])])},
        "duplicates_unsorted": {"text": csv_text(["Timestamp", "flow_gpm"], duplicate_rows)},
        "identity_timestamps": {"text": csv_text(["Timestamp", "asset", "flow_gpm"], [[stamp(i // 2), "A" if i % 2 else "B", i + 1] for i in range(8)])},
        "malformed_blank": {"text": clean + "\n" + f"{stamp(7)},8,extra\n{stamp(8)},\n"},
        "row_order_no_timestamp": {"text": csv_text(["sensor", "other"], [[i, i + 1] for i in range(6)])},
        "no_numeric": {"text": csv_text(["Timestamp", "state"], [[stamp(i), "manual"] for i in range(6)])},
        "headerless_whitespace": {"text": "\n".join(f"{i + 1} {i + 10}" for i in range(6)) + "\n"},
        "sparse_missing_ready": {"text": csv_text(chilled_columns, chilled)},
        "missing_core_pending": {"text": csv_text(["Timestamp", "flow_gpm", "pump_power_kw", "chiller_load_pct", "compressor_power_kw", "alarm_count"], [[stamp(i), i + 1, i + 2, i + 3, i + 4, i] for i in range(6)])},
        "bounded_duplicates": {"text": csv_text(["Timestamp", "flow_gpm"], bounded_rows), "dedup_limit": 3},
        "at_dedup_boundary": {"text": clean, "dedup_limit": 6},
        "below_dedup_boundary": {"text": clean, "dedup_limit": 7},
        "irregular_time": {"text": csv_text(["Timestamp", "flow_gpm"], [[stamp(i), i + 1] for i in [0, 1, 3, 6, 10, 15]])},
        "all_numeric_missing_row": {"text": clean + f"{stamp(7)},NA\n{stamp(8)},\n"},
    }
    for limit in [1, 2, 4, 0, -1]:
        result[f"sample_limit_{limit}"] = {"text": clean, "limit": limit}
    return result


CASES = cases()


def capture_snapshot(case, tmp_path, monkeypatch):
    path = tmp_path / "source.csv"
    path.write_text(case["text"], encoding="utf-8")
    monkeypatch.setattr(upload_validator, "DEDUPLICATION_EXACT_HASH_LIMIT", case.get("dedup_limit", 200_000))
    progress, measured = [], []
    try:
        result = upload_validator.stream_csv_snapshot(
            path, max_analysis_rows=case.get("limit"), csv_progress_update_every=2,
            csv_chunk_size_rows=3, job_id="snapshot-case",
            on_progress=lambda *args: progress.append(list(args)),
            on_measured_progress=lambda *args: measured.append(list(args)),
        )
        output = {"snapshot": result}
    except ValueError as exc:
        output = {"error": {"type": type(exc).__name__, "message": str(exc)}}
    assert path.read_text() == case["text"]
    return {**output, "progress": progress, "measured_progress": measured}


def exact_json(value):
    # No sorted keys: catch dictionary insertion order as well as list/value changes.
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


@pytest.mark.parametrize("name", CASES)
def test_complete_snapshot_matches_prechange_capture(name, tmp_path, monkeypatch):
    expected = json.loads(FIXTURE.read_text())[name]
    actual = capture_snapshot(CASES[name], tmp_path, monkeypatch)
    assert exact_json(actual) == exact_json(expected)


@pytest.mark.parametrize("catalog_kind", ["absent", "without_units", "with_units"])
@pytest.mark.parametrize("fallback", [False, True])
def test_snapshot_trusted_handoff_and_fallback(catalog_kind, fallback, tmp_path, monkeypatch):
    # Exercise the real process_csv_file + wrapper + validator call chain. Stub
    # analysis/persistence at their boundaries, not snapshot processing.
    case = CASES["multiple_aliases_and_missing"]
    path = tmp_path / "source.csv"
    path.write_text(case["text"])
    expected = json.loads(FIXTURE.read_text())["multiple_aliases_and_missing"]["snapshot"]
    trusted_rows = [{"normalized_flow": 123.5, "__source_row_number": 9}]
    catalog = None if catalog_kind == "absent" else {"normalized_flow": {"canonical_role": "flow"}}
    if catalog_kind == "with_units":
        catalog["normalized_flow"]["unit"] = "m3/h"
    trust = {"dataset_identity": "immutable-source", "readiness": {"outcome": "ready"},
             "timestamp_profile": {"dataset_start": "start", "dataset_end": "end"},
             "canonical_dataset": {"analysis_sample_stride": 2}}
    handoff = {"columns": ["normalized_flow"], "rows": trusted_rows, "row_count_total": 2,
               "timestamp_column": None, "telemetry_signal_catalog": catalog}
    monkeypatch.setenv("NERAIUM_MAX_INGESTION_ANALYSIS_ROWS", "5000000")
    monkeypatch.setattr(upload_jobs, "CSV_CHUNK_SIZE_ROWS", 3)
    monkeypatch.setattr(upload_jobs, "CSV_PROGRESS_UPDATE_EVERY", 2)
    monkeypatch.setattr(upload_jobs, "build_historical_ingestion", lambda *a, **kw: (trust, handoff))
    monkeypatch.setattr(upload_jobs, "read_job", lambda *a: {})
    monkeypatch.setattr(upload_jobs, "_set_propagation_stage", lambda *a, **kw: None)
    monkeypatch.setattr(upload_jobs, "_persist_job_progress", lambda *a, **kw: None)
    monkeypatch.setattr(upload_jobs, "_log_processing_event", lambda *a, **kw: None)
    captured = {}
    original_snapshot = upload_jobs.stream_csv_snapshot

    def snapshot(*args, **kwargs):
        result = original_snapshot(*args, **kwargs)
        assert exact_json(result) == exact_json(expected)
        captured["snapshot"] = result
        return result

    def build(*args):
        captured["build_args"] = args
        if fallback:
            raise RuntimeError("downstream analysis failure")
        return {"job_id": "snapshot-case"}

    def partial(**kwargs):
        assert str(kwargs["error"]) == "downstream analysis failure"
        assert exact_json(kwargs["snapshot"]) == exact_json(expected)
        captured["fallback"] = kwargs["snapshot"]
        return {"job_id": "snapshot-case"}

    monkeypatch.setattr(upload_jobs, "stream_csv_snapshot", snapshot)
    monkeypatch.setattr(upload_jobs, "_build_csv_result", build)
    monkeypatch.setattr(upload_jobs, "_complete_with_partial_result", partial)
    monkeypatch.setattr(upload_jobs, "read_upload_result_by_job_id", lambda *a: {"snapshot": captured["snapshot"]})
    assert upload_jobs.process_csv_file(path, job_id="snapshot-case") == {"snapshot": expected}
    args = captured["build_args"]
    assert args[2:8] == (["normalized_flow"], trusted_rows, 2, None, "start", "end")
    assert args[8:10] == (expected["chunk_count"], expected["memory_estimate_bytes"])
    assert args[12] is trust and args[13] is catalog
    assert args[10] == {
        "rows_received": expected["rows_received"], "rows_used": expected["rows_used"],
        "rows_dropped": expected["rows_dropped"], "drop_reasons": expected["drop_reasons"],
        "quality_counts": expected["quality_counts"], "warnings": expected["cleaning_warnings"],
        "schema_detection": expected["schema_detection"], "analysis_gate_state": expected["analysis_gate_state"],
        "data_quality_messages": expected["data_quality_messages"],
        "sample_interval_seconds": expected["sample_interval_seconds"], "imputation_report": expected["imputation_report"],
        "analysis_sample_rows": 1, "analysis_population_rows": 2, "analysis_sampling_applied": True,
        "analysis_sample_stride": 2, "delimiter": expected["delimiter"], "header_present": expected["header_present"],
        "input_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
        "historical_trust_dataset_identity": "immutable-source", "historical_trust_readiness": "ready", "performance": {},
    }
    assert ("fallback" in captured) == fallback
    assert path.read_text() == case["text"]
