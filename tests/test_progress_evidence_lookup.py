from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from unittest.mock import patch

import pytest

from app.services import evidence_store, runtime_db, upload_jobs, upload_state, upload_state_repository as repo
from app.services.dataset_scope import DatasetScope, attach_dataset_scope, dataset_scope_context
from app.services.finding_workflow import materialize_evidence_finding_cases, record_finding_feedback


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 15, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def use_persisted_latest(monkeypatch):
    monkeypatch.setattr(repo, "_runtime_db_latest_enabled", lambda: True)
    monkeypatch.setattr(upload_state, "datetime", FixedDatetime)


def evidence(run_id, **extra):
    return attach_dataset_scope({
        "run_id": run_id,
        "job_id": run_id,
        "status": "queued",
        "created_at": "2026-09-14T00:00:00+00:00",
        "source_name": "hydraulic-response-v1-evidence.csv",
        "provenance": {"dataset_digest": "hydraulic-digest", "source_tag_ids": ["pressure", "flow"]},
        "analysis_result": {"provenance": {"baseline_id": "hydraulic-baseline"}},
        **extra,
    })


def processing(job_id, stage="reading_csv"):
    return attach_dataset_scope({
        "job_id": job_id,
        "attempt_id": job_id,
        "filename": "hydraulic-response-v1-evidence.csv",
        "workflow": "analyze_new_data",
        "status": "PROCESSING",
        "processing_state": stage,
        "message": "Detecting engineering units",
        "traceability": {"dataset_digest": "hydraulic-digest"},
    })


@pytest.mark.parametrize("stage", ["reading_csv", "scoring_drift_relationships", "saving_result"])
def test_progress_entire_latest_contract_matches_full_hydration_without_history_work(stage):
    evidence_store.upsert_evidence_run(evidence("historical", status="complete"))
    evidence_store.upsert_evidence_run(evidence("current"))
    upload_jobs.write_job(processing("current", stage))
    payload = upload_jobs.read_job("current")
    with patch.object(evidence_store, "read_progress_evidence_run", evidence_store.read_evidence_run):
        upload_jobs.write_job(deepcopy(payload))
    expected = repo.read_latest_upload_record()
    with (
        patch.object(evidence_store, "_load_raw_evidence_runs", wraps=evidence_store._load_raw_evidence_runs) as history,
        patch.object(evidence_store, "hydrate_evidence_event_history_db", wraps=evidence_store.hydrate_evidence_event_history_db) as hydrate,
        patch("app.services.finding_workflow.materialize_evidence_finding_cases") as materialize,
    ):
        upload_jobs.write_job(deepcopy(payload))
    actual = repo.read_latest_upload_record()
    assert actual == expected
    assert actual["evidence"]["provenance"]["source_tag_ids"] == ["pressure", "flow"]
    assert actual["evidence"]["analysis_result"]["provenance"]["baseline_id"] == "hydraulic-baseline"
    assert actual["traceability"]["dataset_digest"] == "hydraulic-digest"
    history.assert_not_called()
    hydrate.assert_not_called()
    materialize.assert_not_called()


def test_progress_lookup_isolates_scope_and_does_not_attach_foreign_evidence():
    scope_a = DatasetScope("tenant", "workspace-a", "user")
    scope_b = DatasetScope("tenant", "workspace-b", "user")
    with dataset_scope_context(scope_a):
        evidence_store.upsert_evidence_run(evidence("foreign"))
        expected = evidence_store.read_progress_evidence_run("foreign")
    with dataset_scope_context(scope_b):
        assert evidence_store.read_progress_evidence_run("foreign") is None
        upload_jobs.write_job(processing("foreign"))
        record = repo.read_latest_upload_record()
        assert record["evidence"] is None
        assert record["dataset_scope"] == scope_b.as_dict()
    with dataset_scope_context(scope_a):
        assert evidence_store.read_progress_evidence_run("foreign") == expected


