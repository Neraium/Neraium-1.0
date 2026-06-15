from __future__ import annotations

import csv
import io
from typing import Any

from app.services.upload_state_repository import read_current_upload_result, read_upload_result_by_job_id


def build_live_upload_result(
    columns: list[str] | None = None,
    rows: list[Any] | None = None,
    filename: str = "telemetry.csv",
    **kwargs,
) -> dict[str, Any]:
    """
    Focused adapter for live/data-connection ingestion.
    Preserves the existing CSV-bytes handoff into the upload processing pipeline.
    """
    from app.services.upload_jobs import process_upload_bytes

    columns = columns or kwargs.get("columns") or []
    rows = rows or kwargs.get("rows") or kwargs.get("data_rows") or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)

    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(col, "") for col in columns])
        else:
            writer.writerow(row)

    summary = process_upload_bytes(filename, output.getvalue().encode("utf-8"))
    return read_upload_result_by_job_id(summary["job_id"]) or read_current_upload_result() or {}
