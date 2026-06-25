import { useMemo, useState } from "react";

import PageContainer from "./layout/PageContainer";
import "../styles/operational-workflow.css";

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "insights", label: "Insights" },
  { id: "systems", label: "Systems" },
  { id: "telemetry", label: "Telemetry" },
  { id: "history", label: "History" },
];

const MOBILE_PRIMARY_NAV = [
  { id: "overview", label: "Overview" },
  { id: "insights", label: "Insights" },
  { id: "systems", label: "Systems" },
];

const MOBILE_MORE_NAV = [
  { id: "telemetry", label: "Telemetry" },
  { id: "history", label: "History" },
];

const INVESTIGATION_STATUSES = ["Open", "Acknowledged", "Under Investigation", "Resolved"];
const EMPTY_TELEMETRY_COPY = {
  label: "Start with telemetry",
  detail: "Upload or connect telemetry to begin analysis.",
  cta: "Upload or Connect Telemetry",
  headerStatus: "Waiting for telemetry",
};
const NO_TELEMETRY_STATUS = {
  label: EMPTY_TELEMETRY_COPY.label,
  tone: "unknown",
  detail: EMPTY_TELEMETRY_COPY.detail,
};
const WAITING_FOR_TELEMETRY_STATUS = {
  label: EMPTY_TELEMETRY_COPY.headerStatus,
  tone: "unknown",
  detail: EMPTY_TELEMETRY_COPY.detail,
};
const READY_TO_ANALYZE_STATUS = {
  label: "Ready to Analyze",
  tone: "unknown",
  detail: "Telemetry is available. Run analysis to identify systems, relationships, anomalies, and baseline behavior.",
};
const ANALYZING_STATUS = {
  label: "Building Operating Fingerprint",
  tone: "changed",
  detail: "SII is analyzing telemetry, identifying system behavior, and mapping relationships.",
};
const ANALYSIS_COMPLETE_STATUS = {
  label: "Analysis Complete",
  tone: "normal",
  detail: "Historical telemetry analyzed.",
};
const MONITORING_LIVE_STATUS = {
  label: "Monitoring Live",
  tone: "normal",
  detail: "Live telemetry is connected and current behavior is being monitored.",
};
const NO_BASELINE_AVAILABLE = {
  label: "No Operating Fingerprint Yet",
  tone: "unknown",
  detail: "Run analysis to establish a baseline.",
};
const SYSTEMS_PENDING = {
  title: "Systems Pending",
  countLabel: "Pending",
  summary: "Run analysis to identify systems and relationships.",
};

