from fastapi.testclient import TestClient

from app.main import create_app
from app.services.sii_intelligence import build_sample_intelligence
from app.services.sii_runner import write_latest_sii_state


def test_distributed_cognition_endpoints_return_payloads() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())

    memory = client.get("/api/distributed/memory")
    assert memory.status_code == 200
    assert "latest_snapshot" in memory.json()

    federation = client.get("/api/distributed/federation")
    assert federation.status_code == 200
    assert federation.json().get("privacy_preserving_summary")

    search = client.get("/api/distributed/search")
    assert search.status_code == 200
    assert search.json().get("result", {}).get("total_results", 0) >= 0

    governance = client.get("/api/distributed/governance")
    assert governance.status_code == 200
    assert governance.json().get("validation_status")

