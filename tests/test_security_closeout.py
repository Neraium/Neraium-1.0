"""Focused HTTP presentation/auth abuse cases; no analytical transformations."""
import copy
import csv
import io
import json

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.spreadsheet_export import spreadsheet_safe_csv
from app.core.upload_error_presentation import UploadErrorRoute, public_upload_state
from app.main import create_app
from app.routers import auth, data, evidence, health
from app.services import auth_store

SECRET = '/private/customer/secret.csv password=TOPSECRET psycopg.OperationalError'

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.delenv('NERAIUM_API_TOKEN', raising=False)
    monkeypatch.delenv('NERAIUM_ACCESS_CODE', raising=False)
    monkeypatch.setenv('NERAIUM_BOOTSTRAP_ADMIN_EMAIL', 'admin@example.com')
    monkeypatch.setenv('NERAIUM_BOOTSTRAP_ADMIN_PASSWORD', 'password123')
    auth_store._AUTH_BACKEND = None
    auth_store._AUTH_BACKEND_KEY = None
    app = create_app(Settings(app_env='production', backend_host='127.0.0.1', backend_port=8010,
                             cors_origins=['https://testserver'], runtime_dir=tmp_path))
    return TestClient(app, base_url='https://testserver', headers={'Origin':'https://testserver'})


def login(client):
    response = client.post('/api/auth/login', json={'email':'admin@example.com','password':'password123'})
    assert response.status_code == 200, response.text
    return response


def test_session_cookie_login_me_logout(client):
    response = login(client)
    token = client.cookies.get(auth_store.session_cookie_name())
    assert token not in response.text
    handle = response.json()['session']['session_id']
    assert handle.startswith('session-') and handle != token
    cookie = response.headers['set-cookie'].lower()
    assert all(value in cookie for value in ('httponly', 'secure', 'samesite=lax'))
    me = client.get('/api/auth/me')
    assert me.json()['authenticated'] and token not in me.text
    assert client.post('/api/auth/logout').status_code == 200
    assert not client.get('/api/auth/me').json()['authenticated']
    assert client.get('/api/auth/sessions').status_code == 401


def test_handle_cannot_authenticate_and_admin_can_revoke(client):
    login(client)
    token = client.cookies.get(auth_store.session_cookie_name())
    response = client.get('/api/auth/sessions')
    assert response.status_code == 200 and token not in response.text
    handle = response.json()['sessions'][0]['session_id']
    assert auth_store.get_user_by_session(handle) is None
    response = client.post('/api/auth/sessions/revoke', json={'session_id':handle})
    assert response.status_code == 200 and response.json()['revoked'] == 1
    assert not client.get('/api/auth/me').json()['authenticated']


def test_revoke_all_still_works(client):
    login(client)
    response = client.post('/api/auth/sessions/revoke', json={'email':'admin@example.com','revoke_all_for_user':True})
    assert response.status_code == 200 and response.json()['revoked'] >= 1


def test_management_resolution_beyond_first_page(monkeypatch):
    target = {'session_id':'target-secret'}
    class Backend:
        def list_sessions(self, *, limit, offset):
            return [{'session_id':f'other-{i}'} for i in range(500)] if offset == 0 else [target]
    monkeypatch.setattr(auth_store, '_get_backend', lambda: Backend())
    assert auth_store.resolve_session_management_handle(auth._public_session(target)['session_id']) == 'target-secret'


@pytest.mark.parametrize('path', ['/health','/api/health','/api/ready'])
def test_public_health_minimal(client, monkeypatch, path):
    monkeypatch.setattr(health, 'service_health_snapshot', lambda **kw: {'status':'ok','secret':SECRET})
    monkeypatch.setattr(health, 'readiness_snapshot', lambda settings: ({'startup':'ok'}, []))
    response = client.get(path)
    assert response.status_code == 200
    assert set(response.json()) == {'status','service'}


@pytest.mark.parametrize('path', ['/api/ready?verbose=true','/api/observability/summary','/api/startup-status','/api/routes/debug','/api/intelligence/engine-identity','/api/intelligence/runner-status','/api/domain/mode'])
def test_detailed_diagnostics_not_public(client, path):
    assert client.get(path).status_code in (401,403)


