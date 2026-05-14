from __future__ import annotations

from typing import Any

from sii_reference_architecture.sii_layers import sii_layers


def build_sii_reference_model() -> dict[str, Any]:
    layers = sii_layers()
    return {
        "architecture_name": "Neraium SII Reference Architecture",
        "category_scope": "Systemic Infrastructure Intelligence",
        "design_principles": [
            "explainable structural cognition",
            "replayable and auditable reasoning",
            "evidence lineage completeness",
            "operator-centric interpretation",
            "non-actuating decision support",
        ],
        "layers": layers,
        "interoperability_context": {
            "graph_compatibility": "compatible with graph-based context and ontology-driven digital twin reasoning",
            "distinctiveness": "prioritizes structural cognition, replay continuity, and evidence lineage over generic context brokering",
            "standards_alignment_note": "alignable with graph context models (including NGSI-LD) while preserving SII-native operational language",
        },
    }

