"""Evidence-first primitives shared by Neraium applications."""

from .contracts import (
    ConfidenceDimension,
    ConfidenceLevel,
    DataQuality,
    EvidenceItem,
    EvidencePackage,
    HistoricalComparison,
    Limitation,
    PackageProvenance,
    SimilarityComponent,
    StrictModel,
    Unknown,
)
from .evidence import EvidencePackageAssembler, assess_evidence_support
from .memory import (
    BehavioralMemoryRepository,
    FeatureSpec,
    MemoryMatch,
    MemoryQuery,
    MemoryRecord,
    SimilarityResult,
    WeightedSimilarityEngine,
)
from .store import JsonlEvidencePackageStore

__all__ = [
    "BehavioralMemoryRepository",
    "ConfidenceDimension",
    "ConfidenceLevel",
    "DataQuality",
    "EvidenceItem",
    "EvidencePackage",
    "EvidencePackageAssembler",
    "FeatureSpec",
    "HistoricalComparison",
    "JsonlEvidencePackageStore",
    "Limitation",
    "MemoryMatch",
    "MemoryQuery",
    "MemoryRecord",
    "PackageProvenance",
    "SimilarityComponent",
    "SimilarityResult",
    "StrictModel",
    "Unknown",
    "WeightedSimilarityEngine",
    "assess_evidence_support",
]

