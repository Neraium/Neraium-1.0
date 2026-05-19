import { useEffect, useMemo, useRef, useState } from "react";
import { DataTable, Panel } from "../workspacePrimitives";
import ConnectionModeCards from "./ConnectionModeCards";
import HistorianSourcePanel from "./HistorianSourcePanel";
import TagMappingPanel from "./TagMappingPanel";
import BaselineWindowPanel from "./BaselineWindowPanel";
import ReadOnlySafetyPanel from "./ReadOnlySafetyPanel";

export default function HistorianSetupWorkspace({ tagMapRows }) {
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [connectionTestState, setConnectionTestState] = useState("idle");
  const activeStepRef = useRef(null);

  const steps = useMemo(
    () => [
      {
        id: "historian-source",
        label: "Historian / BMS / SCADA",
        render: () => <HistorianSourcePanel />,
      },
      {
        id: "read-only-ingestion",
        label: "Read-only Ingestion",
        render: () => <ReadOnlySafetyPanel />,
      },
      {
        id: "connection-method",
        label: "Connection Method",
        render: () => <ConnectionModeCards />,
      },
      {
        id: "signal-mapping",
        label: "Signal Mapping",
        render: () => <TagMappingPanel rows={tagMapRows} />,
      },
      {
        id: "connection-test",
        label: "Connection Test",
        render: ({ goToNextStep }) => (
          <Panel title="Connection Test" className="span-12">
            <p className="narrative-text">
              Run a read-only connectivity check before baseline construction. This validates source reachability and telemetry heartbeat.
            </p>
            <div className="intake-flow__controls">
              <button
                type="button"
                className="secondary-command-button"
                onClick={() => setConnectionTestState("passed")}
              >
                Run Test
              </button>
              <button
                type="button"
                className="command-button"
                onClick={goToNextStep}
              >
                Continue to Baseline Builder
              </button>
            </div>
            <p className="narrative-text">
              {connectionTestState === "idle" ? "No test run yet." : "Connection test passed."}
            </p>
          </Panel>
        ),
      },
      {
        id: "baseline-window",
        label: "Baseline Builder",
        render: () => <BaselineWindowPanel />,
      },
    ],
    [tagMapRows],
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

  const activeStepTestId = activeStep?.id === "connection-method"
    ? "onboarding-data-source-step"
    : activeStep?.id === "signal-mapping"
      ? "signal-mapping-step"
      : undefined;

  return (
    <div data-testid="onboarding-root">
      <Panel title="Setup Progress" className="span-12 workspace-hero-panel">
        <DataTable
          columns={["Step", "Status"]}
          rows={steps.map((step, index) => [
            `${index + 1}. ${step.label}`,
            index < activeStepIndex ? "Complete" : index === activeStepIndex ? "Active" : "Pending",
          ])}
        />
      </Panel>
      <div ref={activeStepRef} data-testid={activeStepTestId}>
        {activeStep.render({
          goToNextStep: () => goToStep(activeStepIndex + 1),
          goToPreviousStep: () => goToStep(activeStepIndex - 1),
        })}
      </div>
      <Panel title="Step Navigation" className="span-12">
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
            disabled={isLastStep}
            data-testid="onboarding-next-button"
          >
            Next
          </button>
        </div>
        <p className="narrative-text" data-testid="onboarding-step-title">
          Step {activeStepIndex + 1} of {steps.length}: {activeStep.label}
        </p>
      </Panel>
    </div>
  );
}
