from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import evidence
from app.services.bedrock_interpreter import BedrockInterpretationDisabled, BedrockInterpretationError


@pytest.mark.asyncio
async def test_interpret_evidence_run_uses_governed_package_and_audits(monkeypatch):
    record = {"run_id": "run-1", "initiated_by": "tester"}
    package = {"governance": {"raw_telemetry_included": False}, "finding": {"status": "supported"}}
    generated = {
        "provider": "amazon_bedrock",
        "model_id": "amazon.nova-micro-v1:0",
        "interpretation": "Observed change...",
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        "authoritative_source": "neraium_evidence_package",
        "model_role": "interpretation_only",
    }
    audit_calls = []

    monkeypatch.setattr(evidence, "read_evidence_run", lambda run_id: record)
    monkeypatch.setattr(evidence, "build_evidence_package_payload", lambda value: package)
    monkeypatch.setattr(evidence, "interpret_evidence_package", lambda value: generated)

    async def allow_operator(request):
        return None

    monkeypatch.setattr(evidence, "require_operator_role", allow_operator)
    monkeypatch.setattr(evidence, "record_audit_event", lambda **kwargs: audit_calls.append(kwargs))

    request = SimpleNamespace(state=SimpleNamespace(auth_context={"auth_subject": "operator", "request_id": "req-1"}))
    response = await evidence.interpret_evidence_run(request, "run-1")

    assert response["run_id"] == "run-1"
    assert response["authoritative_source"] == "neraium_evidence_package"
    assert response["model_role"] == "interpretation_only"
    assert audit_calls[0]["action"] == "evidence.interpretation.generated"
    assert audit_calls[0]["detail"]["input_tokens"] == 10
    assert audit_calls[0]["detail"]["output_tokens"] == 20


@pytest.mark.asyncio
async def test_interpret_evidence_run_returns_404_for_unknown_run(monkeypatch):
    monkeypatch.setattr(evidence, "read_evidence_run", lambda run_id: None)
    monkeypatch.setattr(evidence, "read_evidence_by_identity", lambda run_id: None)
    request = SimpleNamespace(state=SimpleNamespace(auth_context={}))

    with pytest.raises(HTTPException) as exc:
        await evidence.interpret_evidence_run(request, "missing")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_interpret_evidence_run_returns_503_when_disabled(monkeypatch):
    monkeypatch.setattr(evidence, "read_evidence_run", lambda run_id: {"run_id": run_id})
    monkeypatch.setattr(evidence, "build_evidence_package_payload", lambda record: {"governance": {"raw_telemetry_included": False}})

    async def allow_operator(request):
        return None

    monkeypatch.setattr(evidence, "require_operator_role", allow_operator)

    def disabled(package):
        raise BedrockInterpretationDisabled("Bedrock interpretation is disabled.")

    monkeypatch.setattr(evidence, "interpret_evidence_package", disabled)
    request = SimpleNamespace(state=SimpleNamespace(auth_context={}))

    with pytest.raises(HTTPException) as exc:
        await evidence.interpret_evidence_run(request, "run-1")

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_interpret_evidence_run_returns_502_on_model_failure(monkeypatch):
    monkeypatch.setattr(evidence, "read_evidence_run", lambda run_id: {"run_id": run_id})
    monkeypatch.setattr(evidence, "build_evidence_package_payload", lambda record: {"governance": {"raw_telemetry_included": False}})

    async def allow_operator(request):
        return None

    monkeypatch.setattr(evidence, "require_operator_role", allow_operator)

    def failed(package):
        raise BedrockInterpretationError("Amazon Bedrock model invocation failed.")

    monkeypatch.setattr(evidence, "interpret_evidence_package", failed)
    request = SimpleNamespace(state=SimpleNamespace(auth_context={}))

    with pytest.raises(HTTPException) as exc:
        await evidence.interpret_evidence_run(request, "run-1")

    assert exc.value.status_code == 502
