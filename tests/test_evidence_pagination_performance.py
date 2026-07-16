from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from app.services import evidence_store


def _records(count: int) -> list[dict]:
    started = datetime(2025, 1, 1, tzinfo=UTC)
    records: list[dict] = []
    for index in range(count):
        created_at = (started + timedelta(minutes=index)).isoformat()
        feedback = (
            [{
                "category": "confirmed_issue",
                "recorded_at": created_at,
                "actor": "operator",
            }]
            if index % 5 == 0
            else []
        )
        records.append({
            "run_id": f"run-{index:05d}",
            "source_type": "upload",
            "source_name": f"historian-{index % 12}",
            "created_at": created_at,
            "status": "complete",
            "observation_type": f"relationship_drift_{index % 6}",
            "variables": [f"sensor_{index % 30}", f"sensor_{(index + 1) % 30}"],
            "drift_metrics": {"baseline_distance": (index % 100) / 100},
            "operator_feedback_history": feedback,
            "latest_feedback_category": "confirmed_issue" if feedback else None,
            "evidence_summary": ["Relationship change persisted across the operating window."],
            "data_conditions": ["complete"],
        })
    return records


def test_indexed_annotations_preserve_legacy_results() -> None:
    records = _records(120)
    legacy: list[dict] = []
    history: list[dict] = []
    for record in sorted(records, key=evidence_store._evidence_sort_key):
        legacy.append(evidence_store._annotate_evidence_record(record, history))
        history.append(record)
    legacy.sort(key=evidence_store._evidence_sort_key, reverse=True)

    indexed = evidence_store._annotate_and_sort_evidence_runs(records)

    assert [item["run_id"] for item in indexed] == [item["run_id"] for item in legacy]
    legacy_by_id = {item["run_id"]: item for item in legacy}
    for item in indexed:
        expected = legacy_by_id[item["run_id"]]
        assert item["historical_fact"] == expected["historical_fact"]
        assert item["validation_event_history"] == expected["validation_event_history"]
        assert item["validation_status"] == expected["validation_status"]
        assert item["validation_outcome"] == expected["validation_outcome"]
        assert item["before_after_intervention"] == expected["before_after_intervention"]


def test_issue_annotation_budget_with_500_realistic_records() -> None:
    records = _records(500)

    started = time.perf_counter()
    annotated = evidence_store._annotate_and_sort_evidence_runs(records)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert len(annotated) == 500
    assert elapsed_ms < 250, f"500-record issue annotation took {elapsed_ms:.1f} ms"


def test_evidence_pages_are_bounded_and_report_next_offset(monkeypatch) -> None:
    records = list(reversed(_records(640)))
    calls: list[tuple[int, int]] = []

    def load_page(limit: int, offset: int = 0) -> list[dict]:
        calls.append((limit, offset))
        return records[offset : offset + limit]

    monkeypatch.setattr(evidence_store, "_load_raw_evidence_runs", load_page)

    first_page = evidence_store.list_evidence_runs_page(limit=50, offset=0)
    second_page = evidence_store.list_evidence_runs_page(limit=50, offset=50)

    assert calls == [(551, 0), (551, 50)]
    assert len(first_page["runs"]) == 50
    assert first_page["runs"][0]["run_id"] == "run-00639"
    assert first_page["runs"][-1]["run_id"] == "run-00590"
    assert first_page["has_more"] is True
    assert first_page["next_offset"] == 50
    assert len(second_page["runs"]) == 50
    assert second_page["offset"] == 50
    assert second_page["next_offset"] == 100


def test_evidence_page_size_is_capped(monkeypatch) -> None:
    records = list(reversed(_records(150)))
    monkeypatch.setattr(
        evidence_store,
        "_load_raw_evidence_runs",
        lambda limit, offset=0: records[offset : offset + limit],
    )

    page = evidence_store.list_evidence_runs_page(limit=10_000, offset=0)

    assert page["limit"] == evidence_store.MAX_EVIDENCE_PAGE_SIZE
    assert len(page["runs"]) == evidence_store.MAX_EVIDENCE_PAGE_SIZE


def test_populated_page_uses_one_bounded_database_query(monkeypatch) -> None:
    records = list(reversed(_records(640)))
    calls: list[tuple[int, int]] = []

    def load_db(limit: int, offset: int = 0) -> list[dict]:
        calls.append((limit, offset))
        return records[offset : offset + limit]

    monkeypatch.setattr(evidence_store, "list_evidence_runs_db", load_db)

    page = evidence_store.list_evidence_runs_page(limit=50, offset=100)

    assert calls == [(551, 100)]
    assert len(page["runs"]) == 50
    assert page["next_offset"] == 150


def test_empty_final_db_page_does_not_restart_from_json(monkeypatch) -> None:
    db_calls: list[tuple[int, int]] = []

    def load_db(limit: int, offset: int = 0) -> list[dict]:
        db_calls.append((limit, offset))
        return _records(1) if offset == 0 else []

    monkeypatch.setattr(evidence_store, "list_evidence_runs_db", load_db)
    monkeypatch.setattr(
        evidence_store,
        "evidence_runs_path",
        lambda: (_ for _ in ()).throw(AssertionError("legacy file should not be read")),
    )

    assert evidence_store._load_raw_evidence_runs(limit=50, offset=500) == []
    assert db_calls == [(50, 500), (1, 0)]
