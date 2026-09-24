"""HTTP abuse regressions; no analytical producers are replaced or exercised."""
from dataclasses import replace
import asyncio
import json

import pytest
from fastapi import Depends, File, Request, UploadFile
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

from app.core.config import Settings, validate_environment_completeness
from app.core.http_boundary import HttpBoundaryMiddleware
from app.core.security import require_api_access, require_admin_role, _client_ip
from app.main import create_app
from app.routers.data import _request_client_ip
from app.services.auth_store import session_cookie_name


@pytest.fixture
def app(tmp_path):
    settings = Settings(app_env='production', backend_host='127.0.0.1', backend_port=8010,
                        cors_origins=['https://ui.example.test'], cors_origin_regex=r'https://trusted\.example\.test',
                        runtime_dir=tmp_path, telemetry_max_request_size_bytes=16, max_upload_size_bytes=16)
    application = create_app(settings)

    @application.post('/api/security-probe')
    async def probe(request: Request):
        return {'body': (await request.body()).decode()}

    @application.post('/api/security-file')
    async def file_probe(file: UploadFile = File(...)):
        return {'size': len(await file.read())}

    @application.get('/api/security-private', dependencies=[Depends(require_api_access)])
    def private():
        return {'ok': True}

    @application.get('/api/security-admin', dependencies=[Depends(require_admin_role)])
    def admin():
        return {'ok': True}

    @application.get('/api/security-error')
    def fail():
        raise RuntimeError('secret-source-telemetry-do-not-echo')

    return application


async def raw_request(app, *, path='/api/security-probe', chunks=(b'{}',), headers=(), method='POST'):
    sent = []
    consumed = 0
    complete = asyncio.Event()
    messages = [{'type': 'http.request', 'body': body, 'more_body': i < len(chunks)-1} for i, body in enumerate(chunks)]
    async def receive():
        nonlocal consumed
        if consumed < len(messages):
            message = messages[consumed]; consumed += 1
            return message
        await complete.wait()
        return {'type': 'http.disconnect'}
    async def send(message):
        sent.append(message)
        if message['type'] == 'http.response.body' and not message.get('more_body', False):
            complete.set()
    scope = {'type':'http', 'asgi':{'version':'3.0'}, 'http_version':'1.1', 'scheme':'https',
             'method':method,'path':path,'raw_path':path.encode(),'query_string':b'',
             'headers':[(b'host',b'testserver'),*headers], 'client':('192.0.2.1',1000), 'server':('testserver',443)}
    await app(scope,receive,send)
    status=next(m['status'] for m in sent if m['type']=='http.response.start')
    return status,consumed,sent


@pytest.mark.parametrize('declared', [None, b'1'])
def test_actual_chunked_body_limited_without_trusting_length(app, declared):
    headers=[] if declared is None else [(b'content-length',declared)]
    status,consumed,_=asyncio.run(raw_request(app,chunks=(b'a'*600_000,b'b'*600_000,b'never read'),headers=headers))
    assert status==413
    assert consumed==2


def test_telemetry_has_its_own_actual_stream_limit(app):
    async def consume(scope, receive, send):
        await receive()
    boundary = HttpBoundaryMiddleware(consume, settings=app.state.settings)
    status,consumed,_=asyncio.run(raw_request(boundary,path='/api/telemetry/ingest',chunks=(b'x'*17,b'never read'),headers=[(b'content-type',b'application/json')]))
    assert status==413
    assert consumed==1


@pytest.mark.parametrize('lengths', [[b'-1'],[b'nan'],[b'+12'],[b'1',b'2']])
def test_malformed_lengths_rejected_before_receive(app,lengths):
    status,consumed,_=asyncio.run(raw_request(app,headers=[(b'content-length',x) for x in lengths]))
    assert status==400
    assert consumed==0


def test_multipart_aggregate_rejected_before_parser(app):
    status,consumed,_=asyncio.run(raw_request(app,path='/api/data/upload',headers=[(b'content-length',str(16+1024*1024+1).encode()),(b'content-type',b'multipart/form-data; boundary=x')]))
    assert status==413
    assert consumed==0


def test_streamed_multipart_parser_returns_413(app):
    prefix=b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n\r\n'
    status,consumed,_=asyncio.run(raw_request(app,path='/api/security-file',headers=[(b'content-type',b'multipart/form-data; boundary=x')],chunks=(prefix,b'x'*(1024*1024),b'\r\n--x--\r\n')))
    assert status==413
    assert consumed==2


def test_accepted_bytes_are_not_transformed(app):
    payload=b'{"source":"\\u00e9", "ordered": [2,1]}'
    status,_,messages=asyncio.run(raw_request(app,chunks=(payload[:10],payload[10:])))
    assert status==200
    body=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
    assert json.loads(body)['body'].encode()==payload


@pytest.mark.parametrize('origin',['https://evil.example.test','null','https://ui.example.test.evil','https://trusted.example.test.evil'])
def test_cookie_write_rejects_untrusted_origin(app,origin):
    client=TestClient(app,base_url='https://testserver')
    client.cookies.set(session_cookie_name(),'opaque-session')
    response=client.post('/api/security-probe',headers={'Origin':origin},content='payload')
    assert response.status_code==403


