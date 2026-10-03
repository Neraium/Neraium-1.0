from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('production_release', ROOT / 'scripts/production_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
REVISION = 'a' * 40
IMAGE = '680779862188.dkr.ecr.us-east-2.amazonaws.com/neraium-prod-api@sha256:' + 'b' * 64


@pytest.fixture
def boundary():
    profile = json.loads(release.BASELINE.read_text())
    definitions = {}
    for role in ('api', 'worker'):
        env = deepcopy(profile['services'][role]['configuration'])
        env['NERAIUM_TELEMETRY_EXECUTOR_CA_PEM'] = 'synthetic-trust-anchor'
        env['NERAIUM_BUILD_SHA'] = 'previous'
        definitions[role] = {
            'family': 'neraium-prod-' + role, 'networkMode': 'awsvpc',
            'requiresCompatibilities': ['FARGATE'], 'taskRoleArn': 'app-role',
            'executionRoleArn': 'execution-role', 'cpu': '1024', 'memory': '2048', 'volumes': [],
            'containerDefinitions': [{
                'name': role, 'image': profile['image_uri'],
                'environment': [{'name': k, 'value': v} for k, v in env.items()],
                'secrets': deepcopy(profile['services'][role]['secret_bindings']),
                'command': ['python', '-m', 'app.entrypoint'],
                'portMappings': [{'containerPort': 8080, 'protocol': 'tcp'}] if role == 'api' else [],
                'healthCheck': {'command': ['CMD-SHELL', "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')\""]} if role == 'api' else {},
            }],
        }
        profile['services'][role]['task_configuration_sha256'] = release.task_fingerprint(definitions[role])
    profile['executor']['ca_sha256'] = hashlib.sha256(b'synthetic-trust-anchor').hexdigest()
    return profile, definitions


@pytest.mark.parametrize('role', ['api', 'worker'])
def test_only_image_and_build_marker_change(boundary, role):
    profile, definitions = boundary
    original = deepcopy(definitions[role])
    candidate = release.candidate_task(original, IMAGE, REVISION, role, profile)
    assert release.task_fingerprint(candidate) == release.task_fingerprint(original)
    assert candidate['containerDefinitions'][0]['image'] == IMAGE
    assert release.mappings(candidate['containerDefinitions'][0]['environment'], 'value')['NERAIUM_BUILD_SHA'] == REVISION
    assert candidate['containerDefinitions'][0]['secrets'] == original['containerDefinitions'][0]['secrets']
    assert definitions[role] == original


@pytest.mark.parametrize('role', ['api', 'worker'])
@pytest.mark.parametrize('name,value', [
    ('NERAIUM_TELEMETRY_EXECUTION_IDENTITY_VERSION', 'concept-keyed.v1'),
    ('NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED', 'false'),
    ('NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES', 'true'),
    ('NERAIUM_TELEMETRY_EXECUTOR_URL', 'http://untrusted.invalid'),
    ('NERAIUM_TELEMETRY_EXECUTOR_AUTH_SECRET_ARN', ''),
    ('NERAIUM_TELEMETRY_EXECUTOR_CA_PEM', ''),
    ('NERAIUM_PROCESS_ROLE', 'combined'),
])
def test_runtime_regressions_fail_before_candidate_creation(boundary, role, name, value):
    profile, definitions = boundary
    for item in definitions[role]['containerDefinitions'][0]['environment']:
        if item['name'] == name:
            item['value'] = value
    with pytest.raises(release.GateError):
        release.candidate_task(definitions[role], IMAGE, REVISION, role, profile)


@pytest.mark.parametrize('name', ['NERAIUM_TELEMETRY_DATABASE_URL', 'NERAIUM_RUNTIME_DATABASE_URL', 'NERAIUM_API_TOKEN', 'NERAIUM_BOOTSTRAP_ADMIN_PASSWORD'])
def test_required_secret_removal_fails_closed(boundary, name):
    profile, definitions = boundary
    definition = definitions['api']
    definition['containerDefinitions'][0]['secrets'] = [s for s in definition['containerDefinitions'][0]['secrets'] if s['name'] != name]
    with pytest.raises(release.GateError):
        release.candidate_task(definition, IMAGE, REVISION, 'api', profile)


@pytest.mark.parametrize('name', ['NERAIUM_INFRA_MONITOR_ENABLED', 'NERAIUM_INFRA_ALERT_SNS_TOPIC_ARN', 'NERAIUM_AUTH_DATABASE_SSLMODE', 'NERAIUM_AUTH_DATABASE_SECRET_ARN'])
def test_monitoring_and_auth_configuration_removal_fails_closed(boundary, name):
    profile, definitions = boundary
    definition = definitions['api']
    definition['containerDefinitions'][0]['environment'] = [s for s in definition['containerDefinitions'][0]['environment'] if s['name'] != name]
    with pytest.raises(release.GateError):
        release.candidate_task(definition, IMAGE, REVISION, 'api', profile)


@pytest.mark.parametrize('image', ['repository:latest', IMAGE.replace('neraium-prod-api', 'unapproved'), IMAGE.replace('680779862188', '111111111111'), IMAGE.replace('us-east-2', 'us-east-1'), IMAGE.replace('@sha256:', ':release-')])
def test_unapproved_or_mutable_image_rejected(boundary, image):
    profile, definitions = boundary
    with pytest.raises(release.GateError, match='approved_repository_digest'):
        release.candidate_task(definitions['api'], image, REVISION, 'api', profile)


def test_duplicate_environment_name_rejected(boundary):
    profile, definitions = boundary
    definitions['api']['containerDefinitions'][0]['environment'].append({'name': 'APP_ENV', 'value': 'prod'})
    with pytest.raises(release.GateError, match='duplicate'):
        release.validate_task(definitions['api'], 'api', profile)


@pytest.mark.parametrize('field,value', [('taskRoleArn', 'untrusted'), ('networkMode', 'host'), ('family', 'neraium-prod-worker')])
def test_task_security_topology_drift_rejected(boundary, field, value):
    profile, definitions = boundary
    definitions['api'][field] = value
    with pytest.raises(release.GateError):
        release.validate_task(definitions['api'], 'api', profile)


@pytest.mark.parametrize('path', ['backend/requirements.txt', 'backend/app/routers/data_connections.py', 'backend/app/services/production_health.py', 'backend/db/migrations/apply_telemetry.py'])
def test_protected_source_change_requires_recertification(monkeypatch, path):
    profile = json.loads(release.BASELINE.read_text())
    assert path in profile['protected_source']
    original = release.git
    def altered(*args):
        data = original(*args)
        return data + b'\n# unreviewed change\n' if args == ('show', profile['repository_revision'] + ':' + path) else data
    monkeypatch.setattr(release, 'git', altered)
    with pytest.raises(release.GateError, match='protected_source_change'):
        release.source_manifest(profile['repository_revision'], profile)


def test_clean_committed_manifest_ignores_dirty_worktree():
    profile = json.loads(release.BASELINE.read_text())
    assert release.source_manifest(profile['repository_revision'], profile) == profile['source_manifest']


def test_general_unprotected_code_release_is_supported(monkeypatch):
    profile = json.loads(release.BASELINE.read_text())
    path = 'backend/app/routers/app_info.py'
    assert path in profile['source_manifest'] and path not in profile['protected_source']
    original = release.git
    def altered(*args):
        data = original(*args)
        return data + b'\n# reviewed general release\n' if args == ('show', profile['repository_revision'] + ':' + path) else data
    monkeypatch.setattr(release, 'git', altered)
    assert release.source_manifest(profile['repository_revision'], profile)[path] != profile['source_manifest'][path]


@pytest.mark.parametrize('revision', ['main', 'HEAD', 'a' * 7, 'a' * 40 + '; echo unsafe'])
def test_ambiguous_source_rejected(revision):
    with pytest.raises(release.GateError, match='full_source_sha'):
        release.source_manifest(revision, {})


class FakeProduction:
    def __init__(self, boundary, fail=None):
        self.profile, self.definitions = deepcopy(boundary)
        self.current = {r: self.profile['services'][r]['task_definition'] for r in self.definitions}
        self.registered = {}
        self.updates = []
        self.fail = fail
        self.probes = 0
        self.ecs = self
    def snapshot(self):
        return {r: {'task': self.registered.get(self.current[r], self.definitions[r]),
                    'service': {'taskDefinition': self.current[r]}} for r in self.definitions}
    def check(self, state, revisions=None, image=None):
        if self.fail == 'preflight': raise release.GateError('preflight_failed')
        for role in state:
            release.validate_task(state[role]['task'], role, self.profile)
            assert state[role]['service']['taskDefinition'] == (revisions or self.profile['rollback'])[role]
        if image and self.fail == 'postflight': raise release.GateError('postflight_failed')
        return {'status': 'PASS'}
    def register_task_definition(self, **candidate):
        role = candidate['containerDefinitions'][0]['name']
        arn = 'next-' + role
        self.registered[arn] = candidate
        return {'taskDefinition': {**candidate, 'taskDefinitionArn': arn}}
    def update_service(self, **args):
        role = 'api' if args['service'].endswith('api-service') else 'worker'
        self.updates.append((role, args['taskDefinition']))
        self.current[role] = args['taskDefinition']
    def wait(self):
        if self.fail == 'worker' and self.current['worker'] == 'next-worker':
            raise release.GateError('worker_gate_failed')
    def probe(self, state):
        self.probes += 1
        if self.fail == 'probe' and self.probes == 2: raise release.GateError('post_probe_failed')
        return {'status': 'PASS'}
    def post_events(self, state):
        if self.fail == 'monitoring': raise release.GateError('monitoring_missing')


def test_dry_run_has_no_aws_writes(boundary):
    production = FakeProduction(boundary)
    result = release.deploy(production, IMAGE, REVISION, production.profile)
    assert 'plan' in result and not production.registered and not production.updates and production.probes == 0


def test_failed_preflight_has_no_aws_writes(boundary):
    production = FakeProduction(boundary, 'preflight')
    with pytest.raises(release.GateError):
        release.deploy(production, IMAGE, REVISION, production.profile, True)
    assert not production.registered and not production.updates


def test_valid_rollout_uses_one_coordinator(boundary):
    production = FakeProduction(boundary)
    result = release.deploy(production, IMAGE, REVISION, production.profile, True)
    assert result['deployment'] == 'PASS'
    assert production.updates == [('worker', 'next-worker'), ('api', 'next-api')]
    assert production.probes == 2


@pytest.mark.parametrize('gate', ['worker', 'postflight', 'probe', 'monitoring'])
def test_failed_rollout_restores_and_verifies_exact_baseline(boundary, gate):
    production = FakeProduction(boundary, gate)
    result = release.deploy(production, IMAGE, REVISION, production.profile, True)
    assert result['status'] == 'FAIL' and result['rollback'] == 'PASS'
    assert production.current == production.profile['rollback']
    assert production.updates[-2:] == [('api', production.profile['rollback']['api']), ('worker', production.profile['rollback']['worker'])]
    assert 'failed' in result['reason'] or 'missing' in result['reason']


def test_workflow_defaults_to_plan_and_only_calls_canonical_cli():
    workflow = yaml.safe_load((ROOT / '.github/workflows/deploy-backend.yml').read_text())
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'workflow_dispatch'}
    assert triggers['workflow_dispatch']['inputs']['apply']['default'] is False
    assert workflow['concurrency']['cancel-in-progress'] is False
    assert workflow['jobs']['release']['if'] == "github.ref == 'refs/heads/fix/deterministic-governed-output'"
    runs = '\n'.join(step.get('run', '') for step in workflow['jobs']['release']['steps'])
    assert 'production_release.py build' in runs and 'production_release.py deploy' in runs
    assert 'aws ecs update-service' not in runs and 'aws secretsmanager get-secret-value' not in runs
    assert 'Dockerfile.connector-overlay' not in runs


