"""Exact metadata exclusion for comparisons with pre-binding analytical fixtures."""
BINDING_FIELDS = frozenset({
    'relationship_assessment_binding', 'relationship_source_evidence', 'relationship_source_ref', 'relationship_evidence_ref',
    'relationship_evidence_id', 'relationship_evidence_registry',
})


def without_binding_metadata(value):
    if isinstance(value, dict):
        return {key: without_binding_metadata(item) for key, item in value.items()
                if key not in BINDING_FIELDS}
    if isinstance(value, list):
        return [without_binding_metadata(item) for item in value]
    return value