@pytest.mark.parametrize('headers',[{'Origin':'https://ui.example.test'},{'Origin':'https://testserver'},{'Referer':'https://ui.example.test/workspace'},{'Origin':'https://trusted.example.test'}])
def test_cookie_write_allows_trusted_frontend(app,headers):
    client=TestClient(app,base_url='https://testserver');client.cookies.set(session_cookie_name(),'opaque-session')
    assert client.post('/api/security-probe',headers=headers,content='ok').json()=={'body':'ok'}


def test_cookie_write_without_origin_or_referer_fails_closed(app):
    client=TestClient(app,base_url='https://testserver');client.cookies.set(session_cookie_name(),'opaque-session')
    assert client.post('/api/security-probe',content='ok').status_code==403
    assert client.get('/api/auth/me').status_code==200


def test_header_only_client_does_not_need_browser_origin(app):
    assert TestClient(app).post('/api/security-probe',headers={'Authorization':'Bearer client'},content='ok').status_code==200


def test_login_rejects_hostile_origin_before_authentication(app):
    response=TestClient(app).post('/api/auth/login',headers={'Origin':'https://evil.example.test'},json={'email':'a@example.com','password':'password123'})
    assert response.status_code==403


@pytest.mark.parametrize('path', ['/api/security-private','/api/security-admin'])
def test_staging_rejects_forged_identity_headers(app,path,monkeypatch):
    monkeypatch.delenv('NERAIUM_API_TOKEN',raising=False)
    app.state.settings=replace(app.state.settings,app_env='staging')
    response=TestClient(app).get(path,headers={'X-Neraium-User':'admin@example.test','X-Neraium-Role':'admin','Authorization':'Bearer invalid'})
    assert response.status_code==401


def test_staging_enforces_role_on_valid_service_token(app,monkeypatch):
    app.state.settings=replace(app.state.settings,app_env='staging')
    monkeypatch.setenv('NERAIUM_API_TOKEN','valid-secret');monkeypatch.setenv('NERAIUM_API_TOKEN_ROLE','viewer')
    response=TestClient(app).get('/api/security-admin',headers={'Authorization':'Bearer valid-secret'})
    assert response.status_code==403


def test_forwarded_header_cannot_spoof_audit_peer():
    req=StarletteRequest({'type':'http','client':('192.0.2.4',99),'headers':[(b'x-forwarded-for',b'198.51.100.1')]})
    assert _client_ip(req)==_request_client_ip(req)=='192.0.2.4'


@pytest.mark.parametrize('path,status', [('/api/security-private',401),('/api/security-error',500)])
def test_private_error_responses_are_not_cacheable_and_do_not_echo_exception(app,path,status):
    response=TestClient(app,base_url='https://testserver',raise_server_exceptions=False).get(path)
    assert response.status_code==status
    assert 'secret-source-telemetry' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['x-frame-options']=='DENY'


def test_early_rejection_preserves_cors_and_security_headers(app):
    response=TestClient(app).post('/api/security-probe',headers={'Origin':'https://ui.example.test','Content-Length':'9999999'})
    assert response.status_code==413
    assert response.headers['access-control-allow-origin']=='https://ui.example.test'
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-content-type-options']=='nosniff'


@pytest.mark.parametrize('query',['','?sslmode=disable','?sslmode=prefer'])
def test_production_direct_auth_db_requires_tls(app,monkeypatch,query):
    monkeypatch.delenv('NERAIUM_AUTH_DATABASE_SECRET_ARN',raising=False)
    monkeypatch.setenv('NERAIUM_AUTH_DATABASE_URL','postgresql://user:pass@db.example.test/auth'+query)
    with pytest.raises(ValueError,match='NERAIUM_AUTH_DATABASE_URL must require TLS'):
        validate_environment_completeness(app.state.settings)


def test_streamed_multipart_limit_closes_parser_tempfiles(app, monkeypatch):
    import starlette.formparsers as parser
    original = parser.SpooledTemporaryFile
    opened = []
    def record_file(*args, **kwargs):
        handle = original(*args, **kwargs)
        opened.append(handle)
        return handle
    monkeypatch.setattr(parser, 'SpooledTemporaryFile', record_file)
    prefix = b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n\r\nsmall'
    status, _, _ = asyncio.run(raw_request(app, path='/api/security-file',
        headers=[(b'content-type', b'multipart/form-data; boundary=x')],
        chunks=(prefix, b'x' * (1024 * 1024), b'\r\n--x--\r\n')))
    assert status == 413
    assert opened and all(handle.closed for handle in opened)


def test_production_direct_auth_db_tls_config_is_accepted(app, monkeypatch):
    monkeypatch.delenv('NERAIUM_AUTH_DATABASE_SECRET_ARN', raising=False)
    monkeypatch.setenv('NERAIUM_AUTH_DATABASE_URL', 'postgresql://user:pass@db.example.test/auth?sslmode=verify-full')
    monkeypatch.setenv('NERAIUM_RUNTIME_DATABASE_URL', 'postgresql://user:pass@db.example.test/runtime?sslmode=verify-full')
    monkeypatch.setenv('CORS_ORIGINS', 'https://ui.example.test')
    validate_environment_completeness(app.state.settings)


def test_staging_cookie_is_secure_even_without_forwarded_headers(app):
    from app.routers.auth import _session_cookie_secure
    app.state.settings = replace(app.state.settings, app_env='staging')
    req = StarletteRequest({'type':'http', 'scheme':'http', 'path':'/', 'query_string':b'',
                           'headers':[(b'host', b'testserver')], 'app':app})
    assert _session_cookie_secure(req)
