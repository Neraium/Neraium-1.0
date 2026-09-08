"""Opt-in, non-customer evidence fixture using the existing dataset scope/storage.

Nothing imports or seeds this fixture during application startup. Run as a module
on the API runtime with --seed, then use --verify-url for read-only HTTP proof.
"""
from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from app.engine.sii.expected_behavior import evaluate_expected_behavior
from app.services.analysis_provenance import canonical_digest, result_digest
from app.services.analysis_result_contract import build_analysis_result
from app.services.dataset_scope import attach_dataset_scope, build_dataset_scope, dataset_scope_context
from app.services.finding_workflow import evidence_finding_id
from app.services.upload_replay import build_replay

WORKSPACE_ID = "synthetic-consequence-verification-only"
SCOPE = build_dataset_scope(user_id="service-token", workspace_id=WORKSPACE_ID)
RUN_ID = "synthetic-water-consequence-v1"
FLOW = "synthetic.water.flow-gpm"
LOAD = "synthetic.test.load"
RELATIONSHIP_ID = "synthetic.water.flow-to-test-load"
FINDING_ID = "synthetic-water-finding-v1"
START = datetime(2026, 9, 1, tzinfo=UTC)
MARKERS = {
    "synthetic": True,
    "verification_only": True,
    "non_customer": True,
    "non_production_control": True,
    "non_actuating": True,
}


def build_fixture() -> dict[str, Any]:
    """Evaluate explicit synthetic reference evidence once, before persistence."""
    rows = [
        {"timestamp": (START + timedelta(hours=i)).isoformat(), FLOW: 110 + 2 * i, LOAD: i}
        for i in range(7)
    ]
    model_id = "synthetic-reference-model-v1"
    model = {
        "model_id": model_id,
        "target_signal": FLOW,
        "predictor_signals": [LOAD],
        "operating_mode": "synthetic-test",
        "validation": {"passed": True},
        "sample_support": 80,
        "model_parameters": {"intercept": 100, "slope": 2, "lag_samples": 0},
        "source_relationships": [RELATIONSHIP_ID],
        "limitations": [
            "Synthetic verification-only reference: expected flow = 100 + 2 * test load gpm. "
            "Model validation and high support are fixture assumptions, not customer observations. "
            "Non-customer, non-production-control, non-actuating."
        ],
    }
    expected = evaluate_expected_behavior(
        active_model={"expected_behavior_models": {model_id: model}},
        rows=rows,
        operating_mode="synthetic-test",
        data_quality={"readiness": "ready"},
        sensor_health={"signals": [{"signal": signal, "health": "healthy"} for signal in (FLOW, LOAD)]},
        source_model_version="synthetic-reference-v1",
        evaluation_time=START.isoformat(),
        timestamp_column="timestamp",
        config={"max_gap_seconds": 3600},
    )
    catalog = {
        FLOW: {
            "canonical_unit": "gpm",
            "rate_unit": "gpm",
            "resource_type": "water",
            "consequence_profile_key": "water_gpm",
            "max_gap_seconds": 3600,
            "max_gap_justification": "The fixture defines seven exact hourly samples; accept one hour, never bridge a missing sample.",
            "consequence_connection_id": "synthetic-no-connector",
            "verification": deepcopy(MARKERS),
        },
        LOAD: {"canonical_unit": "fraction", "verification": deepcopy(MARKERS)},
    }
    finding = {
        "id": FINDING_ID,
        "headline": "SYNTHETIC VERIFICATION ONLY: water response difference",
        "support_level": "high",
        "operating_mode": {"match": "strong"},
        "persistence": {"status": "persistent"},
        "source_relationship_ids": [RELATIONSHIP_ID],
        "source_tags": [FLOW, LOAD],
        "evidence_id": "synthetic-water-evidence-v1",
        "source_time_ranges": [{"current_start": rows[0]["timestamp"], "current_end": rows[-1]["timestamp"]}],
    }
    source = attach_dataset_scope({
        "job_id": RUN_ID, "run_id": RUN_ID, "upload_id": RUN_ID, "analysis_id": RUN_ID,
        "system_id": "synthetic-test-only-water-system",
        "source_type": "verification_fixture",
        "filename": "SYNTHETIC-VERIFICATION-ONLY-water.json",
        "verification": deepcopy(MARKERS),
        "completed_at": rows[-1]["timestamp"],
        "row_count": len(rows), "column_count": 3, "columns": ["timestamp", FLOW, LOAD],
        "normalized_telemetry": {"rows": rows, "tags": [{"tag_name": signal} for signal in (FLOW, LOAD)]},
        "input_hash": canonical_digest(rows),
        "conditions": [finding],
        "analysis_explanation": {"insights": []},
        "sii_result": {"expected_behavior": expected},
        "telemetry_signal_catalog": catalog,
    }, scope=SCOPE, dataset_id=RUN_ID)
    source["analysis_result"] = build_analysis_result(source)
    consequence = source["analysis_result"]["conditions"][0]["measurable_consequence"]
    assert consequence["status"] == "quantified"
    assert consequence["cumulative_amount"] == 3600
    assert consequence["duration_seconds"] == 21600
    replay = build_replay(rows, "timestamp", [FLOW, LOAD], RUN_ID)
    # Link the recorded finding-window consequence, never integrate per frame.
    replay["meta"].update(
        verification=deepcopy(MARKERS),
        measurable_consequence=deepcopy(consequence),
        consequence_scope="entire_recorded_finding_window",
    )
    source["replay_timeline"] = replay
    return source


