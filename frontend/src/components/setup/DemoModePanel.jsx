import { useEffect, useMemo, useState } from "react";
import { Panel } from "../workspacePrimitives";

const STEP_DURATION_MS = 5000;

const DEMO_STEPS = [
  {
    title: "Historian Intake",
    message: "Read-only telemetry intake from historian, BMS, SCADA, or CSV export.",
  },
  {
    title: "Baseline Formation",
    message: "Neraium establishes normal operating relationships across telemetry signals.",
  },
  {
    title: "Structural Monitoring",
    message: "Live or uploaded telemetry is compared against baseline system behavior.",
  },
  {
    title: "Drift Emergence",
    message: "Relationship movement begins before alarms or threshold failures.",
  },
  {
    title: "Operator Review",
    message: "Operators receive a clear focus area and evidence-backed interpretation.",
  },
  {
    title: "Diagnostics",
    message: "Engineering teams can inspect replay, topology, and structural evidence.",
  },
  {
    title: "Replay Timeline",
    message: "Uploaded telemetry can replay the movement from stable behavior into drift or recovery.",
  },
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export default function DemoModePanel() {
  const [stepIndex, setStepIndex] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const activeStep = DEMO_STEPS[stepIndex];
  const progress = useMemo(() => clamp((elapsedMs / STEP_DURATION_MS) * 100, 0, 100), [elapsedMs]);

  useEffect(() => {
    setStepIndex(0);
    setElapsedMs(0);
    setIsPlaying(true);
  }, []);

  useEffect(() => {
    if (!isPlaying) return undefined;
    const timer = window.setInterval(() => {
      setElapsedMs((current) => {
        const next = current + 100;
        if (next >= STEP_DURATION_MS) {
          setStepIndex((index) => (index + 1) % DEMO_STEPS.length);
          return 0;
        }
        return next;
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [isPlaying]);

  function pauseOnManualNavigation(nextStep) {
    setStepIndex(nextStep);
    setElapsedMs(0);
    setIsPlaying(false);
  }

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
          <button type="button" className="secondary-command-button" onClick={() => setIsPlaying((current) => !current)}>
            {isPlaying ? "Pause" : "Play"}
          </button>
          <button
            type="button"
            className="secondary-command-button"
            onClick={() => pauseOnManualNavigation((stepIndex - 1 + DEMO_STEPS.length) % DEMO_STEPS.length)}
          >
            Previous
          </button>
          <button
            type="button"
            className="secondary-command-button"
            onClick={() => pauseOnManualNavigation((stepIndex + 1) % DEMO_STEPS.length)}
          >
            Next
          </button>
          <button
            type="button"
            className="command-button"
            onClick={() => {
              setStepIndex(0);
              setElapsedMs(0);
              setIsPlaying(true);
            }}
          >
            Restart
          </button>
        </div>
      </div>
    </Panel>
  );
}
