from fastapi.testclient import TestClient

from app.main import create_app


def test_upload_valid_csv_returns_preview_metadata() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,room,temperature,humidity\n"
        "2026-05-01T08:00:00Z,Flower 1,75.2,58\n"
        "2026-05-01T08:05:00Z,Flower 1,75.6,59\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("sensor-export.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "sensor-export.csv"
    assert payload["row_count"] == 2
    assert payload["column_count"] == 4
    assert payload["columns"] == ["timestamp", "room", "temperature", "humidity"]
    assert payload["detected_timestamp_column"] == "timestamp"
    assert payload["warnings"] == []
    assert payload["data_quality"]["readiness"] == "ready"
    assert payload["data_quality"]["numeric_column_count"] == 2
    assert payload["timestamp_profile"]["estimated_sample_interval"] == "5 minutes"
    assert payload["preview_rows"][0] == {
        "timestamp": "2026-05-01T08:00:00Z",
        "room": "Flower 1",
        "temperature": "75.2",
        "humidity": "58",
    }


def test_upload_profiles_numeric_columns() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,temperature,humidity\n"
        "2026-05-01T08:00:00Z,74,55\n"
        "2026-05-01T08:05:00Z,76,60\n"
        "2026-05-01T08:10:00Z,80,65\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("numeric-profile.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    profiles = {profile["column"]: profile for profile in payload["numeric_profiles"]}
    assert profiles["temperature"]["min"] == 74
    assert profiles["temperature"]["max"] == 80
    assert profiles["temperature"]["average"] == 76.6667
    assert profiles["temperature"]["missing_count"] == 0
    assert profiles["temperature"]["missing_percent"] == 0
    assert profiles["temperature"]["variability"] == "normal"


def test_upload_profiles_missing_values() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,temperature,humidity\n"
        "2026-05-01T08:00:00Z,74,55\n"
        "2026-05-01T08:05:00Z,,\n"
        "2026-05-01T08:10:00Z,80,65\n"
        "2026-05-01T08:15:00Z,,70\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("missing-values.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    profiles = {profile["column"]: profile for profile in payload["numeric_profiles"]}
    assert profiles["temperature"]["missing_count"] == 2
    assert profiles["temperature"]["missing_percent"] == 50
    assert profiles["humidity"]["missing_count"] == 1
    assert profiles["humidity"]["missing_percent"] == 25


def test_upload_detects_timestamp_profile() -> None:
    client = TestClient(create_app())
    csv_content = (
        "recorded_at,temperature\n"
        "2026-05-01T08:00:00Z,74\n"
        "2026-05-01T08:15:00Z,75\n"
        "2026-05-01T08:30:00Z,76\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("timestamps.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_timestamp_column"] == "recorded_at"
    assert payload["timestamp_profile"]["first_timestamp"] == "2026-05-01T08:00:00"
    assert payload["timestamp_profile"]["last_timestamp"] == "2026-05-01T08:30:00"
    assert payload["timestamp_profile"]["estimated_sample_interval"] == "15 minutes"
    assert payload["timestamp_profile"]["warnings"] == []


def test_upload_marks_readiness_needs_review_for_warnings() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,humidity\n"
        "2026-05-01T08:00:00Z,55\n"
        "not-a-time,110\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("needs-review.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_quality"]["readiness"] == "needs_review"
    assert "Timestamp column contains values that could not be parsed." in payload["warnings"]
    assert (
        "humidity contains values outside the expected 0-100 humidity range."
        in payload["warnings"]
    )


def test_upload_marks_header_only_csv_not_ready() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/data/upload",
        files={"file": ("header-only.csv", "timestamp,temperature\n", "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 0
    assert payload["data_quality"]["readiness"] == "not_ready"
    assert "CSV contains headers but no data rows." in payload["warnings"]


def test_upload_baseline_window_calculation() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,{70 + index}" for index in range(10)
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("baseline-window.csv", f"timestamp,temperature\n{rows}", "text/csv")},
    )

    assert response.status_code == 200
    analysis = response.json()["baseline_analysis"]
    assert analysis["baseline_window_rows"] == 2
    assert analysis["recent_window_rows"] == 2
    assert analysis["columns_analyzed"] == 1


def test_upload_detects_upward_baseline_drift() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,temperature\n"
        "2026-05-01T08:00:00Z,70\n"
        "2026-05-01T08:05:00Z,70\n"
        "2026-05-01T08:10:00Z,72\n"
        "2026-05-01T08:15:00Z,74\n"
        "2026-05-01T08:20:00Z,90\n"
        "2026-05-01T08:25:00Z,90\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("upward-drift.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    drift = response.json()["baseline_analysis"]["column_drift"][0]
    assert drift["baseline_average"] == 70
    assert drift["recent_average"] == 90
    assert drift["direction"] == "up"
    assert drift["drift_flag"] == "review"


def test_upload_detects_downward_baseline_drift() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,humidity\n"
        "2026-05-01T08:00:00Z,80\n"
        "2026-05-01T08:05:00Z,80\n"
        "2026-05-01T08:10:00Z,76\n"
        "2026-05-01T08:15:00Z,72\n"
        "2026-05-01T08:20:00Z,60\n"
        "2026-05-01T08:25:00Z,60\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("downward-drift.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    drift = response.json()["baseline_analysis"]["column_drift"][0]
    assert drift["baseline_average"] == 80
    assert drift["recent_average"] == 60
    assert drift["direction"] == "down"
    assert drift["drift_flag"] == "review"


def test_upload_marks_flat_baseline_data_normal() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,75" for index in range(6)
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("flat-data.csv", f"timestamp,temperature\n{rows}", "text/csv")},
    )

    assert response.status_code == 200
    analysis = response.json()["baseline_analysis"]
    drift = analysis["column_drift"][0]
    assert drift["direction"] == "flat"
    assert drift["drift_flag"] == "normal"
    assert analysis["overall_assessment"] == "normal"


