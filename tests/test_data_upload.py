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
    assert payload["preview_rows"][0] == {
        "timestamp": "2026-05-01T08:00:00Z",
        "room": "Flower 1",
        "temperature": "75.2",
        "humidity": "58",
    }


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
