"""Human-authorized current contracts and immutable historical interpretation."""
from copy import deepcopy
from dataclasses import replace
import os
import time

import pytest

from app.services.analysis_result_contract import build_analysis_result, ensure_analysis_result
from app.services.condition_corroboration import ConditionCorroborationService
from app.services.output_semantics import canonical_json, govern_runtime, semantic_content, semantic_digest
from test_condition_intelligence import historical_rows, relationship


def conditions(links):
    return ConditionCorroborationService().build_conditions(
        relationships=links, findings=[], rows=historical_rows(), timestamp_column='timestamp',
        data_quality={}, operating_mode={}, site_name='', generated_at='2040-01-01T00:00:00Z')


def test_analytical_rank_and_exact_ties_ignore_identity():
    a, b = relationship('z', 'a', 'b'), relationship('a', 'b', 'c')
    assert conditions([a, b])[0]['title_evidence_relationship_id'] == 'z'
    assert conditions([b, a])[0]['title_evidence_relationship_id'] == 'a'
    a['id'], b['id'] = 'first-renamed', '000-second'
    assert conditions([a, b])[0]['title_evidence_relationship_id'] == 'first-renamed'
    b['relationship_importance_score'] = 1
    assert conditions([a, b])[0]['title_evidence_relationship_id'] == '000-second'
    b.pop('relationship_importance_score')
    b['correlation_delta'] = .7
    assert conditions([a, b])[0]['title_evidence_relationship_id'] == '000-second'
    b['correlation_delta'] = a['correlation_delta']
    b['confidence_score'] = .95
    assert conditions([a, b])[0]['title_evidence_relationship_id'] == '000-second'


def test_canonical_unordered_representation_does_not_choose_primary():
    result = conditions([relationship('z', 'b', 'a'), relationship('a', 'a', 'c')])[0]
    primary = result['title_evidence_relationship_id']
    assert result['coherence']['shared_signals'] == sorted(result['coherence']['shared_signals'])
    assert canonical_json({'ids': {'z', 'a'}, 'primary': primary}) == '{"ids":["a","z"],"primary":"z"}'
    assert result['title_evidence_relationship_id'] == primary == 'z'


@pytest.mark.parametrize('key', ['run_id', 'job_id', 'upload_id', 'analysis_id', 'completed_at', 'last_processed_at'])
def test_execution_only_ids_and_clocks_do_not_change_governed_semantics(key):
    source = {'status': 'complete', 'run_id': 'attempt', 'job_id': 'job', 'upload_id': 'upload',
              'analysis_id': 'analysis', 'completed_at': '2030-01-01', 'last_processed_at': '2030-01-01',
              'relationship_model': {'top_relationship_changes': [relationship('r', 'a', 'b')]}}
    changed = {**source, key: '2040-01-01' if key.endswith('_at') else 'other-attempt'}
    a, b = build_analysis_result(source), build_analysis_result(changed)
    assert semantic_content(a) == semantic_content(b)
    assert a['evidence_index'] == b['evidence_index']
    if key != 'last_processed_at':  # completion clock owns generated_at when both exist
        assert a['runtime_metadata'] != b['runtime_metadata']


@pytest.mark.parametrize('key', ['analysis_id', 'run_id'])
def test_connector_source_window_and_run_are_bound(key):
    source = {'status': 'complete', 'source_kind': 'connector', 'analysis_id': 'window', 'run_id': 'ingestion',
              'timestamp_profile': {'first_timestamp': '2026-01-01', 'last_timestamp': '2026-01-02'}}
    a, b = build_analysis_result(source), build_analysis_result({**source, key: 'different-source'})
    assert semantic_digest(a) != semantic_digest(b)
    assert a['identity_contract'] == 'connector-window.v1'
    assert a['analysis_metadata']['run_id'] == 'ingestion'
    assert not a['upload_id']


def test_durable_upload_producer_exception_and_unmarked_source_data():
    source = {'status': 'complete', 'upload_evidence_contract': 'complete-upload-evidence.v2',
              'run_id': 'durable-source', 'job_id': 'durable-source'}
    a = build_analysis_result(source)
    b = build_analysis_result({**source, 'job_id': 'new-source', 'run_id': 'new-source'})
    assert a['upload_id'] == 'durable-source'
    assert semantic_digest(a) != semantic_digest(b)
    assert semantic_digest({'runtime_metadata': {'source_value': 1}}) != semantic_digest({'runtime_metadata': {'source_value': 2}})


