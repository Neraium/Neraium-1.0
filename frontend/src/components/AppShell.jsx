import DesktopWorkspaceLayout from "./shell/layout/DesktopWorkspaceLayout";
import { StatusDot } from "./workspacePrimitives";
import { normalizeOperationalState } from "../viewModels/operationalUiState";

export default function AppShell({
  activeWorkspace,
  workspaceRef,
  workspaceDrawerRef,
  visibleWorkspaces,
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
          roomContext={roomContext}
          timeCoverage={timeCoverage}
          liveOps={liveOps}
          onSelectWorkspace={onSelectWorkspace}
        />
      )}
      mobileHeader={(
        <MobileOperationalHeader
          activeConfig={activeConfig}
          activeWorkspace={activeWorkspace}
          visibleWorkspaces={visibleWorkspaces}
          liveOps={liveOps}
          roomContext={roomContext}
          isWorkspaceMenuOpen={isWorkspaceMenuOpen}
          setIsWorkspaceMenuOpen={setIsWorkspaceMenuOpen}
          onSelectWorkspace={onSelectWorkspace}
        />
      )}
      topStatus={(
        <TopStatusBar
          activeWorkspace={activeWorkspace}
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
            aria-hidden="true"
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
              <div className="workspace-drawer__brand">
                <div className="workspace-drawer__title-block">
                  <strong>NERAIUM</strong>
                  <span>Structural Intelligence</span>
                </div>
              </div>
              <button
                className="workspace-drawer__close"
                type="button"
                aria-label="Close workspace menu"
                onClick={() => setIsWorkspaceMenuOpen(false)}
              >
                <span aria-hidden="true">×</span>
                <span>Close</span>
              </button>
            </div>
            <WorkspaceNavigationContent
              variant="drawer"
              activeWorkspace={activeWorkspace}
              workspaces={visibleWorkspaces}
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

function MobileOperationalHeader({
  activeConfig,
  activeWorkspace,
  visibleWorkspaces,
  liveOps,
  roomContext,
  isWorkspaceMenuOpen,
  setIsWorkspaceMenuOpen,
  onSelectWorkspace,
}) {
  const missionLabel = activeWorkspace === "cultivation-mission-control" ? "Active Deployment" : "Operational Command";
  const hudMetrics = buildOperationalHudMetrics(liveOps);

  return (
    <header className={`mobile-status-bar mobile-status-bar--${liveOps.facilityTone}`}>
      <div className="mobile-status-bar__topline">
        <div className="mobile-status-bar__brand">
          <div className="mobile-status-bar__copy">
            <p className="brand-name brand-name--hero">Neraium // OPS</p>
            <p className="mobile-status-bar__workspace">{missionLabel} · {activeConfig.label}</p>
          </div>
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
      </div>

      <div className={`mobile-command-strip mobile-command-strip--deployment mobile-command-strip--${liveOps.facilityTone}`} aria-label="Live structural cognition ribbon">
        <div className="mobile-command-strip__cell mobile-command-strip__cell--identity">
          <span>Cultivation Primary</span>
          <strong>Live Structural Cognition Active</strong>
        </div>
        {hudMetrics.map((metric, index) => (
          <div className={`mobile-command-strip__cell ${index === 0 ? "mobile-command-strip__cell--primary" : ""}`} key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>

      <nav className="mobile-workspace-pills" aria-label="Priority workspace shortcuts">
        {visibleWorkspaces.map((workspace) => (
          <button
            key={workspace.id}
            type="button"
            className={`mobile-workspace-pill ${activeWorkspace === workspace.id ? "mobile-workspace-pill--active" : ""}`}
            aria-current={activeWorkspace === workspace.id ? "page" : undefined}
            onClick={() => onSelectWorkspace(workspace.id)}
          >
            <span className="mobile-workspace-pill__status" aria-hidden="true" />
            <span>{workspace.eyebrow}</span>
            <strong>{workspace.label}</strong>
            <em>{activeWorkspace === workspace.id ? "Live cognition" : "Linked module"}</em>
          </button>
        ))}
      </nav>
    </header>
  );
}

function WorkspaceNavigationContent({
  variant = "sidebar",
  activeWorkspace,
  workspaces,
  roomContext,
  timeCoverage,
  liveOps,
  onSelectWorkspace,
}) {
  const activeUiState = normalizeOperationalState(liveOps.facilityTone);
  const cultivationFocused = activeWorkspace === "cultivation-mission-control";
  const isDrawer = variant === "drawer";
  return (
    <>
      {!isDrawer ? (
        <div className="sidebar-brand-shell">
          <div className="sidebar-brand">
            <div className="brand-mark">N</div>
            <div>
              <p className="brand-name">NERAIUM // OPS</p>
              <p className="brand-subtitle">Structural Intelligence Control Plane</p>
            </div>
          </div>
          <span className="brand-edition">Operational Command</span>
        </div>
      ) : null}

      <div className="sidebar-section">
        <p className="sidebar-kicker">Workspaces</p>
        <nav className="workspace-nav">
          {workspaces.map((workspace, index) => {
            const isActive = activeWorkspace === workspace.id;
            const tier = index < 3 ? "primary" : index < 6 ? "secondary" : "tertiary";
            const statusText = isActive ? "Active cognition" : tier === "primary" ? "Hot standby" : tier === "secondary" ? "Synchronized" : "Archive-ready";
            return (
              <button
                className={`workspace-nav__item workspace-nav__item--tier-${tier} ${isActive ? `workspace-nav__item--active workspace-nav__item--state-${activeUiState}` : "workspace-nav__item--state-neutral"}`}
                key={workspace.id}
                type="button"
                aria-current={isActive ? "page" : undefined}
                onClick={() => onSelectWorkspace(workspace.id)}
              >
                <span className="workspace-nav__pulse" aria-hidden="true" />
                <div className="workspace-nav__header">
                  <span className="workspace-nav__label">{workspace.label}</span>
                  <StatusDot tone={isActive ? liveOps.facilityTone : tier === "primary" ? "info" : "muted"} />
                </div>
                <span className="workspace-nav__eyebrow">{workspace.eyebrow}</span>
                <span className="workspace-nav__activity">
                  <span>{statusText}</span>
                  <i aria-hidden="true" />
                </span>
                {!isDrawer ? <span className="workspace-nav__detail">{workspace.description}</span> : null}
              </button>
            );
          })}
        </nav>
      </div>

      {!isDrawer && !cultivationFocused ? (
        <div className={`sidebar-section sidebar-section--terminal ui-state-surface ui-state-surface--${activeUiState}`}>
          <p className="sidebar-kicker">Persistent state</p>
          <SidebarTelemetry label="Data source" value={liveOps.dataSourceLabel} />
          <SidebarTelemetry label="Primary room" value={roomContext.primary} />
          <SidebarTelemetry label="Time coverage" value={timeCoverage.summary} />
          <SidebarTelemetry label="Facility state" value={liveOps.facilityStateLabel} />
          <SidebarTelemetry label="Findings" value={`${liveOps.findings.length} active`} />
          <SidebarTelemetry label="Last sync" value={liveOps.connectionSummary} />
        </div>
      ) : null}

      {!isDrawer ? (
        <div className="sidebar-footer">
          <StatusDot tone={liveOps.connectionTone} />
          <div>
            <p>{liveOps.connectionStatusLine}</p>
            <span>{liveOps.connectionActionHint}</span>
          </div>
        </div>
      ) : null}
    </>
  );
}

function TopStatusBar({
  activeWorkspace,
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
  const minimalCultivationHeader = activeWorkspace === "cultivation-mission-control";
  const deploymentMetrics = buildOperationalHudMetrics(liveOps);
  return (
    <header className={`top-status top-status--deployment ${minimalCultivationHeader ? "top-status--minimal top-status--cultivation" : ""}`}>
      <div className="top-status__title">
        <p className="eyebrow">Neraium Command | {activeConfig.eyebrow}</p>
        <h1 id="page-title" className={minimalCultivationHeader ? "sr-only" : ""}>
          {activeConfig.label}
        </h1>
        {!minimalCultivationHeader ? <p>{activeConfig.description}</p> : null}
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

      <div className={`active-deployment-bar active-deployment-bar--${liveOps.facilityTone}`} aria-label="Live structural cognition operational ribbon">
        <div className="active-deployment-bar__header">
          <span className="active-deployment-bar__beacon" aria-hidden="true" />
          <div className="active-deployment-bar__identity">
            <strong>Live Structural Cognition</strong>
            <em>Cultivation Primary · Live Structural Cognition Active</em>
          </div>
          <span className="active-deployment-bar__mode">{activeConfig.eyebrow}</span>
        </div>
        <div className="active-deployment-bar__stream" role="list">
          {deploymentMetrics.map((metric) => (
            <div className={`active-deployment-bar__metric active-deployment-bar__metric--${metric.tone}`} role="listitem" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      </div>

      {!minimalCultivationHeader ? (
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
      ) : (
        <div className="top-status__compact">
          <article className="top-status__compact-item">
            <span>Structural condition</span>
            <strong>{liveOps.facilityStateLabel}</strong>
          </article>
          <article className="top-status__compact-item">
            <span>Primary room</span>
            <strong>{roomContext.primary}</strong>
          </article>
          <article className="top-status__compact-item">
            <span>Next inspect</span>
            <strong>{liveOps.primaryWindow?.label ?? "Facility overview"}</strong>
          </article>
        </div>
      )}
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

function buildOperationalHudMetrics(liveOps) {
  const relationshipCount = liveOps.relationshipRows?.length || 0;
  const replayValue = relationshipCount > 0
    ? `${relationshipCount} Active ${relationshipCount === 1 ? "Trajectory" : "Trajectories"}`
    : "Replay Trajectory Standby";
  const structuralState = ["nominal", "online", "stable"].includes(liveOps.facilityTone)
    ? "Topology Synchronization Stable"
    : "Structural Drift Emerging";
  const propagationValue = ["elevated", "unstable", "offline"].includes(liveOps.facilityTone)
    ? "Propagation Watch Active"
    : "Localized";
  const syncValue = liveOps.intelligenceMode === "empty"
    ? "Topology Synchronization Pending"
    : "Live Telemetry Active";

  return [
    { label: "State", value: structuralState, tone: liveOps.facilityTone },
    { label: "Replay", value: replayValue, tone: liveOps.primaryWindow?.tone ?? "info" },
    { label: "Propagation", value: propagationValue, tone: liveOps.facilityTone },
    { label: "Sync", value: syncValue, tone: liveOps.connectionTone },
    { label: "Updated", value: liveOps.connectionSummary || "Awaiting synchronization", tone: liveOps.connectionTone },
  ];
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
