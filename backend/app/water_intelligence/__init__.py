"""Water Intelligence domain layer.

This package interprets generic SII relationship findings with water-system
meaning. It intentionally does not learn relationships or detect drift; those
remain owned by the SII engine.
"""

from app.water_intelligence.interpreter import (
    WaterIntelligenceContext,
    interpret_water_intelligence,
)
from app.water_intelligence.models import (
    CONFIDENCE_DIMENSIONS,
    GRAPH_TRUST_PROPOSED,
    GRAPH_TRUST_SPECULATIVE,
    GRAPH_TRUST_TRUSTED,
    HYPOTHESIS_OBSERVED,
    HYPOTHESIS_OPERATOR_CONFIRMED,
    HYPOTHESIS_RESOLVED,
    HYPOTHESIS_SUPPORTED,
    HYPOTHESIS_SUSPECTED,
)

__all__ = [
    "CONFIDENCE_DIMENSIONS",
    "GRAPH_TRUST_PROPOSED",
    "GRAPH_TRUST_SPECULATIVE",
    "GRAPH_TRUST_TRUSTED",
    "HYPOTHESIS_OBSERVED",
    "HYPOTHESIS_OPERATOR_CONFIRMED",
    "HYPOTHESIS_RESOLVED",
    "HYPOTHESIS_SUPPORTED",
    "HYPOTHESIS_SUSPECTED",
    "WaterIntelligenceContext",
    "interpret_water_intelligence",
]
