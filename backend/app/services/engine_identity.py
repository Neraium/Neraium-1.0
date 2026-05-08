from __future__ import annotations

import inspect
import subprocess
from pathlib import Path
from typing import Any, Callable

from app.engine import run_engine_analysis
from app.engine.schemas import ENGINE_VERSION
from app.services.driver_attribution import build_driver_attribution
from app.services.sii_intelligence import (
    build_intelligence_status,
    build_sample_intelligence,
    build_upload_intelligence,
)


REPO_ROOT = Path(__file__).resolve().parents[3]

VALIDATION_PROVENANCE = {
    "cmapss_supported": False,
    "known_validation_result": None,
    "validation_source": "No CMAPSS validation runner or local validation result metadata was found in this repo.",
    "same_engine_family": True,
    "same_exact_validation_runner": False,
    "note": (
        "Production cultivation route uses the SII processing layer, while no exact CMAPSS "
        "validation runner is deployed in this backend repo."
    ),
}


def build_engine_identity() -> dict[str, Any]:
    upload_callable = callable_identity(run_engine_analysis)
    facility_callable = callable_identity(build_upload_intelligence)
    attribution_callable = callable_identity(build_driver_attribution)

    return {
        "engine_name": "Neraium SII",
        "engine_version": ENGINE_VERSION,
        "engine_module": upload_callable["module"],
        "engine_class_or_function": upload_callable["callable"],
        "git_commit": git_commit(),
        "deployment_mode": "production",
        "validation_engine_path_present": True,
        "cmapss_validation_supported": VALIDATION_PROVENANCE["cmapss_supported"],
        "driver_attribution_supported": callable(build_driver_attribution),
        "sii_pipeline_supported": callable(run_engine_analysis) and callable(build_upload_intelligence),
        "actual_imports": {
            "upload_processing": upload_callable,
            "facility_intelligence": facility_callable,
            "facility_status": callable_identity(build_intelligence_status),
            "sample_facility_intelligence": callable_identity(build_sample_intelligence),
            "driver_attribution": attribution_callable,
            "validation_runner": None,
        },
        "validation_provenance": VALIDATION_PROVENANCE,
    }


def build_processing_trace(
    *,
    engine_result: dict[str, Any],
    driver_attribution: dict[str, Any],
    rows_processed: int,
    columns_analyzed: int,
) -> dict[str, Any]:
    identity = callable_identity(run_engine_analysis)
    return {
        "sii_pipeline_ran": bool(engine_result.get("audit_trace")),
        "engine_module": identity["module"],
        "engine_version": engine_result.get("engine_version", ENGINE_VERSION),
        "driver_attribution_ran": bool(driver_attribution.get("driver_category")),
        "rows_processed": rows_processed,
        "columns_analyzed": columns_analyzed,
        "evidence_count": len(engine_result.get("evidence", [])),
        "git_commit": git_commit(),
    }


def callable_identity(target: Callable[..., Any]) -> dict[str, str | None]:
    module = inspect.getmodule(target)
    return {
        "module": module.__name__ if module else None,
        "callable": getattr(target, "__qualname__", getattr(target, "__name__", None)),
        "file": inspect.getsourcefile(target),
    }


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"
