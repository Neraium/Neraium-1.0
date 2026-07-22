from fastapi.testclient import TestClient

from app.main import create_app
from app.services import evidence_store


def _record(run_id: str, governance: dict | None = None) -> dict:
    return {
        "run_id": run_id,
        "source_name": "site-historian.csv",
        "source_type": "csv_upload",
        "status": "completed",
        "created_at": "2026-07-20T08:00:00Z",
        "completed_at": "2026-07-20T09:00:00Z",
        "rows_received": 10,
        "rows_accepted": 8,
        "rows_rejected": 2,
        "sensors_detected": 2,
        "system_id": "flow-system",
        "room": "Plant room",
        "evidence_summary": ["Flow response weakened during comparable pump demand."],
        "warnings": ["Two observations were unavailable."],
        "errors": [],
        "data_conditions": ["Historian coverage incomplete"],
        "drift_metrics": {"baseline_distance": 0.42},
        "evidence_windows": [{"type": "data_gap", "source": "Historian X", "start": "2026-07-20T08:10:00Z", "end": "2026-07-20T08:35:00Z"}],
        "observation_type": "relationship_change",
        "observation_status": "open",
        "variables": ["flow", "pump_demand"],
        "operator_feedback_history": [],
        "traceability": {"model_version": "sii-test", "steps": [{"type": "observation", "source": "Historian X"}]},
        "governance_boundary": governance or {"policy_id": "site-policy", "statement": "Derived evidence may leave the site; raw telemetry may not."},
        "raw_telemetry": [{"timestamp": "2026-07-20T08:00:00Z", "flow": 123.4}],
    }


def test_json_evidence_package_applies_governance_and_excludes_raw_telemetry() -> None:
    client = TestClient(create_app())
    evidence_store.upsert_evidence_run(_record("package-governed"))

    response = client.get("/api/evidence/package/package-governed?format=json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["package_type"] == "neraium_evidence_package"
    assert payload["confidence_tier"] == "Narrowed"
    assert payload["governance"]["raw_telemetry_included"] is False
    assert payload["governance"]["policy_id"] == "site-policy"
    assert "raw_telemetry" not in payload
    assert payload["data_gaps"][0]["source"] == "Historian X"
    assert payload["human_notes_and_outcomes"] == []


def test_pdf_evidence_package_is_a_downloadable_pdf() -> None:
    client = TestClient(create_app())
    evidence_store.upsert_evidence_run(_record("package-pdf"))

    response = client.get("/api/evidence/package/package-pdf?format=pdf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "neraium-evidence-package-pdf.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-1.4")
    assert b"NERAIUM EVIDENCE PACKAGE" in response.content


def test_raw_telemetry_requires_explicit_export_permission() -> None:
    client = TestClient(create_app())
    record = _record("package-explicit", {"policy_id": "allow-policy", "raw_telemetry_export_allowed": True})
    evidence_store.upsert_evidence_run(record)

    payload = client.get("/api/evidence/package/package-explicit?format=json").json()

    assert payload["governance"]["raw_telemetry_included"] is True
    assert payload["raw_telemetry"] == record["raw_telemetry"]


def test_tag_for_audit_persists_actor_and_timestamp() -> None:
    client = TestClient(create_app())
    evidence_store.upsert_evidence_run(_record("audit-tag-run"))

    response = client.post("/api/evidence/runs/audit-tag-run/audit-tag", headers={"X-Neraium-User": "engineer@example.com"})

    assert response.status_code == 200
    tags = response.json()["audit_tags"]
    assert len(tags) == 1
    assert tags[0]["actor"] == "engineer@example.com"
    assert tags[0]["tagged_at"].endswith("+00:00")


def test_evidence_package_requires_operator_role_in_production(monkeypatch, tmp_path) -> None:
    from app.core.config import Settings
    from app.services.auth_store import create_user

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    settings = Settings(app_env="production", backend_host="127.0.0.1", backend_port=8010, cors_origins=["https://app.neraium.com"], runtime_dir=tmp_path)
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        evidence_store.upsert_evidence_run(_record("permission-run"))
        create_user("viewer@example.com", "password123", role="viewer")
        login = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "password123"})
        assert login.status_code == 200
        assert client.get("/api/evidence/package/permission-run?format=json").status_code == 403

        create_user("operator@example.com", "password123", role="operator")
        login = client.post("/api/auth/login", json={"email": "operator@example.com", "password": "password123"})
        assert login.status_code == 200
        assert client.get("/api/evidence/package/permission-run?format=json").status_code == 200