def test_incorrect_attempt_cannot_replace_current_progress_or_provenance():
    evidence_store.upsert_evidence_run(evidence("current"))
    upload_jobs.write_job(processing("current"))
    expected = repo.read_latest_upload_record()
    upload_jobs.write_job({
        **processing("current"), "attempt_id": "incorrect-attempt",
        "message": "stale callback", "traceability": {"dataset_digest": "wrong"},
    })
    assert repo.read_latest_upload_record() == expected
    assert upload_jobs.read_job("current")["attempt_id"] == "current"


def test_retry_rejects_old_attempt_and_late_progress_cannot_reopen_terminal():
    evidence_store.upsert_evidence_run(evidence("current"))
    upload_jobs.write_job(processing("current"))
    upload_jobs.write_job({**processing("current"), "status": "FAILED", "processing_state": "failed"})
    failed = repo.read_latest_upload_record()
    published = upload_jobs.read_job("current")
    upload_jobs.write_job(processing("current"))
    assert upload_jobs.read_job("current") == published
    assert repo.read_latest_upload_record()["status"] == "failed"
    assert repo.read_latest_upload_record()["evidence"] == failed["evidence"]
    upload_jobs.write_job({
        **processing("current"), "status": "PENDING", "processing_state": "queued",
        "retry_requested_at": "2026-09-15T01:00:00+00:00",
    })
    retried = repo.read_latest_upload_record()
    assert retried["summary"]["attempt_id"] != "current"
    upload_jobs.write_job(processing("current"))
    assert repo.read_latest_upload_record() == retried


@pytest.mark.parametrize("context", ["complete", "historical", "review", "finding_case"])
def test_context_requiring_full_hydration_preserves_evidence(context):
    record = evidence("current")
    if context in {"complete", "finding_case"}:
        record["status"] = "complete"
    if context == "historical":
        record.update(observation_type="relationship_change", variables=["pressure", "flow"])
        prior = evidence_store.upsert_evidence_run(evidence(
            "prior", status="complete", created_at="2026-09-13T00:00:00+00:00",
            observation_type="relationship_change", variables=["pressure", "flow"],
        ))
        record_finding_feedback(
            materialize_evidence_finding_cases(prior)[0],
            feedback={
                "category": "confirmed_issue", "actor": "operator",
                "recorded_at": "2026-09-13T01:00:00+00:00",
            }, expected_version=None, actor="operator", recorded_at="2026-09-13T01:00:00+00:00",
        )
    evidence_store.upsert_evidence_run(record)
    if context == "finding_case":
        # Existing canonical finding identity must still take the compatibility path.
        runtime_db.upsert_evidence_run_db(evidence("current"))
    if context == "review":
        runtime_db.append_operator_feedback_event_db("current", {
            "event_id": "review", "recorded_at": "2026-09-15T00:00:00+00:00",
            "actor": "operator", "category": "confirmed_issue", "note": "reviewed",
        })
    expected = evidence_store.read_evidence_run("current")
    if context == "historical":
        assert expected["historical_fact"]
        assert expected["before_after_intervention"]["available"] is True
    with patch.object(evidence_store, "read_evidence_run", wraps=evidence_store.read_evidence_run) as full:
        assert evidence_store.read_progress_evidence_run("current") == expected
    full.assert_called_once_with("current")


def test_completion_and_final_evidence_publication_keep_full_reader():
    evidence_store.upsert_evidence_run(evidence("current"))
    upload_jobs.write_job(processing("current"))
    evidence_store.upsert_evidence_run(evidence("current", status="complete"))
    expected = evidence_store.read_evidence_run("current")
    summary = {**processing("current"), "status": "COMPLETE", "processing_state": "complete",
               "result_available": True, "sii_completed": True}
    result = {**summary, "analysis_result": {"insights": []}, "provenance": {"dataset_digest": "hydraulic-digest"}}
    with (
        patch.object(evidence_store, "read_progress_evidence_run", wraps=evidence_store.read_progress_evidence_run) as narrow,
        patch.object(evidence_store, "read_evidence_run", wraps=evidence_store.read_evidence_run) as full,
    ):
        published = repo.write_upload_completion("current", result=result, summary=summary)
        upload_jobs.write_job(summary)
    assert published["status"] == "COMPLETE"
    assert repo.read_latest_upload_record()["evidence"] == expected
    assert repo.read_upload_result_by_job_id("current")["provenance"] == result["provenance"]
    narrow.assert_not_called()
    assert full.call_count >= 1


