from fastapi.testclient import TestClient

from app.main import create_app
from app.routers.audit import current_intelligence
from app.services.sii_intelligence import DEFAULT_CUSTOMER_EXCLUDED_STRUCTURAL_FIELDS, build_sample_intelligence
from app.services.sii_runner import write_latest_sii_state


def test_legitimization_packages_are_not_default_customer_authority() -> None:
    payload = build_sample_intelligence()

    assert DEFAULT_CUSTOMER_EXCLUDED_STRUCTURAL_FIELDS.isdisjoint(payload)
    assert payload["core_sii_outputs"]
    assert payload["aletheia_gate"]
    assert payload["evidence_lineage"]


def test_audit_endpoints_return_replay_and_lineage() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())

    session_response = client.get("/api/audit/session/latest")
    replay_response = client.get("/api/audit/replay/latest")
    evidence_response = client.get("/api/audit/evidence/latest")

    assert session_response.status_code == 200
    assert replay_response.status_code == 200
    assert evidence_response.status_code == 200

    session_payload = session_response.json()
    assert "audit_record" in session_payload
    assert session_payload["audit_record"]["archetypes"] is not None
    assert session_payload["timeline_reconstruction"]

    replay_payload = replay_response.json()
    assert replay_payload["replay"]

    evidence_payload = evidence_response.json()
    assert "evidence_lineage" in evidence_payload


def test_production_audit_has_no_sample_intelligence_fallback(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")

    assert current_intelligence() is None
