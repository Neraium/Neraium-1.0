"""The release preserves the certified rotating auth binding and ALB health contract."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_api_uses_rotating_rds_auth_secret_and_tls():
    baseline = json.loads((ROOT / 'docs/operations/first-customer-production-baseline-2026-10-03.json').read_text())
    api = baseline['services']['api']
    env = api['configuration']
    assert env['NERAIUM_AUTH_DATABASE_SECRET_ARN'].startswith('arn:aws:secretsmanager:us-east-2:680779862188:secret:rds!db-')
    assert env['NERAIUM_AUTH_DATABASE_SSLMODE'] == 'require'
    assert 'NERAIUM_AUTH_DATABASE_URL' not in {s['name'] for s in api['secret_bindings']}
    assert api['topology']['loadBalancers'][0]['containerPort'] == 8080
    # Candidate task fingerprint tests enforce exact preservation of this baseline,
    # including the inherited quoted health command, instead of reconstructing it.
    assert baseline['services']['worker']['topology']['loadBalancers'] == []
    bootstrap = (ROOT / 'scripts/bootstrap-production-aws.sh').read_text()
    assert '"Action": ["secretsmanager:GetSecretValue"]' in bootstrap
    assert '"Action": ["kms:Decrypt"]' in bootstrap
