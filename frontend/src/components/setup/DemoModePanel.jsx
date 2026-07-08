import { useEffect, useMemo, useState } from "react";
import { Panel } from "../workspacePrimitives";

export const STEP_DURATION_MS = 5000;

export const DEMO_STEPS = [
  {
    title: "Telemetry Intake",
    message: "Read-only telemetry intake from a stream, API, broker, or CSV export.",
    workspace: "data-connections",
    tab: "overview",
  },
  {
    title: "Reference Learning",
    message: "Neraium establishes normal operating relationships across telemetry signals.",
    workspace: "data-connections",
    tab: "historian-setup",
  },
  {
    title: "System Monitoring",
    message: "Live streams, historian exports, and telemetry imports are compared against usual system behavior.",
    workspace: "system-body",
  },
  {
    title: "Change Detected",
    message: "Relationship movement begins before alarms or threshold failures.",
    workspace: "system-body",
  },
  {
    title: "Operator Review",
    message: "Operators receive a clear focus area and evidence-backed interpretation.",
    workspace: "system-body",
  },
  {
    title: "Evidence Review",
    message: "Engineering teams can review findings, evidence, and inspection priorities.",
    workspace: "system-body",
  },
  {
    title: "Behavior Timeline",
    message: "Historical telemetry can describe when behavior moved from stable to the current observation.",
    workspace: "system-body",
  },
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export default function DemoModePanel({
  demoState,
  onActivateDemo,
  onTogglePlayback,
  onPrevious,
  onNext,
  onRestart,
}) {
  const [hasActivatedOnce, setHasActivatedOnce] = useState(false);
  const stepIndex = demoState?.stepIndex ?? 0;
  const elapsedMs = demoState?.elapsedMs ?? 0;
  const isPlaying = Boolean(demoState?.active && demoState?.isPlaying);
  const activeStep = DEMO_STEPS[stepIndex];
  const progress = useMemo(() => clamp((elapsedMs / STEP_DURATION_MS) * 100, 0, 100), [elapsedMs]);

  useEffect(() => {
    if (hasActivatedOnce) return;
    onActivateDemo?.();
    setHasActivatedOnce(true);
  }, [hasActivatedOnce, onActivateDemo]);

  return (
    <Panel title="Demo Mode" className="span-12 workspace-hero-panel">
      <p className="section-token">Guided Walkthrough (Sample Presentation Layer)</p>
      <div className="timeline-card">
        <div className="topology-card__status">
          <span className={`status-dot status-dot--${isPlaying ? "nominal" : "review"}`} aria-hidden="true" />
          <strong>{activeStep.title}</strong>
          <span>{activeStep.message}</span>
        </div>
        <div className="timeline-stats">
          <div>
            <span>Step</span>
            <strong>{stepIndex + 1} / {DEMO_STEPS.length}</strong>
          </div>
          <div>
            <span>Status</span>
            <strong>{isPlaying ? "Playing" : "Paused"}</strong>
          </div>
          <div>
            <span>Advance</span>
            <strong>Every 5 seconds</strong>
          </div>
        </div>
        <div className="upload-progress-meter" role="progressbar" aria-label="Demo progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(progress)}>
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="intake-flow__controls">
          <button type="button" className="secondary-command-button" onClick={onTogglePlayback}>
            {isPlaying ? "Pause" : "Play"}
          </button>
          <button
            type="button"
            className="secondary-command-button"
            onClick={onPrevious}
          >
            Previous
          </button>
          <button
            type="button"
            className="secondary-command-button"
            onClick={onNext}
          >
            Next
          </button>
          <button
            type="button"
            className="command-button"
            onClick={onRestart}
          >
            Restart
          </button>
        </div>
      </div>
    </Panel>
  );
}
