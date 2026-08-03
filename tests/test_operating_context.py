from app.services.operating_context import build_operating_context_inputs


def _catalog(demand: str, command: str) -> dict:
    return {
        demand: {"canonical_role": "process_demand", "engineering_units": "kW"},
        command: {"canonical_role": "control_command", "engineering_units": "%"},
    }


def test_context_inputs_use_canonical_roles_not_source_names() -> None:
    baseline_catalog = _catalog("BAS.AHU7.LOAD", "PLC:AO-44")
    current_catalog = _catalog("historian/tag/991", "api.control.value")
    model = {
        "telemetry_schema": {"signal_catalog": baseline_catalog},
        "signal_characteristics": {
            "BAS.AHU7.LOAD": {"samples": 3, "distribution": {"minimum": 20, "maximum": 60, "mean": 40}},
            "PLC:AO-44": {"samples": 3, "distribution": {"minimum": 10, "maximum": 50, "mean": 30}},
        },
        "timestamp_quality": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-01T00:10:00Z"},
    }
    rows = [
        {"historian/tag/991": 22, "api.control.value": 12},
        {"historian/tag/991": 42, "api.control.value": 32},
        {"historian/tag/991": 62, "api.control.value": 52},
    ]

    inputs = build_operating_context_inputs(
        rows=rows,
        telemetry_signal_catalog=current_catalog,
        baseline_model=model,
        comparison_window={"first_timestamp": "2026-02-01T00:00:00Z", "last_timestamp": "2026-02-01T00:10:00Z"},
    )

    assert inputs["baseline"]["process_demand"]["mean"] == 40.0
    assert inputs["comparison"]["process_demand"]["mean"] == 42.0
    assert inputs["comparison"]["process_demand"]["source_variable"] == "historian/tag/991"
    assert inputs["comparison"]["control_command"]["source_variable"] == "api.control.value"


def test_ambiguous_or_unmapped_roles_remain_unavailable() -> None:
    catalog = {
        "tag-a": {"canonical_role": "process_demand"},
        "tag-b": {"canonical_role": "process_demand"},
        "unknown": {"canonical_role": None},
    }
    model = {"telemetry_schema": {"signal_catalog": catalog}, "signal_characteristics": {}}

    inputs = build_operating_context_inputs(
        rows=[{"tag-a": 1, "tag-b": 2, "unknown": 3}], telemetry_signal_catalog=catalog,
        baseline_model=model, comparison_window={},
    )

    assert inputs["baseline"] == {}
    assert inputs["comparison"] == {}
