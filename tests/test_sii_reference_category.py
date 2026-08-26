from fastapi.testclient import TestClient

from app.main import create_app
from app.services.sii_intelligence import DEFAULT_CUSTOMER_EXCLUDED_STRUCTURAL_FIELDS, build_sample_intelligence
from app.services.sii_runner import write_latest_sii_state


def test_static_and_research_sections_are_absent_from_default_sample_authority() -> None:
    payload = build_sample_intelligence()

    assert DEFAULT_CUSTOMER_EXCLUDED_STRUCTURAL_FIELDS.isdisjoint(payload)
    assert payload["supporting_evidence"]
    assert payload["relationship_evidence"]
    assert payload["evidence_lineage"]
    assert payload["rooms"]


def test_audit_and_replay_endpoints_remain_available_with_reference_layer() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())

    assert client.get("/api/replay/timeline").status_code == 200
    assert client.get("/api/audit/session/reference").status_code == 200
    assert client.get("/api/audit/replay/reference").status_code == 200
    assert client.get("/api/audit/evidence/reference").status_code == 200
