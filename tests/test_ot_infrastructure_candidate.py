"""Candidate infrastructure and runtime schema checks; never applies AWS changes."""
from pathlib import Path
import json

import pytest

from app.services.auth_store import _PostgresAuthBackend, AUTH_SCHEMA_MIGRATIONS

ROOT = Path(__file__).resolve().parents[1]


def test_application_sg_has_no_general_internet_or_controller_egress():
    template = json.loads((ROOT / "infra/production/ot-boundary-candidate.json").read_text())
    rules = template["Resources"]["ApplicationSecurityGroup"]["Properties"]["SecurityGroupEgress"]
    assert {(r["FromPort"], r["ToPort"]) for r in rules} == {(443,443),(5432,5432),(8443,8443)}
    assert all(r["IpProtocol"] == "tcp" and "CidrIp" not in r and "CidrIpv6" not in r for r in rules)
    assert {r.get("DestinationSecurityGroupId",{}).get("Ref") for r in rules} == {
        "RdsSecurityGroupId", "ExecutorSecurityGroupId", "EndpointSecurityGroup", None}
    assert len([r for r in rules if "DestinationPrefixListId" in r]) == 1


def test_master_and_source_secret_reads_are_explicitly_denied_and_staged():
    t=json.loads((ROOT / "infra/production/ot-boundary-candidate.json").read_text())
    p=t["Resources"]["RuntimeSecretSeparation"]
    assert p["Condition"] == "RuntimeIdentityQualified"
    assert t["Parameters"]["EnableRuntimeSecretSeparation"]["Default"] == "false"
    statements=p["Properties"]["PolicyDocument"]["Statement"]
    deny=next(s for s in statements if s["Effect"]=="Deny")
    assert deny["Action"]=="secretsmanager:GetSecretValue"
    assert {"Ref":"RdsMasterSecretArn"} in deny["Resource"]
    assert any("telemetry-connections/*" in json.dumps(r) for r in deny["Resource"])
    assert t["Parameters"]["EnablePrivateDns"]["Default"] == "false"
    assert t["Parameters"]["EnableDnsFirewall"]["Default"] == "false"


def test_executor_secret_boundary_and_metadata_are_independent_of_app_role():
    t=json.loads((ROOT / "infra/production/ot-boundary-candidate.json").read_text())
    p=t["Resources"]["ExecutorSecretSeparation"]
    assert p["Properties"]["Roles"] == [{"Ref":"ExecutorRoleName"}]
    deny=p["Properties"]["PolicyDocument"]["Statement"][0]
    assert deny["Effect"] == "Deny"
    assert deny["NotResource"]["Fn::If"][2] == [{"Ref":"ExecutorAuthSecretArn"},{"Ref":"ExecutorTlsSecretArn"}]
    assert t["Resources"]["ExecutorMetadataLaunchTemplate"]["Properties"]["LaunchTemplateData"]["MetadataOptions"]["HttpTokens"] == "required"


class FakeConnection:
    def __init__(self, *, privileged=False, migrated=True, ledger_write=False):
        self.privileged, self.migrated, self.ledger_write = privileged, migrated, ledger_write
        self.statements=[]
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql):
        self.statements.append(sql)
        self.sql=sql
        assert sql.startswith("SELECT"), "runtime attempted DDL or mutation"
        return self
    def fetchone(self):
        return (self.privileged if "FROM pg_roles" in self.sql else self.ledger_write,)
    def fetchall(self):
        return [(m,) for m in AUTH_SCHEMA_MIGRATIONS] if self.migrated else []


def test_production_auth_startup_needs_no_schema_writes(monkeypatch):
    monkeypatch.setenv("APP_ENV","prod")
    backend=_PostgresAuthBackend("local-mock-only")
    conn=FakeConnection()
    monkeypatch.setattr(backend,"_connect",lambda:conn)
    backend.ensure_schema()
    assert len(conn.statements)==7


@pytest.mark.parametrize("failure", ["privileged","migrated","ledger_write"])
def test_privileged_or_unmigrated_auth_runtime_fails_closed(monkeypatch, failure):
    monkeypatch.setenv("APP_ENV","prod")
    backend=_PostgresAuthBackend("local-mock-only")
    conn=FakeConnection(**{failure:False if failure=="migrated" else True})
    monkeypatch.setattr(backend,"_connect",lambda:conn)
    with pytest.raises(RuntimeError): backend.ensure_schema()
