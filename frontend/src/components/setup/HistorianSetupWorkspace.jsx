import { useEffect, useMemo, useRef, useState } from "react";
import { Panel } from "../workspacePrimitives";
import TagMappingPanel from "./TagMappingPanel";

function initialConnection() {
  return {
    sourceType: "",
    endpoint: "",
    authMethod: "",
    pollingMinutes: "5",
  };
}

export default function HistorianSetupWorkspace({ tagMapRows }) {
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [connection, setConnection] = useState(initialConnection);
  const [connectionTestState, setConnectionTestState] = useState("idle");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const activeStepRef = useRef(null);

  const steps = useMemo(
    () => [
      {
        id: "required-info",
        label: "Connection Info",
        render: () => (
          <Panel title="Required Connection Info" className="span-12 workspace-hero-panel">
            <p className="narrative-text">Enter only the required fields to start ingesting telemetry.</p>
            <div className="intake-flow__controls" style={{ display: "grid", gap: 10 }}>
              <input
                aria-label="Source type"
                placeholder="Source type (Historian, API, BMS/BAS)"
                value={connection.sourceType}
                onChange={(event) => setConnection((current) => ({ ...current, sourceType: event.target.value }))}
              />
              <input
                aria-label="Endpoint"
                placeholder="Host / endpoint"
                value={connection.endpoint}
                onChange={(event) => setConnection((current) => ({ ...current, endpoint: event.target.value }))}
              />
              <button
                type="button"
                className="secondary-command-button"
                onClick={() => setShowAdvanced((current) => !current)}
                aria-expanded={showAdvanced}
              >
                {showAdvanced ? "Hide Advanced" : "Show Advanced"}
              </button>
              {showAdvanced ? (
                <>
              <input
                aria-label="Authentication"
                placeholder="Auth method (token/basic/service account)"
                value={connection.authMethod}
                onChange={(event) => setConnection((current) => ({ ...current, authMethod: event.target.value }))}
              />
              <input
                aria-label="Polling interval"
                placeholder="Polling interval in minutes"
                value={connection.pollingMinutes}
                onChange={(event) => setConnection((current) => ({ ...current, pollingMinutes: event.target.value }))}
              />
                </>
              ) : null}
            </div>
          </Panel>
        ),
      },
      {
        id: "signal-mapping",
        label: "Signal Mapping",
        render: () => <TagMappingPanel rows={tagMapRows} />,
      },
      {
        id: "quick-verify",
        label: "Quick Verify",
        render: () => (
          <Panel title="Quick Verify" className="span-12">
            <p className="narrative-text">Read-only connectivity check.</p>
            <div className="intake-flow__controls">
              <button
                type="button"
                className="secondary-command-button"
                onClick={() => setConnectionTestState("passed")}
              >
                Run Test
              </button>
            </div>
            <p className="narrative-text">
              {connectionTestState === "idle" ? "No test run yet." : "Connection test passed."}
            </p>
          </Panel>
        ),
      },
    ],
    [connection, connectionTestState, tagMapRows],
  );

  const activeStep = steps[activeStepIndex] ?? steps[0];
  const isFirstStep = activeStepIndex === 0;
  const isLastStep = activeStepIndex === steps.length - 1;

  useEffect(() => {
    activeStepRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [activeStepIndex]);

  function goToStep(index) {
    const next = Math.max(0, Math.min(index, steps.length - 1));
    setActiveStepIndex(next);
  }

  const canGoNext =
    activeStep.id !== "required-info"
      || (connection.sourceType.trim() && connection.endpoint.trim());
  const activeStepTestId = activeStep?.id === "required-info"
    ? "onboarding-data-source-step"
    : activeStep?.id === "signal-mapping"
      ? "signal-mapping-step"
      : undefined;

  return (
    <div data-testid="onboarding-root">
      <Panel title="Quick Setup" className="span-12 workspace-hero-panel">
        <p className="narrative-text" data-testid="onboarding-step-title">
          Step {activeStepIndex + 1} of {steps.length}: {activeStep.label}
        </p>
        <div className="intake-flow__controls">
          <button
            type="button"
            className="secondary-command-button"
            onClick={() => goToStep(activeStepIndex - 1)}
            disabled={isFirstStep}
          >
            Back
          </button>
          <button
            type="button"
            className="command-button"
            onClick={() => goToStep(activeStepIndex + 1)}
            disabled={isLastStep || !canGoNext}
            data-testid="onboarding-next-button"
          >
            Next
          </button>
        </div>
      </Panel>
      <div ref={activeStepRef} data-testid={activeStepTestId}>
        {activeStep.render({
          goToNextStep: () => goToStep(activeStepIndex + 1),
          goToPreviousStep: () => goToStep(activeStepIndex - 1),
        })}
      </div>
    </div>
  );
}