def test_historical_v1_interpretations_and_replay_are_not_upgraded():
    from app.services import output_semantics_legacy_source as source
    from app.services import output_semantics_legacy_target as target
    from app.services.analysis_provenance import result_digest
    for reader in (source, target):
        old = {'output_semantics': 'governed-output-semantics.v1', 'analysis_id': 'old',
               'generated_at': '2030', 'runtime_metadata': {'run_id': 'attempt'}}
        if reader is source:
            old['runtime_metadata']['contract_version'] = 'execution-metadata.v1'
        before = deepcopy(old)
        assert semantic_digest(old) == reader.semantic_digest(old)
        assert result_digest({'analysis_result': old}) == reader.semantic_digest({'analysis_result': old})
        assert old == before
    from test_telemetry_result_artifact import _execution
    from app.services.telemetry_result_artifact import build_canonical_result_artifact, decode_canonical_result_artifact
    execution = _execution()
    analysis = dict(execution.analysis_result)
    analysis['output_semantics'] = 'governed-output-semantics.v1'
    analysis['conditions'] = [{'id': 'historical', 'title_evidence_relationship_id': 'a', 'evidence_refs': ['evidence-1']}]
    execution = replace(execution, analysis_result=analysis)
    artifact = build_canonical_result_artifact(execution)
    original = artifact.payload
    replay = decode_canonical_result_artifact(artifact)
    assert replay == execution.as_dict()
    # Artifact replay does not invoke the current builder or ranker.
    assert replay['analysis_result']['conditions'][0]['title_evidence_relationship_id'] == 'a'
    assert artifact.payload == original


def test_runtime_location_canonical_artifact_identity_is_preserved():
    from test_telemetry_result_artifact import _execution
    from app.services.telemetry_result_artifact import build_canonical_result_artifact, decode_canonical_result_artifact
    execution = _execution()
    a = deepcopy(dict(execution.analysis_result))
    a['runtime_metadata'] = {'run_id': a['analysis_metadata'].pop('run_id')}
    moved = replace(execution, analysis_result=a)
    artifact = build_canonical_result_artifact(moved)
    assert artifact.result_id == build_canonical_result_artifact(execution).result_id
    assert decode_canonical_result_artifact(artifact) == moved.as_dict()


def test_phase4_source_identity_and_utc_attribution_are_deterministic():
    from app.engine.sii.phase4 import _source_run_id
    from app.engine.sii.behavioral_model import observation_bounds
    columns, rows = ['flow'], [{'flow': 1}]
    a = _source_run_id(columns, rows, {'run_id': 'a', 'job_id': 'a'})
    assert a == _source_run_id(columns, rows, {'run_id': 'b', 'job_id': 'b'})
    assert _source_run_id(columns, rows, {'source_run_id': 'source'}) == 'source'
    old = os.environ.get('TZ')
    try:
        bounds = []
        for zone in ['UTC', 'America/New_York']:
            os.environ['TZ'] = zone
            time.tzset()
            bounds.append(observation_bounds(rows, None, a))
        assert bounds[0] == bounds[1]
        assert bounds[0][0].endswith('+00:00')
    finally:
        if old is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = old
        time.tzset()


def test_schema_order_and_row_chronology_are_preserved():
    from app.engine.sii_inputs import normalize_rows
    a = [{'b': 2, 'a': 1, 'z': 3}, {'z': 6, 'a': 4, 'b': 5}]
    b = [dict(reversed(list(row.items()))) for row in a]
    assert normalize_rows(['a', 'b'], a) == normalize_rows(['a', 'b'], b)
    rows, matrix = normalize_rows(['a', 'b'], a)
    assert list(rows[0]) == ['a', 'b', 'z']
    assert matrix == [['1', '2'], ['4', '5']]


def test_behavioral_snapshot_identity_is_source_bound():
    from app.engine.sii.behavioral_model import build_behavioral_snapshot
    args = dict(model={'model_id': 'model', 'model_version': 'v1'}, source_run_id='source',
                created_at='2026-01-01T00:00:00Z', previous_snapshot_id=None, changes={})
    first = build_behavioral_snapshot(**args)
    assert first == build_behavioral_snapshot(**args)
    assert first['snapshot_id'] != build_behavioral_snapshot(**{**args, 'source_run_id': 'other'})['snapshot_id']


def test_water_generation_clock_is_runtime_and_source_time_remains_semantic():
    from app.services.output_semantics import SEMANTICS_VERSION, runtime_metadata
    first = {'output_semantics': SEMANTICS_VERSION, 'generated_at': '2030',
             'runtime_metadata': runtime_metadata(generated_at='2030'), 'source_timestamp': '2026'}
    second = {**first, 'generated_at': '2040', 'runtime_metadata': runtime_metadata(generated_at='2040')}
    assert semantic_digest(first) == semantic_digest(second)
    assert semantic_digest(first) != semantic_digest({**second, 'source_timestamp': '2025'})


def test_paired_reference_producer_keeps_content_derived_source_analysis_id():
    source = {'status': 'complete', 'source_identity_contract': 'paired-reference.v1', 'analysis_id': 'paired-source-content'}
    first = build_analysis_result(source)
    assert first['identity_contract'] == 'paired-reference.v1'
    assert semantic_digest(first) != semantic_digest(build_analysis_result({**source, 'analysis_id': 'different-source-content'}))


