from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.dataset_scope import build_dataset_scope
from app.services.health_relevance_benchmark import (
    load_benchmark_fixture,
    normalized_report_json,
    run_benchmark,
)
from app.services.health_relevance_methods import (
    BAYESIAN_METHOD_ID,
    INFORMATION_METHOD_ID,
)


_CLI_PATH = Path(__file__).resolve().parents[1] / "scripts" / "inspect_health_relevance.py"
_CLI_SPEC = importlib.util.spec_from_file_location("inspect_health_relevance", _CLI_PATH)
assert _CLI_SPEC is not None and _CLI_SPEC.loader is not None
inspection_cli = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(inspection_cli)


METHOD_IDS = {BAYESIAN_METHOD_ID, INFORMATION_METHOD_ID}
CLI_ARGS = [
    "--workspace-id",
    "ws-synthetic",
    "--facility-id",
    "facility-a",
    "--system-id",
    "system-a",
    "--subject-type",
    "relationship",
    "--subject-id",
    "relationship-r",
    "--subject-mapping-version",
    "mapping-v1",
    "--context-fingerprint",
    "context-high-load",
    "--compatibility-epoch",
    "epoch-v1",
    "--method",
    BAYESIAN_METHOD_ID,
]


@pytest.fixture(scope="module")
def report() -> dict[str, object]:
    return run_benchmark()


def _variant(report: dict[str, object], case_id: str, variant_id: str) -> dict[str, object]:
    case = report["cases"][case_id]
    return next(item for item in case["variants"] if item["id"] == variant_id)


def test_fixture_contains_exactly_cases_a_through_p_and_two_method_configs() -> None:
    fixture = load_benchmark_fixture()

    assert [case["id"] for case in fixture["cases"]] == list("ABCDEFGHIJKLMNOP")
    assert set(fixture["method_config"]) == METHOD_IDS


def test_benchmark_is_byte_deterministic_and_all_fixture_assertions_pass(report) -> None:
    repeated = run_benchmark()

    assert report["passed"] is True
    assert normalized_report_json(report) == normalized_report_json(repeated)
    assert all(item["passed"] for item in report["assertions"])
    assert report["synthetic_only"] is True
    assert report["internal_only"] is True
    assert report["production_effect"] == "none"


@pytest.mark.parametrize(
    ("case_id", "variant_id", "expected_state"),
    [
        ("A", "five_degradations", "emerging_relevance"),
        ("B", "isolated", "insufficient_outcome_evidence"),
        ("C", "repeated_false_positive", "not_supported_by_outcomes"),
        ("D", "high_load_only", "emerging_relevance"),
        ("E", "q_0_40", "contradictory_evidence"),
        ("E", "q_0_50", "contradictory_evidence"),
        ("E", "q_0_60", "contradictory_evidence"),
        ("F", "recovery", "insufficient_outcome_evidence"),
        ("G", "balanced_frequency", "contradictory_evidence"),
        ("H", "incomplete_context", "insufficient_outcome_evidence"),
    ],
)
def test_acceptance_cases_a_through_h(
    report, case_id: str, variant_id: str, expected_state: str
) -> None:
    variant = _variant(report, case_id, variant_id)

    assert variant["passed"] is True
    assert {
        output["state"]["evidence_state"] for output in variant["methods"].values()
    } == {expected_state}


def test_both_methods_consume_the_same_frozen_manifest_with_inspectable_components(report) -> None:
    for case in report["cases"].values():
        for variant in case["variants"]:
            manifest = variant["manifest"]
            methods = variant["methods"]
            assert set(methods) == METHOD_IDS
            assert {
                result["shared_input_manifest_hash"] for result in methods.values()
            } == {manifest["input_manifest_hash"]}
            assert {
                result["shared_input_snapshot_id"] for result in methods.values()
            } == {manifest["input_snapshot_id"]}
            for method in methods.values():
                assert method["result"]["components"]
                assert method["result"]["uncertainty"]
                assert len(method["result"]["contributions"]) == len(
                    manifest["contributions"]
                )
                assert all(
                    "provenance_categories" in contribution
                    for contribution in method["result"]["contributions"]
                )


def test_authority_stable_denominator_and_dedup_contracts(report) -> None:
    independent = _variant(report, "I", "independent")
    influenced = _variant(report, "I", "neraium_influenced")
    assert all(
        output["state"]["evidence_state"] == "supported_relevance"
        for output in independent["methods"].values()
    )
    assert independent["summary"]["independent_count"] == 19
    assert influenced["summary"]["tier_d_count"] == 19
    assert all(
        output["state"]["evidence_state"] == "emerging_relevance"
        for output in influenced["methods"].values()
    )

    silence = _variant(report, "J", "silence_only")
    explicit = _variant(report, "J", "two_protocol_windows")
    assert silence["summary"]["comparison_window_count"] == 0
    assert explicit["summary"]["comparison_window_count"] == 2
    assert explicit["summary"]["protocol_completion"] == 1.0

    dedup = _variant(report, "K", "canonical_and_quarantined")
    assert dedup["idempotency_replay_results"] == ["created", "replay"]
    assert dedup["summary"]["canonical_incident_count"] == 1
    assert dedup["summary"]["positive_family_count"] == 3
    assert dedup["summary"]["duplicate_suppressed_count"] == 2
    assert dedup["summary"]["excluded_count"] == 1
    assert dedup["methods"][BAYESIAN_METHOD_ID]["result"]["components"]["primary_view"][
        "counts"
    ]["directional"] == 1
    assert dedup["methods"][INFORMATION_METHOD_ID]["result"]["components"]["primary_view"][
        "contingency_table"
    ] == {"a": 1, "b": 0, "c": 0, "d": 0}


