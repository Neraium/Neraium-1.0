import React from "react";

export default function SidebarNavigation({
  workspaces,
  activeWorkspace,
  onSelectWorkspace,
  roomContext,
  timeCoverage,
  liveOps,
  StatusDot,
  SidebarTelemetry,
}) {
  return (
    <>
      <div className="sidebar-brand-shell">
        <div className="sidebar-brand">
          <div className="brand-mark">N</div>
          <div>
            <p className="brand-name">NERAIUM // OPS</p>
            <p className="brand-subtitle">Cultivation Infrastructure Control Plane</p>
          </div>
        </div>
        <span className="brand-edition">Enterprise Command</span>
      </div>
      <div className="sidebar-section">
        <p className="sidebar-kicker">Workspaces</p>
        <nav className="workspace-nav">
          {workspaces.map((workspace) => (
            <button
              className={`workspace-nav__item ${activeWorkspace === workspace.id ? "workspace-nav__item--active" : ""}`}
              key={workspace.id}
              type="button"
              aria-current={activeWorkspace === workspace.id ? "page" : undefined}
              onClick={() => onSelectWorkspace(workspace.id)}
            >
              <span className="workspace-nav__label">{workspace.label}</span>
              <span className="workspace-nav__detail">{workspace.description}</span>
            </button>
          ))}
        </nav>
      </div>
      <div className="sidebar-section sidebar-section--terminal">
        <p className="sidebar-kicker">Operational state</p>
        <SidebarTelemetry label="Telemetry source" value={liveOps.dataSourceLabel} />
        <SidebarTelemetry label="Primary room" value={roomContext.primary} />
        <SidebarTelemetry label="Continuation window" value={timeCoverage.summary} />
        <SidebarTelemetry label="Propagation state" value={liveOps.facilityStateLabel} />
        <SidebarTelemetry label="Active findings" value={`${liveOps.findings.length}`} />
        <SidebarTelemetry label="Last sync" value={liveOps.connectionSummary} />
      </div>
      <div className="sidebar-footer">
        <StatusDot tone={liveOps.connectionTone} />
        <div>
          <p>{liveOps.connectionStatusLine}</p>
          <span>{liveOps.connectionActionHint}</span>
        </div>
      </div>
    </>
  );
}
