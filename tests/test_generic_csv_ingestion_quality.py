from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.upload_jobs import process_csv_content


def _rows(count: int = 24, *, no_timestamp: bool = False, sparse: bool = False, extra: bool = False) -> bytes:
    columns = [] if no_timestamp else ["timestamp"]
    columns += ["asset", "temperature_f", "pressure_psi", "motor_kw", "alarm_status"]
    if extra:
        columns.append("vendor_blob")
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    output = [",".join(columns)]
    for index in range(count):
        row = {
            "timestamp": (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z"),
            "asset": "pump-1",
            "temperature_f": f"{70 + index * 0.1:.2f}",
            "pressure_psi": f"{30 + index * 0.2:.2f}",
            "motor_kw": f"{8 + index * 0.05:.2f}",
            "alarm_status": "normal" if index % 10 else "alarm",
            "vendor_blob": "ignored",
        }
        if sparse and index in {5, 6}:
            row["pressure_psi"] = ""
        output.append(",".join(row.get(column, "") for column in columns))
    return "\n".join(output).encode()


def test_sparse_nulls_do_not_block_generic_analysis() -> None:
    result = process_csv_content(filename="generic-sparse.csv", content=_rows(sparse=True))

    assert result["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"
    assert result["data_quality"]["readiness"] == "ready"
    assert result["ingestion_report"]["imputation_report"]["imputed_cells"] == 2
    assert "Sparse missing values detected; short numeric gaps interpolated." in result["data_quality"]["messages"]


def test_unknown_extra_columns_do_not_block_generic_analysis() -> None:
    result = process_csv_content(filename="generic-extra.csv", content=_rows(extra=True))

    assert "vendor_blob" in result["columns"]
    assert result["data_quality"]["analysis_gate_state"] == "READY"
    assert "Unknown extra columns ignored unless they break parsing." in result["data_quality"]["messages"]


def test_out_of_order_timestamps_are_sorted_for_generic_analysis() -> None:
    lines = _rows().decode().splitlines()
    lines[3], lines[4] = lines[4], lines[3]
    result = process_csv_content(filename="generic-unsorted.csv", content="\n".join(lines).encode())

    timestamps = [row["timestamp"] for row in result["preview_rows"][:5]]
    assert timestamps == sorted(timestamps)
    assert result["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"


def test_duplicate_rows_are_dropped_for_generic_analysis() -> None:
    lines = _rows().decode().splitlines()
    lines.insert(8, lines[7])
    result = process_csv_content(filename="generic-duplicate.csv", content="\n".join(lines).encode())

    assert result["row_count"] == 24
    assert result["ingestion_report"]["drop_reasons"]["exact_duplicate_row"] == 1
    assert result["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"


def test_unknown_csv_still_gets_profiled() -> None:
    content = b"name,phase,label\na,b,c\nd,e,f\ng,h,i\nj,k,l\nm,n,o"
    result = process_csv_content(filename="unknown.csv", content=content)

    assert result["data_quality"]["analysis_gate_state"] == "PENDING"
    assert result["data_quality"]["schema_detection"]["generic_profile"]["categorical_columns"]
    assert "Analysis is pending because at least two usable numeric telemetry columns are required." in result["data_quality"]["messages"]


def test_no_timestamp_falls_back_to_row_index_with_numeric_signal() -> None:
    result = process_csv_content(filename="row-index.csv", content=_rows(no_timestamp=True))

    assert result["detected_timestamp_column"] is None
    assert result["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"
    assert result["data_quality"]["readiness"] == "ready"


def test_missing_one_important_sensor_degrades_instead_of_blocking() -> None:
    lines = _rows().decode().splitlines()
    header = lines[0].split(",")
    pressure_index = header.index("pressure_psi")
    for index in range(1, 10):
        parts = lines[index].split(",")
        parts[pressure_index] = ""
        lines[index] = ",".join(parts)
    result = process_csv_content(filename="missing-sensor.csv", content="\n".join(lines).encode())

    assert result["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"
    assert result["data_quality"]["readiness"] == "ready"


def test_empty_csv_returns_error_state() -> None:
    with pytest.raises(ValueError, match="CSV file is empty"):
        process_csv_content(filename="empty.csv", content=b"")


def test_malformed_unreadable_csv_returns_error_state() -> None:
    with pytest.raises(ValueError):
        process_csv_content(filename="malformed.csv", content=b"timestamp,temp\n\x00\x00")


def test_missing_timestamp_and_insufficient_numeric_signal_is_pending() -> None:
    content = b"asset,status,note\npump-1,on,a\npump-1,off,b\npump-1,on,c\npump-1,on,d\npump-1,off,e\npump-1,on,f"
    result = process_csv_content(filename="insufficient-row-index.csv", content=content)

    assert result["data_quality"]["analysis_gate_state"] == "PENDING"
    assert result["data_quality"]["readiness"] == "pending"