export default function OperationalWorkflowWorkspace({
  liveOps,
  canonicalFinding,
  currentSession,
  effectiveLatestUploadResult,
  effectiveLatestUploadSnapshot,
  roomContext,
  domainDetection,
  gateProcessing,
  replayFrame = null,
  onWorkspaceNavigate,
  onUploadComplete,
  onResumePreviousSession,
  onSignOut,
}) {
  const [activeSection, setActiveSection] = useState("overview");
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);
  const [selectedInsightId, setSelectedInsightId] = useState(null);
  const [insightStatuses, setInsightStatuses] = useState({});
  const [operatorNotes, setOperatorNotes] = useState({});

  const model = useMemo(() => buildOperationalModel({
    liveOps,
    canonicalFinding,
    currentSession,
    effectiveLatestUploadResult,
    effectiveLatestUploadSnapshot,
    roomContext,
    domainDetection,
    gateProcessing,
    replayFrame,
  }), [
    liveOps,
    canonicalFinding,
    currentSession,
    effectiveLatestUploadResult,
    effectiveLatestUploadSnapshot,
    roomContext,
    domainDetection,
    gateProcessing,
    replayFrame,
  ]);

  const selectedInsight = model.insights.find((item) => item.id === selectedInsightId) ?? model.insights[0] ?? null;
  const mobileMoreActive = MOBILE_MORE_NAV.some((item) => item.id === activeSection);
  const navMetrics = {
    overview: model.overviewTabMetric,
    insights: String(model.insights.length),
    systems: model.systemsTabMetric,
    telemetry: String(model.signals.length),
    history: String(model.historyItems.length),
  };

  function navigate(sectionId) {
    setActiveSection(sectionId);
    setMobileMoreOpen(false);
  }

  function openInsight(insightId) {
    setSelectedInsightId(insightId);
    navigate("insights");
  }

  function setInsightStatus(insightId, status) {
    setInsightStatuses((current) => ({ ...current, [insightId]: status }));
  }

  function setOperatorNote(insightId, note) {
    setOperatorNotes((current) => ({ ...current, [insightId]: note }));
  }

  function analyzeSystem() {
    if (model.uiState.key === "analyzing") return;
    if (typeof onWorkspaceNavigate === "function") {
      onWorkspaceNavigate("data-connections");
    }
  }

  function viewSystems() {
    navigate("systems");
  }

  return (
    <PageContainer className="operational-workflow">
      <aside className="operational-sidebar" aria-label="Neraium navigation">
        <div className="operational-sidebar__brand">
          <span className="section-token">Neraium</span>
          <strong>{model.siteLabel}</strong>
          <p>{model.domainLabel}</p>
        </div>
        <nav className="operational-nav" aria-label="Primary workflow navigation">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={activeSection === item.id ? "is-active" : ""}
              aria-current={activeSection === item.id ? "page" : undefined}
              onClick={() => navigate(item.id)}
            >
              <span>{item.label}</span>
              <small>{navMetrics[item.id]}</small>
            </button>
          ))}
        </nav>
        <div className="operational-sidebar__footer">
          {model.showSidebarStatus ? <StatusBadge label={model.telemetryStatus.label} tone={model.telemetryStatus.tone} /> : null}
          <small>Last analysis: {model.lastAnalysis}</small>
          {typeof onSignOut === "function" ? (
            <button type="button" className="operational-link-button" onClick={onSignOut}>Sign out</button>
          ) : null}
        </div>
      </aside>

      <main className="operational-main" aria-label="Neraium operational workspace">
        <header className="operational-topbar">
          <div>
            <p className="section-token">{model.headerEyebrow}</p>
            <h1>{sectionTitle(activeSection)}</h1>
            <p className="operational-topbar__context">{model.headerSubtitle}</p>
          </div>
          <div className="operational-topbar__status">
            {model.showHeroStatusBadge ? <StatusBadge label={model.heroStatus.label} tone={model.heroStatus.tone} /> : null}
            <StatusBadge label={model.telemetryStatus.label} tone={model.telemetryStatus.tone} />
          </div>
        </header>

        <div className="operational-mobile-nav" aria-label="Mobile workflow navigation">
          {MOBILE_PRIMARY_NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={activeSection === item.id ? "is-active" : ""}
              aria-current={activeSection === item.id ? "page" : undefined}
              onClick={() => navigate(item.id)}
            >
              <span>{item.label}</span>
              <small>{navMetrics[item.id]}</small>
            </button>
          ))}
          <div className="operational-mobile-nav__more-wrap">
            <button
              type="button"
              className={mobileMoreActive ? "is-active" : ""}
              aria-expanded={mobileMoreOpen}
              aria-haspopup="menu"
              onClick={() => setMobileMoreOpen((value) => !value)}
            >
              <span>More</span>
            </button>
            {mobileMoreOpen ? (
              <div className="operational-mobile-nav__menu" role="menu" aria-label="More navigation">
                {MOBILE_MORE_NAV.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="menuitem"
                    className={activeSection === item.id ? "is-active" : ""}
                    onClick={() => navigate(item.id)}
                  >
                    <span>{item.label}</span>
                    <small>{navMetrics[item.id]}</small>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        {activeSection === "overview" ? (
          <OverviewSection
            model={model}
            onOpenInsight={openInsight}
            onAnalyzeSystem={analyzeSystem}
            onResumePreviousSession={onResumePreviousSession}
            onViewSystems={viewSystems}
          />
        ) : null}

        {activeSection === "insights" ? (
          <InsightsSection
            model={model}
            selectedInsight={selectedInsight}
            insightStatuses={insightStatuses}
            operatorNotes={operatorNotes}
            onSelectInsight={setSelectedInsightId}
            onSetInsightStatus={setInsightStatus}
            onSetOperatorNote={setOperatorNote}
            onOpenSystemStory={() => onWorkspaceNavigate?.("system-story")}
          />
        ) : null}

        {activeSection === "systems" ? (
          <SystemsSection model={model} onOpenInsight={openInsight} />
        ) : null}

        {activeSection === "telemetry" ? (
          <TelemetrySection model={model} onAnalyzeSystem={analyzeSystem} />
        ) : null}

        {activeSection === "history" ? (
          <HistorySection model={model} onResumePreviousSession={onResumePreviousSession} />
        ) : null}

        {typeof onUploadComplete === "function" ? null : null}
      </main>
    </PageContainer>
  );
}

function OverviewSection({ model, onOpenInsight, onAnalyzeSystem, onResumePreviousSession, onViewSystems }) {
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--hero operational-panel--wide" aria-label="Overview status">
        <div className="operational-hero">
          <div className="operational-hero__summary">
            <div className="operational-panel__header operational-panel__header--tight">
              <span className="section-token">Overview</span>
              <h2>{model.heroStatus.label}</h2>
              <p>{model.heroStatus.detail}</p>
            </div>
            <div className="operational-hero__meta">
              {model.showStoryProgress ? <span>{model.storyProgressLabel}</span> : null}
              {model.showBaselineClaim ? <span>{model.baselineStatus.label}</span> : null}
            </div>
            {model.resultSummaryRows.length ? (
              <div className="operational-result-summary" aria-label="Analysis results summary">
                <DetailGrid rows={model.resultSummaryRows} />
              </div>
            ) : null}
            <div className="operational-actions operational-actions--hero">
              <button type="button" className="command-button" onClick={onAnalyzeSystem} disabled={model.analyzeDisabled}>{model.primaryCtaLabel}</button>
              {model.showSystemClaims ? (
                <button type="button" className="secondary-command-button" onClick={onViewSystems}>View Systems</button>
              ) : null}
              {model.canResumePrevious && typeof onResumePreviousSession === "function" ? (
                <button type="button" className="operational-link-button" onClick={onResumePreviousSession}>Resume Previous Analysis</button>
              ) : null}
            </div>
          </div>
          <div className="operational-hero__aside" aria-label="Current operating picture">
            <span className="section-token">Current Picture</span>
            <DetailGrid rows={[
              ["Site", model.siteLabel],
              ["Data source", model.sourceLabel],
              model.showSourceStatus ? ["Status", model.sourceStatusLabel] : null,
              model.showSystemClaims ? ["Systems", model.systemSummaryLabel] : null,
            ]} />
          </div>
        </div>
      </section>

      <section className="operational-panel operational-panel--wide" aria-label="Operational status summary">
        <div className="status-rack">
          {model.statusTiles.map((tile) => <CompactStatusTile key={tile.label} tile={tile} />)}
        </div>
      </section>

      <section className="operational-panel operational-panel--wide" aria-label="Active insights summary">
        <PanelHeader eyebrow="Insights" title="Active Insights" subtitle="Top operational observations only." />
        <InsightList
          insights={model.insights.slice(0, 3)}
          empty={model.analysisComplete
            ? "No current observations."
            : "Insights appear after telemetry analysis."}
          emptyTitle={model.analysisComplete ? "No current observations" : "No active insights"}
          onOpenInsight={onOpenInsight}
        />
      </section>

      <section className="operational-panel operational-panel--compact" aria-label="Fingerprint status">
        <PanelHeader eyebrow="Fingerprint" title="Fingerprint Status" subtitle="Baseline comparison stays compact here." />
        <FingerprintStatus drift={model.fingerprintDrift} />
      </section>

      <section className="operational-panel operational-panel--compact" aria-label="Systems summary">
        <PanelHeader eyebrow="Systems" title={model.systemSummaryTitle} subtitle={model.systemSummaryLabel} />
        <div className="systems-summary">
          <div>
            <strong>{model.systemSummaryCountLabel}</strong>
            <span>{model.systemSummaryDescriptor}</span>
          </div>
          {model.showSystemClaims ? (
            <button type="button" className="secondary-command-button" onClick={onViewSystems}>View Systems</button>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function InsightsSection({
  model,
  selectedInsight,
  insightStatuses,
  operatorNotes,
  onSelectInsight,
  onSetInsightStatus,
  onSetOperatorNote,
  onOpenSystemStory,
}) {
  return (
    <div className="operational-grid operational-grid--split">
      <section className="operational-panel" aria-label="Insight feed">
        <PanelHeader eyebrow="Insights" title="Insight Feed" subtitle="Open, acknowledged, and resolved findings." />
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No insights yet." : model.uiState.status.detail}
          emptyTitle={model.analysisComplete ? "No insights yet" : model.uiState.status.label}
          onOpenInsight={onSelectInsight}
          selectedId={selectedInsight?.id}
        />
      </section>

      <section className="operational-panel operational-panel--detail" aria-label="Insight detail">
        <PanelHeader eyebrow="Investigation" title="Insight Detail" subtitle="What changed, why it matters, and where to begin investigating." />
        {selectedInsight ? (
          <article className="insight-detail">
            <h2>{selectedInsight.summary}</h2>
            <DetailGrid rows={[
              ["System affected", selectedInsight.system],
              ["What changed", selectedInsight.whatChanged],
              ["Why it matters", selectedInsight.whyItMatters],
              ["How the system is behaving", selectedInsight.systemBehavior],
              ["Telemetry integrity", selectedInsight.telemetryNote],
              ["Detected", selectedInsight.detectedAt],
            ]} />
            <section className="operational-block">
              <h3>Suggested investigation priorities</h3>
              <ul className="compact-list">
                {selectedInsight.investigationPriorities.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </section>
            <section className="operational-block">
              <h3>Supporting observations</h3>
              <ul className="compact-list">
                {selectedInsight.supportingObservations.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </section>
            <section className="operational-block">
              <h3>Maintenance correlation</h3>
              <p>Maintenance correlation will appear when maintenance history is connected.</p>
            </section>
            <section className="operator-status-controls" aria-label="Insight status controls">
              {INVESTIGATION_STATUSES.map((status) => (
                <button
                  key={status}
                  type="button"
                  className={(insightStatuses[selectedInsight.id] ?? "Open") === status ? "is-active" : ""}
                  onClick={() => onSetInsightStatus(selectedInsight.id, status)}
                >
                  {status}
                </button>
              ))}
            </section>
            <label className="operator-note-field">
              <span>Operator notes</span>
              <textarea
                rows={4}
                placeholder="Log what was inspected, confirmed, or resolved."
                value={operatorNotes[selectedInsight.id] ?? ""}
                onChange={(event) => onSetOperatorNote(selectedInsight.id, event.target.value)}
              />
            </label>
            <div className="operational-actions">
              <button type="button" className="secondary-command-button" onClick={onOpenSystemStory}>Open System Story</button>
            </div>
          </article>
        ) : (
          <EmptyOperationalState title="No insight selected" body="Select an insight from the feed or analyze telemetry to generate findings." />
        )}
      </section>
    </div>
  );
}

function SystemsSection({ model, onOpenInsight }) {
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label={model.systemsSectionTitle}>
        <PanelHeader eyebrow="Systems" title={model.systemsSectionTitle} subtitle={model.systemsSectionSubtitle} />
        {model.systemCards.length ? (
          <div className="systems-list">
            {model.systemCards.map((system) => (
              <article className="system-summary-row" key={system.id}>
                <div>
                  <strong>{system.name}</strong>
                  <p>{system.status}</p>
                </div>
                <div className="system-summary-row__meta">
                  <span>{system.lastAnalysis}</span>
                  <span>{system.insightSummary}</span>
                  {system.primaryInsightId && typeof onOpenInsight === "function" ? (
                    <button type="button" className="system-summary-row__action" onClick={() => onOpenInsight(system.primaryInsightId)}>Open insight</button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyOperationalState title={SYSTEMS_PENDING.title} body={SYSTEMS_PENDING.summary} />
        )}
      </section>

      <section className="operational-panel" aria-label="Fingerprint panel">
        <PanelHeader eyebrow="Fingerprint" title="Fingerprint Status" subtitle="Baseline comparison remains lightweight." />
        <FingerprintStatus drift={model.fingerprintDrift} />
      </section>

      <section className="operational-panel" aria-label="Signal relationship summary">
        <PanelHeader eyebrow="Relationships" title="Signal Relationship Summary" subtitle="Relationships with the largest behavior shift." />
        <RelationshipList rows={model.relationshipRows} />
      </section>

      <section className="operational-panel operational-panel--wide" aria-label="System insights">
        <PanelHeader eyebrow="Insights" title="Active System Insights" subtitle="Findings tied to the selected or primary system." />
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No active system insights." : model.uiState.status.detail}
          emptyTitle={model.analysisComplete ? "No active system insights" : model.uiState.status.label}
          onOpenInsight={onOpenInsight}
        />
      </section>
    </div>
  );
}

function TelemetrySection({ model, onAnalyzeSystem }) {
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel" aria-label="Source status">
        <PanelHeader eyebrow="Telemetry" title="Source Status" subtitle="Current data source and analysis heartbeat." />
        <StatusBadge label={model.telemetryStatus.label} tone={model.telemetryStatus.tone} />
        <DetailGrid rows={[
          ["Source", model.sourceLabel],
          ["Last analysis", model.lastAnalysis],
          ["Detected data type", model.domainLabel],
        ]} />
      </section>
      <section className="operational-panel" aria-label="Signal browser">
        <PanelHeader eyebrow="Signals" title="Signal Browser" subtitle="Detected telemetry signals and integrity state." />
        <SignalList signals={model.signals} integrity={model.telemetryStatus} />
      </section>
      <section className="operational-panel operational-panel--wide" aria-label="Data quality warnings">
        <PanelHeader eyebrow="Integrity" title="Data Quality" subtitle="Warnings, missing values, and timestamp conditions." />
        <QualityList title="Warnings" items={model.qualityWarnings} empty={model.analysisComplete ? "No data quality warnings reported." : model.uiState.status.detail} />
        <QualityList title="Missing values" items={model.missingValues} empty={model.analysisComplete ? "No missing value summary reported." : model.uiState.status.detail} />
        <QualityList title="Timestamp quality" items={model.timestampNotes} empty={model.analysisComplete ? "Timestamp quality is acceptable or not yet reported." : model.uiState.status.detail} />
        <div className="operational-actions">
          <button type="button" className="command-button" onClick={onAnalyzeSystem} disabled={model.analyzeDisabled}>{model.primaryCtaLabel}</button>
        </div>
      </section>
    </div>
  );
}

function HistorySection({ model, onResumePreviousSession }) {
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label="Behavioral timeline">
        <PanelHeader eyebrow="History" title="Behavioral Timeline" subtitle="Operational record across analyses." />
        <Timeline items={model.historyItems} />
      </section>
      <section className="operational-panel" aria-label="Insight archive">
        <PanelHeader eyebrow="Archive" title="Insight Archive" subtitle="Resolved and historical findings." />
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No insight archive yet." : model.uiState.status.detail}
          emptyTitle={model.analysisComplete ? "No insight archive yet" : model.uiState.status.label}
        />
      </section>
      <section className="operational-panel" aria-label="Comparative analysis">
        <PanelHeader eyebrow="Comparison" title="Compare Operating Periods" subtitle="Before and after review." />
        <p className="operational-copy">Compare two operating periods once multiple analyses are available.</p>
        <p className="operational-copy">Maintenance correlation will appear when maintenance history is connected.</p>
        {model.canResumePrevious && typeof onResumePreviousSession === "function" ? (
          <button type="button" className="secondary-command-button" onClick={onResumePreviousSession}>Resume Previous Analysis</button>
        ) : null}
      </section>
    </div>
  );
}

function buildOperationalModel({ liveOps, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, roomContext, domainDetection, gateProcessing, replayFrame }) {
  const result = effectiveLatestUploadResult ?? liveOps?.latestUploadResult ?? {};
  const snapshot = effectiveLatestUploadSnapshot ?? liveOps?.latestUploadSnapshot ?? {};
  const relationshipRows = Array.isArray(liveOps?.relationshipRows) ? liveOps.relationshipRows : [];
  const quality = collectQuality(result, snapshot);
  const telemetryAvailable = hasTelemetry(result, snapshot, liveOps, replayFrame);
  const telemetryConnected = isTelemetryConnected(liveOps);
  const analysisRunning = isAnalysisRunning({ gateProcessing, result, snapshot, currentSession, liveOps });
  const completedSiiAnalysis = telemetryAvailable && hasCompletedSiiAnalysis({ result, snapshot, currentSession, liveOps });
  const uiState = deriveOperationalUiState({ telemetryAvailable, analysisRunning, analysisComplete: completedSiiAnalysis, telemetryConnected });
  const analysisComplete = uiState.key === "analysisComplete" || uiState.key === "monitoringLive";
  const finding = canonicalFinding ?? liveOps?.canonicalFinding ?? null;
  const hasFinding = analysisComplete && Boolean(finding?.exists || liveOps?.findings?.length);
  const primarySystem = firstText(roomContext?.primary, liveOps?.primaryWindow?.label, result?.system_name, "Primary Water System");
  const baselineAvailable = analysisComplete && hasBaseline({ result, snapshot, relationshipRows, liveOps });
  const telemetryStatus = deriveTelemetryStatus({ result, snapshot, quality, liveOps, analysisComplete, telemetryAvailable, telemetryConnected });
  const heroStatus = uiState.status;
  const lastAnalysis = deriveLastAnalysisLabel({ uiState, liveOps, snapshot, result });
  const fingerprintDrift = deriveFingerprintDrift({ relationshipRows, result, hasFinding, analysisComplete, baselineAvailable });
  const insights = analysisComplete ? buildInsights({ finding, liveOps, result, primarySystem, telemetryStatus, lastAnalysis }) : [];
  const identifiedSystems = analysisComplete ? collectIdentifiedSystems({ liveOps, result, primarySystem }) : [];
  const identifiedSystemCount = identifiedSystems.length;
  const systemCards = analysisComplete ? buildSystemCards({ systems: identifiedSystems, primarySystem, heroStatus, lastAnalysis, insights, fingerprintDrift }) : [];
  const systemSummary = buildSystemSummary({ analysisComplete, identifiedSystemCount, telemetryConnected });
  const signals = buildSignals(result);
  const historyItems = buildHistoryItems({ liveOps, snapshot, result, replayFrame, insights, analysisComplete });
  const domainLabel = formatDomainLabel(domainDetection?.mode ?? result?.domain_detection?.mode ?? result?.detected_schema?.mode ?? "Water system");
  const siteLabel = firstText(result?.facility_name, snapshot?.facility_name, "Current Site");
  const isEmptyTelemetryState = uiState.key === "noTelemetry";
  const sourceLabel = deriveSourceLabel({ uiState, result, snapshot, liveOps });
  const contextLabel = "Site: " + siteLabel + " | Data source: " + sourceLabel;
  const resultSummaryRows = buildResultSummaryRows({ analysisComplete, identifiedSystemCount, relationshipRows, result, liveOps, finding });

  return {
    siteLabel,
    domainLabel,
    sourceLabel,
    contextLabel,
    headerEyebrow: isEmptyTelemetryState ? "NERAIUM SII" : "Neraium Systemic Infrastructure Intelligence",
    headerSubtitle: isEmptyTelemetryState ? siteLabel : contextLabel,
    overviewTabMetric: isEmptyTelemetryState ? "Start" : heroStatus.label,
    showHeroStatusBadge: !isEmptyTelemetryState,
    showStoryProgress: !isEmptyTelemetryState,
    showSourceStatus: !isEmptyTelemetryState,
    showSidebarStatus: !isEmptyTelemetryState,
    sourceStatusLabel: uiState.sourceStatusLabel,
    storyProgressLabel: uiState.storyProgressLabel,
    primaryCtaLabel: uiState.primaryCtaLabel,
    analyzeDisabled: uiState.key === "analyzing",
    showBaselineClaim: baselineAvailable,
    showSystemClaims: analysisComplete,
    resultSummaryRows,
    uiState,
    heroStatus,
    baselineStatus: baselineAvailable ? { label: "Baseline Established", tone: "normal" } : NO_BASELINE_AVAILABLE,
    telemetryStatus,
    lastAnalysis,
    analysisComplete,
    baselineAvailable,
    telemetryConnected,
    identifiedSystemCount,
    fingerprintDrift,
    systemCards,
    systemsTabMetric: systemSummary.tabMetric,
    systemSummaryTitle: systemSummary.title,
    systemSummaryLabel: systemSummary.label,
    systemSummaryCountLabel: systemSummary.countLabel,
    systemSummaryDescriptor: systemSummary.descriptor,
    systemsSectionTitle: systemSummary.sectionTitle,
    systemsSectionSubtitle: systemSummary.sectionSubtitle,
    insights,
    statusTiles: buildStatusTiles({ uiState, telemetryStatus, baselineAvailable, insights, analysisComplete, identifiedSystemCount }),
    relationshipRows,
    signals,
    historyItems,
    qualityWarnings: quality.warnings,
    missingValues: quality.missingValues,
    timestampNotes: quality.timestampNotes,
    canResumePrevious: Boolean(liveOps?.persistedLatestUpload || liveOps?.previousUploadHistory?.length),
    currentSession,
  };
}


function deriveOperationalUiState({ telemetryAvailable, analysisRunning, analysisComplete, telemetryConnected }) {
  if (analysisRunning) {
    return {
      key: "analyzing",
      status: ANALYZING_STATUS,
      sourceStatusLabel: "Analyzing telemetry",
      storyProgressLabel: "Analysis in progress",
      primaryCtaLabel: "Building Fingerprint",
    };
  }
  if (!telemetryAvailable && !telemetryConnected) {
    return {
      key: "noTelemetry",
      status: NO_TELEMETRY_STATUS,
      sourceStatusLabel: EMPTY_TELEMETRY_COPY.headerStatus,
      storyProgressLabel: "",
      primaryCtaLabel: EMPTY_TELEMETRY_COPY.cta,
    };
  }
  if (analysisComplete && telemetryConnected) {
    return {
      key: "monitoringLive",
      status: MONITORING_LIVE_STATUS,
      sourceStatusLabel: "Live telemetry connected",
      storyProgressLabel: "Live telemetry connected",
      primaryCtaLabel: "Analyze Telemetry",
    };
  }
  if (analysisComplete) {
    return {
      key: "analysisComplete",
      status: ANALYSIS_COMPLETE_STATUS,
      sourceStatusLabel: "Historical telemetry analyzed",
      storyProgressLabel: "Analysis based on uploaded telemetry",
      primaryCtaLabel: "Analyze Telemetry",
    };
  }
  return {
    key: "readyToAnalyze",
    status: READY_TO_ANALYZE_STATUS,
    sourceStatusLabel: telemetryConnected ? "Live telemetry connected" : "Telemetry loaded",
    storyProgressLabel: "Telemetry loaded; analysis not run",
    primaryCtaLabel: "Analyze Telemetry",
  };
}

function deriveSourceLabel({ uiState, result, snapshot, liveOps }) {
  if (uiState.key === "noTelemetry") return "None";
  return firstMeaningfulText(
    result?.result_source,
    snapshot?.result_source,
    result?.source,
    snapshot?.source,
    result?.filename,
    snapshot?.filename,
    snapshot?.current_upload?.filename,
    snapshot?.current_upload?.source,
    liveOps?.telemetrySession?.source,
    liveOps?.telemetrySession?.sessionMode,
    uiState.key === "monitoringLive" ? "Live telemetry" : "Uploaded telemetry"
  );
}

function deriveLastAnalysisLabel({ uiState, liveOps, snapshot, result }) {
  if (uiState.key === "noTelemetry") return "No analysis yet";
  if (uiState.key === "readyToAnalyze") return "Not analyzed yet";
  if (uiState.key === "analyzing") return "Analysis in progress";
  return firstText(snapshot?.processed_at, snapshot?.last_processed_at, result?.processed_at, result?.timestamp_profile?.last_timestamp, liveOps?.connectionSummary, "Analysis complete");
}

function buildSystemSummary({ analysisComplete, identifiedSystemCount, telemetryConnected }) {
  if (!analysisComplete) {
    return {
      tabMetric: SYSTEMS_PENDING.countLabel,
      title: SYSTEMS_PENDING.title,
      label: SYSTEMS_PENDING.summary,
      countLabel: SYSTEMS_PENDING.countLabel,
      descriptor: "Pending",
      sectionTitle: SYSTEMS_PENDING.title,
      sectionSubtitle: SYSTEMS_PENDING.summary,
    };
  }

  const noun = identifiedSystemCount === 1 ? "system" : "systems";
  const descriptor = telemetryConnected ? "systems monitored" : "systems identified";
  const label = telemetryConnected
    ? `${identifiedSystemCount} ${noun} monitored`
    : `${identifiedSystemCount} ${noun} identified`;

  return {
    tabMetric: String(identifiedSystemCount),
    title: "Systems Identified",
    label,
    countLabel: String(identifiedSystemCount),
    descriptor,
    sectionTitle: telemetryConnected ? "Monitored Systems" : "Identified Systems",
    sectionSubtitle: telemetryConnected ? "Live telemetry is connected." : "Systems identified by completed SII analysis.",
  };
}

function buildResultSummaryRows({ analysisComplete, identifiedSystemCount, relationshipRows, result, liveOps, finding }) {
  if (!analysisComplete) return [];
  const baselineConfidence = firstText(
    result?.baseline_confidence,
    result?.baseline_analysis?.confidence,
    result?.baseline_profile?.confidence,
    result?.sii_intelligence?.baseline?.confidence,
    liveOps?.baseline?.confidence
  );
  const topRisk = deriveTopRisk({ result, liveOps, finding });
  const recommendedAction = firstText(
    result?.recommended_action,
    result?.recommendation,
    result?.operator_report?.recommended_action,
    result?.operator_report?.review_next,
    finding?.recommendation,
    finding?.reviewNext,
    liveOps?.recommendedAction,
    "Continue monitoring"
  );
  return [
    ["Systems identified", String(identifiedSystemCount)],
    relationshipRows.length > 0 ? ["Relationships mapped", String(relationshipRows.length)] : null,
    baselineConfidence ? ["Baseline confidence", formatConfidence(baselineConfidence)] : null,
    ["Top risk", topRisk],
    ["Recommended action", recommendedAction],
  ];
}

function deriveTopRisk({ result, liveOps, finding }) {
  return firstText(
    result?.top_risk,
    result?.risk_summary,
    result?.operator_report?.top_risk,
    finding?.summary,
    finding?.title,
    liveOps?.topRisk,
    "No major risk detected"
  );
}

function formatConfidence(value) {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return (numeric <= 1 ? Math.round(numeric * 100) : Math.round(numeric)) + "%";
  }
  return String(value);
}

function collectIdentifiedSystems({ liveOps, result, primarySystem }) {
  const candidates = [
    liveOps?.identifiedSystems,
    liveOps?.analyzedSystems,
    result?.identified_systems,
    result?.analyzed_systems,
    result?.systems_identified,
    result?.systems,
    liveOps?.systems,
  ];
  const systems = candidates.find((items) => Array.isArray(items) && items.length > 0) ?? [];
  if (systems.length > 0) {
    return systems.map((system, index) => ({
      id: system.id ?? system.name ?? system.label ?? `system-${index}`,
      name: firstText(system.name, system.label, system.system_name, `System ${index + 1}`),
    }));
  }
  return [{ id: "primary", name: primarySystem }];
}

function buildInsights({ finding, liveOps, result, primarySystem, telemetryStatus, lastAnalysis }) {
  const rawFindings = [];
  if (finding?.exists || finding?.summary || finding?.title) rawFindings.push(finding);
  if (Array.isArray(liveOps?.findings)) rawFindings.push(...liveOps.findings);

  const insights = rawFindings
    .filter(Boolean)
    .map((item, index) => {
      const summary = firstText(item.summary, item.detail, item.title, result?.operator_report?.summary, "System behavior changed from the historical operating pattern.");
      const priorities = toList(item.reviewNext, item.recommendation, item.operator_focus, result?.operator_report?.review_next)
        .flatMap(splitPriorityText);
      const supporting = toList(item.supportingEvidence, item.relationshipEvidence, result?.operator_report?.evidence_summary, result?.finding_evidence_chains)
        .flatMap(splitPriorityText);
      return {
        id: `insight-${index}`,
        system: firstText(item.label, item.affectedSubsystem, item.affected_system, primarySystem),
        status: normalizeInsightStatus(item.status ?? result?.operating_state),
        severity: normalizeSeverity(item.confidence ?? result?.drift_status),
        summary,
        whatChanged: summary,
        whyItMatters: firstText(item.whyItMatters, "The system is no longer matching its operating pattern and may require review."),
        systemBehavior: firstText(item.baselineContext, item.change, "Current behavior is being compared against the historical operating fingerprint."),
        investigationPriorities: priorities.length ? priorities : ["Verify supporting measurements", "Inspect affected equipment", "Compare current operation with recent maintenance activity"],
        supportingObservations: supporting.length ? supporting : ["Behavior changed from historical baseline", "Telemetry was analyzed for relationship changes"],
        telemetryNote: telemetryStatus.detail,
        detectedAt: lastAnalysis,
      };
    });

  if (insights.length > 0) return dedupeInsights(insights).slice(0, 8);
  return [];
}

function buildSystemCards({ systems, primarySystem, heroStatus, lastAnalysis, insights, fingerprintDrift }) {
  const safeSystems = Array.isArray(systems) && systems.length > 0
    ? systems.slice(0, 6).map((system, index) => ({ id: system.id ?? system.name ?? `system-${index}`, name: system.name ?? system.label ?? `System ${index + 1}` }))
    : [{ id: "primary", name: primarySystem }];

  return safeSystems.map((system) => {
    const relatedInsights = insights.filter((item) => item.system === system.name || safeSystems.length === 1);
    return {
      id: system.id,
      name: system.name,
      status: heroStatus.label,
      tone: heroStatus.tone,
      summary: fingerprintDrift.detail,
      lastAnalysis,
      insightSummary: `${relatedInsights.length} active insight${relatedInsights.length === 1 ? "" : "s"}`,
      primaryInsightId: relatedInsights[0]?.id ?? null,
    };
  });
}

function buildStatusTiles({ uiState, telemetryStatus, baselineAvailable, insights, analysisComplete, identifiedSystemCount }) {
  if (uiState.key === "noTelemetry") {
    return [
      { label: "Telemetry", value: "None", detail: "Connect a source to populate this workspace.", tone: "unknown" },
      { label: "Systems", value: SYSTEMS_PENDING.countLabel, detail: SYSTEMS_PENDING.summary, tone: "unknown" },
      { label: "Fingerprint", value: "Pending", detail: NO_BASELINE_AVAILABLE.detail, tone: "unknown" },
    ];
  }

  if (!analysisComplete) {
    return [
      { label: "Telemetry", value: telemetryStatus.label, detail: telemetryStatus.detail, tone: telemetryStatus.tone },
      { label: "Status", value: uiState.status.label, detail: uiState.status.detail, tone: uiState.status.tone },
      { label: "Systems", value: SYSTEMS_PENDING.title, detail: SYSTEMS_PENDING.summary, tone: "unknown" },
      { label: "Fingerprint", value: NO_BASELINE_AVAILABLE.label, detail: NO_BASELINE_AVAILABLE.detail, tone: "unknown" },
    ];
  }

  return [
    { label: "Telemetry", value: telemetryStatus.label, detail: telemetryStatus.detail, tone: telemetryStatus.tone },
    { label: "Status", value: uiState.status.label, detail: uiState.status.detail, tone: uiState.status.tone },
    { label: "Systems", value: String(identifiedSystemCount), detail: identifiedSystemCount + " " + (identifiedSystemCount === 1 ? "system" : "systems") + " identified by SII analysis.", tone: "normal" },
    { label: "Insights", value: String(insights.length), detail: insights.length + " active " + (insights.length === 1 ? "insight" : "insights"), tone: insights.length > 0 ? "changed" : "unknown" },
    baselineAvailable ? { label: "Fingerprint", value: "Established", detail: "Fingerprint comparison is available.", tone: "normal" } : null,
  ].filter(Boolean);
}

function collectQuality(result, snapshot) {
  const dataQuality = result?.data_quality ?? {};
  const timestampProfile = result?.timestamp_profile ?? {};
  const warnings = dedupeText([
    ...(Array.isArray(dataQuality.warnings) ? dataQuality.warnings : []),
    ...(Array.isArray(timestampProfile.warnings) ? timestampProfile.warnings : []),
    ...(Array.isArray(result?.warnings) ? result.warnings : []),
    ...(Array.isArray(result?.backend_warnings) ? result.backend_warnings : []),
  ]);
  const missingValues = dedupeText([
    ...(Array.isArray(dataQuality.missing_values) ? dataQuality.missing_values : []),
    ...(Array.isArray(dataQuality.missing_value_warnings) ? dataQuality.missing_value_warnings : []),
    ...(Array.isArray(result?.missing_values) ? result.missing_values : []),
  ]);
  const timestampNotes = dedupeText([
    timestampProfile.mode,
    timestampProfile.first_timestamp && timestampProfile.last_timestamp ? `${timestampProfile.first_timestamp} to ${timestampProfile.last_timestamp}` : null,
    result?.timestamp_mode,
    snapshot?.timestamp_mode,
  ]);
  return { warnings, missingValues, timestampNotes };
}

function deriveTelemetryStatus({ result, snapshot, quality, liveOps, analysisComplete, telemetryAvailable, telemetryConnected }) {
  if (!analysisComplete) {
    if (telemetryConnected) return { label: "Telemetry Connected", tone: "normal", detail: "Live telemetry is connected; run analysis to identify systems and relationships." };
    return telemetryAvailable
      ? { label: "Telemetry Loaded", tone: "unknown", detail: READY_TO_ANALYZE_STATUS.detail }
      : WAITING_FOR_TELEMETRY_STATUS;
  }
  const text = `${quality.warnings.join(" ")} ${quality.missingValues.join(" ")} ${liveOps?.connectionStatusLine ?? ""}`.toLowerCase();
  if (!result && !snapshot) return { label: "Telemetry Missing", tone: "unknown", detail: "No telemetry has been analyzed yet." };
  if (text.includes("missing")) return { label: "Telemetry Missing", tone: "warning", detail: "Some telemetry values or sources are missing." };
  if (text.includes("inconsistent") || text.includes("timestamp")) return { label: "Telemetry Needs Review", tone: "warning", detail: "Telemetry timing or source consistency needs review." };
  if (quality.warnings.length > 0 || quality.missingValues.length > 0 || String(liveOps?.connectionTone ?? "").includes("degraded")) {
    return { label: "Telemetry Needs Review", tone: "warning", detail: "Telemetry is usable, but one or more quality conditions should be reviewed." };
  }
  return { label: "Telemetry Verified", tone: "normal", detail: "Telemetry integrity is acceptable for operational review." };
}

function deriveFingerprintDrift({ relationshipRows, result, hasFinding, analysisComplete, baselineAvailable }) {
  if (!baselineAvailable) {
    return {
      ...NO_BASELINE_AVAILABLE,
      detail: NO_BASELINE_AVAILABLE.detail,
    };
  }
  if (!analysisComplete) {
    return {
      ...READY_TO_ANALYZE_STATUS,
      detail: "Fingerprint comparison will populate after SII completes analysis.",
    };
  }
  const magnitudes = relationshipRows.map((row) => Math.abs(Number(row.percent_change ?? row.absolute_change ?? row.pair_weight ?? row.change ?? 0))).filter(Number.isFinite);
  const max = magnitudes.length ? Math.max(...magnitudes) : 0;
  if (max > 30 || hasFinding || String(result?.drift_status ?? "").toLowerCase().includes("unstable")) {
    return { label: "Significant Change", tone: "investigate", detail: "Current behavior is materially different from the historical baseline." };
  }
  if (max > 10 || String(result?.drift_status ?? "").toLowerCase().includes("review")) {
    return { label: "Drifting", tone: "changed", detail: "Current behavior is moving away from the historical baseline." };
  }
  return { label: "Stable", tone: "normal", detail: "Current behavior remains close to the historical operating fingerprint." };
}

function buildSignals(result) {
  const columns = Array.isArray(result?.columns) ? result.columns : [];
  const detected = Array.isArray(result?.detected_columns) ? result.detected_columns : [];
  return dedupeText([...columns, ...detected]).slice(0, 24);
}

function buildHistoryItems({ liveOps, snapshot, result, replayFrame, insights, analysisComplete }) {
  const items = [];
  const previous = Array.isArray(liveOps?.previousUploadHistory) ? liveOps.previousUploadHistory : [];
  previous.slice(0, 8).forEach((entry, index) => {
    items.push({
      id: `previous-${index}`,
      title: entry.filename ?? entry.job_id ?? "Previous analysis",
      time: entry.last_processed_at ?? entry.processed_at ?? "Previous period",
      detail: "Previous telemetry analysis available for review.",
    });
  });
  if (analysisComplete && (snapshot?.processed_at || result?.processed_at || replayFrame)) {
    items.unshift({
      id: "current-analysis",
      title: insights.length ? "Current insight generated" : "Current analysis completed",
      time: snapshot?.processed_at ?? result?.processed_at ?? "Current period",
      detail: insights[0]?.summary ?? "Current telemetry was analyzed for system behavior changes.",
    });
  }
  return items;
}

function RelationshipList({ rows }) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return <EmptyOperationalState title="No relationship shifts" body="Relationship drift will appear after baseline comparison is available." />;
  }
  return (
    <ul className="operational-list">
      {rows.slice(0, 8).map((row, index) => {
        const label = Array.isArray(row.columns) ? row.columns.join(" / ") : firstText(row.column, row.pair, row.detail, `Relationship ${index + 1}`);
        const detail = firstText(row.detail, row.summary, row.direction, "Relationship behavior changed against baseline.");
        return <li key={`${label}-${index}`}><strong>{label}</strong><span>{detail}</span></li>;
      })}
    </ul>
  );
}

function SignalList({ signals, integrity }) {
  if (!signals.length) return <EmptyOperationalState title="No signals detected" body="Upload telemetry to populate the signal browser." />;
  return (
    <ul className="operational-list operational-list--signals">
      {signals.map((signal) => <li key={signal}><strong>{signal}</strong><span>{integrity.label}</span></li>)}
    </ul>
  );
}

function InsightList({ insights, empty, emptyTitle = "No active insights", onOpenInsight, selectedId }) {
  if (!insights.length) return <EmptyOperationalState title={emptyTitle} body={empty} />;
  return (
    <div className="insight-feed">
      {insights.map((insight) => {
        const Tag = typeof onOpenInsight === "function" ? "button" : "article";
        return (
          <Tag
            key={insight.id}
            type={Tag === "button" ? "button" : undefined}
            className={`insight-card ${selectedId === insight.id ? "is-selected" : ""}`}
            onClick={Tag === "button" ? () => onOpenInsight(insight.id) : undefined}
          >
            <div className="insight-card__header">
              <span className="section-token">{insight.system}</span>
              <StatusBadge label={insight.status} tone={statusToTone(insight.status)} />
            </div>
            <strong>{insight.summary}</strong>
            <p>{insight.whyItMatters}</p>
            <small>{insight.detectedAt}</small>
          </Tag>
        );
      })}
    </div>
  );
}

function Timeline({ items }) {
  if (!items.length) return <EmptyOperationalState title="No history yet" body="Previous analyses and insight events will appear here over time." />;
  return (
    <ol className="operational-timeline">
      {items.map((item) => <li key={item.id}><span>{item.time}</span><strong>{item.title}</strong><p>{item.detail}</p></li>)}
    </ol>
  );
}

function QualityList({ title, items, empty }) {
  return (
    <section className="operational-block">
      <h3>{title}</h3>
      {items.length ? <ul className="compact-list">{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p>{empty}</p>}
    </section>
  );
}

function DetailGrid({ rows }) {
  return (
    <dl className="operational-detail-grid">
      {rows.filter((row) => row && row.length >= 2).filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "").map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function CompactStatusTile({ tile }) {
  return (
    <article className={`status-tile status-tile--${tile.tone}`}>
      <span>{tile.label}</span>
      <strong>{tile.value}</strong>
      <small>{tile.detail}</small>
    </article>
  );
}

function FingerprintStatus({ drift }) {
  return (
    <div className={`fingerprint-status fingerprint-status--${drift.tone}`}>
      <strong>{drift.label}</strong>
      <p>{drift.detail}</p>
    </div>
  );
}

function PanelHeader({ eyebrow, title, subtitle }) {
  return (
    <div className="operational-panel__header">
      <span className="section-token">{eyebrow}</span>
      <h2>{title}</h2>
      {subtitle ? <p>{subtitle}</p> : null}
    </div>
  );
}

function StatusBadge({ label, tone }) {
  return <span className={`operational-status operational-status--${tone}`}>{label}</span>;
}

function EmptyOperationalState({ title, body }) {
  return <div className="operational-empty"><strong>{title}</strong><p>{body}</p></div>;
}

function sectionTitle(section) {
  if (section === "insights") return "Insights";
  if (section === "systems") return "Systems";
  if (section === "telemetry") return "Telemetry";
  if (section === "history") return "History";
  return "Overview";
}

function normalizeInsightStatus(value) {
  const text = String(value ?? "").toLowerCase();
  if (text.includes("resolve")) return "Resolved";
  if (text.includes("investigat") || text.includes("review")) return "Under Investigation";
  if (text.includes("ack")) return "Acknowledged";
  return "Open";
}

function normalizeSeverity(value) {
  const text = String(value ?? "").toLowerCase();
  if (text.includes("high") || text.includes("unstable") || text.includes("critical")) return "High";
  if (text.includes("moderate") || text.includes("review") || text.includes("elevated")) return "Moderate";
  return "Low";
}

function statusToTone(status) {
  if (status === "Resolved") return "normal";
  if (status === "Under Investigation") return "changed";
  return "investigate";
}

function splitPriorityText(value) {
  return String(value ?? "")
    .split(/\n|;|\.|\u2022/g)
    .map((item) => item.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 8);
}

function toList(...values) {
  return values.flatMap((value) => {
    if (Array.isArray(value)) return value;
    if (value === null || value === undefined || value === "") return [];
    return [value];
  });
}

function dedupeText(items) {
  return [...new Set(items.filter((item) => item !== null && item !== undefined).map((item) => String(item).trim()).filter(Boolean))];
}

function dedupeInsights(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = `${item.system}-${item.summary}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function firstText(...values) {
  const value = values.find((item) => item !== null && item !== undefined && String(item).trim() !== "");
  return value === undefined ? "" : String(value);
}

function firstMeaningfulText(...values) {
  const value = values.find((item) => !isPlaceholderValue(item));
  return value === undefined ? "" : String(value);
}

function isPlaceholderValue(value) {
  if (value === null || value === undefined) return true;
  const text = String(value).trim().toLowerCase();
  return !text || ["empty", "none", "null", "undefined", "no_data", "no data", "n/a", "na"].includes(text);
}

function isTelemetryConnected(liveOps) {
  const text = `${liveOps?.connectionTone ?? ""} ${liveOps?.connectionStatusLine ?? ""} ${liveOps?.connectionSummary ?? ""} ${liveOps?.telemetrySession?.sessionMode ?? ""}`.toLowerCase();
  return Boolean(
    liveOps?.telemetryConnected === true
    || liveOps?.connectionStatus === "connected"
    || liveOps?.connectionStatus === "live"
    || liveOps?.telemetrySession?.connected === true
    || text.includes("connected")
    || text.includes("live telemetry")
  );
}

function isAnalysisRunning({ gateProcessing, result, snapshot, currentSession, liveOps }) {
  const statusText = [
    gateProcessing?.status,
    gateProcessing?.state,
    gateProcessing?.processing_state,
    result?.status,
    result?.processing_state,
    snapshot?.status,
    snapshot?.processing_state,
    currentSession?.status,
    liveOps?.latestStatus,
    liveOps?.uploadState,
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  return Boolean(
    gateProcessing?.active === true
    || currentSession?.isProcessing === true
    || liveOps?.processing === true
    || statusText.includes("processing")
    || statusText.includes("analyzing")
    || statusText.includes("running")
    || statusText.includes("queued")
  );
}

function hasCompletedSiiAnalysis({ result, snapshot, currentSession, liveOps }) {
  const hasIntelligenceData = Boolean(result?.sii_intelligence || result?.engine_result);
  const completed = Boolean(
    currentSession?.hasReliableOperatorEvidence === true
    || result?.sii_reliable_enough_to_show === true
    || result?.sii_completed === true
    || result?.processing_trace?.sii_completed === true
    || snapshot?.sii_completed === true
    || liveOps?.siiVerification?.verified === true
  );
  return hasIntelligenceData && completed;
}

function hasTelemetry(result, snapshot, liveOps, replayFrame) {
  if (replayFrame) return true;
  if (isTelemetryConnected(liveOps)) return true;

  const snapshotStatus = String(snapshot?.status ?? "").trim().toLowerCase();
  const resultStatus = String(result?.status ?? result?.processing_state ?? "").trim().toLowerCase();
  const validUploadStatuses = new Set(["complete", "completed", "uploaded", "ready", "valid", "success", "processed"]);
  const invalidUploadStatuses = new Set(["", "empty", "idle", "pending", "none", "null", "undefined", "failed", "error", "cleared", "reset"]);
  const uploadStatusValid = validUploadStatuses.has(snapshotStatus) || validUploadStatuses.has(resultStatus);
  const uploadStatusInvalid = invalidUploadStatuses.has(snapshotStatus) && invalidUploadStatuses.has(resultStatus);
  const currentUpload = snapshot?.current_upload ?? result?.current_upload ?? liveOps?.currentUpload ?? null;
  const hasUpload = Boolean(
    currentUpload
    || !isPlaceholderValue(result?.job_id)
    || !isPlaceholderValue(snapshot?.job_id)
    || !isPlaceholderValue(result?.upload_id)
    || !isPlaceholderValue(snapshot?.upload_id)
  );
  const hasSource = Boolean(firstMeaningfulText(
    result?.result_source,
    snapshot?.result_source,
    result?.source,
    snapshot?.source,
    result?.filename,
    snapshot?.filename,
    currentUpload?.filename,
    currentUpload?.source,
    liveOps?.telemetrySession?.source,
    liveOps?.telemetrySession?.sessionMode
  ));
  const hasRowsIfReported = [
    result?.row_count,
    result?.rows,
    result?.record_count,
    result?.records,
    snapshot?.row_count,
    snapshot?.rows,
    snapshot?.record_count,
    snapshot?.records,
    currentUpload?.row_count,
    currentUpload?.rows,
    currentUpload?.record_count,
    currentUpload?.records,
  ].every((value) => value === null || value === undefined || Number(value) > 0);
  const hasDetectedTelemetry = Boolean(
    result?.processed_at
    || result?.timestamp_profile?.last_timestamp
    || result?.columns?.length
    || result?.detected_columns?.length
    || snapshot?.processed_at
    || snapshot?.last_processed_at
  );

  return Boolean(
    hasUpload
    && hasSource
    && hasRowsIfReported
    && !uploadStatusInvalid
    && (uploadStatusValid || hasDetectedTelemetry)
  );
}

function hasBaseline({ result, snapshot, relationshipRows, liveOps }) {
  return Boolean(
    relationshipRows.length > 0
    || result?.baseline_analysis
    || result?.baseline_profile
    || result?.sii_intelligence
    || result?.sii_intelligence?.baseline
    || result?.sii_intelligence?.historical_baseline
    || snapshot?.baseline_status === "active"
    || liveOps?.baseline?.active
  );
}

function formatDomainLabel(value) {
  return String(value ?? "Water system")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}
