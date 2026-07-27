from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.engine.sii.common import finite_number, relationship_columns


REQUIRED_PRIOR_FIELDS = (
    "id",
    "name",
    "description",
    "domain",
    "equipment_types",
    "required_signals",
    "required_relationships",
    "required_operating_modes",
    "prerequisites",
    "expected_behavior",
    "validity_conditions",
    "confidence_modifier",
    "limitations",
    "reasoning_template",
)

SUPPORTED_OPERATORS = {
    "contains",
    "contains_all",
    "eq",
    "exists",
    "falsy",
    "gt",
    "gte",
    "in",
    "intersects",
    "lt",
    "lte",
    "not_contains",
    "not_eq",
    "not_in",
    "truthy",
}


def evaluate_physics_reasoning(
    *,
    priors: list[dict[str, Any]] | None,
    analytical_evidence: dict[str, Any],
    equipment_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate externally configured engineering expectations.

    The evaluator is deliberately domain-agnostic. It resolves configured
    evidence selectors and applies only the operator named in each condition.
    It does not alter, rank, or combine the source analytical evidence.
    """

    configured_priors = priors if isinstance(priors, list) else []
    evidence = analytical_evidence if isinstance(analytical_evidence, dict) else {}
    context = equipment_context if isinstance(equipment_context, dict) else {}
    available_signals = _available_signals(evidence)
    available_relationships = _available_relationships(evidence)
    available_modes = _available_modes(evidence.get("operating_modes"))

    evaluated: list[dict[str, Any]] = []
    limitations: list[str] = []
    trace: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, configured in enumerate(configured_priors):
        prior = deepcopy(configured) if isinstance(configured, dict) else {}
        prior_id = str(prior.get("id") or f"invalid_prior_{index + 1}")
        validation_reasons = _validate_prior(prior)
        if prior_id in seen_ids:
            validation_reasons.append("duplicate_prior_id")
        seen_ids.add(prior_id)
        if validation_reasons:
            reason = f"invalid_prior_configuration:{','.join(validation_reasons)}"
            result = _not_applicable_result(prior, prior_id, [reason])
            evaluated.append(result)
            limitations.append(f"{prior_id}: {reason}")
            trace.append(_prior_trace(result))
            continue

        applicability = _evaluate_applicability(
            prior,
            prior_id=prior_id,
            evidence=evidence,
            equipment_context=context,
            available_signals=available_signals,
            available_relationships=available_relationships,
            available_modes=available_modes,
        )
        if applicability["reasons"]:
            result = _not_applicable_result(
                prior,
                prior_id,
                applicability["reasons"],
                checks=applicability["checks"],
            )
            evaluated.append(result)
            trace.append(_prior_trace(result))
            continue

        expectation = _condition_group(prior["expected_behavior"])
        condition_results = [
            _evaluate_condition(
                condition,
                evidence,
                evidence_id=f"physics:{prior_id}:expectation:{condition_index + 1}",
            )
            for condition_index, condition in enumerate(expectation["conditions"])
        ]
        expectation_result = _combine_results(
            [item["satisfied"] for item in condition_results],
            expectation["logic"],
        )
        if expectation_result is True:
            status = "supported"
        elif expectation_result is False:
            status = "contradicted"
        else:
            status = "indeterminate"

        supporting = [
            *applicability["supporting_evidence"],
            *[
                _condition_evidence(item, "Supporting")
                for item in condition_results
                if item["satisfied"] is True
            ],
        ]
        contradictory = [
            _condition_evidence(item, "Contradictory")
            for item in condition_results
            if item["satisfied"] is False
        ]
        unavailable = [
            item
            for item in condition_results
            if item["satisfied"] is None
        ]
        prior_limitations = _string_list(prior.get("limitations"))
        if unavailable:
            prior_limitations.append(
                "One or more configured expected-behavior conditions could not be evaluated from available evidence."
            )
        result = {
            "id": prior_id,
            "name": str(prior["name"]),
            "domain": str(prior["domain"]),
            "status": status,
            "applicable": True,
            "supporting_evidence": supporting,
            "contradictory_evidence": contradictory,
            "limitations": _deduplicate(prior_limitations),
            "reasoning_trace": {
                "applicability": "applicable",
                "applicability_checks": applicability["checks"],
                "expected_behavior_logic": expectation["logic"],
                "condition_results": condition_results,
                "expectation_result": status,
                "rendered_reasoning": _render_reasoning(prior, status),
            },
            "confidence_modifier": deepcopy(prior["confidence_modifier"]),
            "confidence_modifier_applied": False,
            "statistical_evidence_overridden": False,
        }
        evaluated.append(result)
        limitations.extend(result["limitations"])
        trace.append(_prior_trace(result))

    applicable_ids = [item["id"] for item in evaluated if item["applicable"]]
    supporting_ids = [item["id"] for item in evaluated if item["status"] == "supported"]
    contradictory_ids = [item["id"] for item in evaluated if item["status"] == "contradicted"]
    ignored = [
        {
            "id": item["id"],
            "name": item["name"],
            "reason": item["reason"],
            "reasons": list(item["reasoning_trace"]["applicability_reasons"]),
        }
        for item in evaluated
        if not item["applicable"]
    ]
    indeterminate_ids = [item["id"] for item in evaluated if item["status"] == "indeterminate"]
    if not configured_priors:
        limitations.append("No engineering priors were configured; no engineering assumptions were forced.")
    if indeterminate_ids:
        limitations.append(
            "Applicable priors with unavailable expected-behavior evidence remained indeterminate."
        )

    status = "complete" if configured_priors and applicable_ids else "limited"
    reason = None
    if not configured_priors:
        reason = "no_configured_engineering_priors"
    elif not applicable_ids:
        reason = "no_applicable_engineering_priors"
    result = {
        "status": status,
        "active": True,
        "method": "declarative_engineering_prior_evaluation_v1",
        "evaluated_priors": evaluated,
        "applicable_priors": applicable_ids,
        "supporting_priors": supporting_ids,
        "contradictory_priors": contradictory_ids,
        "indeterminate_priors": indeterminate_ids,
        "ignored_priors": ignored,
        "limitations": _deduplicate(limitations),
        "reasoning_trace": trace,
        "available_evidence": {
            "signals": sorted(available_signals),
            "relationships": [
                {"left": left, "right": right}
                for left, right in sorted(available_relationships)
            ],
            "operating_modes": sorted(available_modes),
        },
        "principles": {
            "statistical_evidence_authoritative": True,
            "confidence_modifiers_are_non_probabilistic": True,
            "confidence_modifiers_are_not_aggregated": True,
            "diagnosis_performed": False,
            "recommendations_generated": False,
        },
    }
    if reason:
        result["reason"] = reason
    return result


def _validate_prior(prior: dict[str, Any]) -> list[str]:
    reasons = [f"missing_{field}" for field in REQUIRED_PRIOR_FIELDS if field not in prior]
    if reasons:
        return reasons
    if not str(prior.get("id") or "").strip():
        reasons.append("empty_id")
    if not str(prior.get("name") or "").strip():
        reasons.append("empty_name")
    for field in (
        "equipment_types",
        "required_signals",
        "required_relationships",
        "required_operating_modes",
        "prerequisites",
        "validity_conditions",
        "limitations",
    ):
        if not isinstance(prior.get(field), list):
            reasons.append(f"{field}_must_be_a_list")
    expectation = _condition_group(prior.get("expected_behavior"))
    if not expectation["conditions"]:
        reasons.append("expected_behavior_requires_conditions")
    for condition in [
        *(_condition_group(prior.get("prerequisites"))["conditions"]),
        *(_condition_group(prior.get("validity_conditions"))["conditions"]),
        *expectation["conditions"],
    ]:
        reasons.extend(_validate_condition(condition))
    if not isinstance(prior.get("reasoning_template"), (str, dict)):
        reasons.append("reasoning_template_must_be_text_or_mapping")
    return _deduplicate(reasons)


def _validate_condition(condition: Any) -> list[str]:
    if not isinstance(condition, dict):
        return ["condition_must_be_a_mapping"]
    if not str(condition.get("path") or "").strip():
        return ["condition_requires_path"]
    operator = str(condition.get("operator") or "eq").lower()
    if operator not in SUPPORTED_OPERATORS:
        return [f"unsupported_condition_operator:{operator}"]
    quantifier = str(condition.get("quantifier") or "any").lower()
    if quantifier not in {"all", "any", "none"}:
        return [f"unsupported_condition_quantifier:{quantifier}"]
    return []


def _evaluate_applicability(
    prior: dict[str, Any],
    *,
    prior_id: str,
    evidence: dict[str, Any],
    equipment_context: dict[str, Any],
    available_signals: set[str],
    available_relationships: set[tuple[str, str]],
    available_modes: set[str],
) -> dict[str, Any]:
    reasons: list[str] = []
    checks: list[dict[str, Any]] = []
    supporting_evidence: list[dict[str, Any]] = []
    expected_types = {_normalized(item) for item in prior["equipment_types"] if str(item).strip()}
    actual_types = _equipment_types(equipment_context)
    if expected_types and not actual_types:
        reasons.append("equipment_type_context_unavailable")
    elif expected_types and expected_types.isdisjoint(actual_types):
        reasons.append("equipment_type_not_applicable")
    if expected_types:
        satisfied = bool(actual_types and not expected_types.isdisjoint(actual_types))
        checks.append(
            {
                "check": "equipment_types",
                "configured": sorted(expected_types),
                "observed": sorted(actual_types),
                "satisfied": satisfied,
            }
        )
        if satisfied:
            supporting_evidence.append(
                _applicability_evidence(
                    evidence_id=f"physics:{prior_id}:applicability:equipment_types",
                    originating_module="equipment_context",
                    reasoning="Configured equipment type applicability was satisfied.",
                    expected=sorted(expected_types),
                    observed=sorted(actual_types),
                )
            )

    normalized_signals = {_normalized(item) for item in available_signals}
    required_signals = [
        signal
        for signal in (_signal_name(item) for item in prior["required_signals"])
        if signal
    ]
    missing_signals = [
        signal
        for signal in required_signals
        if _normalized(signal) not in normalized_signals
    ]
    if missing_signals:
        reasons.append(f"required_signals_unavailable:{','.join(missing_signals)}")
    if required_signals:
        satisfied = not missing_signals
        checks.append(
            {
                "check": "required_signals",
                "configured": required_signals,
                "observed": sorted(available_signals),
                "missing": missing_signals,
                "satisfied": satisfied,
            }
        )
        if satisfied:
            supporting_evidence.append(
                _applicability_evidence(
                    evidence_id=f"physics:{prior_id}:applicability:required_signals",
                    originating_module="canonical_evidence",
                    reasoning="All telemetry signals required by the configured prior were available.",
                    expected=required_signals,
                    observed=required_signals,
                )
            )

    missing_relationships = []
    configured_relationships: list[str] = []
    normalized_available = {
        tuple(sorted((_normalized(left), _normalized(right))))
        for left, right in available_relationships
    }
    for relationship in prior["required_relationships"]:
        pair = _relationship_requirement(relationship)
        configured_relationships.append(_relationship_label(relationship))
        if pair is None or tuple(sorted((_normalized(pair[0]), _normalized(pair[1])))) not in normalized_available:
            missing_relationships.append(_relationship_label(relationship))
    if missing_relationships:
        reasons.append(
            f"required_relationships_unavailable:{','.join(missing_relationships)}"
        )
    if configured_relationships:
        satisfied = not missing_relationships
        checks.append(
            {
                "check": "required_relationships",
                "configured": configured_relationships,
                "observed": [
                    f"{left}<->{right}" for left, right in sorted(available_relationships)
                ],
                "missing": missing_relationships,
                "satisfied": satisfied,
            }
        )
        if satisfied:
            supporting_evidence.append(
                _applicability_evidence(
                    evidence_id=f"physics:{prior_id}:applicability:required_relationships",
                    originating_module="relationship_analysis",
                    reasoning="All relationships required by the configured prior were available.",
                    expected=configured_relationships,
                    observed=configured_relationships,
                )
            )

    required_modes = {_normalized(item) for item in prior["required_operating_modes"] if str(item).strip()}
    if required_modes and not available_modes:
        reasons.append("required_operating_mode_context_unavailable")
    elif required_modes and required_modes.isdisjoint({_normalized(item) for item in available_modes}):
        reasons.append("required_operating_modes_not_observed")
    if required_modes:
        satisfied = bool(
            available_modes
            and not required_modes.isdisjoint({_normalized(item) for item in available_modes})
        )
        checks.append(
            {
                "check": "required_operating_modes",
                "configured": sorted(required_modes),
                "observed": sorted(available_modes),
                "satisfied": satisfied,
            }
        )
        if satisfied:
            supporting_evidence.append(
                _applicability_evidence(
                    evidence_id=f"physics:{prior_id}:applicability:required_operating_modes",
                    originating_module="operating_modes",
                    reasoning="A configured operating mode was observed.",
                    expected=sorted(required_modes),
                    observed=sorted(available_modes),
                )
            )

    for group_name in ("prerequisites", "validity_conditions"):
        group = _condition_group(prior[group_name])
        condition_results = [
            _evaluate_condition(
                condition,
                evidence,
                evidence_id=f"physics:{prior_id}:{group_name}:{index + 1}",
            )
            for index, condition in enumerate(group["conditions"])
        ]
        combined = _combine_results(
            [item["satisfied"] for item in condition_results],
            group["logic"],
        )
        checks.append(
            {
                "check": group_name,
                "logic": group["logic"],
                "condition_results": condition_results,
                "satisfied": combined,
            }
        )
        if combined is False:
            reasons.append(f"{group_name}_not_satisfied")
        elif combined is None and group["conditions"]:
            reasons.append(f"{group_name}_evidence_unavailable")
        if combined is True:
            supporting_evidence.extend(
                _condition_evidence(
                    item,
                    "Supporting",
                    evidence_role="applicability",
                )
                for item in condition_results
                if item["satisfied"] is True
            )
    return {
        "reasons": reasons,
        "checks": checks,
        "supporting_evidence": supporting_evidence,
    }


def _not_applicable_result(
    prior: dict[str, Any],
    prior_id: str,
    reasons: list[str],
    *,
    checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": prior_id,
        "name": str(prior.get("name") or prior_id),
        "domain": str(prior.get("domain") or "unavailable"),
        "status": "not_applicable",
        "applicable": False,
        "reason": reasons[0],
        "supporting_evidence": [],
        "contradictory_evidence": [],
        "limitations": _deduplicate(_string_list(prior.get("limitations"))),
        "reasoning_trace": {
            "applicability": "not_applicable",
            "applicability_reasons": list(reasons),
            "applicability_checks": deepcopy(checks or []),
            "expected_behavior_evaluated": False,
            "rendered_reasoning": None,
        },
        "confidence_modifier": deepcopy(prior.get("confidence_modifier")),
        "confidence_modifier_applied": False,
        "statistical_evidence_overridden": False,
    }


def _condition_group(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return {"logic": "all", "conditions": value}
    if isinstance(value, dict) and isinstance(value.get("conditions"), list):
        logic = str(value.get("logic") or "all").lower()
        return {
            "logic": logic if logic in {"all", "any"} else "all",
            "conditions": value["conditions"],
        }
    if isinstance(value, dict) and value.get("path"):
        return {"logic": "all", "conditions": [value]}
    return {"logic": "all", "conditions": []}


def _evaluate_condition(
    condition: dict[str, Any],
    evidence: dict[str, Any],
    *,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    source = str(condition.get("source") or "").strip()
    path = str(condition.get("path") or "").strip()
    source_payload = evidence.get(source) if source else evidence
    values = _resolve_values(source_payload, path)
    filtered = _filter_values(values, condition.get("where"))
    field = str(condition.get("field") or "").strip()
    observed = _resolve_values(filtered, field) if field else filtered
    operator = str(condition.get("operator") or "eq").lower()
    expected = deepcopy(condition.get("value"))
    quantifier = str(condition.get("quantifier") or "any").lower()
    satisfied = _apply_condition(observed, operator, expected, quantifier)
    source_reference = ".".join(part for part in (source, path, field) if part)
    return {
        "evidence_id": evidence_id,
        "source": source or "canonical_evidence",
        "source_reference": source_reference,
        "description": str(condition.get("description") or source_reference),
        "operator": operator,
        "quantifier": quantifier,
        "expected": expected,
        "observed_values": deepcopy(observed),
        "selector": deepcopy(condition),
        "satisfied": satisfied,
        "reason": (
            "condition_satisfied"
            if satisfied is True
            else "condition_not_satisfied"
            if satisfied is False
            else "condition_evidence_unavailable"
        ),
    }


def _resolve_values(value: Any, path: str) -> list[Any]:
    values = value if isinstance(value, list) else [value]
    if not path:
        return [item for item in values if item is not None]
    for part in path.split("."):
        next_values: list[Any] = []
        for item in values:
            if part == "*":
                if isinstance(item, list):
                    next_values.extend(item)
                elif isinstance(item, dict):
                    next_values.extend(item.values())
            elif isinstance(item, dict) and part in item:
                child = item[part]
                if isinstance(child, list):
                    next_values.extend(child)
                else:
                    next_values.append(child)
            elif isinstance(item, list) and part.isdigit() and int(part) < len(item):
                next_values.append(item[int(part)])
        values = next_values
        if not values:
            break
    return [item for item in values if item is not None]


def _filter_values(values: list[Any], where: Any) -> list[Any]:
    if not isinstance(where, dict) or not where:
        return values
    filtered: list[Any] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        matched = True
        for field, requirement in where.items():
            observed = _resolve_values(item, str(field))
            if isinstance(requirement, dict) and "operator" in requirement:
                operator = str(requirement.get("operator") or "eq").lower()
                expected = requirement.get("value")
                quantifier = str(requirement.get("quantifier") or "any").lower()
                matched = _apply_condition(observed, operator, expected, quantifier) is True
            else:
                matched = _apply_condition(observed, "eq", requirement, "any") is True
            if not matched:
                break
        if matched:
            filtered.append(item)
    return filtered


def _apply_condition(
    observed_values: list[Any],
    operator: str,
    expected: Any,
    quantifier: str,
) -> bool | None:
    if operator == "exists":
        return bool(observed_values)
    if not observed_values:
        return None
    comparisons = [_compare(value, operator, expected) for value in observed_values]
    usable = [item for item in comparisons if item is not None]
    if not usable:
        return None
    if quantifier == "all":
        return len(usable) == len(comparisons) and all(usable)
    if quantifier == "none":
        return not any(usable)
    return any(usable)


def _compare(observed: Any, operator: str, expected: Any) -> bool | None:
    if operator == "truthy":
        return bool(observed)
    if operator == "falsy":
        return not bool(observed)
    if operator in {"eq", "not_eq"}:
        equal = _comparable(observed) == _comparable(expected)
        return equal if operator == "eq" else not equal
    if operator in {"in", "not_in"}:
        expected_values = expected if isinstance(expected, (list, tuple, set)) else [expected]
        included = any(_comparable(observed) == _comparable(item) for item in expected_values)
        return included if operator == "in" else not included
    if operator in {"contains", "not_contains", "contains_all", "intersects"}:
        expected_items = _contained_items(expected)
        if isinstance(observed, str):
            observed_text = _normalized(observed)
            if operator == "contains":
                matched = any(item in observed_text for item in expected_items)
            elif operator == "not_contains":
                matched = all(item not in observed_text for item in expected_items)
            elif operator == "contains_all":
                matched = all(item in observed_text for item in expected_items)
            else:
                matched = any(item in observed_text for item in expected_items)
        else:
            observed_items = _contained_items(observed)
            if operator == "contains":
                matched = any(item in observed_items for item in expected_items)
            elif operator == "not_contains":
                matched = all(item not in observed_items for item in expected_items)
            elif operator == "contains_all":
                matched = all(item in observed_items for item in expected_items)
            else:
                matched = bool(set(observed_items) & set(expected_items))
        return matched
    if operator in {"gt", "gte", "lt", "lte"}:
        left = finite_number(observed)
        right = finite_number(expected)
        if left is None or right is None:
            return None
        if operator == "gt":
            return left > right
        if operator == "gte":
            return left >= right
        if operator == "lt":
            return left < right
        return left <= right
    return None


def _condition_evidence(
    result: dict[str, Any],
    classification: str,
    *,
    evidence_role: str = "expected_behavior",
) -> dict[str, Any]:
    return {
        "evidence_id": result["evidence_id"],
        "classification": classification,
        "evidence_role": evidence_role,
        "originating_module": result["source"],
        "source_reference": result["source_reference"],
        "reasoning": result["description"],
        "operator": result["operator"],
        "quantifier": result["quantifier"],
        "expected": deepcopy(result["expected"]),
        "observed_values": deepcopy(result["observed_values"]),
        "selector": deepcopy(result["selector"]),
        "limitations": [],
        "uncertainty": None,
    }


def _applicability_evidence(
    *,
    evidence_id: str,
    originating_module: str,
    reasoning: str,
    expected: Any,
    observed: Any,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "classification": "Supporting",
        "evidence_role": "applicability",
        "originating_module": originating_module,
        "source_reference": "applicability",
        "reasoning": reasoning,
        "operator": "applicability_match",
        "quantifier": "all",
        "expected": deepcopy(expected),
        "observed_values": deepcopy(observed),
        "limitations": [],
        "uncertainty": None,
    }


def _combine_results(results: list[bool | None], logic: str) -> bool | None:
    if not results:
        return None
    if logic == "any":
        if any(item is True for item in results):
            return True
        if all(item is False for item in results):
            return False
        return None
    if any(item is False for item in results):
        return False
    if all(item is True for item in results):
        return True
    return None


def _render_reasoning(prior: dict[str, Any], status: str) -> str:
    template = prior.get("reasoning_template")
    if isinstance(template, dict):
        aliases = {
            "supported": ("supported", "expectation_satisfied"),
            "contradicted": ("contradicted", "expectation_not_satisfied"),
            "indeterminate": ("indeterminate", "insufficient_evidence"),
        }
        selected = next(
            (template[key] for key in aliases[status] if isinstance(template.get(key), str)),
            None,
        )
        if selected is None:
            selected = template.get("default")
        text = str(selected or "")
    else:
        text = str(template or "")
    replacements = {
        "prior_id": str(prior.get("id") or ""),
        "prior_name": str(prior.get("name") or ""),
        "status": status,
        "domain": str(prior.get("domain") or ""),
    }
    for key, value in replacements.items():
        text = text.replace("{" + key + "}", value)
    return text


def _available_signals(evidence: dict[str, Any]) -> set[str]:
    signals: set[str] = set()
    data_conditions = evidence.get("data_quality")
    if isinstance(data_conditions, dict):
        for column in data_conditions.get("numeric_columns", []):
            if str(column).strip():
                signals.add(str(column))
    drift = evidence.get("signal_drift")
    if isinstance(drift, dict):
        for item in drift.get("column_drift", []):
            if isinstance(item, dict) and item.get("column"):
                signals.add(str(item["column"]))
    health = evidence.get("sensor_health")
    if isinstance(health, dict):
        for item in health.get("signals", []):
            if not isinstance(item, dict):
                continue
            signal = item.get("signal") or item.get("column") or item.get("name")
            if signal:
                signals.add(str(signal))
    for module in ("relationship_analysis", "relationship_graph"):
        payload = evidence.get(module)
        if not isinstance(payload, dict):
            continue
        graph = payload.get("relationship_graph") if module == "relationship_analysis" else payload
        if isinstance(graph, dict):
            for node in graph.get("nodes", []):
                if isinstance(node, dict):
                    signal = node.get("source_column") or str(node.get("id") or "").removeprefix("metric:")
                    if signal:
                        signals.add(str(signal))
            for edge in graph.get("edges", []):
                if isinstance(edge, dict):
                    signals.update(relationship_columns(edge))
    return signals


def _available_relationships(evidence: dict[str, Any]) -> set[tuple[str, str]]:
    relationships: set[tuple[str, str]] = set()
    for module in ("relationship_analysis", "relationship_graph"):
        payload = evidence.get(module)
        if not isinstance(payload, dict):
            continue
        graph = payload.get("relationship_graph") if module == "relationship_analysis" else payload
        collections: list[Any] = []
        if isinstance(graph, dict):
            collections.extend((graph.get("edges"), graph.get("changed_edges")))
        collections.extend((payload.get("top_relationship_changes"), payload.get("baseline_relationships")))
        for items in collections:
            if not isinstance(items, list):
                continue
            for edge in items:
                if not isinstance(edge, dict):
                    continue
                columns = relationship_columns(edge)
                if len(columns) == 2:
                    relationships.add(tuple(sorted((columns[0], columns[1]))))
    return relationships


def _available_modes(payload: Any) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    modes: set[str] = set()
    for field in ("baseline_mode", "baseline_mode_label", "recent_mode", "recent_mode_label", "match"):
        value = payload.get(field)
        if value and str(value) != "unavailable":
            modes.add(str(value))
    features = payload.get("features")
    if isinstance(features, dict):
        for period in ("baseline", "recent"):
            period_features = features.get(period)
            if isinstance(period_features, dict):
                modes.update(str(value) for value in period_features.values() if value is not None)
    return modes


def _equipment_types(context: dict[str, Any]) -> set[str]:
    values: list[Any] = []
    for field in ("equipment_type", "type"):
        if context.get(field):
            values.append(context[field])
    if isinstance(context.get("equipment_types"), list):
        values.extend(context["equipment_types"])
    return {_normalized(value) for value in values if str(value).strip()}


def _signal_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("signal") or value.get("name") or "")
    return str(value)


def _relationship_requirement(value: Any) -> tuple[str, str] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return str(value[0]), str(value[1])
    if isinstance(value, dict):
        pair = value.get("signals")
        if isinstance(pair, list) and len(pair) == 2:
            return str(pair[0]), str(pair[1])
        left = value.get("left") or value.get("source")
        right = value.get("right") or value.get("target")
        if left and right:
            return str(left).removeprefix("metric:"), str(right).removeprefix("metric:")
    if isinstance(value, str) and "<->" in value:
        parts = [part.strip() for part in value.split("<->", 1)]
        if len(parts) == 2 and all(parts):
            return parts[0], parts[1]
    return None


def _relationship_label(value: Any) -> str:
    pair = _relationship_requirement(value)
    return f"{pair[0]}<->{pair[1]}" if pair else str(value)


def _prior_trace(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "prior_id": result["id"],
        "status": result["status"],
        "applicable": result["applicable"],
        "reason": result.get("reason"),
        "supporting_evidence_ids": [
            item["evidence_id"] for item in result["supporting_evidence"]
        ],
        "contradictory_evidence_ids": [
            item["evidence_id"] for item in result["contradictory_evidence"]
        ],
        "statistical_evidence_overridden": False,
    }


def _contained_items(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_normalized(item) for item in value]
    return [_normalized(value)]


def _comparable(value: Any) -> Any:
    if isinstance(value, str):
        return _normalized(value)
    return value


def _normalized(value: Any) -> str:
    return str(value).strip().casefold()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in values if str(item).strip()))