@pytest.mark.parametrize('mutation', ['user', 'labels', 'base_layers', 'source_bytes', 'manifest'])
def test_image_certification_rejects_forged_or_inconsistent_provenance(monkeypatch, mutation):
    profile = json.loads(release.BASELINE.read_text())
    content = b'print("synthetic source")\n'
    files = {'backend/app/example.py': hashlib.sha256(content).hexdigest()}
    monkeypatch.setattr(release, 'source_manifest', lambda *_: files)
    base = {'RootFS': {'Layers': ['certified-layer']}, 'Config': {'User': 'neraium', 'Env': ['PYTHONPATH=/app'], 'Entrypoint': None, 'Cmd': ['python', '-m', 'app.entrypoint']}}
    candidate = deepcopy(base)
    candidate['RootFS']['Layers'].append('source-layer')
    candidate['Config']['Labels'] = {'org.opencontainers.image.revision': REVISION, 'com.neraium.release.method': release.METHOD}
    if mutation == 'user': candidate['Config']['User'] = 'root'
    if mutation == 'labels': candidate['Config']['Labels']['org.opencontainers.image.revision'] = 'wrong'
    if mutation == 'base_layers': candidate['RootFS']['Layers'][0] = 'unapproved-runtime'
    def output(command, **kwargs):
        if command[:3] == ['docker', 'image', 'inspect']:
            return json.dumps([base if command[3] == profile['image_uri'] else candidate]).encode()
        assert command == ['docker', 'create', 'candidate']
        return b'isolated-container'
    def run(command, **kwargs):
        if command[:2] == ['docker', 'cp']:
            destination = Path(command[-1])
            (destination / 'app').mkdir()
            (destination / 'app/example.py').write_bytes(content + (b'# tampered' if mutation == 'source_bytes' else b''))
            metadata = {'method': release.METHOD, 'source_sha': REVISION, 'base_image': profile['image_uri'], 'baseline_sha256': hashlib.sha256(release.BASELINE.read_bytes()).hexdigest(), 'source_manifest': files}
            if mutation == 'manifest': metadata['base_image'] = 'unapproved'
            (destination / 'neraium-release.json').write_text(json.dumps(metadata))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(release.subprocess, 'check_output', output)
    monkeypatch.setattr(release.subprocess, 'run', run)
    with pytest.raises(release.GateError):
        release.certify_image('candidate', REVISION, profile)


