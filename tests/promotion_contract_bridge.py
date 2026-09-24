"""Predeclared comparison bridge; never writes or replays a historical artifact.

Only source v1 -> current v2 version declarations, producer ownership and the
known promotion build provenance change. Analytical values, evidence references,
list order, qualification, source identity and state remain untouched.
"""
from copy import deepcopy

from app.services.analysis_provenance import result_digest
from app.services.engine_identity import git_commit
from app.services.upload_output_semantics import encode_upload_result
from app.services.output_semantics import LEGACY_SEMANTICS_VERSION, SEMANTICS_VERSION

SOURCE_BUILD = '97d267d3'


def current_contract_view(retained):
    result = deepcopy(retained)

    def visit(value):
        if isinstance(value, dict):
            if value.get('output_semantics') == LEGACY_SEMANTICS_VERSION:
                value['output_semantics'] = SEMANTICS_VERSION
                if 'analysis_metadata' in value and 'evidence_index' in value:
                    # The retained complete-upload worker establishes durable
                    # upload source ownership, not an arbitrary engine attempt.
                    value['identity_contract'] = 'complete-upload-evidence.v2'
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result)
    packets = [result.get('traceability'), result.get('decision_integrity'),
               (result.get('sii_intelligence') or {}).get('decision_integrity'),
               (result.get('analysis_result') or {}).get('sii_evidence')]
    for packet in packets:
        provenance = (packet or {}).get('provenance')
        if isinstance(provenance, dict) and 'build_commit' in provenance:
            assert provenance['build_commit'] == SOURCE_BUILD
            provenance['build_commit'] = git_commit()
    if result.get('upload_evidence_contract') == 'complete-upload-evidence.v2':
        result = encode_upload_result(result)
        packets = [result.get('traceability'), result.get('decision_integrity'),
                   (result.get('sii_intelligence') or {}).get('decision_integrity'),
                   (result.get('analysis_result') or {}).get('sii_evidence')]
        # This is a new comparison view, never the historical record's hash.
        digest = result_digest(result)
        for packet in packets:
            provenance = (packet or {}).get('provenance')
            if isinstance(provenance, dict) and 'result_hash' in provenance:
                provenance['result_hash'] = digest
    return result
