from app.main import create_app
from fastapi.testclient import TestClient


def test_facility_context_is_shared_through_the_scoped_api() -> None:
    client = TestClient(create_app())
    payload = {
        "site_id": "central-plant",
        "site_name": "Resort Central Plant",
        "timezone": "America/Phoenix",
        "systems": [
            {
                "system_id": "chw-loop-1",
                "name": "Chilled Water Loop 1",
                "system_type": "chilled_water_loop",
                "equipment_ids": ["pump-1", "hx-1"],
            }
        ],
        "equipment": [
            {
                "equipment_id": "pump-1",
                "name": "Primary chilled-water pump",
                "system_id": "chw-loop-1",
                "equipment_type": "pump",
            }
        ],
        "signal_mappings": [
            {
                "raw_tag": "BAS.CHW.P1.SPD",
                "normalized_name": "pump_speed",
                "system_id": "chw-loop-1",
                "equipment_id": "pump-1",
                "unit": "%",
                "sample_rate_seconds": 300,
                "alias": "Primary pump speed",
            }
        ],
    }

    updated = client.put(
        "/api/facility/context",
        headers={"X-Neraium-User": "engineer@example.com"},
        json=payload,
    )
    assert updated.status_code == 200
    assert updated.json()["contract_version"] == "facility-context.v1"
    assert updated.json()["updated_by"] == "engineer@example.com"

    stored = client.get(
        "/api/facility/context",
        headers={"X-Neraium-User": "engineer@example.com"},
    )
    assert stored.status_code == 200
    assert stored.json()["site_id"] == "central-plant"
    assert stored.json()["systems"][0]["system_id"] == "chw-loop-1"
    assert stored.json()["equipment"] == payload["equipment"]
    assert stored.json()["signal_mappings"][0]["alias"] == "Primary pump speed"
