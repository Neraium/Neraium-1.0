import DesktopWorkspaceLayout from "./shell/layout/DesktopWorkspaceLayout";
import { StatusDot } from "./workspacePrimitives";
import { normalizeOperationalState } from "../viewModels/operationalUiState";

export default function AppShell({
  activeWorkspace,
  workspaceRef,
  workspaceDrawerRef,
  visibleWorkspaces,
  expertMode,
  onToggleExpertMode,
  activeConfig,
  apiStatus,
  latestUploadResult,
  roomContext,
  timeCoverage,
  liveOps,
  onSelectWorkspace,
  isWorkspaceMenuOpen,
  setIsWorkspaceMenuOpen,
  isDemoMode,
  onToggleDemoMode,
  demoScenario,
  onSetDemoScenario,
  renderActiveWorkspace,
  formatReadiness,
  formatIntelligenceSourceLabel,
  deriveTriageSummary,
}) {
  return (
    <DesktopWorkspaceLayout
      activeWorkspace={activeWorkspace}
      workspaceRef={workspaceRef}
      navigation={(
        <WorkspaceNavigationContent
          activeWorkspace={activeWorkspace}
          workspaces={visibleWorkspaces}
          expertMode={expertMode}
          onToggleExpertMode={onToggleExpertMode}
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          timeCoverage={timeCoverage}
          liveOps={liveOps}
          onSelectWorkspace={onSelectWorkspace}
        />
      )}
      mobileHeader={(
        <header className="mobile-status-bar">
          <div className="mobile-status-bar__brand">
            <div className="mobile-status-bar__copy">
              <p className="brand-name brand-name--hero">Neraium</p>
              <p className="mobile-status-bar__workspace">{activeConfig.label}</p>
            </div>
          </div>
          <div className="mobile-demo-controls" aria-label="Sample controls">
            <button
              className={`secondary-command-button mobile-demo-controls__toggle ${isDemoMode ? "is-active" : ""}`}
              type="button"
              onClick={onToggleDemoMode}
            >
              {isDemoMode ? "Sample On" : "Sample Off"}
            </button>
            {isDemoMode && (
              <div className="mobile-demo-controls__scenarios" role="group" aria-label="Sample scenario">
                <button
                  className={`secondary-command-button ${demoScenario === "stable" ? "is-active" : ""}`}
                  type="button"
                  onClick={() => onSetDemoScenario("stable")}
                >
                  Stable
                </button>
                <button
                  className={`secondary-command-button ${demoScenario === "drift" ? "is-active" : ""}`}
                  type="button"
                  onClick={() => onSetDemoScenario("drift")}
                >
                  Drift
                </button>
                <button
                  className={`secondary-command-button ${demoScenario === "separation" ? "is-active" : ""}`}
                  type="button"
                  onClick={() => onSetDemoScenario("separation")}
                >
                  Separation
                </button>
              </div>
            )}
          </div>
          <button
            className="workspace-menu-button"
            type="button"
            aria-expanded={isWorkspaceMenuOpen}
            aria-controls="mobile-workspace-drawer"
            onClick={() => setIsWorkspaceMenuOpen((current) => !current)}
          >
            <span className="workspace-menu-button__icon" aria-hidden="true">
              |||
            </span>
            <span>Menu</span>
          </button>
        </header>
      )}
      topStatus={(
        <TopStatusBar
          activeConfig={activeConfig}
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          liveOps={liveOps}
          isDemoMode={isDemoMode}
          onToggleDemoMode={onToggleDemoMode}
          demoScenario={demoScenario}
          onSetDemoScenario={onSetDemoScenario}
          formatReadiness={formatReadiness}
          formatIntelligenceSourceLabel={formatIntelligenceSourceLabel}
          deriveTriageSummary={deriveTriageSummary}
        />
      )}
      drawer={(
        <>
          <div
            className={`workspace-drawer-backdrop ${isWorkspaceMenuOpen ? "workspace-drawer-backdrop--open" : ""}`}
            hidden={!isWorkspaceMenuOpen}
            style={{ pointerEvents: isWorkspaceMenuOpen ? "auto" : "none" }}
            onClick={() => setIsWorkspaceMenuOpen(false)}
          />
          <aside
            ref={workspaceDrawerRef}
            className={`workspace-drawer ${isWorkspaceMenuOpen ? "workspace-drawer--open" : ""}`}
            id="mobile-workspace-drawer"
            aria-label="Workspace drawer"
            aria-hidden={!isWorkspaceMenuOpen}
            style={{ pointerEvents: isWorkspaceMenuOpen ? "auto" : "none" }}
          >
            <div className="workspace-drawer__header">
              <div>
                <p className="sidebar-kicker">Navigation</p>
                <strong>{activeConfig.label}</strong>
              </div>
              <button
                className="workspace-drawer__close"
                type="button"
                aria-label="Close workspace menu"
                onClick={() => setIsWorkspaceMenuOpen(false)}
              >
                Close
              </button>
            </div>
            <WorkspaceNavigationContent
              activeWorkspace={activeWorkspace}
              workspaces={visibleWorkspaces}
              expertMode={expertMode}
              onToggleExpertMode={onToggleExpertMode}
              apiStatus={apiStatus}
              latestUploadResult={latestUploadResult}
              roomContext={roomContext}
              timeCoverage={timeCoverage}
              liveOps={liveOps}
              onSelectWorkspace={onSelectWorkspace}
            />
          </aside>
        </>
      )}
    >
      {renderActiveWorkspace()}
    </DesktopWorkspaceLayout>
  );
}

