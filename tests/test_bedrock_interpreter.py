from __future__ import annotations

import pytest

from app.services.bedrock_interpreter import (
    BedrockInterpretationConfig,
    BedrockInterpretationDisabled,
    BedrockInterpretationError,
    interpret_evidence_package,
)


class FakeBedrockClient:
    def __init__(self) -> None:
        self.request = None

    def converse(self, **kwargs):
        self.request = kwargs
        return {
            "output": {"message": {"content": [{"text": "Observed change\nA supported relationship changed."}]}},
            "usage": {"inputTokens": 101, "outputTokens": 12, "totalTokens": 113},
        }


def _config(enabled: bool = True) -> BedrockInterpretationConfig:
    return BedrockInterpretationConfig(
        enabled=enabled,
        model_id="amazon.nova-micro-v1:0",
        region="us-east-1",
        max_tokens=500,
        temperature=0.1,
    )


def test_interpreter_is_opt_in() -> None:
    with pytest.raises(BedrockInterpretationDisabled):
        interpret_evidence_package({"governance": {"raw_telemetry_included": False}}, config=_config(False))


def test_interpreter_refuses_raw_telemetry_packages() -> None:
    with pytest.raises(BedrockInterpretationError, match="raw telemetry"):
        interpret_evidence_package({"governance": {"raw_telemetry_included": True}}, config=_config())


def test_interpreter_uses_converse_without_changing_authoritative_role() -> None:
    client = FakeBedrockClient()
    result = interpret_evidence_package(
        {
            "governance": {"raw_telemetry_included": False},
            "change_summary": "Pump demand no longer matches hydraulic response.",
            "limitations": ["Root cause not established."],
        },
        config=_config(),
        client=client,
    )

    assert client.request["modelId"] == "amazon.nova-micro-v1:0"
    assert client.request["inferenceConfig"]["temperature"] == 0.1
    assert "Never recalculate findings" in client.request["system"][0]["text"]
    assert "Root cause not established" in client.request["messages"][0]["content"][0]["text"]
    assert result["authoritative_source"] == "neraium_evidence_package"
    assert result["model_role"] == "interpretation_only"
    assert result["usage"]["total_tokens"] == 113
