"""S08: real scoped persistence with customer and restricted forensic views."""
import copy
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.core.failure_evidence_presentation import customer_evidence_view
from app.core.upload_error_presentation import public_upload_state
from app.routers import evidence
from app.services import runtime_db
from app.services.dataset_scope import build_dataset_scope, dataset_scope_context
from test_security_closeout import client, login

ADVERSARIAL = (
    'Traceback (most recent call last):\n'
    '  File "/home/ubuntu/private/customer.py", line 42\n'
    'psycopg.OperationalError: postgresql://operator:SECRET_PASSWORD@10.0.0.7:5432/customer\n'
    'Authorization: Bearer SECRET_TOKEN\n'
    'SELECT secret FROM private_customer WHERE token=\'SECRET_TOKEN\';\n'
    'RuntimeError: connection failed; environment=PRIVATE_ENV'
)
MARKERS = ['/home/ubuntu', 'Traceback', 'psycopg', 'OperationalError', 'postgresql://',
           'SECRET_PASSWORD', '10.0.0.7', 'Authorization', 'Bearer', 'SECRET_TOKEN',
           'SELECT secret', 'private_customer', 'RuntimeError', 'PRIVATE_ENV']


def assert_safe(value):
    text = value.decode("latin-1") if isinstance(value, bytes) else value if isinstance(value, str) else json.dumps(value)
    assert all(marker not in text for marker in MARKERS), text


@pytest.fixture
def stored(client):
    login(client)
    scope = build_dataset_scope(user_id='admin@example.com')
    record = {
        'run_id':'failure-123', 'source_type':'csv_upload', 'source_name':ADVERSARIAL,
        'created_at':'2026-09-24T12:00:00+00:00', 'completed_at':'2026-09-24T12:01:00+00:00',
        'status':'failed', 'observation_status':'failed', 'error_type':'csv_parse_error',
        'errors':[ADVERSARIAL], 'data_conditions':[ADVERSARIAL], 'warnings':[ADVERSARIAL],
        'traceability':{'lineage':[ADVERSARIAL]}, 'provenance':{'exception':ADVERSARIAL},
        'operator_feedback_history':[{'note':ADVERSARIAL}], 'historical_fact':ADVERSARIAL,
        'evidence_summary':[ADVERSARIAL], 'technicalMessage':ADVERSARIAL,
        'unknown_future_diagnostic':{'nested':[ADVERSARIAL]}, 'raw_telemetry':[{'internal':ADVERSARIAL}],
        'governance_boundary':{'raw_telemetry_export_allowed':True,'statement':ADVERSARIAL},
        'build_commit':ADVERSARIAL,'input_hash':'a'*64,'result_hash':'b'*64,'evidence_hash':'c'*64,
        'baseline_id':'baseline-safe','baseline_dataset_id':'dataset-safe',
    }
    # Represents an already-stored historical failure, not a new producer format.
    with dataset_scope_context(scope):
        runtime_db.upsert_evidence_run_db(record)
        raw = runtime_db.read_evidence_run_db(record['run_id'])
    return client, scope, raw


def persisted_bytes(scope):
    with dataset_scope_context(scope), runtime_db.db_connection() as connection:
        return connection.execute('SELECT payload_json FROM evidence_runs WHERE run_id = ?', ('failure-123',)).fetchone()['payload_json']


@pytest.mark.parametrize('path', [
    '/api/evidence/runs', '/api/evidence/runs/failure-123', '/api/evidence/latest',
    '/api/evidence/runs/failure-123/integrity',
    '/api/evidence/export/failure-123?format=json', '/api/evidence/export/failure-123?format=csv',
    '/api/evidence/export/failure-123?format=markdown',
    '/api/evidence/package/failure-123?format=json', '/api/evidence/package/failure-123?format=pdf',
])
def test_all_customer_reads_and_exports_sanitize_without_rewriting(stored, path):
    client, scope, raw = stored
    before = persisted_bytes(scope)
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert_safe(response.content)
    assert b'failure-123' in response.content
    if '/integrity' not in path:
        assert b'csv_parsing_failed' in response.content
    assert persisted_bytes(scope) == before
    with dataset_scope_context(scope):
        assert runtime_db.read_evidence_run_db('failure-123') == raw


