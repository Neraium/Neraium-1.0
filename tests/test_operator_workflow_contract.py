from fastapi.testclient import TestClient

from app.main import create_app
from app.services.sii_intelligence import build_sample_intelligence
from app.services.sii_runner import write_latest_sii_state


def test_canonical_cognition_state_contract_shape() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())
    response = client.get("/api/facility/cognition-state")
    assert response.status_code == 200
    payload = response.json()
    required = {
        "cognition_state",
        "structural_stability",
        "active_archetypes",
        "propagation_pathways",
        "evidence_lineage",
        "structural_memory_matches",
        "continuation_windows",
        "replay_summary",
        "recovery_convergence",
        "operator_explanation",
    }
    assert required.issubset(payload.keys())


def test_demo_replay_payload_is_available() -> None:
    client = TestClient(create_app())
    response = client.get("/api/replay/timeline?mode=demo&intervals=12")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("source") == "demo"
    assert payload.get("meta", {}).get("frame_count", 0) >= 8
    assert len(payload.get("timeline", [])) >= 8

