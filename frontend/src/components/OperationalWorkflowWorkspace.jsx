import { useDeferredValue, useMemo, useState } from "react";

import PageContainer from "./layout/PageContainer";
import "../styles/operational-workflow.css";
import "../styles/design-system.css";

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "insights", label: "Insights" },
  { id: "systems", label: "Systems" },
  { id: "fingerprint", label: "Fingerprint" },
  { id: "more", label: "More" },
];

const MOBILE_PRIMARY_NAV = [
  { id: "overview", label: "Overview" },
  { id: "insights", label: "Insights" },
  { id: "systems", label: "Systems" },
  { id: "fingerprint", label: "Fingerprint" },
  { id: "more", label: "More" },
];

const INVESTIGATION_STATUSES = ["Open", "Acknowledged", "Under Investigation", "Resolved"];
const EMPTY_TELEMETRY_COPY = {
  label: "Start with telemetry",
  detail: "Upload a CSV to begin analysis.",
  cta: "Upload CSV",
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
  label: "CSV loaded / Ready to analyze",
  tone: "unknown",
  detail: "Upload is available. Run analysis to identify systems, relationships, anomalies, and baseline behavior.",
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
  const [selectedInsightId, setSelectedInsightId] = useState(null);
  const [insightStatuses, setInsightStatuses] = useState({});
  const [operatorNotes, setOperatorNotes] = useState({});

  const deferredLiveOps = useDeferredValue(liveOps);
  const deferredCanonicalFinding = useDeferredValue(canonicalFinding);
  const deferredCurrentSession = useDeferredValue(currentSession);
  const deferredLatestUploadResult = useDeferredValue(effectiveLatestUploadResult);
  const deferredLatestUploadSnapshot = useDeferredValue(effectiveLatestUploadSnapshot);
  const deferredRoomContext = useDeferredValue(roomContext);
  const deferredDomainDetection = useDeferredValue(domainDetection);
  const deferredGateProcessing = useDeferredValue(gateProcessing);
  const deferredReplayFrame = useDeferredValue(replayFrame);

  const model = useMemo(() => buildOperationalModel({
    liveOps: deferredLiveOps,
    canonicalFinding: deferredCanonicalFinding,
    currentSession: deferredCurrentSession,
    effectiveLatestUploadResult: deferredLatestUploadResult,
    effectiveLatestUploadSnapshot: deferredLatestUploadSnapshot,
    roomContext: deferredRoomContext,
    domainDetection: deferredDomainDetection,
    gateProcessing: deferredGateProcessing,
    replayFrame: deferredReplayFrame,
  }), [
    deferredLiveOps,
    deferredCanonicalFinding,
    deferredCurrentSession,
    deferredLatestUploadResult,
    deferredLatestUploadSnapshot,
    deferredRoomContext,
    deferredDomainDetection,
    deferredGateProcessing,
    deferredReplayFrame,
  ]);

  const selectedInsight = model.insights.find((item) => item.id === selectedInsightId) ?? model.insights[0] ?? null;
  const navMetrics = {
    overview: model.overviewTabMetric,
    insights: String(model.insights.length),
    systems: model.systemsTabMetric,
    fingerprint: model.fingerprintTabMetric,
    more: model.moreTabMetric,
  };

  function navigate(sectionId) {
    setActiveSection(sectionId);
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

        {activeSection === "fingerprint" ? (
          <FingerprintSection model={model} />
        ) : null}

        {activeSection === "more" ? (
          <MoreSection model={model} onAnalyzeSystem={analyzeSystem} onResumePreviousSession={onResumePreviousSession} />
        ) : null}

        {typeof onUploadComplete === "function" ? null : null}
      </main>
    </PageContainer>
  );
}

