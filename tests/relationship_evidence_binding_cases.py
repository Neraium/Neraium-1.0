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


def project_descriptive_contract(value, path=()):
    """Only for no-profile numerical comparisons to the pre-qualification model.

    New qualification has its own battery. Preserve all old numerical fields;
    map the explicitly retained descriptive endpoint back to its old name.
    Assert abstention rather than hiding a qualified outcome in this projection.
    """
    fields = {'relationship_qualification', 'qualification_summary', 'qualified_evidence',
              'qualified_persistence', 'qualified_persistence_supported', 'qualification_status',
              'reference_qualification_id', 'directional_persistence_supported', 'directional_persistence_status'}
    if isinstance(value, dict):
        result = dict(value)
        if 'qualified_persistence_supported' in result:
            assert result['qualified_persistence_supported'] is False
            assert result['qualification_status'] == 'limited'
        if 'directional_persistence_supported' in result:
            result['temporal_persistence_supported'] = result['directional_persistence_supported']
            result['persistent_relationship_change'] = result['directional_persistence_supported']
            result['temporal_persistence_status'] = result['directional_persistence_status']
        if 'qualified_evidence' in result and 'identity' in result and 'observations' in result:
            assert result['qualified_evidence'] == {}
            result['version'] = 1
        if isinstance(result.get('id'), str) and result['id'].startswith('relationship-authority.v1:'):
            # Assessment-owner hashes necessarily change with the new contract;
            # authority/ownership tests validate these independently of numerics.
            result.pop('id')
        if len(path) >= 2 and path[-2] == 'relationship_changes':
            # Newly exposed descriptive field; its value is still compared in
            # the original graph and dedicated directional invariance tests.
            result.pop('persistence_factor', None)
        return {key: project_descriptive_contract(item, (*path, key)) for key, item in result.items() if key not in fields}
    if isinstance(value, list): return [project_descriptive_contract(item, (*path, i)) for i, item in enumerate(value)]
    return value
