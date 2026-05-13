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
            <p className="brand-subtitle">Structural Intelligence Control Plane</p>
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
        <p className="sidebar-kicker">Persistent state</p>
        <SidebarTelemetry label="Data source" value={liveOps.dataSourceLabel} />
        <SidebarTelemetry label="Primary room" value={roomContext.primary} />
        <SidebarTelemetry label="Time coverage" value={timeCoverage.summary} />
        <SidebarTelemetry label="Facility state" value={liveOps.facilityStateLabel} />
        <SidebarTelemetry label="Findings" value={`${liveOps.findings.length} active`} />
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
