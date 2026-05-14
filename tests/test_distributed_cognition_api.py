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


def test_behavior_science_endpoints_return_payloads() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())

    memory = client.get("/api/distributed/science/memory")
    assert memory.status_code == 200
    assert memory.json().get("seasonal_profiles")

    taxonomy = client.get("/api/distributed/science/taxonomy")
    assert taxonomy.status_code == 200
    assert taxonomy.json().get("classification_result")

    theory = client.get("/api/distributed/science/evolution-theory")
    assert theory.status_code == 200
    assert len(theory.json().get("rules", [])) >= 1

    research = client.get("/api/distributed/science/research")
    assert research.status_code == 200
    assert research.json().get("studies")

    explainability = client.get("/api/distributed/science/explainability")
    assert explainability.status_code == 200
    assert explainability.json().get("assessment")

    lab = client.get("/api/distributed/science/laboratory")
    assert lab.status_code == 200
    assert lab.json().get("scenario")

    federation = client.get("/api/distributed/science/federation")
    assert federation.status_code == 200
    assert federation.json().get("exchange_payload")


def test_universal_framework_endpoints_return_payloads() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())

    primitives = client.get("/api/distributed/framework/primitives")
    assert primitives.status_code == 200
    assert primitives.json().get("primitive_count", 0) >= 10

    mathematics = client.get("/api/distributed/framework/mathematics")
    assert mathematics.status_code == 200
    assert mathematics.json().get("topology_transition")

    governance = client.get("/api/distributed/framework/ontology-governance")
    assert governance.status_code == 200
    assert governance.json().get("promotion_queue")

    training = client.get("/api/distributed/framework/training-curriculum")
    assert training.status_code == 200
    assert training.json().get("modules")

    extreme = client.get("/api/distributed/framework/extreme-environment")
    assert extreme.status_code == 200
    assert extreme.json().get("contexts")

    archive = client.get("/api/distributed/framework/archive")
    assert archive.status_code == 200
    assert archive.json().get("replay_sequences")

    research = client.get("/api/distributed/framework/research-ecosystem")
    assert research.status_code == 200
    assert research.json().get("primitive_dataset")

    reasoning = client.get("/api/distributed/framework/reasoning-substrate")
    assert reasoning.status_code == 200
    assert reasoning.json().get("trace")
