from fastapi.testclient import TestClient

from app.main import create_app
from app.services.sii_intelligence import build_sample_intelligence
from app.services.sii_runner import write_latest_sii_state


def test_sii_reference_sections_present_in_intelligence_payload() -> None:
    payload = build_sample_intelligence()

    assert "sii_reference_architecture" in payload
    assert "ontology_corpus" in payload
    assert "industry_certification_packs" in payload
    assert "multi_site_cognition_network" in payload
    assert "structural_cognition_api_contracts" in payload
    assert "operational_language_standard" in payload
    assert "institutional_validation" in payload
    assert "replay_timeline" in payload


def test_audit_and_replay_endpoints_remain_available_with_reference_layer() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())

    assert client.get("/api/replay/timeline").status_code == 200
    assert client.get("/api/audit/session/reference").status_code == 200
    assert client.get("/api/audit/replay/reference").status_code == 200
    assert client.get("/api/audit/evidence/reference").status_code == 200
