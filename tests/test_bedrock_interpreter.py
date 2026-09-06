from __future__ import annotations

import pytest

from app.services.bedrock_interpreter import (
    BedrockInterpretationConfig,
    BedrockInterpretationDisabled,
    BedrockInterpretationError,
    get_bedrock_config,
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
        model_id="us.amazon.nova-micro-v1:0",
        region="us-east-2",
        max_tokens=500,
        temperature=0.1,
    )


def test_interpreter_is_opt_in() -> None:
    with pytest.raises(BedrockInterpretationDisabled):
        interpret_evidence_package({"governance": {"raw_telemetry_included": False}}, config=_config(False))


def test_staging_cluster_enables_bedrock_by_default(monkeypatch) -> None:
    monkeypatch.delenv("NERAIUM_BEDROCK_ENABLED", raising=False)
    monkeypatch.setenv("NERAIUM_ECS_CLUSTER", "neraium-staging-cluster")
    assert get_bedrock_config().enabled is True


def test_explicit_disable_overrides_staging_default(monkeypatch) -> None:
    monkeypatch.setenv("NERAIUM_ECS_CLUSTER", "neraium-staging-cluster")
    monkeypatch.setenv("NERAIUM_BEDROCK_ENABLED", "false")
    assert get_bedrock_config().enabled is False


def test_non_staging_remains_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("NERAIUM_BEDROCK_ENABLED", raising=False)
    monkeypatch.setenv("NERAIUM_ECS_CLUSTER", "neraium-prod-cluster")
    assert get_bedrock_config().enabled is False


def test_interpreter_refuses_raw_telemetry_packages() -> None:
    class NoModelCall:
        def converse(self, **kwargs):
            pytest.fail("Raw telemetry must be rejected before invoking Bedrock")

    with pytest.raises(BedrockInterpretationError, match="raw telemetry"):
        interpret_evidence_package({"governance": {"raw_telemetry_included": True}}, config=_config(), client=NoModelCall())


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

    assert client.request["modelId"] == "us.amazon.nova-micro-v1:0"
    assert client.request["inferenceConfig"]["temperature"] == 0.1
    assert "Never recalculate findings" in client.request["system"][0]["text"]
    prompt = client.request["system"][0]["text"]
    for boundary in ("why a physical condition occurred", "responsible component", "underlying issue", "measurable consequence", "non-quantifiability"):
        assert boundary in prompt
    assert "Root cause not established" in client.request["messages"][0]["content"][0]["text"]
    assert result["authoritative_source"] == "neraium_evidence_package"
    assert result["model_role"] == "interpretation_only"
    assert result["usage"]["total_tokens"] == 113


@pytest.mark.parametrize("text", ["Likely cause: blocked filter", "A diagnosis is pump failure", "The likely mechanism is valve leakage", "Corrective action: replace the pump"])
def test_interpreter_rejects_retired_conclusions(text):
    class RetiredOutputClient:
        def converse(self, **kwargs):
            assert "Do not produce causes" in kwargs["system"][0]["text"]
            return {"output": {"message": {"content": [{"text": text}]}}}
    with pytest.raises(BedrockInterpretationError, match="retired analytical attribution"):
        interpret_evidence_package({"governance": {"raw_telemetry_included": False}}, config=_config(), client=RetiredOutputClient())


