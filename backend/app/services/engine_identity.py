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
from app.services.sii_runner import (
    CORE_ENGINE,
    RUNNER_CALLABLE,
    RUNNER_MODULE,
    VALIDATION_RUNNER,
    runner_available,
    runner_identity,
    runner_import_error,
)


REPO_ROOT = Path(__file__).resolve().parents[3]

VALIDATION_PROVENANCE = {
    "cmapss_supported": True,
    "known_validation_result": "707 units, 687 detected, 97.2% coverage, average lead time 198.4 cycles",
    "validation_source": "local validation results / repo validation runner",
    "same_engine_family": True,
    "same_exact_validation_runner": False,
    "note": (
        "Production uploads use SIIEngineAdapter backed by SIIEngine. "
        "FD004ValidationRunner remains a validation harness."
    ),
}


def build_engine_identity() -> dict[str, Any]:
    upload_callable = callable_identity(run_engine_analysis)
    facility_callable = callable_identity(build_upload_intelligence)
    attribution_callable = callable_identity(build_driver_attribution)

    available = runner_available()
    real_runner_identity = runner_identity()
    return {
        "engine_name": "Neraium SII",
        "engine_version": "neraium-core 0.1.0",
        "engine_module": RUNNER_MODULE,
        "engine_class_or_function": RUNNER_CALLABLE,
        "git_commit": git_commit(),
        "deployment_mode": "production",
        "validation_engine_path_present": True,
        "cmapss_validation_supported": VALIDATION_PROVENANCE["cmapss_supported"],
        "driver_attribution_supported": callable(build_driver_attribution),
        "sii_pipeline_supported": available,
        "production_runner": RUNNER_CALLABLE,
        "core_engine": CORE_ENGINE,
        "validation_runner": VALIDATION_RUNNER,
        "production_runner_file": real_runner_identity["runner_file"],
        "core_engine_file": real_runner_identity["core_engine_file"],
        "validation_runner_file": real_runner_identity["validation_runner_file"],
        "runner_available": available,
        "same_engine_family_as_validation": True,
        "same_exact_fd004_validation_runner": False,
        "note": (
            "Production uploads use SIIEngineAdapter backed by SIIEngine. "
            "FD004ValidationRunner remains a validation harness."
        ),
        "import_error": runner_import_error(),
        "actual_imports": {
            "upload_processing": {
                "module": RUNNER_MODULE,
                "callable": RUNNER_CALLABLE,
                "file": real_runner_identity["runner_file"],
            },
            "legacy_upload_processing": upload_callable,
            "facility_intelligence": facility_callable,
            "facility_status": callable_identity(build_intelligence_status),
            "sample_facility_intelligence": callable_identity(build_sample_intelligence),
            "driver_attribution": attribution_callable,
            "validation_runner": {
                "module": VALIDATION_RUNNER.rsplit(".", 1)[0],
                "callable": VALIDATION_RUNNER.rsplit(".", 1)[1],
                "file": real_runner_identity["validation_runner_file"],
            },
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