def test_historical_bridge_changes_no_analytical_values_or_evidence_references():
    from promotion_contract_bridge import current_contract_view
    old = {'analysis_result': {'output_semantics': 'governed-output-semantics.v1',
           'analysis_metadata': {}, 'evidence_index': {'original-id': {'value': 3}},
           'conditions': [{'title_evidence_relationship_id': 'z', 'evidence_refs': ['original-id']}],
           'sii_evidence': {'provenance': {'build_commit': '97d267d3'}}}}
    before = deepcopy(old)
    new = current_contract_view(old)
    assert old == before
    assert new['analysis_result']['evidence_index'] == old['analysis_result']['evidence_index']
    assert new['analysis_result']['conditions'] == old['analysis_result']['conditions']
    assert new['analysis_result']['output_semantics'] == 'governed-output-semantics.v2'


def test_upload_attempt_correlation_is_runtime_but_durable_source_id_is_not():
    from app.services.upload_output_semantics import encode_upload_result, upload_compatibility_view
    first = {'upload_id': 'durable-upload', 'dataset_id': 'dataset', 'request_id': 'request-a',
             'upload_session_id': 'session-a', 'attempt_id': 'attempt-a'}
    second = {**first, 'request_id': 'request-b', 'upload_session_id': 'session-b', 'attempt_id': 'attempt-b'}
    a, b = encode_upload_result(first), encode_upload_result(second)
    assert semantic_digest(a) == semantic_digest(b)
    restored = upload_compatibility_view(a)
    for key, value in first.items():
        assert restored[key] == value
    assert semantic_digest(a) != semantic_digest(encode_upload_result({**first, 'upload_id': 'different-source'}))


def test_affected_signal_order_is_governed_evidence_not_a_display_set():
    # Minimal reproduction of the sole 10K retained-reference mismatch. The
    # primary is unchanged; sorting signals changes recommendations/evidence.
    links = [relationship('r1', 'flow_gpm', 'pressure_psi'),
             relationship('r2', 'load_pct', 'pressure_psi')]
    value = conditions(links)[0]
    expected = ['flow_gpm', 'pressure_psi', 'load_pct']
    assert value['affected_signals'] == expected
    assert value['corroboration']['affected_signals'] == expected
    assert value['localization']['signals_involved'] == expected
    assert value['recommended_check'] == 'Verify source data for flow_gpm, pressure_psi, load_pct.'
    assert value['title_evidence_relationship_id'] == 'r1'
    # Shared-signal sets remain canonical without changing governed order.
    assert value['coherence']['shared_signals'] == ['pressure_psi']


def test_runtime_alias_description_cannot_redefine_semantics():
    first = govern_runtime({'analysis_id': 'attempt', 'relationships': [{'value': 2}]})
    second = deepcopy(first)
    second['runtime_metadata']['legacy_root_aliases'] = ['relationships']
    assert semantic_content(first) == semantic_content(second)
    second['relationships'][0]['value'] = 3
    assert semantic_content(first) != semantic_content(second)


def test_projection_retains_current_identity_responsibility():
    from test_telemetry_result_projection import _execution, _metadata, _scope
    from app.services.telemetry_result_projection import build_canonical_result_projection
    execution = _execution()
    execution['analysis_result'] = govern_runtime(execution['analysis_result'], identity_contract='connector-window.v1')
    before = deepcopy(execution)
    projection = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope())
    assert projection.product_result['analysis_result']['identity_contract'] == 'connector-window.v1'
    assert execution == before


def test_terminal_publication_keeps_attempt_runtime_and_retry_identity():
    from app.services import upload_state_repository as repository
    from app.services.output_semantics import SEMANTICS_VERSION, runtime_value
    from app.services.upload_output_semantics import upload_compatibility_view
    from test_upload_state_contract import _persisted_result
    job = 'typed-terminal-attempt'
    result = _persisted_result(job, filename='small.csv')
    result['upload_evidence_contract'] = 'complete-upload-evidence.v2'
    result['analysis_result'] = {'output_semantics': SEMANTICS_VERSION}
    summary = {'job_id': job, 'status': 'COMPLETE', 'processing_state': 'complete',
               'attempt_id': 'explicit-retry', 'result_available': True, 'sii_completed': True}
    repository.write_upload_completion(job, result=result, summary=summary)
    stored = repository.read_upload_result_by_job_id(job)
    assert 'attempt_id' not in stored
    assert runtime_value(stored, 'attempt_id') == 'explicit-retry'
    assert repository._upload_attempt_id(job, stored) == 'explicit-retry'
    assert repository._payloads_share_attempt(summary, stored)
    assert not repository._payloads_share_attempt({**summary, 'attempt_id': 'stale-attempt'}, stored)
    assert upload_compatibility_view(stored)['attempt_id'] == 'explicit-retry'
    original = deepcopy(stored)
    repository.write_upload_completion(job, result={**result, 'engine_result': {'overall_result': 'changed'}}, summary=summary)
    assert repository.read_upload_result_by_job_id(job) == original
