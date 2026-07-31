from app.main import create_app
from app.services import evidence_store, runtime_db
from fastapi.testclient import TestClient


def _record(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "source_type": "csv_upload",
        "status": "completed",
        "created_at": "2026-07-20T08:00:00Z",
        "completed_at": "2026-07-20T09:00:00Z",
        "observation_status": "open",
        "operator_feedback_history": [],
        "finding_status_history": [],
        "variables": ["flow", "pump_speed"],
        "input_hash": "input-v1",
        "result_hash": "result-v1",
        "evidence_hash": "evidence-v1",
    }


def test_feedback_and_workflow_state_are_independent_append_only_events() -> None:
    client = TestClient(create_app())
    evidence_store.upsert_evidence_run(_record("finding-run"))
    original = runtime_db.read_evidence_run_db("finding-run")

    feedback = client.post(
        "/api/evidence/runs/finding-run/feedback",
        headers={"X-Neraium-User": "engineer@example.com"},
        json={"category": "false_positive", "note": "Verified scheduled maintenance."},
    )
    assert feedback.status_code == 200
    assert feedback.json()["observation_status"] == "open"

    status = client.post(
        "/api/evidence/runs/finding-run/status",
        headers={"X-Neraium-User": "engineer@example.com"},
        json={
            "state": "dismissed",
            "note": "Close after verification.",
            "work_order_reference": "WO-1042",
        },
    )
    assert status.status_code == 200
    payload = status.json()
    assert payload["observation_status"] == "dismissed"
    assert payload["work_order_reference"] == "WO-1042"
    assert payload["finding_status_history"][0]["state"] == "dismissed"
    assert payload["operator_feedback_history"][0]["category"] == "false_positive"

    assert runtime_db.read_evidence_run_db("finding-run") == original


def test_missing_finding_does_not_create_orphan_events() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/evidence/runs/missing-finding/status",
        json={"state": "investigating"},
    )

    assert response.status_code == 404
    with runtime_db.db_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM finding_status_events WHERE run_id = ?",
            ("missing-finding",),
        ).fetchone()["count"]
    assert count == 0
