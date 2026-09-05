"""Current product views omit retired attribution conclusions.

Historical blobs and parser schemas remain readable. This projection never changes
relationship measurements or canonical consequence/provenance facts.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_ATOMIC_TYPES = frozenset({str, int, float, bool, type(None)})

_RETIRED = frozenset({
    "cause", "causes", "likelycause", "likelycauses", "probablecause",
    "suspectedcause", "rootcause", "rootcauseconclusion", "rootcauseconclusions",
    "diagnosis", "diagnosticconclusion", "automatedcorrectiveaction",
    "causeestablished", "causeconfirmed", "causeattribution", "attributionstatus",
    "potentialoperationalcauses", "possibleoperationalcauses", "possibleoperationalcausessummary",
    "possibleexplanations", "alternativeexplanations",
    "whyneraiumthinksithappened", "whyneraiumthinks",
    "likelydriver", "primarydriver", "primarydrivers", "driverattribution",
    "counterfactualdriverranking",
})
# Immutable measurements and human-authored history are not analytical conclusions.
_PRESERVED = frozenset({
    "measurable_consequence", "provenance", "source_tag_ids", "source_relationship_ids",
    "normalized_telemetry", "telemetry_signal_catalog", "telemetry_signals",
    "source_rows", "observations", "rows",
    "operator_feedback_history", "field_reports", "feedback", "events",
})


def product_evidence(value: Any) -> Any:
    """Copy a product payload, excluding obsolete conclusion fields at every depth."""
    # JSON scalars are immutable; deepcopy adds overhead for every measured value.
    if type(value) in _ATOMIC_TYPES:
        return value
    if isinstance(value, dict):
        return {
            key: deepcopy(item) if key in _PRESERVED else product_evidence(item)
            for key, item in value.items()
            if str(key).replace("_", "").lower() not in _RETIRED
        }
    if isinstance(value, list):
        return [product_evidence(item) for item in value]
    return deepcopy(value)
