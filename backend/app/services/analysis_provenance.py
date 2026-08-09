from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.engine.sii_contract import ENGINE_NAME, ENGINE_VERSION
from app.services.analysis_result_contract import CONTRACT_VERSION as ANALYSIS_CONTRACT_VERSION
from app.services.engine_identity import git_commit
from app.services.mode_aware_authority import POLICY_VERSION as MODE_AUTHORITY_POLICY_VERSION
from app.water_intelligence.priors import WATER_PRIORS


PROVENANCE_SCHEMA_VERSION = "analysis-provenance.v1"
FINDING_RULE_VERSION = "deterministic_finding_classification_v2"
CONDITION_RULE_VERSION = "deterministic_condition_escalation_v1"


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analysis_configuration(result: dict[str, Any]) -> dict[str, Any]:
    trace = result.get("processing_trace") if isinstance(result.get("processing_trace"), dict) else {}
    water_versions = sorted(
        {
            (prior.prior_id, prior.version)
            for prior in WATER_PRIORS
        }
    )
    return {
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
        "finding_rule_version": FINDING_RULE_VERSION,
        "condition_rule_version": CONDITION_RULE_VERSION,
        "mode_authority_policy_version": MODE_AUTHORITY_POLICY_VERSION,
        "mode_authority_enabled": bool(
            (trace.get("mode_aware_authority") or {}).get("enabled")
        ),
        "mode_authority": "suppression_only",
        "water_prior_versions": [
            {"prior_id": prior_id, "version": version}
            for prior_id, version in water_versions
        ],
    }


def result_digest(result: dict[str, Any]) -> str:
    """Hash deterministic decision and evidence outputs, excluding runtime timing noise."""

    selected = {
        key: result.get(key)
        for key in (
            "organization_id",
            "portfolio_id",
            "system_id",
            "dataset_id",
            "baseline_id",
            "baseline_dataset_id",
            "comparison_dataset_id",
            "workflow",
            "operating_state",
            "drift_status",
            "engine_result",
            "analysis_result",
            "conditions",
            "water_intelligence",
            "sii_result",
        )
        if key in result
    }
    return canonical_digest(_without_runtime_noise(selected))


def build_analysis_provenance(result: dict[str, Any]) -> dict[str, Any]:
    active_baseline = (
        result.get("active_baseline_reference")
        if isinstance(result.get("active_baseline_reference"), dict)
        else {}
    )
    ingestion = result.get("ingestion_report") if isinstance(result.get("ingestion_report"), dict) else {}
    configuration = analysis_configuration(result)
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "analysis_run_id": result.get("run_id") or result.get("job_id"),
        "upload_id": result.get("upload_id") or result.get("job_id"),
        "organization_id": result.get("organization_id"),
        "portfolio_id": result.get("portfolio_id"),
        "site_id": result.get("site_id") or result.get("portfolio_id"),
        "system_id": result.get("system_id"),
        "dataset_id": result.get("dataset_id") or result.get("comparison_dataset_id"),
        "input_hash": ingestion.get("input_hash") or result.get("input_hash"),
        "baseline_id": result.get("baseline_id") or active_baseline.get("model_id"),
        "baseline_dataset_id": result.get("baseline_dataset_id") or active_baseline.get("dataset_id"),
        "baseline_version": active_baseline.get("version"),
        "baseline_hash": active_baseline.get("model_hash"),
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "build_commit": git_commit(),
        "configuration": configuration,
        "configuration_hash": canonical_digest(configuration),
        "result_hash": result_digest(result),
    }


def _without_runtime_noise(value: Any) -> Any:
    volatile_keys = {
        "runtime_seconds",
        "total_runtime_seconds",
        "processing_time_seconds",
        "total_job_ms",
        "completed_at",
        "last_processed_at",
        "generated_at",
    }
    if isinstance(value, dict):
        return {
            str(key): _without_runtime_noise(child)
            for key, child in value.items()
            if str(key) not in volatile_keys
        }
    if isinstance(value, list):
        return [_without_runtime_noise(child) for child in value]
    return value
