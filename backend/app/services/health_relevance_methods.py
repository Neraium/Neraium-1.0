from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from types import MappingProxyType
from typing import Any, Mapping, Sequence


BAYESIAN_METHOD_ID = "bayesian_shrinkage_v1"
INFORMATION_METHOD_ID = "outcome_conditioned_information_v1"

_PRIMARY_AUTHORITY_TIERS = frozenset({"A", "B"})
_KNOWN_AUTHORITY_TIERS = frozenset({"A", "B", "C", "D"})
_DIRECTIONAL_TREATMENTS = frozenset({"positive", "negative"})
_INFORMATION_CELLS = frozenset({"a", "b", "c", "d"})


class MethodInputError(ValueError):
    """Raised when a frozen method manifest is incomplete or malformed."""


def _manifest_identity(frozen_manifest: Mapping[str, Any]) -> tuple[str, str | None]:
    manifest_hash = str(frozen_manifest.get("input_manifest_hash") or "").strip()
    if not manifest_hash:
        raise MethodInputError("input_manifest_hash is required")
    snapshot_id = frozen_manifest.get("input_snapshot_id")
    return manifest_hash, str(snapshot_id) if snapshot_id is not None else None


def _manifest_rows(frozen_manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = frozen_manifest.get("contributions")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise MethodInputError("contributions must be a sequence of mappings")
    if not all(isinstance(row, Mapping) for row in rows):
        raise MethodInputError("every contribution must be a mapping")
    return list(rows)


def _normalized_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _authority_tier(row: Mapping[str, Any]) -> str:
    return str(row.get("authority_tier") or "").strip().upper()


def _contribution_id(row: Mapping[str, Any], index: int) -> str:
    explicit = row.get("contribution_id") or row.get("observation_id")
    if explicit is not None and str(explicit).strip():
        return str(explicit)
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    return f"manifest-row-{index}-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _provenance_categories(row: Mapping[str, Any]) -> list[str]:
    value = row.get("provenance_categories")
    if value is None:
        value = row.get("provenance_categories_json")
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = [value]
        value = decoded
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return sorted({str(item) for item in value if str(item).strip()})


def _eligible(row: Mapping[str, Any]) -> bool:
    return row.get("eligible", True) is True and _normalized_token(row.get("treatment")) != "excluded"


def _evidence_treatment(row: Mapping[str, Any]) -> str:
    value = row.get("evidence_treatment", row.get("treatment"))
    return _normalized_token(value)


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    max_iterations = 200
    epsilon = 3e-14
    minimum = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - (qab * x / qap)
    if abs(d) < minimum:
        d = minimum
    d = 1.0 / d
    result = d
    for iteration in range(1, max_iterations + 1):
        even = 2 * iteration
        coefficient = iteration * (b - iteration) * x / ((qam + even) * (a + even))
        d = 1.0 + coefficient * d
        if abs(d) < minimum:
            d = minimum
        c = 1.0 + coefficient / c
        if abs(c) < minimum:
            c = minimum
        d = 1.0 / d
        result *= d * c

        coefficient = -(a + iteration) * (qab + iteration) * x / (
            (a + even) * (qap + even)
        )
        d = 1.0 + coefficient * d
        if abs(d) < minimum:
            d = minimum
        c = 1.0 + coefficient / c
        if abs(c) < minimum:
            c = minimum
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= epsilon:
            return result
    raise ArithmeticError("beta continued fraction did not converge")


def _regularized_beta(x: float, alpha: float, beta: float) -> float:
    if alpha <= 0.0 or beta <= 0.0:
        raise ValueError("beta parameters must be positive")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    factor = math.exp(
        math.lgamma(alpha + beta)
        - math.lgamma(alpha)
        - math.lgamma(beta)
        + alpha * math.log(x)
        + beta * math.log1p(-x)
    )
    if x < (alpha + 1.0) / (alpha + beta + 2.0):
        return factor * _beta_continued_fraction(alpha, beta, x) / alpha
    return 1.0 - factor * _beta_continued_fraction(beta, alpha, 1.0 - x) / beta


def _beta_quantile(probability: float, alpha: float, beta: float) -> float:
    if probability <= 0.0:
        return 0.0
    if probability >= 1.0:
        return 1.0
    lower = 0.0
    upper = 1.0
    for _ in range(80):
        midpoint = (lower + upper) / 2.0
        if _regularized_beta(midpoint, alpha, beta) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _posterior_view(positive: int, negative: int, *, prior_alpha: float, prior_beta: float) -> dict[str, Any]:
    alpha = prior_alpha + positive
    beta = prior_beta + negative
    lower = _beta_quantile(0.05, alpha, beta)
    upper = _beta_quantile(0.95, alpha, beta)
    return {
        "counts": {"positive": positive, "negative": negative, "directional": positive + negative},
        "prior": {"alpha": prior_alpha, "beta": prior_beta},
        "posterior": {
            "alpha": alpha,
            "beta": beta,
            "mean": alpha / (alpha + beta),
            "median": _beta_quantile(0.5, alpha, beta),
            "credible_interval_90": {"lower": lower, "upper": upper},
            "credible_mass": 0.9,
        },
    }


def _prior_sensitivity(positive: int, negative: int) -> list[dict[str, Any]]:
    results = []
    for label, alpha, beta in (
        ("uniform_beta_1_1", 1.0, 1.0),
        ("jeffreys_beta_0_5_0_5", 0.5, 0.5),
    ):
        view = _posterior_view(positive, negative, prior_alpha=alpha, prior_beta=beta)
        results.append({"label": label, **view["posterior"]})
    return results


class BayesianShrinkageMethod:
    """Pure Beta(2,2) evidence updater with authority-separated views."""

    method_id = BAYESIAN_METHOD_ID

    def evaluate(
        self,
        frozen_manifest: Mapping[str, Any],
        method_config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        manifest_hash, snapshot_id = _manifest_identity(frozen_manifest)
        rows = _manifest_rows(frozen_manifest)
        primary = Counter[str]()
        supplemental = Counter[str]()
        tier_counts = Counter[str]()
        treatments: list[dict[str, Any]] = []

        for index, row in enumerate(rows):
            contribution_id = _contribution_id(row, index)
            authority_tier = _authority_tier(row)
            treatment = _evidence_treatment(row)
            included = _eligible(row) and treatment in _DIRECTIONAL_TREATMENTS
            reason = None
            if not _eligible(row):
                included = False
                reason = str(row.get("exclusion_reason") or "upstream_ineligible")
            elif treatment not in _DIRECTIONAL_TREATMENTS:
                included = False
                reason = "not_directional_for_bayesian_update"
            elif authority_tier not in _KNOWN_AUTHORITY_TIERS:
                included = False
                reason = "authority_tier_incomplete"

            primary_included = included and authority_tier in _PRIMARY_AUTHORITY_TIERS
            if included:
                supplemental[treatment] += 1
                tier_counts[authority_tier] += 1
            if primary_included:
                primary[treatment] += 1
            treatments.append(
                {
                    "contribution_id": contribution_id,
                    "authority_tier": authority_tier or None,
                    "provenance_categories": _provenance_categories(row),
                    "evidence_treatment": treatment or None,
                    "included_in_primary": primary_included,
                    "included_in_supplemental": included,
                    "exclusion_reason": reason,
                }
            )

        primary_view = _posterior_view(
            primary["positive"], primary["negative"], prior_alpha=2.0, prior_beta=2.0
        )
        supplemental_view = _posterior_view(
            supplemental["positive"], supplemental["negative"], prior_alpha=2.0, prior_beta=2.0
        )
        primary_view["authority_tiers"] = ["A", "B"]
        primary_view["prior_sensitivity"] = _prior_sensitivity(
            primary["positive"], primary["negative"]
        )
        supplemental_view["authority_tiers"] = ["A", "B", "C", "D"]

        ignored_config = sorted((method_config or {}).keys())
        return {
            "method_id": self.method_id,
            "input_manifest_hash": manifest_hash,
            "input_snapshot_id": snapshot_id,
            "components": {
                "primary_view": primary_view,
                "supplemental_view": supplemental_view,
                "authority_tier_counts": {tier: tier_counts[tier] for tier in ("A", "B", "C", "D")},
                "contribution_counts": {
                    "manifest": len(rows),
                    "primary_directional": sum(primary.values()),
                    "supplemental_directional": sum(supplemental.values()),
                    "excluded_or_non_directional": len(rows) - sum(supplemental.values()),
                },
                "experimental_config": {
                    "prior": "Beta(2,2)",
                    "credible_mass": 0.9,
                    "ignored_unapproved_config_keys": ignored_config,
                },
            },
            "uncertainty": {
                "primary_credible_interval_90": primary_view["posterior"]["credible_interval_90"],
                "supplemental_credible_interval_90": supplemental_view["posterior"]["credible_interval_90"],
                "sparse_data_shrinkage_target": 0.5,
                "field_calibrated": False,
            },
            "contributions": treatments,
        }


def _information_cell(row: Mapping[str, Any]) -> str | None:
    explicit = _normalized_token(row.get("information_cell"))
    if explicit in _INFORMATION_CELLS:
        return explicit
    outcome_class = _normalized_token(row.get("outcome_class"))
    subject_state = _normalized_token(row.get("subject_state"))
    if subject_state in {"active_changed", "active"}:
        subject_active = True
    elif subject_state in {
        "not_active_changed",
        "present_aligned",
        "absent_evaluable",
        "not_active",
    }:
        subject_active = False
    else:
        return None
    if outcome_class == "validated_health_outcome":
        return "a" if subject_active else "c"
    if outcome_class in {"explicit_comparison", "stable_negative_comparison"}:
        return "b" if subject_active else "d"
    return None


def _mutual_information(table: Mapping[str, float]) -> tuple[float, float, float]:
    a = float(table["a"])
    b = float(table["b"])
    c = float(table["c"])
    d = float(table["d"])
    total = a + b + c + d
    if total <= 0.0:
        return 0.0, 0.0, 0.0
    subject_totals = (a + b, c + d)
    outcome_totals = (a + c, b + d)
    information = 0.0
    for value, subject_total, outcome_total in (
        (a, subject_totals[0], outcome_totals[0]),
        (b, subject_totals[0], outcome_totals[1]),
        (c, subject_totals[1], outcome_totals[0]),
        (d, subject_totals[1], outcome_totals[1]),
    ):
        if value > 0.0 and subject_total > 0.0 and outcome_total > 0.0:
            probability = value / total
            information += probability * math.log2((value * total) / (subject_total * outcome_total))
    outcome_entropy = 0.0
    for outcome_total in outcome_totals:
        if outcome_total > 0.0:
            probability = outcome_total / total
            outcome_entropy -= probability * math.log2(probability)
    normalized = information / outcome_entropy if outcome_entropy > 0.0 else 0.0
    return information, outcome_entropy, max(0.0, min(1.0, normalized))


def _percentile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(probability * len(sorted_values)))
    return float(sorted_values[min(rank - 1, len(sorted_values) - 1)])


def _permutation_reference(
    observations: Sequence[tuple[bool, bool]],
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    if not observations:
        return {
            "seed": seed,
            "iterations": iterations,
            "algorithm": "fixed_seed_outcome_label_permutation_v1",
            "null_median": 0.0,
            "null_percentile_95": 0.0,
            "null_mean": 0.0,
            "null_min": 0.0,
            "null_max": 0.0,
        }
    subjects = [subject_active for subject_active, _ in observations]
    original_outcomes = [health_outcome for _, health_outcome in observations]
    generator = random.Random(seed)
    null_values: list[float] = []
    for _ in range(iterations):
        outcomes = original_outcomes.copy()
        generator.shuffle(outcomes)
        table = {"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.5}
        for subject_active, health_outcome in zip(subjects, outcomes):
            cell = "a" if subject_active and health_outcome else None
            if cell is None:
                cell = "b" if subject_active else "c" if health_outcome else "d"
            table[cell] += 1.0
        null_values.append(_mutual_information(table)[2])
    null_values.sort()
    return {
        "seed": seed,
        "iterations": iterations,
        "algorithm": "fixed_seed_outcome_label_permutation_v1",
        "null_median": _percentile(null_values, 0.5),
        "null_percentile_95": _percentile(null_values, 0.95),
        "null_mean": sum(null_values) / len(null_values),
        "null_min": null_values[0],
        "null_max": null_values[-1],
    }


def _information_view(
    observations: Sequence[tuple[str, str]],
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    raw = {cell: 0 for cell in ("a", "b", "c", "d")}
    for _, cell in observations:
        raw[cell] += 1
    smoothed = {cell: count + 0.5 for cell, count in raw.items()}
    raw_information, raw_entropy, raw_normalized = _mutual_information(raw)
    smoothed_information, smoothed_entropy, observed_normalized = _mutual_information(smoothed)
    binary_observations = [
        (cell in {"a", "b"}, cell in {"a", "c"}) for _, cell in observations
    ]
    permutation = _permutation_reference(binary_observations, seed=seed, iterations=iterations)
    adjusted = max(0.0, observed_normalized - permutation["null_median"])
    return {
        "contingency_table": raw,
        "smoothed_table": smoothed,
        "cell_labels": {
            "a": "subject_active_changed__validated_health_outcome",
            "b": "subject_active_changed__explicit_comparison",
            "c": "subject_not_active_changed__validated_health_outcome",
            "d": "subject_not_active_changed__explicit_comparison",
        },
        "jeffreys_smoothing_per_cell": 0.5,
        "raw_mutual_information_bits": raw_information,
        "smoothed_mutual_information_bits": smoothed_information,
        "raw_outcome_entropy_bits": raw_entropy,
        "smoothed_outcome_entropy_bits": smoothed_entropy,
        "raw_normalized_information": raw_normalized,
        "observed_normalized_information": observed_normalized,
        "adjusted_normalized_information": adjusted,
        "effective_sample_size": len(observations),
        "permutation_reference": permutation,
    }


class OutcomeConditionedInformationMethod:
    """Pure outcome-conditioned information evaluator over inspectable 2x2 cells."""

    method_id = INFORMATION_METHOD_ID
    default_permutation_seed = 918_273
    default_permutation_iterations = 1_000

    def evaluate(
        self,
        frozen_manifest: Mapping[str, Any],
        method_config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        manifest_hash, snapshot_id = _manifest_identity(frozen_manifest)
        rows = _manifest_rows(frozen_manifest)
        config = dict(method_config or {})
        seed = int(config.pop("permutation_seed", self.default_permutation_seed))
        iterations = int(config.pop("permutation_iterations", self.default_permutation_iterations))
        if iterations < 100 or iterations > 100_000:
            raise MethodInputError("permutation_iterations must be between 100 and 100000")

        primary: list[tuple[str, str]] = []
        supplemental: list[tuple[str, str]] = []
        tier_counts = Counter[str]()
        treatments: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            contribution_id = _contribution_id(row, index)
            authority_tier = _authority_tier(row)
            cell = _information_cell(row)
            included = _eligible(row) and cell is not None and authority_tier in _KNOWN_AUTHORITY_TIERS
            reason = None
            if not _eligible(row):
                reason = str(row.get("exclusion_reason") or "upstream_ineligible")
            elif cell is None:
                reason = "information_cell_incomplete"
            elif authority_tier not in _KNOWN_AUTHORITY_TIERS:
                reason = "authority_tier_incomplete"
            primary_included = included and authority_tier in _PRIMARY_AUTHORITY_TIERS
            if included and cell is not None:
                supplemental.append((contribution_id, cell))
                tier_counts[authority_tier] += 1
            if primary_included and cell is not None:
                primary.append((contribution_id, cell))
            treatments.append(
                {
                    "contribution_id": contribution_id,
                    "authority_tier": authority_tier or None,
                    "provenance_categories": _provenance_categories(row),
                    "information_cell": cell,
                    "included_in_primary": primary_included,
                    "included_in_supplemental": included,
                    "exclusion_reason": reason,
                }
            )

        primary.sort()
        supplemental.sort()
        primary_view = _information_view(primary, seed=seed, iterations=iterations)
        supplemental_view = _information_view(supplemental, seed=seed, iterations=iterations)
        primary_view["authority_tiers"] = ["A", "B"]
        supplemental_view["authority_tiers"] = ["A", "B", "C", "D"]

        return {
            "method_id": self.method_id,
            "input_manifest_hash": manifest_hash,
            "input_snapshot_id": snapshot_id,
            "components": {
                "primary_view": primary_view,
                "supplemental_view": supplemental_view,
                "authority_tier_counts": {tier: tier_counts[tier] for tier in ("A", "B", "C", "D")},
                "contribution_counts": {
                    "manifest": len(rows),
                    "primary_evaluable": len(primary),
                    "supplemental_evaluable": len(supplemental),
                    "excluded_or_not_evaluable": len(rows) - len(supplemental),
                },
                "experimental_config": {
                    "jeffreys_smoothing_per_cell": 0.5,
                    "permutation_seed": seed,
                    "permutation_iterations": iterations,
                    "unused_config_keys": sorted(config),
                },
            },
            "uncertainty": {
                "primary_permutation_reference": primary_view["permutation_reference"],
                "supplemental_permutation_reference": supplemental_view["permutation_reference"],
                "field_calibrated": False,
            },
            "contributions": treatments,
        }


METHOD_REGISTRY: Mapping[str, BayesianShrinkageMethod | OutcomeConditionedInformationMethod] = (
    MappingProxyType(
        {
            BAYESIAN_METHOD_ID: BayesianShrinkageMethod(),
            INFORMATION_METHOD_ID: OutcomeConditionedInformationMethod(),
        }
    )
)


def evaluate_health_relevance_method(
    method_id: str,
    frozen_manifest: Mapping[str, Any],
    method_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one of the two approved methods without persistence access."""

    method = METHOD_REGISTRY.get(method_id)
    if method is None:
        raise KeyError(f"unsupported Health Relevance method: {method_id}")
    return method.evaluate(frozen_manifest, method_config)


__all__ = [
    "BAYESIAN_METHOD_ID",
    "INFORMATION_METHOD_ID",
    "METHOD_REGISTRY",
    "BayesianShrinkageMethod",
    "MethodInputError",
    "OutcomeConditionedInformationMethod",
    "evaluate_health_relevance_method",
]