function OverviewSection({ model, onOpenInsight, onAnalyzeSystem, onResumePreviousSession, onViewSystems }) {
  const heroRows = buildOverviewHeroRows(model);
  const brief = buildOverviewBrief(model);
  const checklistItems = buildOverviewChecklist(model);
  const historyItems = model.historyItems.slice(0, 4);
  const fallbackOutputs = buildOverviewOutputs(model);
  const primaryInsight = model.insights[0] ?? null;
  const showSystemsAction = model.analysisComplete && model.identifiedSystemCount > 0;
  const showSupportGrid = model.analysisComplete || model.overviewState === "analyzing";

  function renderPrimaryAction() {
    if (model.analysisComplete && primaryInsight) {
      return <button type="button" className="command-button" onClick={() => onOpenInsight(primaryInsight.id)}>Open Top Insight</button>;
    }
    return (
      <button type="button" className="command-button" onClick={onAnalyzeSystem} disabled={model.analyzeDisabled}>
        {model.overviewState === "noCsvUploaded" ? EMPTY_TELEMETRY_COPY.cta : model.primaryCtaLabel}
      </button>
    );
  }

  function renderSecondaryAction() {
    if (showSystemsAction) {
      return <button type="button" className="secondary-command-button" onClick={onViewSystems}>View Systems</button>;
    }
    if (model.canResumePrevious && typeof onResumePreviousSession === "function") {
      return <button type="button" className="operational-link-button" onClick={onResumePreviousSession}>Resume Previous Analysis</button>;
    }
    return null;
  }

  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--hero operational-panel--wide" aria-label="Overview status">
        <div className="operational-hero">
          <div className="operational-hero__summary">
            <div className="operational-panel__header operational-panel__header--tight">
              <span className="section-token">Overview</span>
              <h2>{model.overviewState === "noCsvUploaded" ? EMPTY_TELEMETRY_COPY.label : model.heroStatus.label}</h2>
              <p>{model.overviewState === "noCsvUploaded" ? EMPTY_TELEMETRY_COPY.detail : model.heroStatus.detail}</p>
            </div>
            {model.overviewState === "noCsvUploaded" ? null : (
              <div className="operational-hero__meta">
                <span>{model.storyProgressLabel || "Awaiting telemetry"}</span>
                <span>{model.sourceLabel}</span>
                <span>{model.telemetryStatus.label}</span>
                {model.showBaselineClaim ? <span>{model.baselineStatus.label}</span> : null}
              </div>
            )}
            {model.analysisComplete ? (
              <div className="operational-result-summary" aria-label="Executive summary">
                <DetailGrid rows={model.executiveSummaryRows} />
              </div>
            ) : (
              <div className="operational-result-summary" aria-label="Source summary">
                <DetailGrid rows={model.overviewState === "noCsvUploaded" ? [
                  ["Source", model.sourceLabel],
                  ["Status", "Awaiting upload"],
                  ["Rows", model.sourceRowCount],
                  ["Telemetry", "No CSV yet"],
                ] : [
                  ["Source", model.sourceLabel],
                  ["Status", model.sourceStatusLabel],
                  ["Rows", model.sourceRowCount],
                  ["Telemetry", model.telemetryStatus.label],
                ]} />
              </div>
            )}
            <div className="operational-actions operational-actions--hero">
              {renderPrimaryAction()}
              {renderSecondaryAction()}
            </div>
          </div>
          <aside className="operational-hero__aside" aria-label="Overview quick facts">
            <span className="section-token">Command pulse</span>
            <DetailGrid rows={heroRows} />
          </aside>
        </div>
      </section>

      {showSupportGrid ? (
        <div className="overview-support-grid">
          <section className="operational-panel" aria-label="Status at a glance">
            <PanelHeader eyebrow="Command Pulse" title="Status At A Glance" subtitle="Immediate telemetry, fingerprint, and system posture." />
            <div className="status-rack status-rack--dense">
              {model.statusTiles.map((tile) => <CompactStatusTile key={tile.label} tile={tile} />)}
            </div>
          </section>

          <section className="operational-panel" aria-label="Operator brief">
            <PanelHeader eyebrow="Operator Brief" title={brief.title} subtitle={brief.subtitle} />
            <ul className="operational-list operational-list--stacked overview-checklist">
              {checklistItems.map((item) => (
                <li key={item}>
                  <strong>{item}</strong>
                </li>
              ))}
            </ul>
            <div className="operational-actions operational-actions--overview">
              {model.analysisComplete && primaryInsight ? (
                <button type="button" className="secondary-command-button" onClick={() => onOpenInsight(primaryInsight.id)}>Inspect Finding</button>
              ) : null}
              {showSystemsAction ? (
                <button type="button" className="secondary-command-button" onClick={onViewSystems}>Open Systems</button>
              ) : null}
            </div>
          </section>

          <section className="operational-panel operational-panel--wide" aria-label="Recent analysis activity">
            <PanelHeader eyebrow="Activity" title={historyItems.length ? "Recent Analysis Activity" : "What This Run Returns"} subtitle={historyItems.length ? "Latest analysis and historical context." : "What the operator receives when analysis completes."} />
            {historyItems.length ? (
              <Timeline items={historyItems} />
            ) : (
              <ul className="operational-list operational-list--stacked overview-checklist">
                {fallbackOutputs.map((item) => (
                  <li key={item}>
                    <strong>{item}</strong>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}

function buildOverviewHeroRows(model) {
  const primaryInsight = model.insights[0] ?? null;
  if (model.overviewState === "noCsvUploaded") {
    return [
      ["Telemetry", "Awaiting upload"],
      ["Systems", SYSTEMS_PENDING.countLabel],
      ["Fingerprint", "Pending"],
      ["Last analysis", model.lastAnalysis],
    ];
  }

  return [
    ["Telemetry", model.telemetryStatus.label],
    ["Systems", model.analysisComplete ? String(model.identifiedSystemCount) : SYSTEMS_PENDING.countLabel],
    ["Fingerprint", model.analysisComplete ? model.fingerprintDrift.label : NO_BASELINE_AVAILABLE.label],
    ["Top insight", primaryInsight?.system ?? (model.analysisComplete ? "No active insight" : "Pending")],
    ["Source", model.sourceLabel],
    ["Last analysis", model.lastAnalysis],
  ];
}

function buildOverviewBrief(model) {
  if (model.overviewState === "noCsvUploaded") {
    return {
      title: "Start With A Telemetry Export",
      subtitle: "Upload a CSV and Neraium will turn it into a systems view, operating fingerprint, and operator-ready brief.",
    };
  }
  if (model.overviewState === "analyzing") {
    return {
      title: "Analysis Is In Motion",
      subtitle: "The pipeline is validating telemetry, building the fingerprint, and translating the result into operator language.",
    };
  }
  if (model.analysisComplete) {
    return {
      title: "Use The Result To Decide What To Check Next",
      subtitle: "Focus first on the highest-risk system, then confirm the telemetry conditions before acting.",
    };
  }
  return {
    title: "Telemetry Is Loaded And Ready",
    subtitle: "Run analysis to identify systems, map relationships, and establish the operating fingerprint.",
  };
}

function buildOverviewChecklist(model) {
  if (model.overviewState === "noCsvUploaded") {
    return [
      "Choose a timestamped telemetry CSV from the system you want to review.",
      "Run analysis to identify systems, relationships, and baseline behavior.",
      "Open Insights and Systems after the run completes to inspect what changed.",
    ];
  }
  if (model.overviewState === "analyzing") {
    return [
      "Validation and normalization are running first so the result stays trustworthy.",
      "The fingerprint pass compares current behavior with the learned baseline before insights are published.",
      "When saving completes, results appear immediately even if final report artifacts keep processing in the background.",
    ];
  }
  if (model.analysisComplete) {
    const topInsight = model.insights[0]?.summary ?? "Review the highest-priority system change first.";
    return [
      `Primary focus: ${topInsight}`,
      `Telemetry posture: ${model.telemetryStatus.detail}`,
      `Fingerprint readout: ${model.fingerprintDrift.detail}`,
    ];
  }
  return [
    "The CSV is available and ready for the analysis pipeline.",
    "Neraium will identify systems, map relationships, and build the operating fingerprint from this export.",
    "Use the result to move from raw telemetry to specific operator checks.",
  ];
}

function buildOverviewOutputs(model) {
  const outputs = [
    "Identified systems and affected equipment groups.",
    "Mapped signal relationships and system-level drift.",
    "An operating fingerprint with insight summaries and recommended checks.",
  ];
  if (model.overviewState !== "noCsvUploaded") {
    outputs.push("Telemetry quality warnings so the operator knows how much to trust the result.");
  }
  return outputs;
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
              ["Severity", selectedInsight.severity],
              ["Confidence", selectedInsight.confidenceScore ? `${selectedInsight.confidence} (${selectedInsight.confidenceScore})` : selectedInsight.confidence],
              ["Confidence rationale", selectedInsight.confidenceRationale],
              ["Evidence summary", selectedInsight.evidenceSummary],
              ["What happened", selectedInsight.whatHappened],
              ["Why Neraium thinks it happened", selectedInsight.whyNeraiumThinks],
              ["What could happen next", selectedInsight.possibleConsequence],
              ["What the operator should check", selectedInsight.operatorCheck],
              ["Recommended action", selectedInsight.recommendedAction],
              ["Telemetry integrity", selectedInsight.telemetryNote],
              ["Detected", selectedInsight.detectedAt],
            ]} />
             {selectedInsight.contributingFactors?.length ? (
              <section className="operational-block">
                <h3>Contributing factors</h3>
                <ul className="compact-list">
                  {selectedInsight.contributingFactors.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </section>
            ) : null}
            {selectedInsight.contributingMetrics?.length ? (
              <section className="operational-block">
                <h3>Contributing metrics</h3>
                <ul className="compact-list">
                  {selectedInsight.contributingMetrics.map((item, index) => <li key={`${item.name ?? item.source_column ?? "metric"}-${index}`}>{firstText(item.name, item.source_column)}</li>)}
                </ul>
              </section>
            ) : null}
            {selectedInsight.contributingRelationships?.length ? (
              <section className="operational-block">
                <h3>Contributing relationships</h3>
                <ul className="compact-list">
                  {selectedInsight.contributingRelationships.map((item, index) => <li key={`${item.id ?? "relationship"}-${index}`}>{toList(item.columns).join(" / ") || firstText(item.change_type, item.relationship_type)}</li>)}
                </ul>
              </section>
            ) : null}
            {selectedInsight.evidence?.length ? (
              <section className="operational-block">
                <h3>Evidence</h3>
                {selectedInsight.evidence.map((item, index) => <EvidencePanel key={index} evidence={item} />)}
              </section>
            ) : null}
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
                  <DetailGrid rows={[
                    ["Confidence", system.confidence],
                    ["What changed", system.whatChanged?.join("; ")],
                    ["Relationships", system.relationships?.join("; ")],
                  ]} />
                  {system.keyBehaviors?.length ? (
                    <ul className="compact-list">
                      {system.keyBehaviors.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  ) : null}
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

      <section className="operational-panel" aria-label="Signal relationship summary">
        <PanelHeader eyebrow="Relationships" title="Signal Relationship Summary" subtitle="Relationships with the largest behavior shift." />
        <RelationshipList rows={model.relationshipRows} />
      </section>
    </div>
  );
}

function FingerprintSection({ model }) {
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label="Fingerprint interpretation">
        <PanelHeader eyebrow="Fingerprint" title="Operating Fingerprint" subtitle="Plain-language meaning of the baseline comparison." />
        <FingerprintStatus drift={model.fingerprintDrift} />
        <DetailGrid rows={model.fingerprintRows} />
      </section>
    </div>
  );
}

function MoreSection({ model, onAnalyzeSystem, onResumePreviousSession }) {
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label="Advanced status">
        <PanelHeader eyebrow="Status" title="Advanced Status" subtitle="Detailed source, analysis, systems, and fingerprint state." />
        <div className="status-rack">
          {model.statusTiles.map((tile) => <CompactStatusTile key={tile.label} tile={tile} />)}
        </div>
      </section>
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
      <section className="operational-panel" aria-label="Fingerprint panel">
        <PanelHeader eyebrow="Fingerprint" title="Fingerprint Status" subtitle="Baseline comparison and operating fingerprint detail." />
        <FingerprintStatus drift={model.fingerprintDrift} />
      </section>

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
  const analysisExplanation = extractAnalysisExplanation(result, snapshot);
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
  const fingerprintDrift = deriveFingerprintDrift({ relationshipRows, result, hasFinding, analysisComplete, baselineAvailable, analysisExplanation });
  const insights = analysisComplete ? buildInsights({ finding, liveOps, result, primarySystem, telemetryStatus, lastAnalysis, analysisExplanation }) : [];
  const identifiedSystems = analysisComplete ? collectIdentifiedSystems({ liveOps, result, primarySystem, analysisExplanation }) : [];
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
  const sourceRowCount = deriveSourceRowCount({ result, snapshot });
  const overviewState = deriveOverviewState(uiState.key);
  const executiveSummaryRows = buildExecutiveSummaryRows({
    analysisComplete,
    identifiedSystemCount,
    insights,
    fingerprintDrift,
    result,
    liveOps,
    finding,
    analysisExplanation,
  });

  return {
    siteLabel,
    domainLabel,
    sourceLabel,
    contextLabel,
    headerEyebrow: isEmptyTelemetryState ? "NERAIUM SII" : "Neraium Systemic Infrastructure Intelligence",
    headerSubtitle: isEmptyTelemetryState ? siteLabel : contextLabel,
    overviewState,
    overviewTabMetric: isEmptyTelemetryState ? "Start" : heroStatus.label,
    moreTabMetric: "Details",
    fingerprintTabMetric: fingerprintDrift.label,
    showHeroStatusBadge: !isEmptyTelemetryState,
    showSidebarStatus: !isEmptyTelemetryState,
    sourceStatusLabel: uiState.sourceStatusLabel,
    sourceRowCount,
    storyProgressLabel: uiState.storyProgressLabel,
    primaryCtaLabel: uiState.primaryCtaLabel,
    analyzeDisabled: uiState.key === "analyzing",
    showBaselineClaim: baselineAvailable,
    executiveSummaryRows,
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
    fingerprintRows: buildFingerprintRows(analysisExplanation),
    systemCards,
    systemsTabMetric: systemSummary.tabMetric,
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


function deriveOverviewState(uiStateKey) {
  if (uiStateKey === "noTelemetry") return "noCsvUploaded";
  if (uiStateKey === "readyToAnalyze") return "csvUploadedReady";
  if (uiStateKey === "analyzing") return "analyzing";
  return "analysisComplete";
}

function deriveSourceRowCount({ result, snapshot }) {
  const currentUpload = snapshot?.current_upload ?? result?.current_upload ?? null;
  return firstText(
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
    currentUpload?.records
  );
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
      primaryCtaLabel: "Analyze CSV",
    };
  }
  if (analysisComplete) {
    return {
      key: "analysisComplete",
      status: ANALYSIS_COMPLETE_STATUS,
      sourceStatusLabel: "Historical telemetry analyzed",
      storyProgressLabel: "Analysis based on uploaded telemetry",
      primaryCtaLabel: "Analyze CSV",
    };
  }
  return {
    key: "readyToAnalyze",
    status: READY_TO_ANALYZE_STATUS,
    sourceStatusLabel: telemetryConnected ? "Live telemetry connected" : "Telemetry loaded",
    storyProgressLabel: "Telemetry loaded; analysis not run",
    primaryCtaLabel: "Analyze CSV",
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

function extractAnalysisExplanation(result, snapshot) {
  const interpretation = result?.system_interpretation ?? snapshot?.system_interpretation ?? {};
  const explanation = result?.analysis_explanation ?? interpretation?.analysis_explanation ?? snapshot?.analysis_explanation;
  return explanation && typeof explanation === "object" ? explanation : {};
}

function buildFingerprintRows(analysisExplanation) {
  const fingerprint = analysisExplanation?.fingerprint ?? {};
  return [
    ["Meaning", fingerprint.meaning],
    ["Largest deviation", fingerprint.largest_deviation],
    ["Confidence", fingerprint.confidence],
    ["Baseline rows", fingerprint.baseline_window_rows],
    ["Recent rows", fingerprint.recent_window_rows],
    ["Columns analyzed", fingerprint.columns_analyzed],
    ["Primary driver", fingerprint.primary_driver],
  ];
}

function buildExecutiveSummaryRows({ analysisComplete, insights, fingerprintDrift, result, liveOps, finding, analysisExplanation }) {
  if (!analysisComplete) return [];
  const summary = analysisExplanation?.executive_summary ?? {};
  const topInsight = insights[0] ?? {};
  const topRecommendation = firstText(
    summary.recommended_action,
    topInsight.recommendedAction,
    result?.recommended_action,
    result?.recommendation,
    result?.operator_report?.recommended_action,
    result?.operator_report?.review_next,
    finding?.recommendation,
    finding?.reviewNext,
    liveOps?.recommendedAction
  );
  return [
    ["Overall operational status", firstText(summary.overall_operational_status, result?.operating_state, result?.sii_intelligence?.facility_state)],
    ["Highest-priority finding", firstText(summary.highest_priority_finding, topInsight.summary)],
    ["Biggest emerging risk", firstText(summary.biggest_emerging_risk, topInsight.possibleConsequence, fingerprintDrift.detail)],
    ["Recommended action", topRecommendation],
  ];
}

function collectIdentifiedSystems({ liveOps, result, primarySystem, analysisExplanation }) {
  const explanatorySystems = Array.isArray(analysisExplanation?.systems) ? analysisExplanation.systems : [];
  if (explanatorySystems.length > 0) {
    return explanatorySystems.map((system, index) => ({
      ...system,
      id: system.id ?? system.name ?? "system-" + index,
      name: firstText(system.name, system.label, "System " + (index + 1)),
    }));
  }
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

function buildInsights({ finding, liveOps, result, primarySystem, telemetryStatus, lastAnalysis, analysisExplanation }) {
  const explanatoryInsights = Array.isArray(analysisExplanation?.insights) ? analysisExplanation.insights : [];
  if (explanatoryInsights.length > 0) {
    return explanatoryInsights.map((item, index) => ({
      id: item.id ?? "insight-" + index,
      system: firstText(item.system, primarySystem),
      status: normalizeInsightStatus(item.status ?? item.severity),
      severity: normalizeSeverity(item.severity),
      summary: firstText(item.title, item.explanation),
      whatHappened: firstText(item.what_changed, item.whatChanged, item.explanation),
      whyNeraiumThinks: firstText(item.why_neraium_thinks_it_happened, item.why_neraium_thinks, item.likely_cause, item.likelyCause),
      possibleConsequence: firstText(item.possible_operational_consequence, item.possible_consequence, item.possibleConsequence),
      recommendedAction: firstText(item.recommended_action, item.recommendedAction),
      operatorCheck: firstText(item.recommended_operator_check, item.operator_check, item.operatorCheck),
      contributingFactors: toList(item.contributing_factors, item.contributingFactors).flatMap(splitPriorityText),
      contributingRelationships: Array.isArray(item.contributing_relationships) ? item.contributing_relationships : [],
      contributingMetrics: Array.isArray(item.contributing_metrics) ? item.contributing_metrics : [],
      evidence: Array.isArray(item.evidence_items) ? item.evidence_items : (Array.isArray(item.evidence) ? item.evidence : []),
      evidenceSummary: item.evidence_summary,
      sourceTimeRanges: Array.isArray(item.source_time_ranges) ? item.source_time_ranges : [],
      confidence: item.confidence,
      confidenceScore: item.confidence_score,
      confidenceRationale: item.confidence_rationale,
      telemetryNote: telemetryStatus.detail,
      detectedAt: lastAnalysis,
    })).filter((item) => item.summary);
  }

  const rawFindings = [];
  if (finding?.exists || finding?.summary || finding?.title) rawFindings.push(finding);
  if (Array.isArray(liveOps?.findings)) rawFindings.push(...liveOps.findings);

  const insights = rawFindings
    .filter(Boolean)
    .map((item, index) => {
      const summary = firstText(item.summary, item.detail, item.title, result?.operator_report?.summary);
      const supporting = toList(item.supportingEvidence, item.relationshipEvidence, result?.operator_report?.evidence_summary, result?.finding_evidence_chains)
        .flatMap(splitPriorityText);
      return {
        id: "insight-" + index,
        system: firstText(item.label, item.affectedSubsystem, item.affected_system, primarySystem),
        status: normalizeInsightStatus(item.status ?? result?.operating_state),
        severity: normalizeSeverity(item.confidence ?? result?.drift_status),
        summary,
        whatHappened: summary,
        whyNeraiumThinks: item.whyItMatters,
        possibleConsequence: item.possibleConsequence,
        recommendedAction: firstText(item.recommendation, item.reviewNext),
        operatorCheck: item.operator_focus,
        evidence: supporting.length ? [{ supporting_signals: supporting }] : [],
        telemetryNote: telemetryStatus.detail,
        detectedAt: lastAnalysis,
      };
    })
    .filter((item) => item.summary);

  if (insights.length > 0) return dedupeInsights(insights).slice(0, 8);
  return [];
}

function buildSystemCards({ systems, primarySystem, heroStatus, lastAnalysis, insights, fingerprintDrift }) {
  const safeSystems = Array.isArray(systems) && systems.length > 0
    ? systems.slice(0, 6).map((system, index) => ({ ...system, id: system.id ?? system.name ?? "system-" + index, name: system.name ?? system.label ?? "System " + (index + 1) }))
    : [{ id: "primary", name: primarySystem }];

  return safeSystems.map((system) => {
    const relatedInsights = insights.filter((item) => item.system === system.name || safeSystems.length === 1);
    return {
      id: system.id,
      name: system.name,
      status: firstText(system.health_status, system.status, heroStatus.label),
      tone: heroStatus.tone,
      summary: firstText(system.summary, fingerprintDrift.detail),
      confidence: system.confidence,
      keyBehaviors: toList(system.key_behaviors, system.keyBehaviors).flatMap(splitPriorityText),
      whatChanged: toList(system.what_changed, system.whatChanged).flatMap(splitPriorityText),
      relationships: toList(system.relationships, system.relationship_summary).flatMap(splitPriorityText),
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
      { label: "Status", value: uiState.status.label, detail: analysisComplete ? "Result saved and ready for review." : uiState.status.detail, tone: uiState.status.tone },
      { label: "Systems", value: SYSTEMS_PENDING.title, detail: SYSTEMS_PENDING.summary, tone: "unknown" },
      { label: "Fingerprint", value: NO_BASELINE_AVAILABLE.label, detail: NO_BASELINE_AVAILABLE.detail, tone: "unknown" },
    ];
  }

  return [
    { label: "Telemetry", value: telemetryStatus.label, detail: telemetryStatus.detail, tone: telemetryStatus.tone },
    { label: "Status", value: uiState.status.label, detail: analysisComplete ? "Result saved and ready for review." : uiState.status.detail, tone: uiState.status.tone },
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

function deriveFingerprintDrift({ relationshipRows, result, hasFinding, analysisComplete, baselineAvailable, analysisExplanation }) {
  const fingerprint = analysisExplanation?.fingerprint ?? {};
  if (analysisComplete && fingerprint.meaning) {
    const changed = fingerprint.status === "changed";
    return {
      label: changed ? "Changed" : "Stable",
      tone: changed ? "changed" : "normal",
      detail: fingerprint.meaning,
    };
  }
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
      detail: insights[0]?.summary ? `Top finding: ${insights[0].summary}` : "Current telemetry was analyzed for system behavior changes.",
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
            <p>{firstText(insight.whatHappened, insight.possibleConsequence)}</p>
            <small>{insight.detectedAt}</small>
          </Tag>
        );
      })}
    </div>
  );
}

function EvidencePanel({ evidence }) {
  const supportingSignals = toList(evidence.supporting_signals, evidence.supportingSignals).flatMap(splitPriorityText);
  const metricChanges = toList(evidence.relevant_metric_changes, evidence.relevantMetricChanges).flatMap(splitPriorityText);
  const sourceColumns = toList(evidence.source_columns, evidence.sourceColumns, evidence.source_metrics, evidence.sourceMetrics, evidence.source_tags, evidence.sourceTags).flatMap(splitPriorityText);
  const sourceRanges = Array.isArray(evidence.source_time_ranges) ? evidence.source_time_ranges.map(formatEvidenceRange).filter(Boolean) : [];
  return (
    <details className="evidence-panel">
      <summary>Evidence{evidence.confidence ? " (" + evidence.confidence + ")" : ""}</summary>
      <DetailGrid rows={[
        ["Summary", evidence.summary],
        ["Type", evidence.type],
        ["Confidence", evidence.confidence_score ? `${evidence.confidence} (${evidence.confidence_score})` : evidence.confidence],
        ["Time window", evidence.time_window ?? evidence.timeWindow],
        ["Persistence / duration", evidence.persistence_duration ?? evidence.persistenceDuration],
        ["Calculated delta", evidence.calculated_delta ?? evidence.calculatedDelta],
        ["Calculated percent delta", evidence.calculated_percent_delta ?? evidence.calculatedPercentDelta],
        ["Upload", evidence.source_upload_id ?? evidence.upload_id],
        ["Analysis", evidence.analysis_id],
      ]} />
      {sourceColumns.length ? <QualityList title="Source columns" items={sourceColumns} empty="" /> : null}
      {sourceRanges.length ? <QualityList title="Source time ranges" items={sourceRanges} empty="" /> : null}
      {supportingSignals.length ? <QualityList title="Supporting signals" items={supportingSignals} empty="" /> : null}
      {metricChanges.length ? <QualityList title="Relevant metric changes" items={metricChanges} empty="" /> : null}
    </details>
  );
}

function formatEvidenceRange(range) {
  if (!range || typeof range !== "object") return "";
  const label = firstText(range.label, range.window);
  const direct = [range.start, range.end].filter(Boolean).join(" to ");
  const comparison = [
    range.baseline_start && range.baseline_end ? `baseline ${range.baseline_start} to ${range.baseline_end}` : "",
    range.current_start && range.current_end ? `current ${range.current_start} to ${range.current_end}` : "",
  ].filter(Boolean).join("; ");
  return [label, firstText(direct, comparison)].filter(Boolean).join(": ");
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
  if (section === "fingerprint") return "Fingerprint";
  if (section === "more") return "More";
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