def test_unapproved_remote_source_is_rejected(monkeypatch):
    profile = json.loads(release.BASELINE.read_text())
    monkeypatch.setattr(release, 'git', lambda *args: (profile['repository_revision'] + '\n').encode())
    monkeypatch.setattr(release.subprocess, 'run', lambda command, **kwargs: subprocess.CompletedProcess(command, 1))
    with pytest.raises(release.GateError, match='approved_remote_branch'):
        release.source_manifest(profile['repository_revision'], profile)


@pytest.mark.parametrize('mutation', ['load_balancer', 'desired_count', 'image'])
def test_live_service_topology_and_image_drift_stop_release(boundary, mutation):
    profile, definitions = boundary
    state = {}
    for role in ('api', 'worker'):
        frozen = profile['services'][role]
        service = {**deepcopy(frozen['topology']), 'taskDefinition': frozen['task_definition'], 'status': 'ACTIVE', 'runningCount': 1, 'pendingCount': 0, 'deployments': [{'rolloutState': 'COMPLETED'}]}
        state[role] = {'service': service, 'task': definitions[role], 'running': [{'taskDefinitionArn': frozen['task_definition'], 'lastStatus': 'RUNNING', 'containers': [{'imageDigest': profile['image_uri'].split('@')[1]}]}]}
    if mutation == 'load_balancer': state['api']['service']['loadBalancers'][0]['containerPort'] = 80
    if mutation == 'desired_count': state['api']['service']['desiredCount'] = 0
    if mutation == 'image': state['api']['task']['containerDefinitions'][0]['image'] = IMAGE
    production = release.Production.__new__(release.Production)
    production.profile = profile
    with pytest.raises(release.GateError):
        production.check(state)


