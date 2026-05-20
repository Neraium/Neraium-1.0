from fastapi.testclient import TestClient

from app.main import create_app


def test_domain_mode_roundtrip_and_facility_profile() -> None:
    client = TestClient(create_app())

    initial = client.get("/api/domain/mode")
    assert initial.status_code == 200
    assert initial.json()["mode"] in {"aquatic", "cultivation"}

    switched = client.post("/api/domain/mode", json={"mode": "cultivation"})
    assert switched.status_code == 200
    assert switched.json()["mode"] == "cultivation"

    facility = client.get("/api/facility/systems?include_persisted=0")
    assert facility.status_code == 200
    payload = facility.json()
    assert payload["domain_mode"] == "cultivation"
    assert any(system["name"] == "HVAC" for system in payload["systems"])

    switched_back = client.post("/api/domain/mode", json={"mode": "aquatic"})
    assert switched_back.status_code == 200
    assert switched_back.json()["mode"] == "aquatic"

    facility_aquatic = client.get("/api/facility/systems?include_persisted=0")
    assert facility_aquatic.status_code == 200
    payload_aquatic = facility_aquatic.json()
    assert payload_aquatic["domain_mode"] == "aquatic"
    assert any(system["name"] == "Circulation" for system in payload_aquatic["systems"])