def test_customer_status_category_reference_and_digest_references(stored, monkeypatch):
    client, _, raw = stored
    # Ordinary customer view stays safe even for an administrator.
    response = client.get('/api/evidence/runs/failure-123').json()
    assert response['status'] == 'failed'
    assert response['data_conditions'] == ['csv_parsing_failed']
    assert response['errors'] == ['The CSV could not be parsed. Check its format and try again.']
    assert response['run_id'] == raw['run_id']
    assert response['created_at'] == raw['created_at']
    for key in ('input_hash','result_hash','evidence_hash'):
        assert response[key] == raw[key]
    monkeypatch.setattr('app.core.security.get_user_by_session', lambda token: {'email':'admin@example.com','role':'viewer'})
    ordinary = client.get('/api/evidence/runs/failure-123')
    assert ordinary.status_code == 200
    assert_safe(ordinary.content)
    assert client.get('/api/evidence/runs/failure-123/forensic').status_code == 403


@pytest.mark.parametrize('role', ['viewer','operator'])
def test_forensic_role_denial(stored, monkeypatch, role):
    client, _, _ = stored
    monkeypatch.setattr('app.core.security.get_user_by_session', lambda token: {'email':'admin@example.com','role':role})
    response = client.get('/api/evidence/runs/failure-123/forensic')
    assert response.status_code == 403
    assert_safe(response.content)


def test_forensic_admin_exact_stored_record_and_audit(stored, monkeypatch):
    client, scope, raw = stored
    before = persisted_bytes(scope); events = []
    monkeypatch.setattr(evidence, 'record_audit_event', lambda **event: events.append(event))
    response = client.get('/api/evidence/runs/failure-123/forensic')
    assert response.status_code == 200
    assert response.json() == {'view':'internal_forensic_failure.v1','record':raw}
    assert response.headers['cache-control'] == 'no-store'
    assert events[0]['action'] == 'evidence.failure.forensic.read'
    assert_safe(events)
    assert persisted_bytes(scope) == before


@pytest.mark.parametrize('environment', ['production','development'])
def test_forensic_anonymous_and_forged_role_rejected(client, environment):
    client.app.state.settings = replace(client.app.state.settings, app_env=environment)
    response = client.get('/api/evidence/runs/failure-123/forensic',
                          headers={'X-Neraium-User':'admin@example.com','X-Neraium-Role':'admin'})
    assert response.status_code == 401
    assert_safe(response.content)


def test_forensic_scope_cannot_be_bypassed(stored):
    client, _, raw = stored
    other = build_dataset_scope(user_id='other@example.com')
    with dataset_scope_context(other):
        runtime_db.upsert_evidence_run_db({**raw,'run_id':'other-failure','dataset_scope':other.as_dict()})
    response = client.get('/api/evidence/runs/other-failure/forensic')
    assert response.status_code == 404
    assert_safe(response.content)


@pytest.mark.parametrize('operation,payload,function', [
    ('audit-tag',None,'tag_evidence_for_audit'),
    ('feedback',{'category':'sensor_or_data_problem'},'record_operator_feedback'),
    ('status',{'state':'open'},'record_finding_status'),
])
def test_mutation_response_uses_projection_without_projecting_storage(stored, monkeypatch, operation, payload, function):
    client, scope, raw = stored
    before = persisted_bytes(scope)
    monkeypatch.setattr(evidence, function, lambda *a, **kw: copy.deepcopy(raw))
    response = client.post('/api/evidence/runs/failure-123/'+operation, json=payload)
    assert response.status_code == 200, response.text
    assert_safe(response.content)
    assert response.json()['data_conditions'] == ['csv_parsing_failed']
    assert persisted_bytes(scope) == before


