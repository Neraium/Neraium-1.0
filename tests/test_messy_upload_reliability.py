from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time

from app.services.evidence_store import read_evidence_run
from app.services.upload_jobs import process_csv_content


def test_messy_csv_degrades_gracefully_and_reports_cleaning() -> None:
    result = process_csv_content(
        filename="messy-real-world.csv",
        content=(
            " Event Time ,Zone Name,Temp F,RH %,extra_note\n"
            "2026-05-01T08:20:00Z,Flower A,78 F,61%,late\n"
            "\n"
            "2026-05-01T08:00:00Z,Flower A,74 F,55%,start\n"
            "2026-05-01T08:05:00Z,Flower A,,56%,missing temp\n"
            "2026-05-01T08:05:00Z,Flower A,75 F,56%,duplicate\n"
            "not-a-time,Flower A,76 F,57%,bad timestamp\n"
            "2026-05-01T08:10:00Z,Flower A,bad,58%,bad temp only\n"
            "2026-05-01T08:15:00Z,Flower A,bad,nope,no numeric values\n"
            "2026-05-01T08:25:00Z,Flower A,79 F,62%,ok\n"
            "2026-05-01T08:30:00Z,Flower A,80 F,63%,ok\n"
            "2026-05-01T08:35:00Z,Flower A,81 F,64%,ok\n"
            "2026-05-01T08:40:00Z,Flower A,82 F,65%,ok\n"
            "2026-05-01T08:45:00Z,Flower A,83 F,66%,ok\n"
            "2026-05-01T08:50:00Z,Flower A,84 F,67%,ok\n"
            "2026-05-01T08:55:00Z,Flower A,85 F,68%,ok\n"
        ).encode(),
    )

    report = result["ingestion_report"]
    assert report["rows_received"] == 15
    assert report["rows_used"] == 11
    assert report["rows_dropped"] == 4
    assert report["drop_reasons"] == {
        "blank_row": 1,
        "invalid_timestamp": 1,
        "duplicate_timestamp": 1,
        "no_usable_numeric_values": 1,
    }
    assert report["quality_counts"]["rows_with_missing_values"] == 1
    assert report["quality_counts"]["rows_with_invalid_numeric"] == 1
    assert result["preview_rows"][0]["Event Time"] == "2026-05-01T08:00:00Z"
    assert result["processing_time_seconds"] >= 0
    assert result["evidence_persistence"]["persisted"] is True
    assert result["evidence_persistence"]["synthetic_fallback_used"] is False
    assert read_evidence_run(result["job_id"])["rows_rejected"] == 4


def test_whitespace_delimited_cmapss_style_upload_is_ingested(client) -> None:
    rows = "\n".join(
        f"1 {cycle} {0.1 * cycle:.2f} {0.2 * cycle:.2f} {500 + cycle} {20 + cycle / 10:.2f}"
        for cycle in range(1, 31)
    )
    upload = client.post(
        "/api/data/upload",
        files={"file": ("train_FD001.txt", rows, "text/plain")},
    )
    assert upload.status_code == 202
    status_url = upload.json()["status_url"]
    deadline = time.monotonic() + 5
    status = {}
    while time.monotonic() < deadline:
        status = client.get(status_url).json()
        if status.get("status") in {"COMPLETE", "FAILED"}:
            break
        time.sleep(0.02)
    assert status.get("status") == "COMPLETE"
    result = client.get("/api/data/latest-upload?include_persisted=1").json()["latest_result"]

    report = result["ingestion_report"]
    assert report["delimiter"] == "whitespace"
    assert report["header_present"] is False
    assert report["rows_received"] == 30
    assert report["rows_used"] == 30
    assert result["columns"] == [f"column_{index}" for index in range(1, 7)]
    assert result["numeric_profiles"]
    assert result["sii_runner_result"]["runner_used"] is True
    assert result["evidence_persistence"]["persisted"] is True


def test_insufficient_baseline_is_explicit_and_not_displayable() -> None:
    result = process_csv_content(
        filename="too-small.csv",
        content=(
            "timestamp,temp_c,pressure_kpa\n"
            "2026-05-01T08:00:00Z,21,101\n"
            "2026-05-01T08:07:00Z,22,102\n"
            "2026-05-01T08:19:00Z,23,103\n"
            "2026-05-01T08:31:00Z,24,104\n"
        ).encode(),
    )

    assert "Insufficient baseline" in result["quality_warning"]
    assert result["sii_reliable_enough_to_show"] is False
    assert result["evidence_persistence"]["persisted"] is True
    assert result["evidence_persistence"]["synthetic_fallback_used"] is False


def test_valid_noisy_irregular_telemetry_remains_evidence_backed() -> None:
    offsets = [0, 5, 11, 16, 24, 29, 35, 44, 49, 55, 62, 70, 75, 83, 90, 98, 105, 113, 120, 128]
    start = datetime(2026, 5, 1, 8, tzinfo=timezone.utc)
    rows = []
    for index, offset in enumerate(offsets):
        timestamp = (start + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z")
        rows.append(f"{timestamp},AHU 1,{72 + (index % 4)} F,{1.2 + index * 0.03:.2f} kPa,{45 + (index % 5)}%")
    result = process_csv_content(
        filename="noisy-units.csv",
        content=("Recorded At,Asset Name,Supply Temp (mixed),Static Pressure weird,RH-percent\n" + "\n".join(rows)).encode(),
    )

    assert result["ingestion_report"]["rows_dropped"] == 0
    assert result["timestamp_profile"]["estimated_sample_interval"] is None
    assert any("inconsistent" in warning.lower() for warning in result["timestamp_profile"]["warnings"])
    assert result["sii_reliable_enough_to_show"] is True
    assert result["evidence_persistence"]["persisted"] is True
    assert read_evidence_run(result["job_id"])["source_name"] == "noisy-units.csv"


def test_six_month_upload_performance_smoke() -> None:
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(180 * 48):
        timestamp = (start + timedelta(minutes=30 * index)).isoformat().replace("+00:00", "Z")
        rows.append(f"{timestamp},{72 + (index % 7) * 0.2:.1f},{48 + (index % 11) * 0.3:.1f},{300 + index % 17}")
    result = process_csv_content(
        filename="six-month-telemetry.csv",
        content=("timestamp,temperature,humidity,airflow\n" + "\n".join(rows)).encode(),
    )

    assert result["ingestion_report"]["rows_received"] == 8640
    assert result["ingestion_report"]["rows_used"] == 8640
    assert result["processing_stats"]["sampled_rows"] == 8640
    assert result["processing_time_seconds"] < 20
    assert result["sii_reliable_enough_to_show"] is True
    assert result["evidence_persistence"]["persisted"] is True
