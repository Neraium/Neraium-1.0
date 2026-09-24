"""Complete 10k production regression; retained worker, comparator and live clocks."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys

from app.services.output_semantics import semantic_content, semantic_digest
from promotion_contract_bridge import current_contract_view

ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / 'docs/performance/production-processing-2026/raw'


def load(path):
    with gzip.open(path, 'rt') as handle:
        return json.load(handle)


def test_complete_10000_upload_repeat(tmp_path):
    # Import the retained worker, never its scale controller. Keep its source,
    # defaults, full returned output and comparator; isolate new audit artifacts.
    output = Path(os.environ.get('UPLOAD_GATE_OUTPUT', tmp_path / 'gate'))
    output.mkdir(parents=True, exist_ok=True)
    code = """
import importlib.util, pathlib, sys
import app
spec = importlib.util.spec_from_file_location('retained', sys.argv[1])
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
b.RAW = pathlib.Path(sys.argv[2]); b.RT = b.RAW / 'runtime'
b.worker('end_to_end', 10000, sys.argv[3])
from app.services import aletheia_governance
from app.services.evidence_store import read_evidence_run
b.dump(b.RAW / (sys.argv[3] + '.evidence.json'), read_evidence_run('production-benchmark'))
(b.RAW / (sys.argv[3] + '.audit.jsonl')).write_text(aletheia_governance.EVP_LOG_PATH.read_text() if aletheia_governance.EVP_LOG_PATH.exists() else '')
"""
    for label in ('first', 'repeat'):
        proc = subprocess.run([sys.executable, '-c', code, str(RETAINED / 'benchmark.py'), str(output), label],
                              cwd=ROOT, env={**{k: v for k, v in os.environ.items() if k != 'PYTEST_CURRENT_TEST'},
                                   'PYTHONHASHSEED': '0', 'PYTHONPATH': str(ROOT / 'backend')},
                              capture_output=True, text=True, timeout=180)
        (output / f'{label}.log').write_text(proc.stdout + proc.stderr)
        assert proc.returncode == 0, proc.stderr
    a, b = [load(output / f'end_to_end-10000-{label}.output.json.gz') for label in ('first', 'repeat')]
    assert semantic_digest(a) == semantic_digest(b), 'complete upload semantic mismatch'
    assert semantic_content(a) == semantic_content(b)
    from app.services.analysis_provenance import result_digest
    from app.services.output_semantics import runtime_value
    analytical = analytical_snapshot(a)
    for label in ('warmup', '1'):
        retained = load(RETAINED / f'end_to_end-10000-{label}.output.json.gz')
        assert analytical == analytical_snapshot(current_contract_view(retained)), label
    assert analytical == analytical_snapshot(b)
    # Prospective retirement projection, declared before the gate: remove only
    # the retired envelope and its exclusively Aletheia source binding.
    repaired = load(RETAINED.parent / 'complete-upload-repair/final-gate/end_to_end-10000-first.output.json.gz')
    repaired['sii_intelligence'].pop('aletheia_gate')
    repaired['sii_intelligence']['source_metadata'].pop('source_evidence')
    assert semantic_content(a) == semantic_content(current_contract_view(repaired)), 'pre-retirement candidate equivalence under declared v2 bridge'
    assert a['runtime_metadata'] != b['runtime_metadata']
    for label, result in zip(('first', 'repeat'), (a, b)):
        evidence = json.loads((output / f'{label}.evidence.json').read_text())
        digest = result_digest(result)
        assert evidence['result_hash'] == digest
        for packet in (result['traceability'], result['decision_integrity'],
                       result['sii_intelligence']['decision_integrity'], result['analysis_result']['sii_evidence']):
            assert packet['provenance']['result_hash'] == digest
        records = [json.loads(line) for line in (output / f'{label}.audit.jsonl').read_text().splitlines()]
        assert records == []
        assert 'aletheia_gate' not in result['sii_intelligence']
        assert runtime_value(result, 'completed_at')
        assert runtime_value(result['job_progress'], 'elapsed_seconds') > 0
        assert runtime_value(result['processing_stats'], 'processing_time_seconds') > 0
        assert result['row_count'] == 10000
    (output / 'GATE.json').write_text(json.dumps({
        'status': 'pass', 'observations_per_upload': 10000, 'complete_uploads': 2,
        'comparator': 'governed-output-semantics.v2; predeclared source-v1 version/build bridge for retained evidence',
        'semantic_digest': semantic_digest(a),
        'analytical_component_digests': {key: semantic_digest(value) for key, value in analytical.items()},
        'retained_analytical_comparison': ['warmup: equal', '1: equal'],
        'pre_retirement_candidate': 'complete semantic equality after two declared legacy removals',
        'evidence_hashes_verified': True, 'no_legacy_evps_created': True,
    }, indent=2) + '\n')


def test_upload_execution_representation_round_trip_and_source_sensitivity():
    from copy import deepcopy
    from app.services.upload_output_semantics import encode_upload_result, upload_compatibility_view
    from app.services.analysis_provenance import result_digest
    source = load(RETAINED / 'end_to_end-10000-warmup.output.json.gz')
    encoded = encode_upload_result(source)
    decoded = upload_compatibility_view(encoded)
    # Every moved value is preserved exactly, including clocks that happened to
    # agree in the retained pair. No source-time field is moved recursively.
    from app.services.upload_output_semantics import _owned_records
    for (original, fields), (restored, _) in zip(_owned_records(source), _owned_records(decoded)):
        if isinstance(original, dict):
            for field in fields:
                if field in original:
                    assert restored[field] == original[field]
    assert encode_upload_result(decoded) == encoded
    assert encoded['timestamp_profile'] == source['timestamp_profile']
    assert encoded['traceability']['timestamps']['upload_start'] == source['traceability']['timestamps']['upload_start']
    assert encoded['traceability']['timestamps']['upload_end'] == source['traceability']['timestamps']['upload_end']
    original_digest = result_digest(encoded)
    for change in ('input', 'decision', 'source_time', 'ordering', 'configuration'):
        altered = deepcopy(encoded)
        if change == 'input':
            altered['ingestion_report']['input_hash'] = 'different-source-bytes'
        elif change == 'decision':
            altered['engine_result']['overall_result'] = 'different-decision'
        elif change == 'source_time':
            altered['analysis_result']['source_observation_timestamp'] = '1900-01-01'
        elif change == 'ordering':
            altered['analysis_result']['relationships'].reverse()
        else:
            altered['processing_trace']['mode_aware_authority']['enabled'] = not altered['processing_trace']['mode_aware_authority']['enabled']
        assert result_digest(altered) != original_digest, change


def analytical_snapshot(result):
    """Requested analytical components; NOT the complete-output comparator."""
    engine = result['sii_result']
    governed = result['analysis_result']
    return semantic_content({
        'source_identity': {key: result.get(key) for key in (
            'dataset_id', 'organization_id', 'portfolio_id', 'system_id', 'site_id',
            'phase4_system_identity', 'active_baseline_reference')},
        'source_bytes': result['ingestion_report']['input_hash'],
        'analytical_state': {key: result.get(key) for key in ('operating_state', 'drift_status', 'engine_result')},
        'current_sii': {key: result['sii_intelligence'].get(key) for key in (
            'core_sii_outputs', 'evidence_chain_quality', 'evidence_lineage',
            'observed_persistence', 'regime_context', 'baseline_comparison',
            'relationship_evidence', 'supporting_evidence', 'facility_state',
            'confidence_basis', 'confidence_components', 'review_next')},
        'canonical_replay': result['replay_timeline'],
        'relationship_graph': engine['relationship_graph'],
        'numerical_relationship_evidence': engine['relationship_analysis'],
        'persistence_recurrence': engine['persistence_analysis'],
        'operating_context': {'modes': engine['operating_modes'], 'inputs': result['operating_context_inputs']},
        'evidence_sufficiency': {'data_quality': result['data_quality'],
                                 'module_statuses': engine['processing_trace']['module_statuses'],
                                 'governed_quality': governed['data_quality']},
        'governed_conditions_insights_consequences_narratives': {
            key: governed[key] for key in ('conditions', 'insights', 'executive_summary',
                                           'recommendations', 'relationships', 'evidence_index',
                                           'relationship_graph', 'stable_window', 'deviation_window',
                                           'current_state_window', 'normalized_telemetry')},
        'other_analytical_modules': {key: value for key, value in engine.items() if key != 'processing_trace'},
    })


def test_retained_146_leaf_inventory_is_exhaustive():
    a, b = [load(RETAINED / f'end_to_end-10000-{label}.semantic.json.gz') for label in ('warmup', '1')]
    def leaves(x, y, path=''):
        if isinstance(x, dict):
            assert x.keys() == y.keys()
            for key in x:
                yield from leaves(x[key], y[key], path + '/' + key)
        elif isinstance(x, list):
            assert len(x) == len(y)
            for index, (left, right) in enumerate(zip(x, y)):
                yield from leaves(left, right, path + '/' + str(index))
        elif x != y:
            yield path
    inventory = json.loads((RETAINED.parent / 'complete-upload-repair/FIELD_TRACE.json').read_text())
    assert len(inventory) == 146
    assert {row['path'] for row in inventory} == set(leaves(a, b))
    assert all(row['producer'] and row['consumer'] and row['prospective_representation'] for row in inventory)