@pytest.mark.parametrize("text", [
    "Driver: blocked filter",
    "Primary driver: pump degradation",
    "The driver appears to be valve leakage.",
    "Explanation: pump cavitation.",
    "The explanation is a failed valve.",
    "Reason: fouled heat exchanger.",
    "The reason for this condition is low refrigerant.",
    "Underlying issue: pump failure.",
    "Responsible component: valve.",
    "This occurred because the filter is blocked.",
    "This was caused by pump failure.",
    "The likely mechanism is seal leakage.",
    "Diagnosis: pump cavitation.",
    "Corrective action: replace the pump.",
    "Primary driver is the pump.",
    "The underlying issue is pump failure.",
    "The responsible component is the valve.",
    "Failure source: compressor.",
    "The source of the problem is the seal.",
    "This indicates pump failure.",
    "This suggests a failed valve.",
    "The explanation for the observed change is pump cavitation.",
    "The valve is responsible for this condition.",
    "**Driver:** blocked filter",
    "Reason — fouled heat exchanger.",
    "### Explanation\nPump cavitation.",
    "The reason this consequence is not quantifiable is insufficient timestamp coverage. Driver: blocked filter",
    "Explanation of calculation methodology: timestamp-aware trapezoidal integration; the explanation is a failed valve.",
    "No physical attribution is established from available evidence. This indicates pump failure.",
    "No physical attribution is established, but the driver appears to be valve leakage.",
    "This occurred\nbecause the filter is blocked.",
    "This indicates\npump failure.",
    "The reason for this\ncondition is low refrigerant.",
    "The likely\nmechanism is seal leakage.",
    "Corrective\naction: replace the pump.",
    "Reason: insufficient timestamp coverage because the pump failed.",
    "Explanation: timestamp-aware trapezoidal integration; underlying issue: valve leakage.",
    "Reason: missing timestamps. The explanation is pump cavitation.",
    "Drivers: pump degradation and valve leakage.",
    "The explanations are pump cavitation and a blocked filter.",
    "Corrective actions: replace the pump.",
])
def test_interpreter_rejects_renamed_physical_attribution(text):
    class AttributionClient:
        def converse(self, **kwargs):
            return {"output": {"message": {"content": [{"text": text}]}}}

    with pytest.raises(BedrockInterpretationError, match="retired analytical attribution"):
        interpret_evidence_package(
            {"governance": {"raw_telemetry_included": False}},
            config=_config(), client=AttributionClient(),
        )


@pytest.mark.parametrize("text", [
    "The relationship between flow and pressure changed persistently.",
    "Observed behavior remained above expected.",
    "Three relationships support this finding.",
    "The reason this consequence is not quantifiable is insufficient timestamp coverage.",
    "Explanation of calculation methodology: timestamp-aware trapezoidal integration.",
    "Demand is retained as operating context.",
    "No physical attribution is established from available evidence.",
    "The relationship between supply temperature and flow changed.",
    "This finding is supported by three relationships.",
    "The reason this result is not quantifiable is insufficient timestamp coverage.",
    "Explanation of the calculation methodology.",
    "Demand is a contextual driver variable in this relationship model.",
    "This indicates insufficient timestamp coverage.",
    "No physical cause is established from available evidence.",
    "Root cause is not established.",
    "Reason: insufficient timestamp coverage.",
    "The reason is missing timestamps.",
    "Explanation: timestamp-aware trapezoidal integration.",
    "The explanation is the calculation methodology.",
    "Demand is retained as a contextual driver.",
    "There are three supporting reasons.",
    "**Explanation of calculation methodology:**\nTimestamp-aware trapezoidal integration.\n\nDemand is retained as operating context.",
])
def test_interpreter_preserves_noncausal_observations_and_limitations(text):
    class ObservationClient:
        def converse(self, **kwargs):
            return {"output": {"message": {"content": [{"text": text}]}}}

    result = interpret_evidence_package(
        {"governance": {"raw_telemetry_included": False}},
        config=_config(), client=ObservationClient(),
    )
    assert result["interpretation"] == text
    assert result["authoritative_source"] == "neraium_evidence_package"
    assert result["model_role"] == "interpretation_only"


def test_interpreter_validates_attribution_across_converse_content_blocks():
    class SplitClient:
        def converse(self, **kwargs):
            return {"output": {"message": {"content": [
                {"text": "Three relationships support this finding. This occurred"},
                {"text": "because the filter is blocked."},
            ]}}}

    with pytest.raises(BedrockInterpretationError, match="retired analytical attribution"):
        interpret_evidence_package(
            {"governance": {"raw_telemetry_included": False}},
            config=_config(), client=SplitClient(),
        )
