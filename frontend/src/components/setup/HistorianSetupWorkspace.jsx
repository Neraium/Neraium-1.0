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

export default function HistorianSetupWorkspace({ tagMapRows, onOpenUpload = null }) {
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [connection, setConnection] = useState(initialConnection);
  const [connectionTestState, setConnectionTestState] = useState("idle");
  const [isSetupComplete, setIsSetupComplete] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const activeStepRef = useRef(null);

  const steps = useMemo(
    () => [
      {
        id: "required-info",
        label: "Connection",
        render: () => (
          <Panel title="Required Connection Info" className="span-12 workspace-hero-panel">
            <p className="narrative-text">Add source type and endpoint, then continue.</p>
            <div className="setup-grid">
              <label>
                <span>Source Type</span>
                <input
                  aria-label="Source type"
                  placeholder="Historian, API, BMS/BAS"
                  value={connection.sourceType}
                  onChange={(event) => setConnection((current) => ({ ...current, sourceType: event.target.value }))}
                />
              </label>
              <label>
                <span>Endpoint</span>
                <input
                  aria-label="Endpoint"
                  placeholder="Host / endpoint"
                  value={connection.endpoint}
                  onChange={(event) => setConnection((current) => ({ ...current, endpoint: event.target.value }))}
                />
              </label>
            </div>
            <div className="intake-flow__controls">
              <button
                type="button"
                className="secondary-command-button"
                onClick={() => setShowAdvanced((current) => !current)}
                aria-expanded={showAdvanced}
              >
                {showAdvanced ? "Hide Optional Fields" : "Show Optional Fields"}
              </button>
            </div>
            {showAdvanced ? (
              <div className="setup-grid">
                <label>
                  <span>Authentication</span>
                  <input
                    aria-label="Authentication"
                    placeholder="Token, basic, service account"
                    value={connection.authMethod}
                    onChange={(event) => setConnection((current) => ({ ...current, authMethod: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Polling Interval (min)</span>
                  <input
                    aria-label="Polling interval"
                    placeholder="5"
                    value={connection.pollingMinutes}
                    onChange={(event) => setConnection((current) => ({ ...current, pollingMinutes: event.target.value }))}
                  />
                </label>
              </div>
            ) : null}
          </Panel>
        ),
      },
      {
        id: "signal-mapping",
        label: "Mapping",
        render: () => <TagMappingPanel rows={tagMapRows} />,
      },
      {
        id: "quick-verify",
        label: "Verify",
        render: () => (
          <Panel title="Quick Verify" className="span-12">
            <p className="narrative-text">Run one read-only check, then finish.</p>
            <div className="intake-flow__controls">
              <button
                type="button"
                className="secondary-command-button"
                onClick={() => setConnectionTestState("passed")}
              >
                Run Read-Only Check
              </button>
            </div>
            <p className="narrative-text">
              {connectionTestState === "idle" ? "No verification run yet." : "Read-only verification passed."}
            </p>
            {connectionTestState === "passed" ? (
              <div className="intake-flow__controls">
                <button
                  type="button"
                  className="command-button"
                  onClick={() => setIsSetupComplete(true)}
                >
                  Finish Setup
                </button>
              </div>
            ) : null}
            {isSetupComplete ? (
              <div className="intake-flow__controls" style={{ alignItems: "flex-start", flexDirection: "column", gap: 8 }}>
                <p className="narrative-text">Setup complete. Continue to upload telemetry data.</p>
                {typeof onOpenUpload === "function" ? (
                  <button type="button" className="command-button" onClick={onOpenUpload}>
                    Go to Upload
                  </button>
                ) : null}
              </div>
            ) : null}
          </Panel>
        ),
      },
    ],
    [connection, connectionTestState, isSetupComplete, onOpenUpload, showAdvanced, tagMapRows],
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
        <div className="setup-stepper" aria-hidden="true">
          {steps.map((step, index) => (
            <span
              key={step.id}
              className={index === activeStepIndex ? "is-active" : index < activeStepIndex ? "is-complete" : ""}
            >
              {index + 1}
            </span>
          ))}
        </div>
        <div className="intake-flow__controls">
          <button
            type="button"
            className="secondary-command-button"
            onClick={() => goToStep(activeStepIndex - 1)}
            disabled={isFirstStep}
          >
            Back
          </button>
          {!isLastStep ? (
            <button
              type="button"
              className="command-button"
              onClick={() => goToStep(activeStepIndex + 1)}
              disabled={!canGoNext}
              data-testid="onboarding-next-button"
            >
              Next
            </button>
          ) : null}
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
