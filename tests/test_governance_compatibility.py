"""Baseline regression for the complete SII result, including compatibility."""
import hashlib
import json

from app.engine.sii_engine import evaluate_sii
from app.governance.authority_store import RuntimeAuthorityDecisionStore
from test_sii_engine_v2 import _profiles, _stable_rows


def stable_result(value):
    # These fields are measured execution diagnostics, duplicated in fusion.
    # Analytical results, findings, state, severity and compatibility stay intact.
    diagnostics = {"runtime_seconds", "total_runtime_seconds", "step_timings", "performance"}
    if isinstance(value, dict):
        return {key: ("upload-fixture" if key == "run_id" and isinstance(item, str) and item.startswith("upload-")
                      else stable_result(item)) for key, item in value.items() if key not in diagnostics}
    if isinstance(value, list):
        return [stable_result(item) for item in value]
    return value


def test_unused_governance_preserves_base_sii_result_and_compatibility(monkeypatch):
    import app.governance.maturity as maturity_module

    def unexpected(*args, **kwargs):
        raise AssertionError("Live SII must not call governance")
    monkeypatch.setattr(maturity_module, "evaluate_maturity", unexpected)
    monkeypatch.setattr(RuntimeAuthorityDecisionStore, "append_decision", unexpected)
    columns, rows = _stable_rows()
    result = evaluate_sii(columns=columns, rows=rows, numeric_profiles=_profiles(columns),
                          timestamp_column="timestamp", config={"numeric_columns": columns[1:]})
    digest = hashlib.sha256(json.dumps(stable_result(result), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    # Captured from the base branch at 31fc1556 with the repository dependencies.
    assert digest == "334b6bd43f0ea23f1e8100b075c29cc8c19f5b1852b71bb59591410e36020dc4"
