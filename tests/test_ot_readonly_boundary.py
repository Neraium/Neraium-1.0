"""Adversarial resource/identity admission; no network or customer systems."""
import httpx
import pytest


from app.connectors.base import ConnectorExecutionContext, TelemetryConnectorError
from app.connectors.https_telemetry import HttpsTelemetryConnector
from app.services.connector_execution import ConnectorExecutionBroker, RemoteHttpsTelemetryConnector, APPROVED_HOST
from app.services.telemetry_egress import TelemetryEgressError, TelemetryEgressPolicy
from app.services.telemetry_resource_policy import TelemetryResourcePolicyRegistry, VERSION
from test_connector_execution import make_job, signed, FakeSecretClient, FakeConnectorSecretStore


@pytest.fixture(autouse=True)
def migrate_replay_store(tmp_path):
    from db.migrations.connector_replay import apply
    apply(tmp_path / "replay.sqlite")


def manifest():
    return {"version": VERSION, "policies": {"synthetic-v2": {
        "kind": "synthetic", "origin": f"https://{APPROVED_HOST}",
        "method": "GET", "paths": ["/telemetry"], "query": {},
        "allow_pagination": False, "authentication_scheme": "none",
    }}}


def customer_job_and_registry():
    job = make_job()
    job["configuration"]["authentication_scheme"] = "bearer"
    job["credential"] = {"binding_id": "binding-y", "provider": "aws_secrets_manager",
        "reference": "arn:aws:secretsmanager:us-east-2:000000000000:secret:neraium/prod/telemetry-connections/scope-x/connection-y",
        "resource_scope_id": job["resource_scope_id"], "connection_id": job["connection_id"],
        "version_marker": "reviewed-version"}
    data = manifest()
    p = data["policies"]["synthetic-v2"]
    p.update(kind="customer", authentication_scheme="bearer",
        scope={k:job[k] for k in ("tenant_scope_id","workspace_id","facility_id","resource_scope_id","connection_id")},
        credential={k:job["credential"][k] for k in ("binding_id","provider","reference")},
        read_only_evidence="local-fixture-permission-denials")
    return job, data


def context(job):
    return ConnectorExecutionContext(configuration=job["configuration"], secret_binding=None,
        **{k:job[k] for k in ("tenant_scope_id","workspace_id","facility_id","resource_scope_id","connection_id")})


@pytest.mark.parametrize("role", ["api", "worker"])
@pytest.mark.parametrize("url", ["https://unapproved.example.test", "https://127.0.0.1", "https://169.254.169.254"])
def test_application_execution_cannot_forward_arbitrary_destinations(role, url, monkeypatch):
    # Both process roles use this remote adapter. Failure precedes secret or HTTP access.
    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", role)
    class NoSecretReads:
        def get_secret_value(self, **kwargs):
            pytest.fail("denied request attempted signing-key retrieval")
    provider = RemoteHttpsTelemetryConnector(endpoint="https://executor.internal:8443",
        ca_pem="BEGIN CERTIFICATE", auth_secret_arn="local-auth", secret_client=NoSecretReads())
    job = make_job(); job["configuration"]["base_url"] = url
    with pytest.raises(TelemetryConnectorError):
        provider.fetch_incremental(context(job))


@pytest.mark.parametrize("url", ["https://localhost", "https://127.5.6.7", "https://[::1]",
    "https://10.1.2.3", "https://172.31.1.2", "https://192.168.1.2", "https://169.254.1.2",
    "https://169.254.169.254", "https://[fe80::1]", "https://unapproved.example.test",
    f"https://{APPROVED_HOST}:8443", f"https://{APPROVED_HOST}.attacker.test",
    f"http://{APPROVED_HOST}"])
def test_signed_executor_denies_prohibited_destinations_before_child(tmp_path, monkeypatch, url):
    monkeypatch.setattr("app.services.connector_execution._execute_unprivileged",
        lambda *a, **kw: pytest.fail("denied job reached child"))
    key = "local-test-key-" * 4
    broker = ConnectorExecutionBroker(secret_store=FakeConnectorSecretStore(FakeSecretClient(key)),
        auth_secret_arn="executor-auth", replay_db_path=str(tmp_path / "replay.sqlite"))
    job = make_job(); job["configuration"]["base_url"] = url
    body, timestamp, signature = signed(job, key)
    with pytest.raises(TelemetryConnectorError):
        broker.execute(body, timestamp=timestamp, signature=signature)


@pytest.mark.parametrize("path", ["/control/setpoint", "/telemetry/../control/setpoint",
    "/telemetry/%2e%2e/control", "/telemetry%2fcontrol", "/%74elemetry", "/telemetry;control",
    "//attacker.test/control", "/telemetry/", "/TELEMETRY"])
def test_same_host_get_does_not_authorize_other_resources(path):
    job = make_job(); job["configuration"]["request_path"] = path
    with pytest.raises(TelemetryConnectorError):
        ConnectorExecutionBroker._validate_authority(job)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT"])
def test_resource_method_policy_is_get_only(method):
    policy = TelemetryResourcePolicyRegistry(manifest()).authorize_job(make_job())
    with pytest.raises(TelemetryEgressError):
        policy.authorize_request(f"https://{APPROVED_HOST}/telemetry", method=method)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT"])
def test_executor_rejects_configured_method_before_dispatch(method):
    job=make_job(); job["configuration"]["method"]=method
    with pytest.raises(TelemetryConnectorError): ConnectorExecutionBroker._validate_authority(job)


@pytest.mark.parametrize("operation", ["write", "command", "setpoint", "publish", "unknown"])
def test_executor_rejects_unsupported_operations(operation):
    with pytest.raises(TelemetryConnectorError):
        ConnectorExecutionBroker._validate_authority(make_job(operation=operation))