def test_monitoring_fingerprint_detects_disabled_alarm_and_filter_loss():
    alarms = [{'AlarmName': 'synthetic', 'ActionsEnabled': True, 'Threshold': 3, 'StateValue': 'OK'}]
    filters = {'api': [{'filterName': 'synthetic', 'filterPattern': 'completed'}]}
    expected = release.monitoring_fingerprint(alarms, filters)
    alarms[0]['StateValue'] = 'ALARM'
    assert release.monitoring_fingerprint(alarms, filters) == expected
    alarms[0]['ActionsEnabled'] = False
    assert release.monitoring_fingerprint(alarms, filters) != expected
    alarms[0]['ActionsEnabled'] = True
    filters['api'] = []
    assert release.monitoring_fingerprint(alarms, filters) != expected


@pytest.mark.parametrize('endpoint,status', [('health', 'ok'), ('ready', 'ready')])
def test_health_gate_accepts_only_certified_api_json(endpoint, status):
    release.validate_health_response(json.dumps({'service': 'neraium-api', 'status': status}).encode(), endpoint)
    for body in (b'<html>SPA</html>', b'{}', b'[]', b'{"service":"other","status":"ok"}', b'{"service":"neraium-api","status":"failed"}'):
        with pytest.raises(release.GateError, match='invalid_response'):
            release.validate_health_response(body, endpoint)


@pytest.mark.parametrize('mutation', ['valid', 'runtime_file', 'symlink', 'whiteout'])
def test_overlay_layers_cannot_modify_runtime_or_add_uncommitted_files(mutation):
    import io
    import tarfile
    payload = b'committed source'
    allowed = {'app/example.py': hashlib.sha256(payload).hexdigest()}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        entry = tarfile.TarInfo({'runtime_file': 'usr/lib/unsafe.py', 'whiteout': 'app/.wh.example.py'}.get(mutation, 'app/example.py'))
        entry.mode = 0o644
        if mutation == 'symlink':
            entry.type = tarfile.SYMTYPE
            entry.linkname = '/unapproved'
            archive.addfile(entry)
        else:
            entry.size = len(payload)
            archive.addfile(entry, io.BytesIO(payload))
    buffer.seek(0)
    with tarfile.open(fileobj=buffer) as layer:
        if mutation == 'valid':
            release.validate_overlay_layer(layer, allowed)
        else:
            with pytest.raises(release.GateError, match='outside_source'):
                release.validate_overlay_layer(layer, allowed)
