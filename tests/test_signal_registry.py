from __future__ import annotations

from typing import Any

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.signal_registry import SignalRegistryService
from app.services.telemetry_domain import TelemetryScopeRef


class _Repository:
    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    def upsert_external_signals(self, scope: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.scope = scope
        self.written = kwargs["signals"]
        return self.written

    def list_external_signals(self, scope: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.scope = scope
        return [{"external_tag_id": "tag-1", **kwargs}]

    def get_external_signal(self, scope: Any, **kwargs: Any) -> dict[str, Any]:
        self.scope = scope
        return {"external_tag_id": "tag-1", **kwargs}

    def list_canonical_signal_concepts(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"canonical_name": "pump_power", **kwargs}]


@pytest.fixture
def scope() -> TelemetryScopeRef:
    return TelemetryScopeRef(
        tenant_scope_id="tenant-a",
        workspace_id="facility-a",
        facility_id="facility-a",
        resource_scope_id=canonical_phase4_resource_scope_id(
            "tenant-a", "facility-a"
        ),
    )


def test_discovery_registers_stable_source_identity_without_mapping(scope: TelemetryScopeRef) -> None:
    repository = _Repository()
    service = SignalRegistryService(repository, lambda *_args: None)  # type: ignore[arg-type]
    first = service.register_discovered_signals(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        signals=[
            {
                "external_tag_id": "CentralPlant.Pump01.Power",
                "external_tag_name": "Pump 1 power",
                "source_unit": "kW",
                "metadata": {"source_group": "plant"},
            }
        ],
    )
    second = service.register_discovered_signals(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        signals=[
            {
                "external_tag_id": "CentralPlant.Pump01.Power",
                "external_tag_name": "Pump 1 power",
                "source_unit": "kW",
            }
        ],
    )

    assert first[0]["signal_id"] == second[0]["signal_id"]
    assert "enabled" not in first[0]
    assert "canonical_signal_id" not in first[0]


def test_discovery_rejects_nested_secret_metadata_before_repository(
    scope: TelemetryScopeRef,
) -> None:
    repository = _Repository()
    service = SignalRegistryService(repository, lambda *_args: None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="telemetry_signal_metadata_invalid"):
        service.register_discovered_signals(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            signals=[
                {
                    "external_tag_id": "safe-tag",
                    "metadata": {"nested": {"apiToken": "canary"}},
                }
            ],
        )
    assert repository.written == []


def test_registry_reads_product_taxonomy_without_exposing_a_write_seam(
    scope: TelemetryScopeRef,
) -> None:
    repository = _Repository()
    service = SignalRegistryService(repository, lambda *_args: None)  # type: ignore[arg-type]
    assert service.list_canonical_concepts(limit=5000) == [
        {"canonical_name": "pump_power", "active_only": True, "limit": 5000}
    ]
    assert not hasattr(service, "create_canonical_concept")


def test_registry_reads_exact_signal_without_page_scan(scope: TelemetryScopeRef) -> None:
    repository = _Repository()
    service = SignalRegistryService(repository, lambda *_args: None)  # type: ignore[arg-type]
    assert service.get_signal(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        signal_id="00000000-0000-0000-0000-000000000002",
    ) == {
        "external_tag_id": "tag-1",
        "connection_id": "00000000-0000-0000-0000-000000000001",
        "signal_id": "00000000-0000-0000-0000-000000000002",
    }
