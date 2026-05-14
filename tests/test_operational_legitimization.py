from fastapi.testclient import TestClient

from app.main import create_app
from app.services.sii_intelligence import build_sample_intelligence
from app.services.sii_runner import write_latest_sii_state


def test_legitimization_payload_sections_exist() -> None:
    payload = build_sample_intelligence()

    assert "cognition_validation" in payload
    assert "operational_audit" in payload
    assert "domain_validation_case_studies" in payload
    assert "sii_standard" in payload
    assert "structural_progression_dataset" in payload
    assert "operational_cognition_simulation" in payload
    assert "institutional_trust" in payload
    assert "behavioral_infrastructure_twin" in payload


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