def fixture_paths() -> dict[str, str]:
    return {
        "replay": f"/api/data/replay/{RUN_ID}",
        "replay_alias": f"/api/replay/{RUN_ID}",
        "result": f"/api/data/intake/{RUN_ID}/result",
        "evidence": f"/api/evidence/runs/{RUN_ID}",
        "finding": f"/api/findings/{evidence_finding_id(RUN_ID, FINDING_ID)}",
    }


def seed_fixture() -> dict[str, Any]:
    """Seed only the fixed service verification scope; never select a customer scope.

    Existing artifacts are read verbatim on repeated calls. New fixture versions
    require a new run ID, so this command cannot rewrite recorded hashes.
    """
    from app.services import runtime_db, upload_state_repository as repository
    from app.services.finding_workflow import materialize_evidence_finding_cases
    from app.services.upload_evidence import build_evidence_record_from_result

    with dataset_scope_context(SCOPE):
        stored = repository.read_upload_result_by_job_id(RUN_ID)
        record = runtime_db.read_evidence_run_db(RUN_ID)
        if stored is not None:
            if stored.get("verification") != MARKERS or stored.get("run_id") != RUN_ID:
                raise ValueError("Reserved fixture identity is already occupied; refusing to overwrite.")
            if record is None:
                raise ValueError("Fixture is incomplete; inspect persisted state before retrying.")
        else:
            if record is not None:
                raise ValueError("Reserved evidence identity is already occupied; refusing to overwrite.")
            stored = build_fixture()
            repository.write_upload_result(RUN_ID, stored)
            record = build_evidence_record_from_result(
                run_id=RUN_ID, filename=stored["filename"], source_type="verification_fixture",
                result=stored, created_at=START.isoformat(), completed_at=stored["completed_at"],
                status="completed", initiated_by="synthetic-verification-only",
            )
            # Use the existing scoped stores without replacing the legacy global
            # evidence JSON mirror or publishing a latest-upload pointer.
            runtime_db.upsert_evidence_run_db(record)
            materialize_evidence_finding_cases(record)
        return {
            "verification": MARKERS, "workspace_id": WORKSPACE_ID, "run_id": RUN_ID,
            "paths": fixture_paths(), "result_hash": result_digest(stored),
            "artifact_hash": canonical_digest(stored),
        }