def test_identity_correction_staleness_idempotency_and_isolation_contracts(report) -> None:
    compatible = _variant(report, "L", "compatible_epoch")
    changed = _variant(report, "L", "material_change")
    assert compatible["compatibility_epoch"] != changed["compatibility_epoch"]
    assert compatible["input_manifest_hash"] != changed["input_manifest_hash"]
    assert all(
        output["state"]["evidence_state"] == "insufficient_outcome_evidence"
        for output in changed["methods"].values()
    )

    history = report["cases"]["M"]["variants"]
    assert len({item["input_manifest_hash"] for item in history}) == 3
    assert history[-1]["summary"]["eligible_outcome_count"] == 0
    assert history[-1]["summary"]["negative_count"] == 0
    assert history[-1]["summary"]["excluded_count"] == 1

    assert _variant(report, "N", "exactly_180_days")["freshness_status"] == "current"
    assert _variant(report, "N", "after_180_days")["freshness_status"] == "stale"
    assert _variant(report, "O", "created_replay_conflict")[
        "idempotency_replay_results"
    ] == ["created", "replay", "conflict"]

    tenant_a = _variant(report, "P", "tenant_a")
    tenant_b = _variant(report, "P", "tenant_b")
    assert tenant_a["scope"] != tenant_b["scope"]
    assert tenant_a["input_manifest_hash"] != tenant_b["input_manifest_hash"]
    assert tenant_a["summary"]["positive_count"] == 1
    assert tenant_b["summary"]["positive_count"] == 0


def test_comparison_reports_no_forced_winner_and_all_dimensions(report) -> None:
    expected_dimensions = {
        "sparse_data_behavior",
        "stability",
        "contradictory_evidence",
        "negative_evidence",
        "context_specificity",
        "authority_weighting",
        "false_positive_resistance",
        "version_stability",
        "interpretability",
    }
    assert report["comparison"]["winner"] == "neither_clearly_dominates"
    assert report["comparison"]["production_selection_made"] is False
    for dimensions in report["evaluation_dimensions"].values():
        assert set(dimensions) == expected_dimensions
        assert all(result["passed"] for result in dimensions.values())


def test_non_causal_language_lint_passes_every_case(report) -> None:
    assert all(case["language_lint"]["passed"] for case in report["cases"].values())
    recovery = report["cases"]["F"]["language_lint"]
    assert recovery["violations"] == []


def test_cli_requires_every_exact_scope_and_state_key_argument() -> None:
    parser = inspection_cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(CLI_ARGS[:-2])
    args = parser.parse_args(CLI_ARGS)
    assert args.workspace_id == "ws-synthetic"
    assert args.system_id == "system-a"
    assert args.context_fingerprint == "context-high-load"
    assert args.method == BAYESIAN_METHOD_ID


def test_cli_resolves_service_token_admin_and_calls_only_exact_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = build_dataset_scope(
        tenant_id="tenant-a", user_id="workspace:synthetic", workspace_id="default"
    )
    workspace = SimpleNamespace(dataset_scope=scope)
    access = object()
    calls: dict[str, object] = {}
    monkeypatch.setenv("NERAIUM_API_TOKEN", "configured-secret")
    monkeypatch.setenv("NERAIUM_API_TOKEN_ROLE", "admin")
    def resolve_workspace(**kwargs):
        calls["workspace"] = kwargs
        return workspace

    def authorize(**kwargs):
        calls["authorize"] = kwargs
        return access

    def inspect(resolved_access, **kwargs):
        calls["inspect"] = {"access": resolved_access, **kwargs}
        return {"internal_only": True, "state": {"evidence_state": "emerging_relevance"}}

    monkeypatch.setattr(inspection_cli, "resolve_workspace_context", resolve_workspace)
    monkeypatch.setattr(inspection_cli, "authorize_internal_access", authorize)
    monkeypatch.setattr(inspection_cli, "inspect_health_relevance", inspect)

    result = inspection_cli.inspect_from_args(inspection_cli.build_parser().parse_args(CLI_ARGS))

    assert result["internal_only"] is True
    assert calls["workspace"] == {
        "subject": "service-token",
        "requested_workspace_id": "ws-synthetic",
        "auth_source": "service_token",
    }
    assert calls["authorize"]["role"] == "admin"
    assert calls["authorize"]["workspace_authorized"] is True
    assert calls["inspect"]["access"] is access
    assert calls["inspect"]["subject_id"] == "relationship-r"
    assert calls["inspect"]["context_fingerprint"] == "context-high-load"
    assert calls["inspect"]["method_class"] == BAYESIAN_METHOD_ID


def test_cli_has_no_write_list_all_network_or_http_surface() -> None:
    source_path = Path(inspection_cli.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        str(node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    option_strings = {
        argument.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        for argument in node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    }

    assert not ({"requests", "urllib", "httpx", "socket"} & imported_roots)
    assert not any("write" in option or "list" in option for option in option_strings)
    assert "inspect_health_relevance" in source_path.read_text(encoding="utf-8")


def test_cli_uses_opaque_json_error_when_service_identity_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NERAIUM_API_TOKEN", raising=False)

    assert inspection_cli.main(CLI_ARGS) == 2
    assert json.loads(capsys.readouterr().err) == {
        "error": "Health Relevance state not found."
    }
