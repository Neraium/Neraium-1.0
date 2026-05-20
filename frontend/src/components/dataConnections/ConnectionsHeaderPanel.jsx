import { Panel } from "../workspacePrimitives";

export default function ConnectionsHeaderPanel({
  tabs,
  activeTab,
  onSelectTab,
  onResetEverything,
  disableReset,
  onResumePreviousSession,
  onOpenUpload,
  disableActions = false,
  workflowStage = "setup",
}) {
  const railSteps = [
    { id: "setup", label: "Setup" },
    { id: "upload", label: "Upload" },
    { id: "status", label: "Status" },
  ];

  return (
    <Panel title="Historian Intake" className="span-12 workspace-hero-panel">
      <div className="intake-stage-rail" aria-label="Intake workflow">
        {railSteps.map((step) => (
          <span
            key={step.id}
            className={`intake-stage-chip ${workflowStage === step.id ? "is-active" : ""}`}
          >
            {step.label}
          </span>
        ))}
      </div>
      <div className="intake-flow__controls" role="tablist" aria-label="Historian intake sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? "command-button" : "secondary-command-button"}
            onClick={() => onSelectTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
        <button
          type="button"
          className="secondary-command-button"
          onClick={onResetEverything}
          disabled={disableReset}
          aria-label="Reset everything"
        >
          Reset Everything
        </button>
        {activeTab === "connect-live" ? (
          <>
            <button
              type="button"
              className="secondary-command-button"
              onClick={onResumePreviousSession}
              disabled={disableActions}
            >
              Resume Session
            </button>
            <button
              type="button"
              className="command-button"
              onClick={onOpenUpload}
              disabled={disableActions}
            >
              Upload Data
            </button>
          </>
        ) : null}
      </div>
    </Panel>
  );
}