def test_upload_baseline_warns_for_missing_numeric_values() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,temperature\n"
        "2026-05-01T08:00:00Z,70\n"
        "2026-05-01T08:05:00Z,\n"
        "2026-05-01T08:10:00Z,72\n"
        "2026-05-01T08:15:00Z,74\n"
        "2026-05-01T08:20:00Z,\n"
        "2026-05-01T08:25:00Z,90\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("missing-baseline.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    analysis = response.json()["baseline_analysis"]
    assert analysis["overall_assessment"] == "needs_review"
    assert (
        "temperature has missing values in baseline or recent windows."
        in analysis["warnings"]
    )


def test_upload_baseline_handles_too_few_rows() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,temperature\n"
        "2026-05-01T08:00:00Z,70\n"
        "2026-05-01T08:05:00Z,71\n"
        "2026-05-01T08:10:00Z,72\n"
        "2026-05-01T08:15:00Z,73\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("too-few-rows.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    analysis = response.json()["baseline_analysis"]
    assert analysis["columns_analyzed"] == 0
    assert analysis["overall_assessment"] == "needs_review"
    assert "At least 5 data rows are needed for baseline comparison." in analysis["warnings"]


def test_upload_generates_operator_report_from_ready_data() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,75,58" for index in range(10)
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("ready-report.csv", f"timestamp,temperature,humidity\n{rows}", "text/csv")},
    )

    assert response.status_code == 200
    report = response.json()["operator_report"]
    assert report["title"] == "Cultivation Data Upload Report"
    assert report["data_readiness"] == "ready"
    assert "usable for initial review" in report["summary"]
    assert report["time_coverage"]["detected_timestamp_column"] == "timestamp"
    assert report["key_observations"]
    assert report["recommended_operator_checks"]


def test_upload_report_includes_limitations_when_data_needs_review() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,humidity\n"
        "2026-05-01T08:00:00Z,55\n"
        "not-a-time,110\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("limited-report.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    report = response.json()["operator_report"]
    assert report["data_readiness"] == "needs_review"
    assert any("Evidence is limited" in limitation for limitation in report["limitations"])


def test_upload_report_does_not_invent_causes() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,{70 + index}" for index in range(10)
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("cause-check.csv", f"timestamp,temperature\n{rows}", "text/csv")},
    )

    assert response.status_code == 200
    report_text = str(response.json()["operator_report"]).lower()
    assert "root cause is" not in report_text
    assert "caused by" not in report_text
    assert "will fail" not in report_text
    assert "yield impact is" not in report_text


def test_upload_report_references_only_available_sections() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,75" for index in range(6)
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("sections-used.csv", f"timestamp,temperature\n{rows}", "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["operator_report"]["source_sections_used"] == [
        "data_quality",
        "timestamp_profile",
        "numeric_profiles",
        "baseline_analysis",
    ]


def test_upload_report_for_empty_profile_does_not_make_unsupported_claims() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/data/upload",
        files={"file": ("header-only-report.csv", "timestamp,temperature\n", "text/csv")},
    )

    assert response.status_code == 200
    report = response.json()["operator_report"]
    report_text = str(report).lower()
    assert report["data_readiness"] == "not_ready"
    assert "does not yet have enough usable structure" in report["summary"]
    assert "root cause" in report_text
    assert "predict" in report_text
    assert "root cause is" not in report_text
    assert "crop stress prediction" not in report_text


def test_upload_rejects_invalid_extension() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/data/upload",
        files={"file": ("sensor-export.txt", "timestamp,value\n2026-05-01,75", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only .csv files are supported."


def test_upload_rejects_empty_csv() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/data/upload",
        files={"file": ("empty.csv", "", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV file is empty."