def test_verbose_readiness_admin_and_viewer(client, monkeypatch):
    monkeypatch.setattr(health, 'readiness_snapshot', lambda settings: ({'startup':'ok'}, []))
    monkeypatch.setattr(health, 'service_health_snapshot', lambda **kw: {'status':'ok'})
    monkeypatch.setattr(health, 'runtime_diagnostics', lambda *a, **kw: {'authorized':True})
    monkeypatch.setattr(health, 'resolve_latest_upload_session', lambda **kw: {})
    login(client)
    response = client.get('/api/ready?verbose=true')
    assert response.status_code == 200 and response.json()['diagnostics']['authorized']
    monkeypatch.setattr('app.core.security.get_user_by_session', lambda token: {'email':'viewer@example.com','role':'viewer'})
    assert client.get('/api/ready?verbose=true').status_code == 403
    assert client.get('/api/auth/sessions').status_code == 403


@pytest.mark.parametrize('cell', ['=1+1','+cmd','-cmd','@SUM(A1)','\t=1+1','\r=1+1','  =1+1','a,\"b\n=1'])
def test_csv_presentation_only(cell):
    out = io.StringIO(newline=''); csv.writer(out).writerow(['source',cell])
    original = out.getvalue()
    result = list(csv.reader(io.StringIO(spreadsheet_safe_csv(original))))[0][1]
    assert result == ("'"+cell if cell != 'a,\"b\n=1' else cell)
    assert list(csv.reader(io.StringIO(original)))[0][1] == cell


def test_actual_csv_export_does_not_mutate_record(client, monkeypatch):
    record = {'run_id':'safe-run','source_name':'=1+1'}
    before = copy.deepcopy(record)
    monkeypatch.setattr(evidence, 'read_evidence_run', lambda run_id: record)
    monkeypatch.setattr(evidence, 'record_audit_event', lambda **kw: None)
    login(client)
    response = client.get('/api/evidence/export/safe-run?format=csv')
    assert response.status_code == 200
    cells = [cell for row in csv.reader(io.StringIO(response.text)) for cell in row]
    assert "'=1+1" in cells and '=1+1' not in cells
    assert record == before


@pytest.mark.parametrize('status_code', [400,404,413,415,422,500,503])
def test_upload_http_failure_sanitized(client, status_code):
    router = APIRouter(route_class=UploadErrorRoute)
    @router.get('/api/data/closeout-error')
    def failure():
        return JSONResponse({'message':SECRET,'technicalMessage':SECRET,'exception_type':'PrivateImpl'}, status_code=status_code)
    client.app.include_router(router)
    response = client.get('/api/data/closeout-error')
    assert response.status_code == status_code
    assert 'TOPSECRET' not in response.text and '/private' not in response.text and 'PrivateImpl' not in response.text
    assert response.json()['message'] and response.json()['error_code']


def test_exception_logging_has_no_secret(client, caplog):
    router = APIRouter(route_class=UploadErrorRoute)
    @router.get('/api/data/closeout-exception')
    def failure():
        raise RuntimeError(SECRET)
    client.app.include_router(router)
    response = client.get('/api/data/closeout-exception')
    assert response.status_code == 500
    assert SECRET not in response.text and SECRET not in caplog.text
    assert 'RuntimeError' in caplog.text


def test_failed_poll_and_stream(client, monkeypatch):
    failure = {'job_id':'job-safe','status':'FAILED','processing_state':'failed','progress':0,'message':SECRET,
               'error_type':'csv_parse_error','technicalMessage':SECRET}
    before = copy.deepcopy(failure)
    monkeypatch.setattr(data, 'resolve_upload_status', lambda *a, **kw: failure.copy())
    login(client)
    for path in ('/api/data/upload-status/job-safe','/api/data/upload-stream/job-safe'):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert SECRET not in response.text and 'csv_parsing_failed' in response.text
    assert failure == before


