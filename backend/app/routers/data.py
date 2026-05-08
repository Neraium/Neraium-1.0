from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.engine import run_engine_analysis
from app.services.baseline_analysis import build_baseline_analysis
from app.services.csv_parser import parse_csv_content, preview_rows
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import (
    build_data_quality,
    build_warnings,
    detect_timestamp_column,
    profile_numeric_columns,
    profile_timestamps,
)
from app.services.driver_attribution import build_driver_attribution
from app.services.operator_report import build_operator_report
from app.services.sii_intelligence import build_upload_intelligence

router = APIRouter(tags=["data"])


@router.post("/data/upload")
async def upload_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    try:
        columns, data_rows = parse_csv_content(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    warnings = build_warnings(columns, data_rows)
    detected_timestamp_column = detect_timestamp_column(columns)
    if detected_timestamp_column is None:
        warnings.append("No obvious timestamp column detected.")

    numeric_profiles = profile_numeric_columns(columns, data_rows)
    warnings.extend(
        f"{profile['column']} contains {profile['missing_count']} missing numeric values."
        for profile in numeric_profiles
        if profile["missing_count"] > 0
    )
    timestamp_profile = profile_timestamps(columns, data_rows, detected_timestamp_column)
    warnings.extend(timestamp_profile["warnings"])
    warnings.extend(
        profile["range_warning"]
        for profile in numeric_profiles
        if profile["range_warning"] is not None
    )
    data_quality = build_data_quality(
        row_count=len(data_rows),
        column_count=len(columns),
        numeric_column_count=len(numeric_profiles),
        timestamp_detected=detected_timestamp_column is not None,
        warnings=warnings,
    )
    baseline_analysis = build_baseline_analysis(columns, data_rows, numeric_profiles)
    cultivation_mapping = map_cultivation_columns(columns)
    operator_report = build_operator_report(
        data_quality=data_quality,
        timestamp_profile=timestamp_profile,
        numeric_profiles=numeric_profiles,
        baseline_analysis=baseline_analysis,
        cultivation_mapping=cultivation_mapping,
    )
    engine_result = run_engine_analysis(
        columns=columns,
        rows=data_rows,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        cultivation_mapping=cultivation_mapping,
        numeric_profiles=numeric_profiles,
    )
    driver_attribution = build_driver_attribution(
        room_state={
            "room": primary_room_from_upload(columns, data_rows),
            "state": state_from_assessment(baseline_analysis["overall_assessment"]),
            "severity": severity_from_assessment(baseline_analysis["overall_assessment"]),
        },
        telemetry_context={
            "columns": columns,
            "rows": data_rows,
            "numeric_profiles": numeric_profiles,
            "timestamp_profile": timestamp_profile,
            "data_quality": data_quality,
            "cultivation_mapping": cultivation_mapping,
        },
        baseline_context={
            "baseline_analysis": baseline_analysis,
            "cultivation_mapping": cultivation_mapping,
        },
        engine_result=engine_result,
    )
    sii_intelligence = build_upload_intelligence(
        filename=filename,
        row_count=len(data_rows),
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        operator_report=operator_report,
        timestamp_profile=timestamp_profile,
    )

    return {
        "filename": filename,
        "row_count": len(data_rows),
        "column_count": len(columns),
        "columns": columns,
        "preview_rows": preview_rows(columns, data_rows),
        "detected_timestamp_column": detected_timestamp_column,
        "warnings": warnings,
        "numeric_profiles": numeric_profiles,
        "timestamp_profile": timestamp_profile,
        "data_quality": data_quality,
        "baseline_analysis": baseline_analysis,
        "cultivation_mapping": cultivation_mapping,
        "operator_report": operator_report,
        "engine_result": engine_result,
        "driver_attribution": driver_attribution,
        "sii_intelligence": sii_intelligence,
    }


def primary_room_from_upload(columns: list[str], rows: list[list[str]]) -> str:
    room_columns = [
        index
        for index, column in enumerate(columns)
        if any(token in column.lower() for token in ("room", "zone", "bay"))
    ]
    if not room_columns:
        return "Current room"
    room_index = room_columns[0]
    for row in rows:
        if room_index < len(row) and row[room_index].strip():
            return row[room_index].strip()
    return "Current room"


def state_from_assessment(assessment: str) -> str:
    return "Needs review" if assessment == "needs_review" else "Monitoring"


def severity_from_assessment(assessment: str) -> str:
    return "review" if assessment == "needs_review" else "info"
