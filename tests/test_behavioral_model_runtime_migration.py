from __future__ import annotations

from copy import deepcopy

from app.engine.sii.behavioral_model_contract import (
    AuthenticatedPhase4Scope,
    scoped_behavioral_model_id,
)
from app.engine.sii.behavioral_model_store import RuntimeBehavioralModelStore


def _scope() -> AuthenticatedPhase4Scope:
    return AuthenticatedPhase4Scope(
        tenant_scope_id="org-1",
        workspace_id="ws-1",
    )


def _legacy_ledger(scope_provenance: dict | None) -> dict:
    ledger = {
        "models": {
            "v1": {
                "model_id": "legacy-system-1",
                "model_version": "v1",
                "signal_memory": {},
                "relationship_memory": {},
            }
        },
        "active_model_version": "v1",
        "snapshots": {},
        "snapshot_order": [],
        "events": {},
        "event_order": [],
        "learning_decisions": {},
        "decision_order": [],
        "candidate_baselines": {},
        "activated_baselines": {},
        "active_baseline_version": None,
        "write_audit": [],
    }
    if scope_provenance is not None:
        ledger["scope_provenance"] = scope_provenance
    return ledger


def test_explicit_safe_v1_migration_preserves_source_and_uses_v2_scope_namespace() -> None:
    scope = _scope()
    scoped_model_id = scoped_behavioral_model_id(scope, "system-1")
    legacy = _legacy_ledger(None)
    verified_scope_mapping = {
        **scope.as_dict(),
        "server_authenticated": True,
        "proof_reference": "server-upload-routing-audit:run-1",
    }
    payloads = {"sii_behavioral_model_ledger_v1::legacy-system-1": deepcopy(legacy)}

    store = RuntimeBehavioralModelStore(
        reader=lambda key: deepcopy(payloads.get(key)),
        writer=lambda key, value: payloads.__setitem__(key, deepcopy(value)),
    )
    result = store.migrate_legacy_ledger(
        scope,
        legacy_model_id="legacy-system-1",
        scoped_model_id=scoped_model_id,
        verified_scope_mapping=verified_scope_mapping,
    )

    expected_key = (
        f"sii_behavioral_model_ledger_v2::{scope.scope_digest}::{scoped_model_id}"
    )
    assert result["classification"] == "safely_mappable"
    assert result["disposition"] == "migrated"
    assert result["migrated_key"] == expected_key
    assert payloads["sii_behavioral_model_ledger_v1::legacy-system-1"] == legacy
    assert payloads[expected_key]["authenticated_scope"] == scope.as_dict()
    assert payloads[expected_key]["migration_provenance"]["original_model_id"] == "legacy-system-1"
    assert payloads[expected_key]["migration_provenance"]["verified_scope_mapping"] == verified_scope_mapping
    assert payloads[expected_key]["models"]["v1"]["legacy_original_model_id"] == "legacy-system-1"
    assert store.load_model(scope, scoped_model_id)["model_version"] == "v1"


def test_ambiguous_v1_ledger_is_quarantined_and_never_written_as_v2() -> None:
    scope = _scope()
    scoped_model_id = scoped_behavioral_model_id(scope, "system-1")
    legacy = _legacy_ledger(
        {
            "tenant_scope_id": scope.tenant_scope_id,
            "workspace_id": scope.workspace_id,
            # Deliberately missing resource scope: it cannot be guessed.
            "server_authenticated": True,
        }
    )
    payloads = {"sii_behavioral_model_ledger_v1::legacy-system-1": deepcopy(legacy)}
    store = RuntimeBehavioralModelStore(
        reader=lambda key: deepcopy(payloads.get(key)),
        writer=lambda key, value: payloads.__setitem__(key, deepcopy(value)),
    )

    result = store.migrate_legacy_ledger(
        scope,
        legacy_model_id="legacy-system-1",
        scoped_model_id=scoped_model_id,
    )

    assert result["classification"] == "ambiguous"
    assert result["disposition"] == "quarantined"
    assert result["migrated_key"] is None
    assert set(payloads) == {"sii_behavioral_model_ledger_v1::legacy-system-1"}
    assert store.load_model(scope, scoped_model_id) is None


def test_self_declared_legacy_scope_is_not_accepted_as_migration_proof() -> None:
    scope = _scope()
    scoped_model_id = scoped_behavioral_model_id(scope, "system-1")
    legacy = _legacy_ledger(
        {
            **scope.as_dict(),
            "server_authenticated": True,
            "proof_reference": "untrusted-ledger-claim",
        }
    )
    payloads = {"sii_behavioral_model_ledger_v1::legacy-system-1": deepcopy(legacy)}
    store = RuntimeBehavioralModelStore(
        reader=lambda key: deepcopy(payloads.get(key)),
        writer=lambda key, value: payloads.__setitem__(key, deepcopy(value)),
    )

    result = store.migrate_legacy_ledger(
        scope,
        legacy_model_id="legacy-system-1",
        scoped_model_id=scoped_model_id,
    )

    assert result["classification"] == "ambiguous"
    assert result["disposition"] == "quarantined"
    assert result["reasons"] == ["verified_scope_mapping_missing"]
    assert set(payloads) == {"sii_behavioral_model_ledger_v1::legacy-system-1"}
