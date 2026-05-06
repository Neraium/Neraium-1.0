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
