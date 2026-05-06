import csv
import io
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(tags=["data"])

PREVIEW_ROW_LIMIT = 5
TIMESTAMP_COLUMN_HINTS = (
    "timestamp",
    "time",
    "datetime",
    "date",
    "recorded_at",
    "created_at",
)


@router.post("/data/upload")
async def upload_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.") from exc

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    columns = [column.strip() for column in rows[0]]
    if not any(columns):
        raise HTTPException(status_code=400, detail="CSV file must include a header row.")

    data_rows = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    warnings = _build_warnings(columns, data_rows)
    detected_timestamp_column = _detect_timestamp_column(columns)

    if detected_timestamp_column is None:
        warnings.append("No obvious timestamp column detected.")

    return {
        "filename": filename,
        "row_count": len(data_rows),
        "column_count": len(columns),
        "columns": columns,
        "preview_rows": _preview_rows(columns, data_rows),
        "detected_timestamp_column": detected_timestamp_column,
        "warnings": warnings,
    }


def _detect_timestamp_column(columns: list[str]) -> str | None:
    normalized_columns = [(column, column.lower().replace(" ", "_")) for column in columns]
    for column, normalized in normalized_columns:
        if normalized in TIMESTAMP_COLUMN_HINTS or "timestamp" in normalized:
            return column
    return None


def _preview_rows(columns: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
    preview: list[dict[str, str]] = []
    for row in rows[:PREVIEW_ROW_LIMIT]:
        preview.append(
            {
                column: row[index].strip() if index < len(row) else ""
                for index, column in enumerate(columns)
            }
        )
    return preview


def _build_warnings(columns: list[str], rows: list[list[str]]) -> list[str]:
    warnings: list[str] = []
    if len(set(columns)) != len(columns):
        warnings.append("Duplicate column names detected.")
    if any(not column for column in columns):
        warnings.append("One or more columns are unnamed.")
    if not rows:
        warnings.append("CSV contains headers but no data rows.")
    if any(len(row) != len(columns) for row in rows):
        warnings.append("One or more rows have a different column count than the header.")
    return warnings