function WorkspaceNavigationContent({
  activeWorkspace,
  workspaces,
  expertMode,
  onToggleExpertMode,
  roomContext,
  timeCoverage,
  liveOps,
  onSelectWorkspace,
}) {
  const activeUiState = normalizeOperationalState(liveOps.facilityTone);
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
        <button
          type="button"
          className={`secondary-command-button ${expertMode ? "is-active" : ""}`}
          onClick={onToggleExpertMode}
        >
          {expertMode ? "Expert Mode On" : "Expert Mode Off"}
        </button>
        <nav className="workspace-nav">
          {workspaces.map((workspace) => (
            <button
              className={`workspace-nav__item ${activeWorkspace === workspace.id ? `workspace-nav__item--active workspace-nav__item--state-${activeUiState}` : "workspace-nav__item--state-neutral"}`}
              key={workspace.id}
              type="button"
              aria-current={activeWorkspace === workspace.id ? "page" : undefined}
              onClick={() => onSelectWorkspace(workspace.id)}
            >
              <div className="workspace-nav__header">
                <span className="workspace-nav__label">{workspace.label}</span>
                <StatusDot tone={activeWorkspace === workspace.id ? liveOps.facilityTone : "muted"} />
              </div>
              <span className="workspace-nav__eyebrow">{workspace.eyebrow}</span>
              <span className="workspace-nav__detail">{workspace.description}</span>
            </button>
          ))}
        </nav>
      </div>

      <div className={`sidebar-section sidebar-section--terminal ui-state-surface ui-state-surface--${activeUiState}`}>
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

function TopStatusBar({
  activeConfig,
  apiStatus,
  latestUploadResult,
  roomContext,
  liveOps,
  isDemoMode,
  onToggleDemoMode,
  demoScenario,
  onSetDemoScenario,
  formatReadiness,
  formatIntelligenceSourceLabel,
  deriveTriageSummary,
}) {
  const intelligenceLabel = formatIntelligenceSourceLabel(liveOps.intelligenceMode);
  const triageSummary = deriveTriageSummary(liveOps, roomContext);
  const uiState = normalizeOperationalState(liveOps.facilityTone);
  const degradedMode = apiStatus?.state === "offline";
  return (
    <header className="top-status">
      <div className="top-status__title">
        <p className="eyebrow">Neraium Command | {activeConfig.eyebrow}</p>
        <h1 id="page-title">{activeConfig.label}</h1>
        <p>{activeConfig.description}</p>
        <div className="top-status__meta">
          <span className={`top-status__signal top-status__signal--${liveOps.connectionTone}`} aria-label={liveOps.connectionStatusLine}>
            <StatusDot tone={liveOps.connectionTone} />
          </span>
          <span className={`sii-source-chip sii-source-chip--${liveOps.intelligenceMode}`}>
            {intelligenceLabel}
          </span>
          {liveOps.connectionActionHint && (
            <span className="top-status__meta-copy top-status__meta-copy--actionable">{liveOps.connectionActionHint}</span>
          )}
        </div>
      </div>

      <div className={`top-status__brief top-status__brief--${liveOps.facilityTone} ui-state-surface ui-state-surface--${uiState}`}>
        <article className="top-status__brief-item">
          <span>What's changing</span>
          <strong>{triageSummary.problem}</strong>
        </article>
        <article className="top-status__brief-item">
          <span>Where it is spreading</span>
          <strong>{triageSummary.where}</strong>
        </article>
        <article className="top-status__brief-item top-status__brief-item--wide">
          <span>Why trust this</span>
          <p>{triageSummary.why}</p>
        </article>
        <article className="top-status__brief-item top-status__brief-item--wide">
          <span>What to inspect</span>
          <p>{triageSummary.human}</p>
        </article>
      </div>
      {degradedMode ? (
        <div className="top-status__degraded">
          <strong>Degraded Mode Active</strong>
          <p>
            Backend connectivity is unavailable. Neraium is preserving structural cognition context for operator review while
            live route data reconnects.
          </p>
        </div>
      ) : null}

      <div className="status-rack">
        <StatusChip label="Severity" value={liveOps.facilityStateLabel} tone={liveOps.facilityTone} />
        <StatusChip label="Primary room" value={roomContext.primary} tone={liveOps.facilityTone} />
        <StatusChip label="Next inspect" value={liveOps.primaryWindow?.label ?? "Facility overview"} tone={liveOps.primaryWindow?.tone ?? "info"} />
        <StatusChip
          label="What changed"
          value={latestUploadResult?.data_quality ? formatReadiness(latestUploadResult.data_quality?.readiness) : liveOps.readinessLabel}
          tone={latestUploadResult?.data_quality?.readiness ?? liveOps.connectionTone}
        />
        <button className="secondary-command-button" type="button" onClick={onToggleDemoMode}>
          {isDemoMode ? "Sample On" : "Sample Off"}
        </button>
        {isDemoMode && (
          <>
            <button className={`secondary-command-button ${demoScenario === "stable" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("stable")}>
              Stable
            </button>
            <button className={`secondary-command-button ${demoScenario === "drift" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("drift")}>
              Drift
            </button>
            <button className={`secondary-command-button ${demoScenario === "separation" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("separation")}>
              Separation
            </button>
          </>
        )}
      </div>
    </header>
  );
}

function StatusChip({ label, value, tone }) {
  const uiState = normalizeOperationalState(tone);
  return (
    <div className={`status-chip status-chip--${tone} ui-state-surface ui-state-surface--${uiState}`}>
      <div className="status-chip__head">
        <StatusDot tone={tone} />
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
    </div>
  );
}

function SidebarTelemetry({ label, value }) {
  return (
    <div className="sidebar-telemetry">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
