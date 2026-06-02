from fastapi.testclient import TestClient

from app.main import create_app


def post_csv(client: TestClient, filename: str, content: str):
    return client.post(
        "/api/data/upload",
        files={"file": (filename, content, "text/csv")},
    )


def wait_for_terminal_upload_status(client: TestClient, status_url: str) -> dict:
    for _ in range(160):
        response = client.get(status_url)
        payload = response.json()
        if payload["status"] in {"COMPLETE", "FAILED"}:
            return payload
    raise AssertionError("Upload did not reach a terminal state.")


def test_latest_upload_disables_adaptive_learning_snapshot() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index * 0.4:.1f},{58 + index * 0.2:.1f}"
        for index in range(8)
    )
    upload = post_csv(client, "adaptive.csv", f"timestamp,room,temperature,humidity\n{rows}")
    wait_for_terminal_upload_status(client, upload.json()["status_url"])

    latest = client.get("/api/data/latest-upload")
    assert latest.status_code == 200
    payload = latest.json()
    assert payload["adaptive_learning"] == {}


def test_operator_feedback_updates_evidence_record_without_adaptive_memory() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T09:{index:02d}:00Z,Flower 2,{80 + index * 0.6:.1f},{63 + index * 0.3:.1f}"
        for index in range(8)
    )
    upload = post_csv(client, "feedback.csv", f"timestamp,room,temperature,humidity\n{rows}")
    status_payload = wait_for_terminal_upload_status(client, upload.json()["status_url"])
    assert status_payload["status"] == "COMPLETE"

    latest = client.get("/api/data/latest-upload").json()
    run_id = latest["history"][0]["job_id"]
    response = client.post(f"/api/evidence/runs/{run_id}/feedback", json={"category": "false_positive", "note": "Known maintenance context"})
    assert response.status_code == 200
    record = response.json()
    assert record["latest_feedback_category"] == "false_positive"
    assert record["operator_feedback_history"][0]["category"] == "false_positive"

    refreshed = client.get("/api/data/latest-upload").json()
    assert refreshed["adaptive_learning"] == {}