@pytest.mark.parametrize("field", ["tenant_scope_id", "workspace_id", "facility_id", "resource_scope_id", "connection_id"])
def test_executor_missing_authority_denies(field):
    with pytest.raises(TelemetryConnectorError):
        ConnectorExecutionBroker._validate_authority(make_job(**{field:""}))


@pytest.mark.parametrize("scope", ["tenant_scope_id", "workspace_id", "facility_id", "resource_scope_id", "connection_id"])
def test_even_correctly_signed_authority_cannot_relabel_customer_scope(scope):
    job, data = customer_job_and_registry()
    registry = TelemetryResourcePolicyRegistry(data)
    assert registry.authorize_job(job)
    job[scope] = "foreign-scope"
    with pytest.raises(TelemetryConnectorError):
        ConnectorExecutionBroker._validate_authority(job, resource_policy_registry=registry)


@pytest.mark.parametrize("field", ["binding_id", "reference", "provider", "version_marker"])
def test_missing_or_retargeted_credential_denies(field):
    job, data = customer_job_and_registry(); registry = TelemetryResourcePolicyRegistry(data)
    job["credential"].pop(field)
    with pytest.raises(TelemetryEgressError): registry.authorize_job(job)
    job["credential"] = None
    with pytest.raises(TelemetryEgressError): registry.authorize_job(job)


@pytest.mark.parametrize("change", [{"method":"POST"}, {"paths":[]}, {"paths":["/*"]},
    {"query":{"value":{"max_length":True}}}, {"allow_pagination":"false"},
    {"origin":"https://localhost"}, {"unexpected":True}])
def test_malformed_policy_denies(change):
    data = manifest(); data["policies"]["synthetic-v2"].update(change)
    with pytest.raises(TelemetryEgressError): TelemetryResourcePolicyRegistry(data)


def test_missing_policy_and_customer_permission_evidence_deny(monkeypatch, tmp_path):
    job = make_job(); job["configuration"].pop("resource_policy_id")
    with pytest.raises(TelemetryEgressError): TelemetryResourcePolicyRegistry.load().authorize_job(job)
    job["configuration"]["resource_policy_id"] = "nonexistent"
    with pytest.raises(TelemetryEgressError): TelemetryResourcePolicyRegistry.load().authorize_job(job)
    _, data = customer_job_and_registry(); data["policies"]["synthetic-v2"].pop("read_only_evidence")
    with pytest.raises(TelemetryEgressError): TelemetryResourcePolicyRegistry(data)
    path = tmp_path / "policy.json"; monkeypatch.setenv("NERAIUM_TELEMETRY_RESOURCE_POLICY_FILE", str(path))
    for raw in [b'{', b'{"version":"x","version":"y","policies":{}}', b'a' * (256*1024+1)]:
        path.write_bytes(raw)
        with pytest.raises(TelemetryEgressError): TelemetryResourcePolicyRegistry.load()
    path.unlink()
    with pytest.raises(TelemetryEgressError): TelemetryResourcePolicyRegistry.load()


def test_query_values_duplicates_and_patterns_are_constrained():
    data = manifest(); p = data["policies"]["synthetic-v2"]
    p.update(paths=["/telemetry/{segment}"], query={"limit":{"max_length":3,"values":["100"]}})
    job = make_job(); job["configuration"]["request_path"] = "/telemetry/tag_1"
    policy = TelemetryResourcePolicyRegistry(data).authorize_job(job)
    policy.authorize_request(f"https://{APPROVED_HOST}/telemetry/tag_2?limit=100")
    for path in ["/telemetry/tag_2?limit=101", "/telemetry/tag_2?limit=100&limit=100",
                 "/telemetry/tag_2?value=99", "/telemetry/a/b", "/telemetry/.."]:
        with pytest.raises(TelemetryEgressError): policy.authorize_request(f"https://{APPROVED_HOST}"+path)


@pytest.mark.parametrize("continuation", ["/control/setpoint", "https://unapproved.example.test/telemetry"])
def test_pagination_cannot_expand_resource_policy(continuation):
    data = manifest(); data["policies"]["synthetic-v2"]["allow_pagination"] = True
    job = make_job(); job["configuration"]["next_page_path"] = "next"
    job["configuration"]["records_path"] = "records"
    seen = []
    class Resolver:
        def resolve(self, *args): return ("93.184.216.34",)
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"records":[], "next":continuation})
    provider = HttpsTelemetryConnector(resource_policy_registry=TelemetryResourcePolicyRegistry(data),
        egress_policy=TelemetryEgressPolicy(resolver=Resolver()), transport=httpx.MockTransport(handler))
    with pytest.raises(TelemetryConnectorError): provider.fetch_incremental(context(job))
    assert len(seen) == 1


def test_approved_synthetic_get_works_and_redirects_are_denied():
    class Resolver:
        def resolve(self, *args): return ("93.184.216.34",)
    for status in [200,302]:
        seen=[]
        def handler(request):
            seen.append(request)
            assert request.method == "GET" and request.url.path == "/telemetry"
            return httpx.Response(status, json=[], headers={"location":"https://169.254.169.254/latest/meta-data"})
        provider=HttpsTelemetryConnector(egress_policy=TelemetryEgressPolicy(resolver=Resolver()), transport=httpx.MockTransport(handler))
        if status==200: assert provider.fetch_incremental(context(make_job())).observations == ()
        else:
            with pytest.raises(TelemetryConnectorError): provider.fetch_incremental(context(make_job()))
        assert len(seen)==1
