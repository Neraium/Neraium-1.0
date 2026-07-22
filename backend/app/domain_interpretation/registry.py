from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class DomainInterpretationContext:
    columns: list[str]
    engine_result: dict[str, Any]
    relationship_model: dict[str, Any]
    baseline_analysis: dict[str, Any]
    normalized_telemetry: dict[str, Any] | None = None
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None
    timestamp_profile: dict[str, Any] | None = None
    data_quality: dict[str, Any] | None = None
    operating_mode: str | None = None
    site_id: str | None = None
    system_id: str | None = None
    asset_id: str | None = None
    asset_metadata: dict[str, Any] | None = None
    config: dict[str, Any] = field(default_factory=dict)
    generated_at: str | None = None
    upload_id: str | None = None
    analysis_id: str | None = None


@dataclass(frozen=True)
class DomainInterpreterSpec:
    key: str
    interpret: Callable[[DomainInterpretationContext], dict[str, Any] | None]
    legacy_result_key: str | None = None


def _water_interpreter(context: DomainInterpretationContext) -> dict[str, Any] | None:
    from app.water_intelligence import WaterIntelligenceContext, interpret_water_intelligence

    return interpret_water_intelligence(
        WaterIntelligenceContext(
            columns=context.columns,
            engine_result=context.engine_result,
            relationship_model=context.relationship_model,
            baseline_analysis=context.baseline_analysis,
            normalized_telemetry=context.normalized_telemetry,
            telemetry_signal_catalog=context.telemetry_signal_catalog,
            timestamp_profile=context.timestamp_profile,
            data_quality=context.data_quality,
            operating_mode=context.operating_mode,
            site_id=context.site_id,
            system_id=context.system_id,
            asset_id=context.asset_id,
            asset_metadata=context.asset_metadata,
            config=context.config,
            generated_at=context.generated_at,
            upload_id=context.upload_id,
            analysis_id=context.analysis_id,
        )
    )


def default_domain_interpreters() -> tuple[DomainInterpreterSpec, ...]:
    return (
        DomainInterpreterSpec(
            key="water",
            legacy_result_key="water_intelligence",
            interpret=_water_interpreter,
        ),
    )


def interpret_domain_layers(
    context: DomainInterpretationContext,
    interpreters: tuple[DomainInterpreterSpec, ...] | list[DomainInterpreterSpec] | None = None,
) -> dict[str, Any]:
    interpretations: dict[str, Any] = {}
    legacy_fields: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []

    for spec in interpreters if interpreters is not None else default_domain_interpreters():
        try:
            interpretation = spec.interpret(context)
        except Exception as exc:
            errors.append(
                {
                    "domain": spec.key,
                    "legacy_result_key": spec.legacy_result_key,
                    "error": exc.__class__.__name__,
                    "message": str(exc),
                    "effect": "domain_interpretation_skipped_original_sii_result_preserved",
                }
            )
            continue
        if not isinstance(interpretation, dict):
            continue
        interpretations[spec.key] = interpretation
        if spec.legacy_result_key:
            legacy_fields[spec.legacy_result_key] = interpretation

    return {
        "domain_interpretations": interpretations,
        "domain_interpretation_errors": errors,
        "legacy_fields": legacy_fields,
    }


def attach_domain_interpretations(
    result: dict[str, Any],
    context: DomainInterpretationContext,
    interpreters: tuple[DomainInterpreterSpec, ...] | list[DomainInterpreterSpec] | None = None,
) -> dict[str, Any]:
    domain_result = interpret_domain_layers(context, interpreters=interpreters)
    interpretations = domain_result["domain_interpretations"]
    errors = domain_result["domain_interpretation_errors"]
    if interpretations:
        result["domain_interpretations"] = interpretations
    if errors:
        result["domain_interpretation_errors"] = errors
    result.update(domain_result["legacy_fields"])
    return result
