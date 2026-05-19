import { Panel } from "../workspacePrimitives";

export default function ConnectionsHeaderPanel({
  tabs,
  activeTab,
  onSelectTab,
  onResetEverything,
  disableReset,
}) {
  return (
    <Panel title="Historian Intake" className="span-12 workspace-hero-panel">
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
      </div>
    </Panel>
  );
}
