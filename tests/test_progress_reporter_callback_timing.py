"""Progress intervals start after successful synchronous persistence."""

import math

import pytest

from app.services.job_progress import ProgressReporter
from app.services.relationship_baselines import build_relationship_baseline


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now


def report(reporter, **overrides):
    values = {"stage": "mapping", "substage": "scoring_drift_relationships"}
    values.update(overrides)
    return reporter.report(**values)


@pytest.mark.parametrize("callback_seconds", [0.0, 0.125, 4.0])
def test_interval_starts_after_successful_callback(callback_seconds):
    clock = Clock()
    writes = []

    def persist(**values):
        writes.append(values)
        clock.now += callback_seconds
        return values

    reporter = ProgressReporter(
        job_id="comparison", workflow="comparison", persist=persist,
        minimum_interval_seconds=2, monotonic=clock,
    )
    assert report(reporter, completed_units=1)["completed_units"] == 1
    assert report(reporter, completed_units=2) is None
    clock.now += 1.875
    assert report(reporter, completed_units=3) is None
    clock.now += 0.125
    assert report(reporter, completed_units=4)["completed_units"] == 4
    assert [w["completed_units"] for w in writes] == [1, 4]
    assert reporter.write_count == 2


@pytest.mark.parametrize("transition", [
    {"force": True, "completed_units": 28, "total_units": 28},
    {"substage": "finalizing"},
    {"status": "queued"},
    {"status": "completed"},
    {"status": "failed"},
    {"status": "cancelled"},
])
def test_forced_and_transition_updates_bypass_interval(transition):
    clock = Clock()
    writes = []

    def persist(**values):
        writes.append(values)
        clock.now += 4
        return values

    reporter = ProgressReporter(
        job_id="comparison", workflow="comparison", persist=persist,
        minimum_interval_seconds=2, monotonic=clock,
    )
    report(reporter, completed_units=23, total_units=28)
    result = report(reporter, **transition)
    assert result == writes[-1]
    assert len(writes) == 2
    for key, value in transition.items():
        if key != "force":
            assert result[key] == value
    if transition.get("status") in {"completed", "failed", "cancelled"}:
        assert report(reporter, **transition) is not None
        assert len(writes) == 3


@pytest.mark.parametrize("failed_update", [{}, {"force": True}, {"substage": "finalizing"}])
def test_failed_callback_keeps_successful_write_and_transition_state(failed_update):
    clock = Clock()
    fail = False

    def persist(**values):
        clock.now += 4
        if fail:
            raise RuntimeError("persistence failed")
        return values

    reporter = ProgressReporter(
        job_id="comparison", workflow="comparison", persist=persist,
        minimum_interval_seconds=2, monotonic=clock,
    )
    report(reporter)
    previous = (reporter._last_write, reporter._last_substage, reporter._last_status)
    clock.now += 2
    fail = True
    with pytest.raises(RuntimeError, match="persistence failed"):
        report(reporter, **failed_update)
    assert (reporter._last_write, reporter._last_substage, reporter._last_status) == previous
    assert reporter.write_count == 1
    fail = False
    assert report(reporter, **failed_update) is not None
    assert reporter.write_count == 2


def test_slow_progress_callback_preserves_all_28_pair_results():
    columns = [f"pump_{index}_power_kw" for index in range(8)]
    rows = [
        {column: 20 + math.sin(row / (index + 2)) * (index + 1)
         for index, column in enumerate(columns)}
        for row in range(100)
    ]
    expected = build_relationship_baseline(rows, columns)
    clock = Clock()
    writes = []
    events = []

    def persist(**values):
        writes.append(values)
        clock.now += 4
        return values

    reporter = ProgressReporter(
        job_id="comparison", workflow="comparison", persist=persist,
        minimum_interval_seconds=2, monotonic=clock,
    )

    def progress(completed, total):
        events.append((completed, total))
        report(reporter, completed_units=completed, total_units=total,
               force=completed == total)

    actual = build_relationship_baseline(rows, columns, progress_callback=progress)
    assert actual == expected
    assert actual["relationship_pair_accounting"]["eligible_unique_pair_count"] == 28
    assert events == [(completed, 28) for completed in range(29)]
    assert [w["completed_units"] for w in writes] == [0, 28]
    assert writes[-1]["total_units"] == 28