def test_interpretation_input_is_customer_safe(stored, monkeypatch):
    client, scope, _ = stored
    before = persisted_bytes(scope); packages=[]
    def interpret(package):
        packages.append(package)
        return {'interpretation':package['limitations']}
    monkeypatch.setattr(evidence, 'interpret_evidence_package', interpret)
    response = client.post('/api/evidence/runs/failure-123/interpretation')
    assert response.status_code == 200, response.text
    assert packages
    assert_safe(packages); assert_safe(response.content)
    assert persisted_bytes(scope) == before


def test_projection_success_and_nested_analytical_content_unchanged():
    record = {'run_id':'complete-1','status':'completed','errors':[ADVERSARIAL],
              'sii_evidence':{'status':'failed','value':1.23456789},'result_hash':'d'*64}
    before=copy.deepcopy(record)
    assert customer_evidence_view(record) is record
    assert record == before


def test_latest_embedded_failed_evidence_has_same_projection():
    failed = {'run_id':'old-failure','created_at':'2026-09-24','status':'failed','errors':[ADVERSARIAL]}
    payload = {'status':'COMPLETE','current_upload':{'status':'complete','evidence':failed},
               'result':{'status':'failed','errors':[ADVERSARIAL]}}
    before=copy.deepcopy(payload)
    safe=public_upload_state(payload)
    assert safe['current_upload']['evidence'] == customer_evidence_view(failed)
    assert_safe(safe['current_upload'])
    assert safe['result'] == payload['result'] and payload == before


def test_capture_keeps_original_forensic_exception(stored):
    _, scope, _ = stored
    from app.routers.data import _upsert_failed_evidence_record
    with dataset_scope_context(scope):
        _upsert_failed_evidence_record(job_id='captured-failure',filename='source.csv',source_type='csv_upload',error_message=ADVERSARIAL)
        record=runtime_db.read_evidence_run_db('captured-failure')
    assert record['errors'] == [ADVERSARIAL] and record['data_conditions'] == [ADVERSARIAL]
    assert_safe(customer_evidence_view(record))


def test_unknown_category_and_corrupt_timestamps_fail_safe():
    record={'status':'FAILED','run_id':'failure-1','error_type':ADVERSARIAL,
            'created_at':ADVERSARIAL,'completed_at':ADVERSARIAL,'evidence_hash':ADVERSARIAL}
    safe=customer_evidence_view(record)
    assert_safe(safe)
    assert safe['data_conditions'] == ['unexpected_server_error']
    assert 'evidence_hash' not in safe


def test_actual_latest_routes_project_embedded_evidence(stored, monkeypatch):
    client, _, raw = stored
    from app.routers import data
    payload={'status':'COMPLETE','current_upload':{'status':'complete','evidence':raw}}
    before=copy.deepcopy(payload)
    monkeypatch.setattr(data,'resolve_latest_upload_payload',lambda **kw:payload)
    monkeypatch.setattr(data,'read_latest_candidate',lambda:None)
    monkeypatch.setattr(data,'read_active_behavioral_model',lambda:None)
    for path in ('/api/data/latest-upload','/latest-upload'):
        response=client.get(path)
        assert response.status_code == 200
        assert_safe(response.content)
        assert response.json()['current_upload']['evidence']['data_conditions'] == ['csv_parsing_failed']
    assert payload == before


def test_successful_api_and_export_preserved_forensic_rejects_nonfailure(stored):
    client,scope,_=stored
    from app.services.evidence_store import read_evidence_run, build_evidence_export_payload
    from app.models.api_models import EvidenceRunResponse
    success={'run_id':'success-1','status':'completed','source_type':'csv_upload',
             'created_at':'2026-09-24T11:00:00+00:00','evidence_summary':['Governed evidence'],
             'input_hash':'d'*64,'result_hash':'e'*64,'sii_evidence':{'value':1.23456789}}
    with dataset_scope_context(scope):
        runtime_db.upsert_evidence_run_db(success)
        original=read_evidence_run('success-1')
    response=client.get('/api/evidence/runs/success-1')
    assert response.status_code == 200
    assert response.json() == EvidenceRunResponse(**original).model_dump(mode='json')
    exported=client.get('/api/evidence/export/success-1?format=json')
    assert exported.json() == build_evidence_export_payload(original)
    assert client.get('/api/evidence/runs/success-1/forensic').status_code == 409