def test_progress_keeps_legacy_import_fallback(monkeypatch, tmp_path):
    marker = evidence_store.LEGACY_EVIDENCE_IMPORT_MARKER
    legacy = evidence("legacy")
    legacy_path = tmp_path / "legacy-evidence.json"
    legacy_path.write_text(json.dumps([legacy]), encoding="utf-8")
    monkeypatch.setattr(evidence_store, "evidence_runs_path", lambda: legacy_path)
    assert runtime_db.read_evidence_run_db("legacy") is None
    with patch.object(evidence_store, "read_evidence_run", wraps=evidence_store.read_evidence_run) as full:
        actual = evidence_store.read_progress_evidence_run("legacy")
    full.assert_called_once_with("legacy")
    assert runtime_db.read_latest_payload(marker) is True
    assert actual == evidence_store.read_evidence_run("legacy")
    assert actual["provenance"] == legacy["provenance"]


def assert_progress_lookup_preserves_current_evidence(monkeypatch):
    """Shared contract exercised with SQLite rows and real PostgreSQL mappings."""
    monkeypatch.setattr(repo, "_runtime_db_latest_enabled", lambda: True)
    scope = DatasetScope("row-shape", "current-workspace", "user")
    other_scope = DatasetScope("row-shape", "other-workspace", "user")
    with dataset_scope_context(scope):
        evidence_store.upsert_evidence_run(evidence("row-current"))
        expected = evidence_store.read_evidence_run("row-current")
        with (
            patch.object(evidence_store, "_load_raw_evidence_runs", wraps=evidence_store._load_raw_evidence_runs) as history,
            patch.object(evidence_store, "hydrate_evidence_event_history_db", wraps=evidence_store.hydrate_evidence_event_history_db) as hydrate,
        ):
            upload_jobs.write_job(processing("row-current"))
            latest = repo.read_latest_upload_record()
            assert latest["evidence"] is not None
            assert latest["evidence"] == expected
            assert latest["evidence"]["provenance"]["dataset_digest"] == "hydraulic-digest"
            assert latest["evidence"]["analysis_result"]["provenance"]["baseline_id"] == "hydraulic-baseline"
            assert evidence_store.read_progress_evidence_run("row-current") == expected
            with dataset_scope_context(other_scope):
                assert evidence_store.read_progress_evidence_run("row-current") is None
            history.assert_not_called()
            hydrate.assert_not_called()


@pytest.mark.parametrize("row_shape", ["sqlite_row", "postgres_mapping"])
def test_progress_lookup_preserves_evidence_for_both_row_shapes(monkeypatch, row_shape):
    observed = []

    def row_factory(cursor, values):
        row = sqlite3.Row(cursor, values)
        # Execute the real query, retaining its actual column names in both shapes.
        result = dict(row) if row_shape == "postgres_mapping" else row
        observed.append(result)
        return result

    @contextmanager
    def connection_with_row_shape():
        with runtime_db.db_connection() as connection:
            connection.row_factory = row_factory
            yield connection

    monkeypatch.setattr(evidence_store, "db_connection", connection_with_row_shape)
    assert_progress_lookup_preserves_current_evidence(monkeypatch)
    assert observed
    assert all(row["has_context"] == 0 for row in observed)
    if row_shape == "sqlite_row":
        assert all(row[0] == row["has_context"] for row in observed)
    else:
        assert all(isinstance(row, dict) and 0 not in row for row in observed)
