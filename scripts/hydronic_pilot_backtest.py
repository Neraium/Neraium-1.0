#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chronologically replay hydronic telemetry and compare findings with alarms or work orders."
    )
    parser.add_argument("telemetry_csv", type=Path)
    parser.add_argument("events_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timestamp-column", default="")
    parser.add_argument("--minimum-rows", type=int, default=96)
    parser.add_argument("--step-rows", type=int, default=24)
    parser.add_argument("--max-lead-hours", type=float, default=168.0)
    return parser.parse_args()


def load_telemetry(path: Path, explicit_timestamp: str) -> tuple[list[str], list[dict[str, str]], str]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    timestamp_column = explicit_timestamp or next(
        (column for column in columns if column.strip().lower() in {"timestamp", "datetime", "date_time", "time"}),
        "",
    )
    if not timestamp_column:
        raise ValueError("timestamp_column_not_found")
    for row in rows:
        _timestamp(row.get(timestamp_column), f"telemetry.{timestamp_column}")
    rows.sort(key=lambda row: _timestamp(row.get(timestamp_column), f"telemetry.{timestamp_column}"))
    return columns, rows, timestamp_column


def load_events(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        events = [dict(row) for row in csv.DictReader(source)]
    for index, event in enumerate(events, start=1):
        event["event_id"] = str(event.get("event_id") or f"event-{index}")
        _timestamp(event.get("event_at"), "events.event_at")
    return events


def prefix_csv(columns: list[str], rows: list[dict[str, str]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def replay_findings(
    columns: list[str],
    rows: list[dict[str, str]],
    timestamp_column: str,
    *,
    minimum_rows: int,
    step_rows: int,
) -> list[dict[str, Any]]:
    os.environ["NERAIUM_INLINE_REPLAY_GENERATION"] = "0"
    os.environ["NERAIUM_MODE_AWARE_SUPPRESSION_ENABLED"] = "1"
    os.environ["NERAIUM_DISABLE_RUNTIME_DB_LATEST"] = "1"
    from app.services.upload_jobs import process_csv_content

    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    final_positions = list(range(minimum_rows, len(rows) + 1, step_rows))
    if rows and (not final_positions or final_positions[-1] != len(rows)):
        final_positions.append(len(rows))
    for position in final_positions:
        current = rows[:position]
        detected_at = str(current[-1][timestamp_column])
        result = process_csv_content(
            prefix_csv(columns, current),
            filename=f"hydronic-replay-{position}.csv",
            job_id=f"backtest-{position}-{uuid.uuid4().hex[:8]}",
        )
        analysis = result.get("analysis_result") if isinstance(result.get("analysis_result"), dict) else {}
        conditions = analysis.get("conditions") if isinstance(analysis.get("conditions"), list) else []
        for index, condition in enumerate(conditions):
            if not isinstance(condition, dict):
                continue
            signals = [str(value) for value in condition.get("affected_signals") or []]
            signature = "|".join(sorted(signals)) + "|" + str(condition.get("finding_class") or condition.get("headline") or index)
            finding_id = sha256(signature.encode("utf-8")).hexdigest()[:16]
            if finding_id in seen:
                continue
            seen.add(finding_id)
            localization = condition.get("localization") if isinstance(condition.get("localization"), dict) else {}
            findings.append({
                "finding_id": finding_id,
                "condition_id": condition.get("condition_id"),
                "detected_at": detected_at,
                "source_window_end": detected_at,
                "rows_available": position,
                "system_id": localization.get("system"),
                "signals": signals,
                "headline": condition.get("headline"),
                "confidence_score": condition.get("confidence_score"),
            })
    return findings


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise ValueError("output_already_exists")
    if args.minimum_rows < 12 or args.step_rows < 1:
        raise ValueError("invalid_replay_window")
    columns, rows, timestamp_column = load_telemetry(args.telemetry_csv, args.timestamp_column)
    if len(rows) < args.minimum_rows:
        raise ValueError("insufficient_telemetry_rows")
    events = load_events(args.events_csv)

    with tempfile.TemporaryDirectory(prefix="neraium-hydronic-backtest-") as runtime:
        os.environ["NERAIUM_RUNTIME_DIR"] = runtime
        from app.services.sii_runner import configure_runtime_dir as configure_sii_runner_dir
        from app.services.upload_jobs import configure_runtime_dir

        configure_runtime_dir(runtime)
        configure_sii_runner_dir(Path(runtime))
        findings = replay_findings(
            columns,
            rows,
            timestamp_column,
            minimum_rows=args.minimum_rows,
            step_rows=args.step_rows,
        )

    from app.services.analysis_provenance import canonical_digest, file_digest
    from app.services.engine_identity import git_commit
    from app.services.pilot_benchmark import assert_no_future_leakage, match_findings_to_events

    assert_no_future_leakage(findings)
    config = {
        "version": "hydronic-pilot-backtest.v1",
        "timestamp_column": timestamp_column,
        "minimum_rows": args.minimum_rows,
        "step_rows": args.step_rows,
        "max_lead_hours": args.max_lead_hours,
        "mode_aware_suppression_enabled": True,
        "future_rows_available_to_each_run": False,
    }
    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "methodology": "Chronological prefix replay; every analysis receives only rows at or before detected_at.",
        "telemetry_sha256": file_digest(args.telemetry_csv),
        "events_sha256": file_digest(args.events_csv),
        "build_commit": git_commit(),
        "configuration": config,
        "configuration_hash": canonical_digest(config),
        "findings": findings,
        "benchmark": match_findings_to_events(findings, events, max_lead_hours=args.max_lead_hours),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Hydronic pilot backtest written: {args.output}")
    return 0


def _timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_timestamp:{field}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"timezone_required:{field}")
    return parsed


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Backtest failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