def test_nested_failure_preserves_governed_result():
    canonical = {'status':'failed','message':SECRET,'source_identity':'unchanged'}
    payload = {'status':'FAILED','message':SECRET,'latest_result':canonical,
               'current_upload':{'summary':{'status':'FAILED','technicalMessage':SECRET},'private':SECRET}}
    before = copy.deepcopy(payload)
    safe = public_upload_state(payload)
    assert safe['latest_result'] == canonical
    assert SECRET not in json.dumps(safe['current_upload'])
    assert payload == before


def test_success_payload_unchanged():
    payload = {'status':'COMPLETE','result':{'status':'FAILED','message':SECRET},'summary':{'status':'COMPLETE'}}
    assert public_upload_state(payload) == payload


def test_bad_login_and_malformed_cookie(client):
    response = client.post('/api/auth/login', json={'email':'admin@example.com','password':'incorrect'})
    assert response.status_code == 401
    client.cookies.set(auth_store.session_cookie_name(), 'not-a-valid-token')
    assert client.get('/api/auth/sessions').status_code == 401


def test_public_degraded_status_preserved(client, monkeypatch):
    monkeypatch.setattr(health, 'service_health_snapshot', lambda **kw: {'status':'degraded','failed_modules':[SECRET]})
    monkeypatch.setattr(health, 'readiness_snapshot', lambda settings: ({'startup':'error'}, [SECRET]))
    for path in ('/health','/api/health','/api/ready'):
        response = client.get(path)
        assert response.status_code == 503 and set(response.json()) == {'status','service'}


def test_real_upload_validation_and_connector_error(client, monkeypatch):
    login(client)
    response = client.post('/api/data/upload', files={'file':('not-supported.exe', b'bad', 'application/octet-stream')})
    assert response.status_code == 400, response.text
    assert response.json()['error_code'] == 'validation_failed'
    from app.routers import connectors
    def fail(*args, **kwargs):
        raise HTTPException(status_code=400, detail=SECRET)
    monkeypatch.setattr(connectors, 'validate_csv_upload_filename', fail)
    response = client.post('/api/connectors/csv/upload', files={'file':('safe.csv', b'timestamp,value\n0,1')})
    assert response.status_code == 410 and SECRET not in response.text
    # Exercise the retained local compatibility route without re-enabling it in production.
    client.app.dependency_overrides[connectors.require_legacy_connector_compatibility] = lambda: None
    response = client.post('/api/connectors/csv/upload', files={'file':('safe.csv', b'timestamp,value\n0,1')})
    assert response.status_code == 400 and SECRET not in response.text


def test_latest_http_error_summary_sanitized(client, monkeypatch):
    raw = {'status':'FAILED','processing_state':'failed','message':SECRET,'technicalMessage':SECRET,
           'current_upload':{'summary':{'status':'FAILED','message':SECRET}}}
    before = copy.deepcopy(raw)
    monkeypatch.setattr(data, 'resolve_latest_upload_payload', lambda **kw: raw)
    monkeypatch.setattr(data, 'read_latest_candidate', lambda: None)
    monkeypatch.setattr(data, 'read_active_behavioral_model', lambda: None)
    login(client)
    for path in ('/api/data/latest-upload','/latest-upload'):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert SECRET not in response.text
    assert raw == before


def test_unstructured_error_category_cannot_break_sanitizer():
    from app.core.upload_error_presentation import public_upload_error
    payload = public_upload_error({'error_type':{'secret':SECRET},'message':SECRET})
    assert payload['error_code'] == 'unexpected_server_error'
    assert SECRET not in json.dumps(payload)


def test_failure_presentation_keeps_governed_summary_and_timeout():
    governed = {'evidence':'unaltered','source_identity':'unchanged'}
    payload = {'status':'TIMEOUT','processing_state':'timeout','error_type':'timeout',
               'message':SECRET,'system_interpretation':governed,'traceability':governed}
    safe = public_upload_state(payload)
    assert safe['status'] == 'TIMEOUT' and safe['error_code'] == 'server_timeout'
    assert safe['system_interpretation'] == governed and safe['traceability'] == governed
    assert SECRET not in json.dumps(safe)
