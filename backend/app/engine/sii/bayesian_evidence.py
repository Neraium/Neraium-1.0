from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable


DEFERRED_REASON = "validated_likelihoods_and_calibration_unavailable"


@dataclass
class BayesianEvidenceRegistry:
    """Future-facing registration contract; it performs no posterior update."""

    likelihoods: dict[str, dict[str, Any]] = field(default_factory=dict)
    priors: dict[str, dict[str, Any]] = field(default_factory=dict)
    posterior_updaters: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def register_evidence_likelihood(
        self,
        evidence_type: str,
        *,
        versioned_parameters: dict[str, Any],
        calibration_dataset_references: list[str],
        calibration_metrics: dict[str, Any],
        reliability_metrics: dict[str, Any],
        validation_metrics: dict[str, Any],
        acceptance_criteria: dict[str, Any],
    ) -> None:
        self.likelihoods[str(evidence_type)] = {
            "versioned_parameters": deepcopy(versioned_parameters),
            "calibration_dataset_references": list(calibration_dataset_references),
            "calibration_metrics": deepcopy(calibration_metrics),
            "reliability_metrics": deepcopy(reliability_metrics),
            "validation_metrics": deepcopy(validation_metrics),
            "acceptance_criteria": deepcopy(acceptance_criteria),
        }

    def register_prior_calibration(
        self, prior_id: str, *, parameters: dict[str, Any], calibration_reference: str
    ) -> None:
        self.priors[str(prior_id)] = {
            "parameters": deepcopy(parameters),
            "calibration_reference": str(calibration_reference),
        }

    def register_posterior_updater(self, updater_id: str, updater: Callable[..., Any]) -> None:
        self.posterior_updaters[str(updater_id)] = updater


def evaluate_bayesian_evidence(
    config: dict[str, Any] | None = None,
    *,
    registry: BayesianEvidenceRegistry | None = None,
) -> dict[str, Any]:
    """Return a gated interface state; never reinterpret heuristic confidence."""

    cfg = config if isinstance(config, dict) else {}
    feature_enabled = bool(cfg.get("enabled"))
    requirements = {
        "explicit_feature_configuration": feature_enabled,
        "validated_likelihood_models": bool(cfg.get("validated_likelihood_models")),
        "calibration_dataset_identifiers": bool(cfg.get("calibration_dataset_identifiers")),
        "calibration_metrics": bool(cfg.get("calibration_metrics")),
        "reliability_analysis": bool(cfg.get("reliability_analysis")),
        "versioned_model_parameters": bool(cfg.get("versioned_model_parameters")),
        "acceptance_test_approval": bool(cfg.get("acceptance_test_approval")),
        "registered_likelihoods": bool(registry and registry.likelihoods),
        "registered_posterior_updater": bool(registry and registry.posterior_updaters),
    }
    complete = all(requirements.values())
    reason = "posterior_update_engine_not_implemented" if complete else DEFERRED_REASON
    return {
        "status": "deferred",
        "active": False,
        "reason": reason,
        "calibration_reference": deepcopy(cfg.get("calibration_dataset_identifiers")),
        "validation_metrics": deepcopy(cfg.get("calibration_metrics")) if complete else None,
        "posterior": None,
        "requirements": requirements,
        "interfaces": {
            "evidence_likelihood_registration": True,
            "prior_calibration": True,
            "posterior_updates": True,
            "calibration_dataset_references": True,
            "reliability_metrics": True,
            "validation_metrics": True,
            "acceptance_criteria": True,
        },
        "safeguards": {
            "heuristic_confidence_converted_to_probability": False,
            "arbitrary_likelihood_ratios_used": False,
            "fixed_weight_posterior_generated": False,
        },
    }