def verify_responses(get) -> dict[str, Any]:
    """Verify actual HTTP responses without invoking any analytical function."""
    payloads = {}
    statuses = {}
    for name, path in fixture_paths().items():
        response = get(path)
        statuses[name] = response.status_code
        if response.status_code != 200:
            raise ValueError(f"{path}: expected HTTP 200, got {response.status_code}")
        payloads[name] = response.json()
        _verify_product_boundary(payloads[name])
    source = payloads["result"]["result"]
    canonical = source["analysis_result"]["conditions"][0]["measurable_consequence"]
    assert source["verification"] == MARKERS
    assert canonical["status"] == "quantified"
    assert canonical["cumulative_amount"] == 3600
    assert canonical["duration_seconds"] == 21600
    assert canonical["cumulative_unit"] == "gal"
    assert canonical["direction"] == "above_expected"
    assert canonical["support_level"] == "high"
    assert canonical["start_timestamp"] == START.timestamp()
    assert canonical["end_timestamp"] == (START + timedelta(hours=6)).timestamp()
    assert canonical["finding_id"] == FINDING_ID
    assert canonical["evidence_id"] == "synthetic-water-evidence-v1"
    assert canonical["analysis_run_id"] == RUN_ID
    assert canonical["source_relationship_ids"] == [RELATIONSHIP_ID]
    assert canonical["source_tag_ids"] == [FLOW, LOAD]
    assert canonical["methodology"] == "timestamp_aware_trapezoidal_integration"
    assert canonical["methodology_version"] == "1.0.0"
    assert canonical["provenance"]["effective_max_gap_seconds"] == 3600
    assert canonical["provenance"]["signal_metadata"]["verification"] == MARKERS
    assert canonical["provenance"]["acquisition_gap_policy"] == {
        "source": "signal_catalog", "max_gap_seconds": 3600,
        "connection_id": "synthetic-no-connector", "method": "explicit_maximum_interval_gap_v1",
    }
    for name in ("replay", "replay_alias"):
        assert payloads[name]["frame_count"] == 7
        assert payloads[name]["meta"]["verification"] == MARKERS
        assert payloads[name]["meta"]["measurable_consequence"] == canonical
    assert payloads["finding"]["measurable_consequence"] == canonical
    assert payloads["evidence"]["condition"]["measurable_consequence"] == canonical
    assert payloads["evidence"]["result_hash"] == result_digest(source)
    return {"verification": MARKERS, "http_statuses": statuses, "consequence": canonical}


def _verify_product_boundary(value: Any) -> None:
    forbidden = {
        "cause", "causes", "likelycause", "likelycauses", "rootcause",
        "driver", "drivers", "primarydriver", "primarydrivers", "driverattribution",
        "attribution", "attributionconfidence", "diagnosis", "leak", "waste",
        "savings", "cost", "remediation",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert key.replace("_", "").lower() not in forbidden, key
            _verify_product_boundary(item)
    elif isinstance(value, list):
        for item in value:
            _verify_product_boundary(item)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--seed", action="store_true", help="Persist in the fixed service verification scope on this API runtime.")
    modes.add_argument("--verify-url", help="Read existing fixture through HTTPS; requires NERAIUM_API_TOKEN.")
    args = parser.parse_args()
    if args.seed:
        output = seed_fixture()
    elif args.verify_url:
        from urllib.parse import urlparse
        import httpx

        url = urlparse(args.verify_url)
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            parser.error("--verify-url requires an HTTPS origin without credentials, query, or fragment")
        token = os.environ.get("NERAIUM_API_TOKEN", "").strip()
        if not token:
            parser.error("NERAIUM_API_TOKEN is required")
        with httpx.Client(base_url=args.verify_url, headers={
            "Authorization": f"Bearer {token}", "X-Neraium-Workspace-Id": WORKSPACE_ID,
        }, timeout=30, follow_redirects=False) as client:
            output = verify_responses(client.get)
    else:
        output = build_fixture()
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
