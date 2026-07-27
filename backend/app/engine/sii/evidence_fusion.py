from __future__ import annotations

from copy import deepcopy
from typing import Any


SOURCE_MODULE_ORDER = (
    "signal_drift",
    "relationship_analysis",
    "operating_modes",
    "physics_reasoning",
    "adaptive_persistence",
    "temporal_analysis",
    "multiscale_analysis",
    "relationship_graph",
    "covariance_analysis",
    "data_quality",
    "sensor_health",
    "uncertainty",
)

CLASSIFICATIONS = ("Supporting", "Limiting", "Contradictory", "Neutral")


def fuse_evidence(
    *,
    analytical_evidence: dict[str, Any],
    physics_reasoning: dict[str, Any],
    processing_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Organize canonical evidence without weighting, voting, or inference."""

    evidence = analytical_evidence if isinstance(analytical_evidence, dict) else {}
    physics = physics_reasoning if isinstance(physics_reasoning, dict) else {}
    source_trace = processing_trace if isinstance(processing_trace, dict) else {}
    source_payloads = {
        module: (
            physics
            if module == "physics_reasoning"
            else evidence.get(module, {})
        )
        for module in SOURCE_MODULE_ORDER
    }

    inventory = [
        _module_evidence_item(module, source_payloads[module], source_trace)
        for module in SOURCE_MODULE_ORDER
    ]
    physics_items = _physics_evidence_items(physics)
    inventory.extend(physics_items)
    inventory = _unique_evidence(inventory)

    by_classification = {
        classification: [
            item for item in inventory if item["classification"] == classification
        ]
        for classification in CLASSIFICATIONS
    }
    ignored_priors = [
        deepcopy(item)
        for item in physics.get("ignored_priors", [])
        if isinstance(item, dict)
    ]
    evaluated_priors = [
        str(item.get("id"))
        for item in physics.get("evaluated_priors", [])
        if isinstance(item, dict) and item.get("id")
    ]
    limiting_ids = [
        item["evidence_id"] for item in by_classification["Limiting"]
    ]
    observations = [
        _observation(
            prior,
            inventory=inventory,
            limiting_ids=limiting_ids,
            evaluated_priors=evaluated_priors,
            ignored_priors=ignored_priors,
            uncertainty=evidence.get("uncertainty"),
            source_trace=source_trace,
        )
        for prior in physics.get("evaluated_priors", [])
        if isinstance(prior, dict)
        and prior.get("applicable")
        and prior.get("status") in {"supported", "contradicted"}
    ]

    module_statuses = {
        module: _module_status(source_payloads[module])
        for module in SOURCE_MODULE_ORDER
    }
    fusion_trace = {
        "method": "transparent_evidence_organization_v1",
        "module_order": list(SOURCE_MODULE_ORDER),
        "module_statuses": module_statuses,
        "evidence_item_ids": [item["evidence_id"] for item in inventory],
        "observation_ids": [item["observation_id"] for item in observations],
        "source_processing_trace": deepcopy(source_trace),
        "weighted_scoring_performed": False,
        "voting_performed": False,
        "probability_estimated": False,
        "diagnosis_performed": False,
        "recommendations_generated": False,
    }
    return {
        "status": "complete",
        "active": True,
        "method": "transparent_evidence_organization_v1",
        "observations": observations,
        "supporting_evidence": by_classification["Supporting"],
        "limiting_evidence": by_classification["Limiting"],
        "contradictory_evidence": by_classification["Contradictory"],
        "neutral_evidence": by_classification["Neutral"],
        "evidence_inventory": inventory,
        "evaluated_engineering_priors": evaluated_priors,
        "ignored_engineering_priors": ignored_priors,
        "uncertainty": deepcopy(evidence.get("uncertainty", {})),
        "processing_trace": fusion_trace,
        "principles": {
            "evidence_independent": True,
            "statistical_evidence_authoritative": True,
            "human_review_required": True,
            "engineering_interpretation_provided": False,
        },
    }


def _module_evidence_item(
    module: str,
    payload: Any,
    processing_trace: dict[str, Any],
) -> dict[str, Any]:
    copied = deepcopy(payload)
    classification = _module_classification(module, copied)
    limitations = _module_limitations(copied)
    status = _module_status(copied)
    module_trace = processing_trace.get("module_statuses", {}).get(module)
    return {
        "evidence_id": f"module:{module}",
        "classification": classification,
        "originating_module": module,
        "reasoning": (
            f"Canonical {module} output is preserved as {classification.lower()} evidence "
            f"with source status {status}."
        ),
        "limitations": limitations,
        "uncertainty": (
            deepcopy(copied)
            if module == "uncertainty"
            else deepcopy(copied.get("uncertainty", {}))
            if isinstance(copied, dict)
            else {}
        ),
        "processing_trace": deepcopy(module_trace if isinstance(module_trace, dict) else {}),
        "evidence": copied,
    }


def _physics_evidence_items(physics: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for prior in physics.get("evaluated_priors", []):
        if not isinstance(prior, dict):
            continue
        prior_id = str(prior.get("id") or "unknown")
        for field, classification in (
            ("supporting_evidence", "Supporting"),
            ("contradictory_evidence", "Contradictory"),
        ):
            for index, source in enumerate(prior.get(field, [])):
                if not isinstance(source, dict):
                    continue
                evidence_id = str(
                    source.get("evidence_id")
                    or f"physics:{prior_id}:{field}:{index + 1}"
                )
                items.append(
                    {
                        **deepcopy(source),
                        "evidence_id": evidence_id,
                        "classification": classification,
                        "originating_module": str(
                            source.get("originating_module") or "physics_reasoning"
                        ),
                        "evaluated_by_module": "physics_reasoning",
                        "engineering_prior_id": prior_id,
                        "limitations": list(source.get("limitations") or []),
                        "uncertainty": deepcopy(source.get("uncertainty")),
                        "processing_trace": {
                            "prior_id": prior_id,
                            "prior_status": prior.get("status"),
                            "confidence_modifier": deepcopy(prior.get("confidence_modifier")),
                            "confidence_modifier_applied": False,
                        },
                    }
                )
    return items


def _observation(
    prior: dict[str, Any],
    *,
    inventory: list[dict[str, Any]],
    limiting_ids: list[str],
    evaluated_priors: list[str],
    ignored_priors: list[dict[str, Any]],
    uncertainty: Any,
    source_trace: dict[str, Any],
) -> dict[str, Any]:
    prior_id = str(prior["id"])
    status = str(prior["status"])
    prior_supporting = [
        item
        for item in prior.get("supporting_evidence", [])
        if isinstance(item, dict)
    ]
    applicability_support = [
        item
        for item in prior_supporting
        if item.get("evidence_role") == "applicability"
    ]
    expectation_support = [
        item
        for item in prior_supporting
        if item.get("evidence_role") != "applicability"
    ]
    supporting_source = (
        prior_supporting
        if status == "supported"
        else [
            *applicability_support,
            *prior.get("contradictory_evidence", []),
        ]
    )
    contrary_source = (
        prior.get("contradictory_evidence", [])
        if status == "supported"
        else expectation_support
    )
    supporting_ids = _evidence_ids(supporting_source)
    contradictory_ids = _evidence_ids(contrary_source)
    index = {item["evidence_id"]: item for item in inventory}
    contributing_modules = {
        "physics_reasoning",
        *[
            str(item.get("originating_module") or "physics_reasoning")
            for item in [*supporting_source, *contrary_source]
            if isinstance(item, dict)
        ],
    }
    rendered_reasoning = prior.get("reasoning_trace", {}).get("rendered_reasoning")
    return {
        "observation_id": f"engineering_observation:{prior_id}",
        "observation": str(rendered_reasoning or prior.get("name") or prior_id),
        "behavioral_status": (
            "consistent_with_configured_expectation"
            if status == "supported"
            else "not_consistent_with_configured_expectation"
        ),
        "contributing_analytical_modules": sorted(contributing_modules),
        "supporting_evidence": [
            deepcopy(index[evidence_id])
            for evidence_id in supporting_ids
            if evidence_id in index
        ],
        "limiting_evidence": [
            deepcopy(index[evidence_id])
            for evidence_id in limiting_ids
            if evidence_id in index
        ],
        "contradictory_evidence": [
            deepcopy(index[evidence_id])
            for evidence_id in contradictory_ids
            if evidence_id in index
        ],
        "evaluated_engineering_priors": list(evaluated_priors),
        "ignored_engineering_priors": deepcopy(ignored_priors),
        "analytical_uncertainty": deepcopy(uncertainty if isinstance(uncertainty, dict) else {}),
        "processing_trace": {
            "prior_id": prior_id,
            "prior_status": status,
            "supporting_evidence_ids": supporting_ids,
            "limiting_evidence_ids": list(limiting_ids),
            "contradictory_evidence_ids": contradictory_ids,
            "source_module_statuses": deepcopy(source_trace.get("module_statuses", {})),
            "confidence_modifier": deepcopy(prior.get("confidence_modifier")),
            "confidence_modifier_applied": False,
            "weighted_scoring_performed": False,
        },
        "engineering_interpretation": None,
        "human_review_required": True,
        "causal_interpretation_provided": False,
        "maintenance_recommendation_provided": False,
    }


def _module_classification(module: str, payload: Any) -> str:
    if not isinstance(payload, dict) or not payload:
        return "Limiting"
    if isinstance(payload, dict):
        explicit = str(payload.get("evidence_classification") or "").title()
        if explicit in CLASSIFICATIONS:
            return explicit
        status = str(payload.get("status") or "").lower()
        if status in {"failed", "limited", "not_ready", "unavailable"}:
            return "Limiting"
    if module == "uncertainty" and _module_limitations(payload):
        return "Limiting"
    if module == "data_quality" and isinstance(payload, dict):
        if payload.get("readiness") in {"not_ready", "pending"} or payload.get("warnings"):
            return "Limiting"
    if module == "sensor_health" and isinstance(payload, dict):
        signals = payload.get("signals", [])
        if any(
            isinstance(item, dict)
            and str(item.get("health") or "").lower() not in {"", "healthy", "good"}
            for item in signals
        ):
            return "Limiting"
    return "Neutral"


def _module_limitations(payload: Any) -> list[str]:
    if not isinstance(payload, dict) or not payload:
        return ["Canonical module output was unavailable."]
    limitations = [
        str(item)
        for field in ("limitations", "warnings")
        for item in (payload.get(field) if isinstance(payload.get(field), list) else [])
        if str(item).strip()
    ]
    status = str(payload.get("status") or "").lower()
    reason = payload.get("reason")
    if reason and status in {"failed", "limited", "not_ready", "unavailable"}:
        limitations.append(str(reason))
    return list(dict.fromkeys(limitations))


def _module_status(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "unavailable"
    return str(payload.get("status") or payload.get("readiness") or "available")


def _evidence_ids(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [
        str(item["evidence_id"])
        for item in items
        if isinstance(item, dict) and item.get("evidence_id")
    ]


def _unique_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        evidence_id = str(item["evidence_id"])
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        output.append(item)
    return output
