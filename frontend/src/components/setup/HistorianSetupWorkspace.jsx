import { useEffect, useMemo, useRef, useState } from "react";
import { DataTable, Panel } from "../workspacePrimitives";
import ConnectionModeCards from "./ConnectionModeCards";
import HistorianSourcePanel from "./HistorianSourcePanel";
import TagMappingPanel from "./TagMappingPanel";
import BaselineWindowPanel from "./BaselineWindowPanel";
import ReadOnlySafetyPanel from "./ReadOnlySafetyPanel";

export default function HistorianSetupWorkspace({ tagMapRows }) {
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const activeStepRef = useRef(null);

  const steps = useMemo(
    () => [
      {
        id: "historian-source",
        label: "1. Historian / BMS / SCADA",
        render: () => <HistorianSourcePanel />,
      },
      {
        id: "read-only-ingestion",
        label: "2. Read-only Ingestion",
        render: () => <ReadOnlySafetyPanel />,
      },
      {
        id: "intake-connector",
        label: "3. Neraium Intake Connector",
        render: () => <ConnectionModeCards />,
      },
      {
        id: "signal-mapping",
        label: "4. Signal Mapping",
        render: ({ goToNextStep }) => <TagMappingPanel rows={tagMapRows} onContinue={goToNextStep} />,
      },
      {
        id: "baseline-window",
        label: "5. Baseline Builder",
        render: () => <BaselineWindowPanel />,
      },
      {
        id: "live-structural-analysis",
        label: "6. Live Structural Analysis",
        render: () => (
          <Panel title="Live Structural Analysis" className="span-12">
            <p className="narrative-text">
              Real-time telemetry is compared against baseline relationships to detect structural drift and generate governed findings.
            </p>
          </Panel>
        ),
      },
      {
        id: "operator-ui-reports",
        label: "7. Operator UI / Reports",
        render: () => (
          <Panel title="Operator UI / Reports" className="span-12">
            <p className="narrative-text">
              Findings are surfaced to operators with supporting evidence, timeline context, and recommended next actions.
            </p>
          </Panel>
        ),
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

  return (
    <>
      <Panel title="Historian Intake Architecture" className="span-12 workspace-hero-panel">
        <DataTable
          columns={["Pipeline Stage"]}
          rows={[
            ["Historian / BMS / SCADA"],
            ["read-only ingestion"],
            ["Neraium Intake Connector"],
            ["Tag Mapper + Normalizer"],
            ["Baseline Builder"],
            ["Live Structural Analysis"],
            ["Operator UI / Reports"],
          ]}
        />
      </Panel>
      <Panel title="Setup Progress" className="span-12">
        <div className="intake-flow__controls" role="tablist" aria-label="Historian setup steps">
          {steps.map((step, index) => (
            <button
              key={step.id}
              type="button"
              role="tab"
              aria-selected={activeStepIndex === index}
              className={activeStepIndex === index ? "command-button" : "secondary-command-button"}
              onClick={() => goToStep(index)}
            >
              {step.label}
            </button>
          ))}
        </div>
      </Panel>
      <div ref={activeStepRef}>
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
          >
            Next
          </button>
        </div>
        <p className="narrative-text">
          Step {activeStepIndex + 1} of {steps.length}: {activeStep.label}
        </p>
      </Panel>
    </>
  );
}
