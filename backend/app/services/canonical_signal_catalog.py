"""Versioned, source-neutral canonical signal concepts shipped by Neraium.

This catalog is product taxonomy, not source discovery. External tags only gain
one of these identities through an explicit, authorized signal mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


CANONICAL_SIGNAL_TAXONOMY_VERSION = 1


@dataclass(frozen=True, slots=True)
class CanonicalSignalConceptDefinition:
    concept_id: str
    canonical_name: str
    display_name: str
    physical_dimension: str
    canonical_unit: str
    description: str
    taxonomy_version: int = CANONICAL_SIGNAL_TAXONOMY_VERSION


CANONICAL_SIGNAL_CONCEPTS_V1 = (
    CanonicalSignalConceptDefinition(
        concept_id="4385267d-f840-59c4-ba65-06a6726e3189",
        canonical_name="electrical.active_power",
        display_name="Active power",
        physical_dimension="power",
        canonical_unit="kW",
        description="Rate of real electrical energy transfer.",
    ),
    CanonicalSignalConceptDefinition(
        concept_id="b7f427ba-b036-539e-a527-15ed76bf3b35",
        canonical_name="temperature",
        display_name="Temperature",
        physical_dimension="temperature",
        canonical_unit="degC",
        description="Measured thermodynamic temperature.",
    ),
    CanonicalSignalConceptDefinition(
        concept_id="9fa5d454-6b13-5f59-99d1-7f6fb0a3e07f",
        canonical_name="pressure",
        display_name="Pressure",
        physical_dimension="pressure",
        canonical_unit="kPa",
        description="Measured gauge or differential pressure as mapped context specifies.",
    ),
    CanonicalSignalConceptDefinition(
        concept_id="a19db5be-5ca1-5373-a9e4-6957e9f54c43",
        canonical_name="volumetric_flow",
        display_name="Volumetric flow",
        physical_dimension="flow",
        canonical_unit="L/s",
        description="Volume of fluid passing a point per unit time.",
    ),
    CanonicalSignalConceptDefinition(
        concept_id="ba959381-2fc2-556f-aa57-279a9f97d3b8",
        canonical_name="fraction",
        display_name="Fraction",
        physical_dimension="fraction",
        canonical_unit="fraction",
        description="Dimensionless ratio represented canonically from zero to one.",
    ),
)

CANONICAL_SIGNAL_CONCEPTS_BY_ID: Mapping[str, CanonicalSignalConceptDefinition] = (
    MappingProxyType({item.concept_id: item for item in CANONICAL_SIGNAL_CONCEPTS_V1})
)


__all__ = [
    "CANONICAL_SIGNAL_CONCEPTS_BY_ID",
    "CANONICAL_SIGNAL_CONCEPTS_V1",
    "CANONICAL_SIGNAL_TAXONOMY_VERSION",
    "CanonicalSignalConceptDefinition",
]
