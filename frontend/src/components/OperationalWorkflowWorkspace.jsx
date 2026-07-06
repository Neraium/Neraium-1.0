import { useDeferredValue, useMemo, useRef, useState } from "react";

import PageContainer from "./layout/PageContainer";
import { sanitizeOperatorList, sanitizeOperatorText } from "../viewModels/operatorFinding";
import "../styles/operational-workflow.css";

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "insights", label: "Insights" },
  { id: "systems", label: "Systems" },
  { id: "fingerprint", label: "Fingerprint" },
  { id: "evidence", label: "Evidence" },
  { id: "more", label: "More" },
];

const MOBILE_PRIMARY_NAV = [
  { id: "overview", label: "Overview" },
  { id: "insights", label: "Insights" },
  { id: "systems", label: "Systems" },
  { id: "fingerprint", label: "Fingerprint" },
  { id: "evidence", label: "Evidence" },
  { id: "more", label: "More" },
];

const RESULT_TAB_IDS = new Set(["insights", "systems", "fingerprint", "evidence"]);
const EMPTY_TAB_METRIC = "—";

const hiddenFileInputStyle = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

const EMPTY_TELEMETRY_COPY = {
  label: "Analyze infrastructure behavior",
  detail: "Upload historical telemetry to identify relationship changes across operational systems.",
  fileStatus: "No file selected",
  cta: "Select CSV",
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
  detail: "Analyzing telemetry, identifying system behavior, and mapping relationships.",
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
  onWorkspaceNavigate,
  onCsvSelected,
  onUploadComplete,
  onResumePreviousSession,
  onSignOut,
}) {
  const [activeSection, setActiveSection] = useState("overview");
  const [selectedInsightId, setSelectedInsightId] = useState(null);
  const overviewUploadInputRef = useRef(null);

  const deferredLiveOps = useDeferredValue(liveOps);
  const deferredCanonicalFinding = useDeferredValue(canonicalFinding);
  const deferredCurrentSession = useDeferredValue(currentSession);
  const deferredLatestUploadResult = useDeferredValue(effectiveLatestUploadResult);
  const deferredLatestUploadSnapshot = useDeferredValue(effectiveLatestUploadSnapshot);
  const deferredRoomContext = useDeferredValue(roomContext);
  const deferredDomainDetection = useDeferredValue(domainDetection);
  const deferredGateProcessing = useDeferredValue(gateProcessing);

  const model = useMemo(() => buildOperationalModel({
    liveOps: deferredLiveOps,
    canonicalFinding: deferredCanonicalFinding,
    currentSession: deferredCurrentSession,
    effectiveLatestUploadResult: deferredLatestUploadResult,
    effectiveLatestUploadSnapshot: deferredLatestUploadSnapshot,
    roomContext: deferredRoomContext,
    domainDetection: deferredDomainDetection,
    gateProcessing: deferredGateProcessing,
  }), [
    deferredLiveOps,
    deferredCanonicalFinding,
    deferredCurrentSession,
    deferredLatestUploadResult,
    deferredLatestUploadSnapshot,
    deferredRoomContext,
    deferredDomainDetection,
    deferredGateProcessing,
  ]);

  const selectedInsight = model.insights.find((item) => item.id === selectedInsightId) ?? model.insights[0] ?? null;
  const navMetrics = {
    overview: model.overviewTabMetric,
    insights: model.insightsTabMetric,
    systems: model.systemsTabMetric,
    fingerprint: model.fingerprintTabMetric,
    evidence: model.evidenceTabMetric,
    more: model.moreTabMetric,
  };
  const visibleSection = !model.resultTabsReady || (model.disableResultTabs && RESULT_TAB_IDS.has(activeSection)) ? "overview" : activeSection;
  const shellClassName = model.resultTabsReady ? "operational-workflow" : "operational-workflow operational-workflow--intake";

  function navigate(sectionId) {
    setActiveSection(sectionId);
  }

  function openInsight(insightId) {
    setSelectedInsightId(insightId);
    navigate("insights");
  }

  function openEvidence(insightId) {
    setSelectedInsightId(insightId);
    navigate("evidence");
  }

  function openOverviewFilePicker() {
    overviewUploadInputRef.current?.click();
  }

  function handleOverviewFileSelection(event) {
    const files = Array.from(event?.target?.files ?? []);
    if (!files.length) return;
    if (typeof onCsvSelected === "function") {
      onCsvSelected(files);
    }
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
    <PageContainer className={shellClassName}>
      {model.resultTabsReady ? (
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
                className={visibleSection === item.id ? "is-active" : ""}
                aria-label={[item.label, navMetrics[item.id]].filter(Boolean).join(" ")}
                aria-current={visibleSection === item.id ? "page" : undefined}
                onClick={() => navigate(item.id)}
              >
                <span>{item.label}</span>
                <small>{navMetrics[item.id]}</small>
              </button>
            ))}
          </nav>
          <div className="operational-sidebar__footer">
            {model.showSidebarStatus ? (
              <>
                <StatusBadge label={model.telemetryStatus.label} tone={model.telemetryStatus.tone} />
                <small>Last analysis: {model.lastAnalysis}</small>
              </>
            ) : null}
            {typeof onSignOut === "function" ? (
              <button type="button" className="operational-link-button" onClick={onSignOut}>Sign out</button>
            ) : null}
          </div>
        </aside>
      ) : null}

      <main className="operational-main" aria-label="Neraium operational workspace">
        <header className="operational-topbar">
          <div>
            <p className="section-token">{model.headerEyebrow}</p>
            <h1>{model.resultTabsReady ? sectionTitle(visibleSection) : "Operational Intelligence"}</h1>
            <p className="operational-topbar__context">{model.headerSubtitle}</p>
          </div>
          {model.showTopbarStatus ? (
            <div className="operational-topbar__status">
              <StatusBadge label={model.telemetryStatus.label} tone={model.telemetryStatus.tone} />
            </div>
          ) : null}
        </header>

        {model.resultTabsReady ? (
          <div className="operational-mobile-nav" aria-label="Mobile workflow navigation">
            {MOBILE_PRIMARY_NAV.map((item) => (
              <button
                key={item.id}
                type="button"
                className={visibleSection === item.id ? "is-active" : ""}
                aria-label={[item.label, navMetrics[item.id]].filter(Boolean).join(" ")}
                aria-current={visibleSection === item.id ? "page" : undefined}
                onClick={() => navigate(item.id)}
              >
                <span>{item.label}</span>
                <small>{navMetrics[item.id]}</small>
              </button>
            ))}
          </div>
        ) : null}

        {visibleSection === "overview" ? (
          <OverviewSection
            model={model}
            onOpenInsight={openInsight}
            onOpenEvidence={openEvidence}
            onAnalyzeSystem={analyzeSystem}
            uploadInputRef={overviewUploadInputRef}
            onSelectCsv={openOverviewFilePicker}
            onFileSelection={handleOverviewFileSelection}
            onResumePreviousSession={onResumePreviousSession}
            onViewSystems={viewSystems}
          />
        ) : null}

        {visibleSection === "insights" ? (
          <InsightsSection
            model={model}
            selectedInsight={selectedInsight}
            onSelectInsight={setSelectedInsightId}
          />
        ) : null}

        {visibleSection === "systems" ? (
          <SystemsSection model={model} onOpenInsight={openInsight} />
        ) : null}

        {visibleSection === "fingerprint" ? (
          <FingerprintSection model={model} />
        ) : null}

        {visibleSection === "evidence" ? (
          <EvidenceSection model={model} selectedInsightId={selectedInsightId} />
        ) : null}

        {visibleSection === "more" ? (
          <MoreSection model={model} onAnalyzeSystem={analyzeSystem} onResumePreviousSession={onResumePreviousSession} />
        ) : null}

        {typeof onUploadComplete === "function" ? null : null}
      </main>
    </PageContainer>
  );
}

function OverviewSection({ model, onOpenInsight, onOpenEvidence, onAnalyzeSystem, uploadInputRef, onSelectCsv, onFileSelection, onResumePreviousSession, onViewSystems }) {
  if (model.overviewState === "noCsvUploaded") {
    return (
      <div className="operational-grid operational-grid--empty">
        <section className="operational-panel operational-panel--start" aria-label="Start analysis">
          <div className="operational-start-card">
            <div className="operational-panel__header operational-panel__header--tight">
              <h2>{EMPTY_TELEMETRY_COPY.label}</h2>
              <p>{EMPTY_TELEMETRY_COPY.detail}</p>
            </div>
            <input data-testid="overview-csv-upload-input" ref={uploadInputRef} accept=".csv,text/csv" type="file" className="intake-flow__input" style={hiddenFileInputStyle} onChange={onFileSelection} />
            <small>{EMPTY_TELEMETRY_COPY.fileStatus}</small>
            <div className="operational-actions operational-actions--hero">
              <button type="button" className="command-button" onClick={onSelectCsv}>
                {EMPTY_TELEMETRY_COPY.cta}
              </button>
            </div>
          </div>
        </section>
      </div>
    );
  }

  const primaryInsight = model.insights[0] ?? null;
  const showSystemsAction = model.analysisComplete && model.identifiedSystemCount > 0;

  function renderPrimaryAction() {
    if (model.analysisComplete && primaryInsight) {
      return <button type="button" className="command-button" onClick={() => onOpenInsight(primaryInsight.id)}>Open insight</button>;
    }
    return (
      <button type="button" className="command-button" onClick={onAnalyzeSystem} disabled={model.analyzeDisabled}>
        {model.primaryCtaLabel}
      </button>
    );
  }

  function renderSecondaryAction() {
    if (showSystemsAction) {
      return <button type="button" className="secondary-command-button" onClick={onViewSystems}>View systems</button>;
    }
    if (model.canResumePrevious && typeof onResumePreviousSession === "function") {
      return <button type="button" className="operational-link-button" onClick={onResumePreviousSession}>Resume Previous Analysis</button>;
    }
    return null;
  }

  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--hero operational-panel--wide" aria-label="Executive summary">
        <div className="operator-summary-card">
          <div className="operational-panel__header operational-panel__header--tight">
            <span className="section-token">Overview</span>
            <h2>{model.heroStatus.label}</h2>
            <p>{model.heroStatus.detail}</p>
          </div>
          {model.analysisComplete ? (
            <ExecutiveSummary
              checklist={model.completionChecklist}
              notice={model.dataQualityNotice}
              report={model.operatorReport}
              rows={model.executiveSummaryRows}
            />
          ) : (
            <div className="operator-summary-card__rows" aria-label="Source summary">
              <SummaryRows rows={[
                ["Source", model.sourceLabel],
                ["Status", model.sourceStatusLabel],
                ["Rows", model.sourceRowCount],
                ["Telemetry", model.telemetryStatus.label],
                model.overviewState === "analyzing" ? ["Progress", model.storyProgressLabel] : null,
              ]} />
            </div>
          )}
          <div className="operational-actions operational-actions--hero">
            {renderPrimaryAction()}
            {model.analysisComplete && primaryInsight?.hasEvidence ? (
              <button type="button" className="secondary-command-button" onClick={() => onOpenEvidence(primaryInsight.id)}>Review evidence</button>
            ) : null}
            {renderSecondaryAction()}
          </div>
        </div>
      </section>
    </div>
  );
}

function InsightsSection({
  model,
  selectedInsight,
  onSelectInsight,
}) {
  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label="Insights">
        <PanelHeader eyebrow="Insights" title="Insights" subtitle="Priority findings from the completed analysis." />
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No insights yet." : model.uiState.status.detail}
          emptyTitle={model.analysisComplete ? "No insights yet" : model.uiState.status.label}
          onOpenInsight={onSelectInsight}
          selectedId={selectedInsight?.id}
        />
        {selectedInsight ? <InsightDetail insight={selectedInsight} /> : null}
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

function EvidenceSection({ model, selectedInsightId }) {
  const groups = prioritizeEvidenceGroups(model.evidenceGroups, selectedInsightId);
  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label="Evidence">
        <PanelHeader eyebrow="Evidence" title="Supporting Telemetry" subtitle="Details are collapsed until an operator opens them." />
        {groups.length ? (
          <div className="evidence-group-list">
            {groups.map((group) => (
              <article className={group.id === selectedInsightId ? "evidence-group is-selected" : "evidence-group"} key={group.id}>
                <div className="evidence-group__header">
                  <div>
                    <span className="section-token">{group.system}</span>
                    <h3>{group.title}</h3>
                  </div>
                  <div className="evidence-group__badges">
                    {group.severity ? <StatusBadge label={group.severity} tone={severityToTone(group.severity)} /> : null}
                    {group.confidence ? <StatusBadge label={formatConfidenceDisplay(group.confidence, group.confidenceScore)} tone="unknown" /> : null}
                  </div>
                </div>
                <div className="evidence-group__items">
                  {group.evidence.map((item, index) => <EvidencePanel key={item.evidence_id ?? index} evidence={item} />)}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyOperationalState title="No supporting telemetry yet" body={model.analysisComplete ? "No detailed evidence was reported for this result." : model.uiState.status.detail} />
        )}
      </section>
    </div>
  );
}

function MoreSection({ model, onAnalyzeSystem, onResumePreviousSession }) {
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel" aria-label="Upload details">
        <PanelHeader eyebrow="Upload" title="Upload Details" subtitle="Source file and last completed review." />
        <StatusBadge label={model.telemetryStatus.label} tone={model.telemetryStatus.tone} />
        <DetailGrid rows={[
          ["Source", model.sourceLabel],
          ["Last analysis", model.lastAnalysis],
          ["Detected data type", model.domainLabel],
        ]} />
      </section>
      <section className="operational-panel" aria-label="Analysis metadata">
        <PanelHeader eyebrow="Analysis" title="Analysis Metadata" subtitle="Source file, references, and generation time." />
        <DetailGrid rows={model.analysisMetadataRows} />
      </section>
      <section className="operational-panel" aria-label="Detected signals">
        <PanelHeader eyebrow="Signals" title="Detected Signals" subtitle="Telemetry headers found in the uploaded file." />
        <SignalList signals={model.signals} integrity={model.telemetryStatus} />
      </section>
      <section className="operational-panel" aria-label="Data quality">
        <PanelHeader eyebrow="Integrity" title="Data Quality" subtitle="Warnings, missing values, and timestamp conditions." />
        <QualityList title="Warnings" items={model.qualityWarnings} empty={model.analysisComplete ? "No data quality warnings reported." : model.uiState.status.detail} />
        <QualityList title="Missing values" items={model.missingValues} empty={model.analysisComplete ? "No missing value summary reported." : model.uiState.status.detail} />
        <QualityList title="Timestamp quality" items={model.timestampNotes} empty={model.analysisComplete ? "Timestamp quality is acceptable or not yet reported." : model.uiState.status.detail} />
        <div className="operational-actions">
          <button type="button" className="command-button" onClick={onAnalyzeSystem} disabled={model.analyzeDisabled}>{model.primaryCtaLabel}</button>
        </div>
      </section>
      <section className="operational-panel operational-panel--wide" aria-label="Analysis history">
        <PanelHeader eyebrow="History" title="Analysis History" subtitle="Saved operational reviews." />
        <Timeline items={model.historyItems} />
      </section>
      {model.canResumePrevious && typeof onResumePreviousSession === "function" ? (
        <section className="operational-panel" aria-label="Previous analysis">
          <PanelHeader eyebrow="Previous" title="Previous Analysis" subtitle="Continue a saved review." />
          <button type="button" className="secondary-command-button" onClick={onResumePreviousSession}>Resume Previous Analysis</button>
        </section>
      ) : null}
    </div>
  );
}

function buildOperationalModel({ liveOps, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, roomContext, domainDetection, gateProcessing }) {
  const result = effectiveLatestUploadResult ?? liveOps?.latestUploadResult ?? {};
  const snapshot = effectiveLatestUploadSnapshot ?? liveOps?.latestUploadSnapshot ?? {};
  const analysisExplanation = extractAnalysisExplanation(result, snapshot);
  const canonicalRelationships = Array.isArray(analysisExplanation?.relationships) ? analysisExplanation.relationships : [];
  const relationshipRows = canonicalRelationships.length ? canonicalRelationships : (Array.isArray(liveOps?.relationshipRows) ? liveOps.relationshipRows : []);
  const quality = collectQuality(result, snapshot);
  const telemetryAvailable = hasTelemetry(result, snapshot, liveOps);
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
  const dataQualityNotice = deriveDataQualityNotice({ quality, liveOps, analysisComplete });
  const heroStatus = uiState.status;
  const lastAnalysis = deriveLastAnalysisLabel({ uiState, liveOps, snapshot, result });
  const fingerprintDrift = deriveFingerprintDrift({ relationshipRows, result, hasFinding, analysisComplete, baselineAvailable, analysisExplanation });
  const fingerprintEvidence = resolveEvidenceRefs(analysisExplanation?.fingerprint, analysisExplanation);
  const insights = analysisComplete ? buildInsights({ finding, liveOps, result, primarySystem, telemetryStatus, lastAnalysis, analysisExplanation }) : [];
  const evidenceGroups = analysisComplete ? buildEvidenceGroups({ insights, fingerprintEvidence, fingerprintDrift }) : [];
  const identifiedSystems = analysisComplete ? collectIdentifiedSystems({ liveOps, result, primarySystem, analysisExplanation }) : [];
  const identifiedSystemCount = identifiedSystems.length;
  const systemCards = analysisComplete ? buildSystemCards({ systems: identifiedSystems, primarySystem, heroStatus, lastAnalysis, insights, fingerprintDrift }) : [];
  const systemSummary = buildSystemSummary({ analysisComplete, identifiedSystemCount, telemetryConnected });
  const signals = buildSignals(result);
  const historyItems = buildHistoryItems({ liveOps, snapshot, result, insights, analysisComplete });
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
  const operatorReport = analysisComplete ? buildOperatorInterpretationReport({
    analysisExplanation,
    insights,
    relationshipRows,
    fingerprintDrift,
    result,
    finding,
    identifiedSystems,
  }) : null;
  const completionChecklist = buildCompletionChecklist({
    identifiedSystemCount,
    insights,
    relationshipRows,
    fingerprintDrift,
    baselineAvailable,
  });

  const resultTabsReady = analysisComplete;

  return {
    siteLabel,
    domainLabel,
    sourceLabel,
    contextLabel,
    headerEyebrow: "Neraium",
    headerSubtitle: isEmptyTelemetryState ? siteLabel : contextLabel,
    overviewState,
    overviewTabMetric: isEmptyTelemetryState ? "Start" : (resultTabsReady ? "Summary" : heroStatus.label),
    moreTabMetric: "Details",
    insightsTabMetric: resultTabsReady ? "Findings" : EMPTY_TAB_METRIC,
    fingerprintTabMetric: resultTabsReady ? "Baseline" : EMPTY_TAB_METRIC,
    evidenceTabMetric: resultTabsReady ? "Support" : EMPTY_TAB_METRIC,
    disableResultTabs: !resultTabsReady,
    resultTabsReady,
    showTopbarStatus: !isEmptyTelemetryState && !analysisComplete,
    showSidebarStatus: !isEmptyTelemetryState && !analysisComplete,
    sourceStatusLabel: uiState.sourceStatusLabel,
    sourceRowCount,
    storyProgressLabel: uiState.storyProgressLabel,
    primaryCtaLabel: uiState.primaryCtaLabel,
    analyzeDisabled: uiState.key === "analyzing",
    showBaselineClaim: baselineAvailable,
    executiveSummaryRows,
    completionChecklist,
    dataQualityNotice,
    uiState,
    heroStatus,
    operatorReport,
    baselineStatus: baselineAvailable ? { label: "Baseline Established", tone: "normal" } : NO_BASELINE_AVAILABLE,
    telemetryStatus,
    lastAnalysis,
    analysisComplete,
    baselineAvailable,
    telemetryConnected,
    identifiedSystemCount,
    fingerprintDrift,
    fingerprintRows: buildFingerprintRows(analysisExplanation),
    analysisMetadataRows: buildAnalysisMetadataRows({ result, snapshot, analysisExplanation }),
    systemCards,
    systemsTabMetric: resultTabsReady ? "Inventory" : EMPTY_TAB_METRIC,
    systemsSectionTitle: systemSummary.sectionTitle,
    systemsSectionSubtitle: systemSummary.sectionSubtitle,
    insights,
    evidenceGroups,
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
    result?.analysis_result?.source_file,
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
    sectionSubtitle: telemetryConnected ? "Live telemetry is connected." : "Systems identified by the completed analysis.",
  };
}

function extractAnalysisExplanation(result, snapshot) {
  const interpretation = result?.system_interpretation ?? snapshot?.system_interpretation ?? {};
  const currentUpload = snapshot?.current_upload ?? {};
  const explanation = result?.analysis_result
    ?? result?.analysis_explanation
    ?? currentUpload?.result?.analysis_result
    ?? snapshot?.analysis_result
    ?? interpretation?.analysis_result
    ?? interpretation?.analysis_explanation
    ?? snapshot?.analysis_explanation;
  return explanation && typeof explanation === "object" ? explanation : {};
}

function buildFingerprintRows(analysisExplanation) {
  const fingerprint = analysisExplanation?.fingerprint ?? {};
  const normalBehavior = fingerprint.normal_operating_behavior ?? fingerprint.baseline_summary;
  const currentBehavior = fingerprint.current_behavior ?? fingerprint.current_behavior_summary;
  return [
    ["Explanation", operatorText(fingerprint.explanation, fingerprint.plain_language_explanation, fingerprint.meaning)],
    ["Drift status", operatorText(fingerprint.drift_status, fingerprint.status)],
    ["Confidence", formatConfidenceDisplay(fingerprint.confidence, fingerprint.confidence_score)],
    ["Normal behavior", typeof normalBehavior === "object" ? compactJson(normalBehavior) : operatorText(normalBehavior)],
    ["Current behavior", typeof currentBehavior === "object" ? compactJson(currentBehavior) : operatorText(currentBehavior)],
    ["Largest deviations", toList(fingerprint.largest_deviations, fingerprint.largest_deviation).flatMap(splitPriorityText).map(operatorText).join("; ")],
    ["Change onset", analysisExplanation?.change_onset],
    ["Stable window", formatBehaviorWindow(analysisExplanation?.stable_window)],
    ["Deviation window", formatBehaviorWindow(analysisExplanation?.deviation_window)],
    ["Current state window", formatBehaviorWindow(analysisExplanation?.current_state_window)],
  ];
}

function buildAnalysisMetadataRows({ result, snapshot, analysisExplanation }) {
  const metadata = analysisExplanation?.analysis_metadata ?? {};
  return [
    ["Analysis reference", firstText(analysisExplanation?.analysis_id, metadata.analysis_id, result?.analysis_id, result?.run_id, result?.job_id)],
    ["Upload reference", firstText(analysisExplanation?.upload_id, metadata.upload_id, result?.upload_id, result?.job_id, snapshot?.upload_id)],
    ["Source file", firstText(analysisExplanation?.source_file, result?.source_file, result?.filename, snapshot?.filename, snapshot?.current_upload?.filename)],
    ["Generated at", firstText(analysisExplanation?.generated_at, result?.completed_at, result?.last_processed_at, snapshot?.last_processed_at)],
    ["Rows", firstText(metadata.row_count, result?.row_count, snapshot?.rows_processed)],
    ["Columns", firstText(metadata.column_count, result?.column_count, snapshot?.columns_detected)],
  ];
}

function buildExecutiveSummaryRows({ analysisComplete, insights, fingerprintDrift, result, liveOps, finding, analysisExplanation }) {
  if (!analysisComplete) return [];
  const summary = analysisExplanation?.executive_summary ?? {};
  const topInsight = insights[0] ?? {};
  const topRecommendation = firstText(
    summary.recommended_action,
    topInsight.operatorCheck,
    topInsight.recommendedAction,
    result?.recommended_action,
    result?.recommendation,
    result?.operator_report?.recommended_action,
    result?.operator_report?.review_next,
    finding?.recommendation,
    finding?.reviewNext,
    liveOps?.recommendedAction
  );
  const meaningfulChange = hasMeaningfulOperationalChange({ insights, fingerprintDrift });
  return [
    ["Overall condition", deriveExecutiveOverallStatus({ summary, insights, fingerprintDrift, result })],
    [
      "Highest Priority Finding",
      conciseOperatorSentence(
        summary.highest_priority_finding,
        topInsight.summary,
        meaningfulChange ? fingerprintDrift.detail : "No material subsystem change detected."
      ),
    ],
    [
      "Biggest Risk",
      conciseOperatorSentence(
        summary.biggest_emerging_risk,
        topInsight.possibleConsequence,
        topInsight.whyItMatters,
        meaningfulChange ? fingerprintDrift.detail : "Current behavior remains close to the baseline."
      ),
    ],
    ["Recommended Next Check", conciseOperatorSentence(topRecommendation, "Continue monitoring.")],
  ];
}


function buildOperatorInterpretationReport({ analysisExplanation, insights, relationshipRows, fingerprintDrift, result, finding, identifiedSystems }) {
  const source = analysisExplanation?.operator_interpretation
    ?? result?.operator_interpretation
    ?? result?.operator_report?.operator_interpretation
    ?? null;
  if (source && typeof source === "object" && (source.overall_status || source.primary_finding)) {
    return normalizeOperatorInterpretationReport(source);
  }
  if (!hasMeaningfulOperationalChange({ insights, fingerprintDrift }) && !finding?.exists) {
    return normalizeOperatorInterpretationReport({
      overall_status: {
        condition: "Plant behavior consistent with historical operation",
        confidence: formatConfidenceLevel(fingerprintDrift?.confidence, null),
        urgency: "Low",
        fingerprint: fingerprintDrift?.label ?? "Stable",
        subsystem: identifiedSystems?.[0]?.name ?? "Uploaded telemetry",
      },
      executive_summary: [
        "During the last analysis period, reviewed telemetry remained close to its historical operating pattern.",
        "No subsystem-level behavior change was flagged by the available baseline comparison.",
      ],
      primary_finding: {
        title: "Operating fingerprint remains stable",
        what_changed: ["No reviewed operating relationship moved beyond the baseline review threshold."],
        why_it_matters: ["Stable relationships reduce the need to investigate this subsystem first."],
      },
      suggested_investigation: ["Continue routine monitoring."],
      supporting_evidence: { relationships: [], fingerprint_confidence: "Low", relationship_persistence: "Low" },
      did_not_observe: ["No subsystem-level relationship change was flagged."],
      trend: { direction: "Stable", subsystem_stability: "Stable", recommended_follow_up: "Continue routine monitoring" },
    });
  }

  const primaryInsight = insights[0] ?? {};
  const relationshipLabels = dedupeText([
    ...insightRelationshipLabels(primaryInsight),
    ...(Array.isArray(relationshipRows) ? relationshipRows.map(relationshipDisplayName) : []),
  ].filter(Boolean)).slice(0, 6);
  const subsystem = formatSubsystemName(firstText(primaryInsight.system, identifiedSystems?.[0]?.name, "Uploaded telemetry"));
  return normalizeOperatorInterpretationReport({
    overall_status: {
      condition: `${subsystem} subsystem deviating from historical operation`,
      confidence: formatConfidenceLevel(primaryInsight.confidence, primaryInsight.confidenceScore),
      urgency: primaryInsight.severity === "High" ? "High" : "Medium",
      fingerprint: fingerprintDrift?.label ?? "Changed",
      subsystem,
    },
    executive_summary: [
      `During the last analysis period, the ${subsystem} subsystem no longer behaved according to its historical operating pattern.`,
      relationshipLabels.length > 1
        ? "Several relationships that normally move together changed simultaneously, suggesting a subsystem-level change rather than a single instrument drifting."
        : "At least one operating relationship changed from its established pattern, suggesting a subsystem behavior shift worth checking.",
      "No immediate failure is indicated, but the behavior differs from the established operating fingerprint.",
    ],
    primary_finding: {
      title: firstText(primaryInsight.summary, `${subsystem} subsystem behavior changed`),
      system: subsystem,
      what_changed: relationshipLabels.length
        ? [`The historical relationships in the ${subsystem} subsystem deviated from their established operating patterns during the analysis window.`, ...relationshipLabels]
        : whatChangedBriefing(primaryInsight, relationshipLabels),
      why_it_matters: whyItMattersBriefing(primaryInsight),
    },
    possible_operational_causes: operationalCauseHypotheses(primaryInsight),
    suggested_investigation: suggestedInvestigationSteps({ subsystem, relationshipLabels, insight: primaryInsight }),
    supporting_evidence: {
      relationships: relationshipLabels,
      fingerprint_confidence: formatConfidenceLevel(primaryInsight.confidence, primaryInsight.confidenceScore),
      relationship_persistence: relationshipLabels.length > 1 ? "High" : "Medium",
    },
    did_not_observe: didNotObserveStatements(subsystem),
    trend: {
      first_observed: firstText(result?.timestamp_profile?.first_timestamp, result?.deformation_started_at, "Current analysis window"),
      direction: "Increasing",
      subsystem_stability: "Declining",
      recommended_follow_up: "Monitor next 24 hours",
    },
  });
}

function normalizeOperatorInterpretationReport(source) {
  const status = source.overall_status ?? {};
  const primary = source.primary_finding ?? {};
  const evidence = source.supporting_evidence ?? {};
  const trend = source.trend ?? {};
  const condition = operatorText(status.condition, status.overall_condition, source.condition);
  const subsystem = formatSubsystemName(operatorText(status.subsystem, primary.system, source.subsystem));
  return {
    condition,
    subsystem,
    confidence: formatConfidenceLevel(status.confidence, status.confidence_score),
    urgency: normalizeUrgencyLabel(status.urgency),
    fingerprint: operatorText(status.fingerprint, status.fingerprint_status),
    executiveSummary: sanitizeOperatorList(toList(source.executive_summary, source.summary).flatMap(splitPriorityText)).slice(0, 4),
    primaryFinding: {
      title: operatorText(primary.title, primary.summary),
      system: subsystem,
      whatChanged: sanitizeOperatorList(toList(primary.what_changed, primary.whatChanged).flatMap(splitPriorityText)).slice(0, 8),
      whyItMatters: sanitizeOperatorList(toList(primary.why_it_matters, primary.whyItMatters).flatMap(splitPriorityText)).slice(0, 4),
    },
    possibleOperationalCauses: sanitizeOperatorList(toList(source.possible_operational_causes, source.possibleOperationalCauses).flatMap(splitPriorityText)).slice(0, 8),
    suggestedInvestigation: sanitizeOperatorList(toList(source.suggested_investigation, source.suggestedInvestigation).flatMap(splitPriorityText)).map(ensureSentence).slice(0, 8),
    supportingEvidence: {
      relationships: sanitizeOperatorList(toList(evidence.relationships).flatMap(splitPriorityText)).map(formatRelationshipObservedLabel).slice(0, 8),
      fingerprintConfidence: formatConfidenceLevel(evidence.fingerprint_confidence, evidence.fingerprint_confidence_score),
      relationshipPersistence: normalizePersistenceLabel(evidence.relationship_persistence),
    },
    didNotObserve: sanitizeOperatorList(toList(source.did_not_observe, source.things_not_observed).flatMap(splitPriorityText)).map(ensureSentence).slice(0, 5),
    trend: {
      firstObserved: operatorText(trend.first_observed, trend.firstObserved),
      direction: operatorText(trend.direction, trend.progression),
      subsystemStability: operatorText(trend.subsystem_stability, trend.subsystemStability),
      recommendedFollowUp: operatorText(trend.recommended_follow_up, trend.recommendedFollowUp),
    },
  };
}

function relationshipDisplayName(row) {
  if (!row || typeof row !== "object") return "";
  const sourceTarget = row.source && row.target ? [row.source, row.target].map((item) => String(item).replace(/^tag:/, "").replace(/^metric:/, "")) : [];
  return cleanRelationshipLabel(Array.isArray(row.display_columns) ? row.display_columns.join(" / ") : (Array.isArray(row.columns) ? row.columns.join(" / ") : firstText(row.name, row.label, row.pair, sourceTarget.join(" / "))));
}

function suggestedInvestigationSteps({ subsystem, relationshipLabels, insight }) {
  const searchText = [subsystem, relationshipLabels.join(" "), insight?.summary].join(" ").toLowerCase();
  if (/flow|pressure|pump|valve|vfd|filter|hydraulic/.test(searchText)) {
    return [
      "Review filter differential pressure trends.",
      "Verify current pump operating point.",
      "Compare valve positions with historical operation.",
      "Review recent maintenance and operator logs.",
      "Confirm VFD commands match expected operation.",
    ];
  }
  if (/chemical|chlor|dose|feed|quality|ph|orp/.test(searchText)) {
    return [
      "Review chemical feed trends.",
      "Verify current dosing setpoints and feed pump status.",
      "Compare water quality readings with historical operation.",
      "Review recent chemical changes and operator logs.",
      "Confirm control commands match expected operation.",
    ];
  }
  if (/thermal|cooling|heat|chiller|condenser|tower/.test(searchText)) {
    return [
      "Review heat transfer and temperature approach trends.",
      "Verify current equipment staging and operating point.",
      "Compare flow and valve positions with historical operation.",
      "Review recent maintenance and load changes.",
      "Confirm control commands match expected operation.",
    ];
  }
  return [
    firstText(insight?.operatorCheck, insight?.recommendedAction, "Review the contributing signal trends."),
    "Verify current operating mode and setpoints.",
    "Compare equipment states with historical operation.",
    "Review recent maintenance and operator logs.",
    "Monitor the next operating window for persistence.",
  ];
}

function didNotObserveStatements(subsystem) {
  const text = String(subsystem ?? "").toLowerCase();
  return [
    text.includes("thermal") ? "" : "No evidence of abnormal thermal subsystem behavior was flagged.",
    text.includes("chemical") ? "" : "Chemical feed relationships remain consistent with the available baseline.",
    text.includes("electrical") || text.includes("energy") ? "" : "Electrical load relationships remain stable in the reviewed evidence.",
  ].filter(Boolean);
}

function normalizeUrgencyLabel(value) {
  const text = firstText(value).toLowerCase();
  if (text.includes("high") || text.includes("critical")) return "High";
  if (text.includes("medium") || text.includes("moderate") || text.includes("elevated")) return "Medium";
  if (text.includes("low")) return "Low";
  return firstText(value, "Low");
}

function normalizePersistenceLabel(value) {
  const text = firstText(value).toLowerCase();
  if (text.includes("high")) return "High";
  if (text.includes("medium") || text.includes("moderate")) return "Medium";
  if (text.includes("low")) return "Low";
  return firstText(value, "Low");
}

function buildCompletionChecklist({ identifiedSystemCount, insights, relationshipRows, fingerprintDrift, baselineAvailable }) {
  const relationshipChangeDetected = relationshipRows.length > 0 || hasMeaningfulOperationalChange({ insights, fingerprintDrift });
  return [
    identifiedSystemCount > 0 ? "Systems identified" : "Systems unavailable",
    relationshipChangeDetected ? "Relationship changes detected" : "No relationship changes detected",
    baselineAvailable ? "Baseline updated" : "Baseline unavailable",
  ];
}

function deriveExecutiveOverallStatus({ summary, insights, fingerprintDrift, result }) {
  const rawStatus = operatorText(summary.overall_operational_status, result?.operating_state, result?.sii_intelligence?.facility_state);
  const statusText = rawStatus.toLowerCase();
  const meaningfulChange = hasMeaningfulOperationalChange({ insights, fingerprintDrift });

  if (!meaningfulChange) return "Normal operation";
  if (statusText.includes("unstable") || statusText.includes("critical") || statusText.includes("instability") || insights.some((insight) => insight.severity === "High")) {
    return "Operational instability observed";
  }
  if (insights.length > 1) return "Multiple subsystem changes detected";
  if (insights.length === 1) return "Localized subsystem change detected";
  return "Subsystem behavior changed";
}

function hasMeaningfulOperationalChange({ insights, fingerprintDrift }) {
  if (insights.length > 0) return true;
  const label = String(fingerprintDrift?.label ?? "").toLowerCase();
  const tone = String(fingerprintDrift?.tone ?? "").toLowerCase();
  return tone === "changed" || tone === "investigate" || label.includes("change") || label.includes("drift");
}

function conciseOperatorSentence(...values) {
  const text = operatorText(...values);
  if (!text) return "";
  const match = text.match(/^(.+?[.!?])(?:\s|$)/);
  return (match ? match[1] : text).trim();
}

function collectIdentifiedSystems({ liveOps, result, primarySystem, analysisExplanation }) {
  const explanatorySystems = Array.isArray(analysisExplanation?.systems) ? analysisExplanation.systems : [];
  if (explanatorySystems.length > 0) {
    return explanatorySystems.map((system, index) => {
      const relationshipChanges = Array.isArray(system.relationship_changes) ? system.relationship_changes : [];
      const relationshipSummaries = relationshipChanges
        .map((item) => firstText(item.explanation, item.what_changed, item.summary, item.change_type))
        .filter(Boolean);
      return {
        ...system,
        id: system.id ?? system.name ?? "system-" + index,
        name: firstText(system.name, system.label, "System " + (index + 1)),
        relationships: toList(system.relationships, relationshipSummaries),
      };
    });
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

function resolveEvidenceRefs(item, analysisExplanation) {
  const index = analysisExplanation?.evidence_index ?? {};
  const refs = Array.isArray(item?.evidence_refs) ? item.evidence_refs : [];
  return refs
    .map((ref) => index?.[ref])
    .filter((entry) => entry && typeof entry === "object");
}

function summarizeEvidence(items) {
  return items
    .map((item) => firstText(item.description, item.summary, item.type))
    .filter(Boolean)
    .slice(0, 4)
    .join("; ");
}

function buildInsights({ finding, liveOps, result, primarySystem, telemetryStatus, lastAnalysis, analysisExplanation }) {
  const explanatoryInsights = Array.isArray(analysisExplanation?.insights) ? analysisExplanation.insights : [];
  if (explanatoryInsights.length > 0) {
    return explanatoryInsights.map((item, index) => {
      const resolvedEvidence = resolveEvidenceRefs(item, analysisExplanation);
      const evidence = resolvedEvidence.length ? resolvedEvidence : (Array.isArray(item.evidence_items) ? item.evidence_items : (Array.isArray(item.evidence) ? item.evidence : []));
      return {
        id: item.id ?? "insight-" + index,
        system: cleanDisplayText(firstText(item.system, toList(item.affected_systems)[0], primarySystem)),
        status: normalizeInsightStatus(item.status ?? item.severity),
        severity: normalizeSeverity(item.severity),
        summary: operatorText(item.title, item.explanation),
        whatHappened: operatorText(item.what_happened, item.what_changed, item.whatChanged, item.explanation),
        whyItMatters: operatorText(item.why_it_matters, item.possible_operational_consequence, item.possible_consequence, item.possibleConsequence, item.likely_cause, item.why_neraium_thinks_it_happened, item.why_neraium_thinks, item.likelyCause),
        whyNeraiumThinks: operatorText(item.why_neraium_thinks_it_happened, item.why_neraium_thinks, item.likely_cause, item.why_it_matters, item.likelyCause),
        possibleConsequence: operatorText(item.possible_operational_consequence, item.possible_consequence, item.possibleConsequence),
        recommendedAction: operatorText(firstDistinctText(firstText(item.operator_check, item.recommended_operator_check, item.recommended_check), item.recommended_action, item.recommendedAction, item.recommendation, item.recommended_check)),
        operatorCheck: operatorText(item.operator_check, item.operatorCheck, item.recommended_operator_check, item.recommended_check),
        possibleOperationalCauses: dedupeText(toList(item.possible_operational_causes, item.possibleOperationalCauses, item.possible_operational_causes_summary).flatMap(splitPriorityText).map(operatorText)),
        contributingFactors: dedupeText(toList(item.likely_contributors, item.contributing_factors, item.contributingFactors, item.source_tags).flatMap(splitPriorityText).map(cleanDisplayText)),
        contributingRelationships: Array.isArray(item.contributing_relationships) ? item.contributing_relationships : [],
        affectedRelationships: relationshipContributionLabels(item.contributing_relationships),
        contributingMetrics: Array.isArray(item.contributing_metrics) ? item.contributing_metrics : [],
        evidence,
        hasEvidence: evidence.length > 0,
        evidenceSummary: operatorEvidenceSummary(item.evidence_summary, summarizeEvidence(resolvedEvidence)),
        sourceTimeRanges: Array.isArray(item.source_time_ranges) ? item.source_time_ranges : [],
        confidence: item.confidence,
        confidenceScore: item.confidence_score,
        confidenceRationale: operatorText(item.confidence_rationale),
        telemetryNote: telemetryStatus.detail,
        detectedAt: lastAnalysis,
      };
    }).filter((item) => item.summary);
  }

  const rawFindings = [];
  if (finding?.exists || finding?.summary || finding?.title) rawFindings.push(finding);
  if (Array.isArray(liveOps?.findings)) rawFindings.push(...liveOps.findings);

  const insights = rawFindings
    .filter(Boolean)
    .map((item, index) => {
      const summary = firstText(item.summary, item.detail, item.title, result?.operator_report?.summary);
      const supporting = toList(item.supportingEvidence, item.relationshipEvidence, result?.operator_report?.evidence_summary, result?.finding_evidence_chains)
        .flatMap(splitPriorityText)
        .map(operatorText);
      const evidence = supporting.length ? [{ supporting_signals: supporting }] : [];
      return {
        id: "insight-" + index,
        system: cleanDisplayText(firstText(item.label, item.affectedSubsystem, item.affected_system, primarySystem)),
        status: normalizeInsightStatus(item.status ?? result?.operating_state),
        severity: normalizeSeverity(item.confidence ?? result?.drift_status),
        summary: operatorText(summary),
        whatHappened: operatorText(summary),
        whyItMatters: operatorText(item.whyItMatters, item.possibleConsequence),
        whyNeraiumThinks: operatorText(item.whyItMatters),
        possibleConsequence: operatorText(item.possibleConsequence),
        recommendedAction: operatorText(item.recommendation, item.reviewNext),
        operatorCheck: operatorText(item.operator_focus),
        possibleOperationalCauses: dedupeText(toList(item.possibleOperationalCauses, item.possible_operational_causes).flatMap(splitPriorityText).map(operatorText)),
        evidence,
        hasEvidence: evidence.length > 0,
        telemetryNote: telemetryStatus.detail,
        detectedAt: lastAnalysis,
      };
    })
    .filter((item) => item.summary);

  if (insights.length > 0) return dedupeInsights(insights).slice(0, 8);
  return [];
}

function buildEvidenceGroups({ insights, fingerprintEvidence, fingerprintDrift }) {
  const groups = insights
    .filter((insight) => insight.evidence?.length)
    .map((insight) => ({
      id: insight.id,
      title: insight.summary,
      system: insight.system,
      severity: insight.severity,
      confidence: insight.confidence,
      confidenceScore: insight.confidenceScore,
      evidence: insight.evidence,
    }));

  const seenEvidence = new Set(groups.flatMap((group) => group.evidence.map(evidenceKey)));
  const uniqueFingerprintEvidence = (fingerprintEvidence ?? []).filter((item) => {
    const key = evidenceKey(item);
    if (seenEvidence.has(key)) return false;
    seenEvidence.add(key);
    return true;
  });

  if (uniqueFingerprintEvidence.length) {
    groups.push({
      id: "fingerprint",
      title: "Operating fingerprint evidence",
      system: "Operating fingerprint",
      severity: fingerprintDrift.label,
      confidence: "",
      confidenceScore: null,
      evidence: uniqueFingerprintEvidence,
    });
  }

  return groups;
}

function evidenceKey(item) {
  return firstText(item?.evidence_id, item?.id, item?.description, item?.summary, compactJson(item));
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

function collectQuality(result, snapshot) {
  const dataQuality = result?.analysis_result?.data_quality ?? result?.data_quality ?? {};
  const timestampProfile = result?.timestamp_profile ?? {};
  const signalIntegrity = Array.isArray(dataQuality.signal_integrity)
    ? dataQuality.signal_integrity.filter((profile) => profile && profile.gap_type)
    : [];
  const warnings = dedupeText([
    ...(Array.isArray(dataQuality.warnings) ? dataQuality.warnings : []),
    ...(Array.isArray(timestampProfile.warnings) ? timestampProfile.warnings : []),
    ...(Array.isArray(result?.warnings) ? result.warnings : []),
  ]);
  const missingSummary = formatMissingValueSummary(dataQuality);
  const missingValues = dedupeText([
    missingSummary,
    ...(Array.isArray(dataQuality.missing_values) ? dataQuality.missing_values : []),
    ...(Array.isArray(dataQuality.missing_value_warnings) ? dataQuality.missing_value_warnings : []),
    ...(Array.isArray(result?.missing_values) ? result.missing_values : []),
  ]);
  const timestampWindow = timestampProfile.first_timestamp && timestampProfile.last_timestamp
    ? timestampProfile.first_timestamp + " to " + timestampProfile.last_timestamp
    : null;
  const timestampNotes = dedupeText([
    timestampProfile.mode,
    timestampWindow,
    result?.timestamp_mode,
    snapshot?.timestamp_mode,
  ]);
  const confidenceReduced = Boolean(
    dataQuality.reduced_confidence
    || dataQuality.confidence_reduced
    || dataQuality.suppress_confidence
    || signalIntegrity.some((profile) => profile.suppress_confidence)
  );
  return {
    warnings,
    missingValues,
    timestampNotes,
    signalIntegrity,
    affectedSignalCount: signalIntegrity.length,
    confidenceReduced,
  };
}

function deriveDataQualityNotice({ quality, liveOps, analysisComplete }) {
  if (!analysisComplete) return null;
  const degradedConnection = String(liveOps?.connectionTone ?? "").toLowerCase().includes("degraded");
  const hasWarnings = quality.warnings.length > 0;
  const hasMissingValues = quality.missingValues.length > 0;
  if (!quality.confidenceReduced && !degradedConnection && !hasWarnings && !hasMissingValues) return null;

  const detail = conciseOperatorSentence(quality.missingValues[0], quality.warnings[0]);
  if (quality.confidenceReduced || degradedConnection) {
    return {
      label: "Analysis completed with reduced confidence.",
      tone: "warning",
      detail,
    };
  }
  if (quality.affectedSignalCount > 1) {
    return {
      label: quality.affectedSignalCount + " telemetry signals contained intermittent missing values",
      tone: "warning",
      detail,
    };
  }
  if (hasMissingValues) {
    return {
      label: "Some telemetry samples were unavailable",
      tone: "warning",
      detail,
    };
  }
  return {
    label: "Analysis completed with minor data quality warnings",
    tone: "warning",
    detail,
  };
}

function deriveTelemetryStatus({ result, snapshot, quality, liveOps, analysisComplete, telemetryAvailable, telemetryConnected }) {
  if (!analysisComplete) {
    if (telemetryConnected) return { label: "Telemetry Connected", tone: "normal", detail: "Live telemetry is connected; run analysis to identify systems and relationships." };
    return telemetryAvailable
      ? { label: "Telemetry Loaded", tone: "unknown", detail: READY_TO_ANALYZE_STATUS.detail }
      : WAITING_FOR_TELEMETRY_STATUS;
  }
  const qualityNotice = deriveDataQualityNotice({ quality, liveOps, analysisComplete });
  if (!result && !snapshot) return { label: "Telemetry unavailable", tone: "unknown", detail: "No telemetry has been analyzed yet." };
  if (qualityNotice) return qualityNotice;
  return { label: "Telemetry acceptable", tone: "normal", detail: "Telemetry integrity is acceptable for interpretation." };
}

function deriveFingerprintDrift({ relationshipRows, result, hasFinding, analysisComplete, baselineAvailable, analysisExplanation }) {
  const fingerprint = analysisExplanation?.fingerprint ?? {};
  if (analysisComplete && fingerprint.meaning) {
    const driftStatus = String(fingerprint.drift_status ?? fingerprint.status ?? "").toLowerCase();
    const changed = driftStatus === "changed" || driftStatus === "drifting" || driftStatus === "review" || driftStatus === "unstable";
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
      detail: "Fingerprint comparison will populate after analysis completes.",
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
  const normalizedTags = Array.isArray(result?.analysis_result?.normalized_telemetry?.tags)
    ? result.analysis_result.normalized_telemetry.tags.map((tag) => tag.tag_name)
    : [];
  return dedupeText([...columns, ...detected, ...normalizedTags]).slice(0, 24);
}

function buildHistoryItems({ liveOps, snapshot, result, insights, analysisComplete }) {
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
  if (analysisComplete && (snapshot?.processed_at || result?.processed_at || result?.last_processed_at || result?.completed_at)) {
    items.unshift({
      id: "current-analysis",
      title: insights.length ? "Current insight generated" : "Current analysis completed",
      time: snapshot?.processed_at ?? result?.processed_at ?? result?.last_processed_at ?? result?.completed_at ?? "Current period",
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
        const sourceTarget = row.source && row.target ? [row.source, row.target].map((item) => String(item).replace(/^tag:/, "").replace(/^metric:/, "")) : [];
        const rawLabel = Array.isArray(row.columns) ? row.columns.join(" / ") : (Array.isArray(row.source_tags) ? row.source_tags.join(" / ") : firstText(row.column, row.pair, sourceTarget.join(" / "), row.detail, "Relationship " + (index + 1)));
        const label = cleanRelationshipLabel(rawLabel);
        const detail = operatorText(row.explanation, row.what_changed, row.detail, row.summary, row.change_type, "Relationship behavior changed against baseline.");
        return <li key={label + "-" + index}><strong>{label}</strong><span>{detail}</span></li>;
      })}
    </ul>
  );
}

function SignalList({ signals, integrity }) {
  if (!signals.length) return <EmptyOperationalState title="No signals detected" body="Detected signals will appear after telemetry is uploaded." />;
  return (
    <ul className="operational-list operational-list--signals">
      {signals.map((signal) => <li key={signal}><strong>{cleanDisplayText(signal)}</strong><span>{integrity.label}</span></li>)}
    </ul>
  );
}

function InsightList({ insights, empty, emptyTitle = "No active insights", onOpenInsight, selectedId }) {
  if (!insights.length) return <EmptyOperationalState title={emptyTitle} body={empty} />;
  return (
    <div className="insight-feed insight-feed--cards">
      {insights.map((insight) => {
        const selected = selectedId === insight.id;
        const title = formatInsightTitle(insight.summary);
        const relationships = insightRelationshipLabels(insight).slice(0, 8);
        const summary = operatorSummaryBriefing(insight, relationships)[0] || title;
        return (
          <article
            key={insight.id}
            className={selected ? "insight-card insight-card--compact is-selected" : "insight-card insight-card--compact"}
            aria-current={selected ? "true" : undefined}
          >
            <div className="insight-card__header">
              <span className="section-token">{formatSubsystemName(insight.system)}</span>
              <div className="insight-card__badges">
                <StatusBadge label={insight.severity} tone={severityToTone(insight.severity)} />
                <StatusBadge label={formatConfidenceLevel(insight.confidence, insight.confidenceScore)} tone="unknown" />
              </div>
            </div>
            <h3>{title}</h3>
            <p className="insight-card__summary">{summary}</p>
            <button type="button" className="secondary-command-button insight-card__open" onClick={() => onOpenInsight?.(insight.id)}>Open</button>
          </article>
        );
      })}
    </div>
  );
}

function InsightDetail({ insight }) {
  const causes = operationalCauseHypotheses(insight).slice(0, 6);
  const relationships = insightRelationshipLabels(insight).slice(0, 8);
  return (
    <article className="insight-detail-card" aria-label="Insight detail">
      <div className="insight-briefing__header">
        <span className="section-token">{formatSubsystemName(insight.system)}</span>
        <h3>{formatInsightTitle(insight.summary)}</h3>
      </div>
      <dl className="insight-briefing__status" aria-label="Insight status">
        <div>
          <dt>Severity</dt>
          <dd><StatusBadge label={insight.severity} tone={severityToTone(insight.severity)} /></dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd><StatusBadge label={formatConfidenceLevel(insight.confidence, insight.confidenceScore)} tone="unknown" /></dd>
        </div>
      </dl>
      <BriefingTextBlock title="Summary" lines={operatorSummaryBriefing(insight, relationships)} />
      <BriefingList title="Possible Operational Causes" items={causes} />
      {relationships.length ? <RelationshipObservedList items={relationships} /> : null}
      <BriefingList
        title="Recommended Investigation"
        items={suggestedInvestigationSteps({
          subsystem: insight.system,
          relationshipLabels: relationships,
          insight,
        }).slice(0, 4)}
        limit={4}
      />
      {insight.hasEvidence ? <InsightEvidenceDrawer insight={insight} /> : null}
    </article>
  );
}

function BriefingTextBlock({ title, lines }) {
  const visibleLines = toList(lines).filter(Boolean).slice(0, title === "Summary" ? 2 : 3);
  if (!visibleLines.length) return null;
  return (
    <section className="insight-briefing__section">
      <h4>{title}</h4>
      {visibleLines.map((line) => <p key={line}>{line}</p>)}
    </section>
  );
}

function BriefingList({ title, items, limit = 6 }) {
  const visibleItems = dedupeText(toList(items).map(cleanBriefingText)).slice(0, limit);
  if (!visibleItems.length) return null;
  return (
    <section className="insight-briefing__section">
      <h4>{title}</h4>
      <ul className="operator-briefing-list">{visibleItems.map((item) => <li key={item}>{item}</li>)}</ul>
    </section>
  );
}

function RelationshipObservedList({ items }) {
  const visibleItems = dedupeText(items.map(formatRelationshipObservedLabel)).slice(0, 8);
  if (!visibleItems.length) return null;
  return (
    <section className="insight-briefing__section">
      <h4>Relationships Involved</h4>
      <ul className="operator-briefing-list">{visibleItems.map((item) => <li key={item}>{item}</li>)}</ul>
    </section>
  );
}

function InsightEvidenceDrawer({ insight }) {
  const evidenceItems = Array.isArray(insight.evidence) ? insight.evidence : [];
  if (!evidenceItems.length) return null;
  return (
    <details className="insight-evidence-drawer">
      <summary>Evidence</summary>
      <div className="insight-evidence-drawer__body">
        {evidenceItems.map((item, index) => (
          <div className="insight-evidence-item" key={item.evidence_id ?? index}>
            <EvidenceDetails evidence={item} />
          </div>
        ))}
      </div>
    </details>
  );
}

function EvidencePanel({ evidence }) {
  return (
    <details className="evidence-panel">
      <summary>Evidence</summary>
      <EvidenceDetails evidence={evidence} />
    </details>
  );
}

function EvidenceDetails({ evidence }) {
  const supportingSignals = toList(evidence.description, evidence.supporting_signals, evidence.supportingSignals).flatMap(splitPriorityText).map(operatorText);
  const metricChanges = toList(evidence.metric_delta, evidence.relevant_metric_changes, evidence.relevantMetricChanges).flatMap(formatEvidenceDelta).flatMap(splitPriorityText);
  const sourceColumns = toList(evidence.source_columns, evidence.sourceColumns, evidence.source_metrics, evidence.sourceMetrics, evidence.source_tags, evidence.sourceTags).flatMap(splitPriorityText).map(cleanDisplayText);
  const sourceRanges = Array.isArray(evidence.source_time_ranges) ? evidence.source_time_ranges.map(formatEvidenceRange).filter(Boolean) : [];
  return (
    <div className="evidence-details-body">
      <DetailGrid rows={[
        ["Summary", operatorText(evidence.description, evidence.summary)],
        ["Confidence", formatConfidenceDisplay(evidence.confidence, evidence.confidence_score)],
        ["Time window", evidence.time_window ?? evidence.timeWindow],
        ["Persistence / duration", evidence.persistence_duration ?? evidence.persistenceDuration],
        ["Calculated change", evidence.calculated_delta ?? evidence.calculatedDelta],
        ["Relationship measurements", evidence.relationship_delta ? compactJson(evidence.relationship_delta) : ""],
        ["Calculated percent change", evidence.calculated_percent_delta ?? evidence.calculatedPercentDelta],
        ["Upload reference", evidence.source_upload_id ?? evidence.upload_id],
        ["Analysis reference", evidence.analysis_id],
      ]} />
      {sourceColumns.length ? <QualityList title="Source signals" items={sourceColumns} empty="" /> : null}
      {sourceRanges.length ? <QualityList title="Source time ranges" items={sourceRanges} empty="" /> : null}
      {supportingSignals.length ? <QualityList title="Supporting signals" items={supportingSignals} empty="" /> : null}
      {metricChanges.length ? <QualityList title="Relevant metric changes" items={metricChanges} empty="" /> : null}
    </div>
  );
}

function compactJson(value) {
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function formatEvidenceDelta(value) {
  if (Array.isArray(value)) return value.map(formatEvidenceDelta).filter(Boolean);
  if (!value || typeof value !== "object") return value ? [String(value)] : [];
  const label = cleanDisplayText(firstText(value.tag_name, value.label, value.name, value.source_column, value.change_type));
  const details = [
    value.percent_change !== undefined ? `percent change: ${value.percent_change}` : "",
    value.absolute_change !== undefined ? `absolute change: ${value.absolute_change}` : "",
    value.baseline_average !== undefined ? `baseline average: ${value.baseline_average}` : "",
    value.current_average !== undefined ? `current average: ${value.current_average}` : "",
    value.baseline_strength !== undefined ? `baseline operating coupling: ${value.baseline_strength}` : "",
    value.current_strength !== undefined ? `current operating coupling: ${value.current_strength}` : "",
    value.correlation_delta !== undefined ? `operating pattern change: ${value.correlation_delta}` : "",
  ].filter(Boolean).join(", ");
  return [firstText([label, details].filter(Boolean).join(" - "), compactJson(value))];
}

function formatBehaviorWindow(window) {
  if (!window || typeof window !== "object") return "";
  return firstText(window.time_window, [window.start, window.end].filter(Boolean).join(" to "), window.description);
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
  if (section === "evidence") return "Evidence";
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

function severityToTone(severity) {
  const text = String(severity ?? "").toLowerCase();
  if (text.includes("high") || text.includes("significant") || text.includes("critical")) return "investigate";
  if (text.includes("moderate") || text.includes("changed") || text.includes("review") || text.includes("drift")) return "changed";
  return "normal";
}

function prioritizeEvidenceGroups(groups, selectedInsightId) {
  if (!selectedInsightId) return groups;
  return [...groups].sort((left, right) => {
    if (left.id === selectedInsightId) return -1;
    if (right.id === selectedInsightId) return 1;
    return 0;
  });
}

function ExecutiveSummary({ checklist, notice, report, rows }) {
  return (
    <div className="operator-executive-summary" aria-label="Executive summary rows">
      {notice ? (
        <div className={"operator-summary-notice operator-summary-notice--" + notice.tone}>
          <strong>{notice.label}</strong>
          {notice.detail ? <p>{notice.detail}</p> : null}
        </div>
      ) : null}
      {report ? <OperatorInterpretation report={report} /> : null}
      <ul className="operator-completion-list" aria-label="Analysis completion checks">
        {checklist.map((item) => (
          <li key={item}>
            <span aria-hidden="true">✓</span>
            <strong>{item}</strong>
          </li>
        ))}
      </ul>
      <dl className="executive-summary-list">
        {rows.filter((row) => row && row.length >= 2).filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "").map(([label, value]) => (
          <div className="executive-summary-item" key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function OperatorInterpretation({ report }) {
  const statusRows = [
    ["Severity", report.urgency],
    ["Confidence", report.confidence],
  ];
  const primary = report.primaryFinding ?? {};
  const evidence = report.supportingEvidence ?? {};
  const relationships = evidence.relationships?.length ? evidence.relationships : primary.whatChanged;
  const trendRows = [
    ["Condition", report.condition],
    ["Operating fingerprint", report.fingerprint],
    ["First observed", report.trend?.firstObserved],
    ["Progression", report.trend?.direction],
    ["Subsystem stability", report.trend?.subsystemStability],
    ["Follow-up", report.trend?.recommendedFollowUp],
  ];

  return (
    <div className="operator-interpretation" aria-label="Operator interpretation report">
      <section className="operator-interpretation__block" aria-label="Overall system status">
        <span className="section-token">{report.subsystem || "Insight"}</span>
        <h3>{primary.title || report.condition}</h3>
        <div className="operator-interpretation__status-row">
          {statusRows.filter(([, value]) => value).map(([label, value]) => (
            <span key={label}><strong>{label}:</strong> {value}</span>
          ))}
        </div>
      </section>

      <section className="operator-interpretation__block" aria-label="Executive summary">
        <h3>Summary</h3>
        {report.executiveSummary.slice(0, 2).map((line) => <p key={line}>{ensureSentence(line)}</p>)}
      </section>

      <div className="operator-interpretation__columns">
        <BriefingList title="Possible Operational Causes" items={report.possibleOperationalCauses} />
        <BriefingList title="Recommended Investigation" items={report.suggestedInvestigation} limit={3} />
      </div>

      {relationships?.length ? <RelationshipObservedList items={relationships} /> : null}

      <details className="insight-evidence-drawer">
        <summary>Evidence</summary>
        <div className="insight-evidence-drawer__body">
          <DetailGrid rows={[
            ["Fingerprint confidence", evidence.fingerprintConfidence],
            ["Operating persistence", evidence.relationshipPersistence],
            ...trendRows,
          ]} />
          {report.didNotObserve?.length ? <BriefingList title="Not Observed" items={report.didNotObserve} /> : null}
        </div>
      </details>
    </div>
  );
}

function SummaryRows({ rows }) {
  return (
    <div className="summary-row-list">
      {rows.filter((row) => row && row.length >= 2).filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "").map(([label, value]) => (
        <div className="summary-row" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
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

function formatConfidenceDisplay(label, score) {
  const cleanLabel = firstText(label)
    .split("_")
    .join(" ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
  const percent = confidencePercent(score);
  if (!cleanLabel && percent === null) return "";
  if (percent === null) return cleanLabel;
  return `${cleanLabel || "Confidence"} · ${percent}%`;
}

function confidencePercent(score) {
  if (score === null || score === undefined || score === "") return null;
  const value = Number(score);
  if (!Number.isFinite(value)) return null;
  const normalized = value > 1 && value <= 100 ? value : value * 100;
  return Math.max(0, Math.min(100, Math.round(normalized)));
}

function firstDistinctText(reference, ...values) {
  const referenceText = firstText(reference).trim().toLowerCase();
  return firstText(...values.filter((value) => firstText(value).trim().toLowerCase() !== referenceText));
}

function formatMissingValueSummary(dataQuality) {
  const profiles = Array.isArray(dataQuality?.signal_integrity)
    ? dataQuality.signal_integrity.filter((profile) => profile && profile.gap_type)
    : [];
  if (!profiles.length) return "";
  const affected = dedupeText(profiles.map((profile) => humanizeSignalName(profile.signal_id))).slice(0, 4);
  const missingPercents = profiles
    .map((profile) => 1 - Number(profile.completeness))
    .filter((value) => Number.isFinite(value) && value > 0);
  const maxMissing = missingPercents.length ? Math.max(...missingPercents) : null;
  const missingText = maxMissing === null ? "Missing values" : `${formatPercent(maxMissing)} missing values`;
  const affectedText = affected.length ? ` in ${formatList(affected)}` : "";
  const confidenceText = profiles.some((profile) => profile.suppress_confidence)
    ? " Confidence reduced."
    : " Confidence reduced slightly.";
  return `${missingText} detected${affectedText}.${confidenceText}`;
}

function humanizeSignalName(value) {
  return firstText(value)
    .replace(/_/g, " ")
    .replace(/\b(f|c|psi|pct|gal)\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanDisplayText(value) {
  const text = sanitizeOperatorText(firstText(value))
    .replace(/^tag:/i, "")
    .replace(/^metric:/i, "")
    .replace(/\btag[-_\s]?pair\b/gi, "relationship")
    .replace(/\bColumn\s+(\d+)\b/gi, (match, number) => "Signal " + number)
    .replace(/_+/g, " ")
    .replace(/\s+\/\s+/g, " / ")
    .replace(/\s+/g, " ")
    .trim();
  return text || firstText(value);
}

function cleanRelationshipLabel(value) {
  return cleanDisplayText(value)
    .replace(/::/g, " / ")
    .replace(/\s+vs\.?\s+/gi, " / ")
    .replace(/\s+/g, " ")
    .trim();
}

function relationshipContributionLabels(values) {
  if (!Array.isArray(values)) return [];
  return dedupeText(values.map((item) => {
    if (!item || typeof item !== "object") return cleanRelationshipLabel(item);
    const displayColumns = Array.isArray(item.display_columns) ? item.display_columns : [];
    const rawColumns = Array.isArray(item.columns) ? item.columns : [];
    return cleanRelationshipLabel(firstText(item.label, displayColumns.join(" / "), rawColumns.join(" / ")));
  }).filter(Boolean));
}


const DEFAULT_OPERATIONAL_CAUSES = [
  "Operating setpoint changed",
  "Control sequence adjustment",
  "Process demand changed",
  "Recent maintenance activity",
];

const OPERATIONAL_CAUSE_SETS = [
  {
    pattern: /flow|pressure|pump|valve|vfd|filter/i,
    causes: [
      "Filter loading",
      "Pump operating point changed",
      "Valve position changed",
      "VFD control adjustment",
      "Process demand changed",
      "Recent maintenance activity",
    ],
  },
  {
    pattern: /thermal|condenser|chilled|chw|lwt|cooling|coil|temperature|approach/i,
    causes: [
      "Heat exchanger fouling",
      "Cooling tower performance changed",
      "Water flow changed",
      "Valve position changed",
      "Process load changed",
      "Recent maintenance activity",
    ],
  },
  {
    pattern: /air|ahu|fan|damper|duct|coil leaving/i,
    causes: [
      "Damper position changed",
      "Fan speed changed",
      "Coil heat transfer changed",
      "Airflow restriction increasing",
      "Zone demand changed",
      "Recent maintenance activity",
    ],
  },
  {
    pattern: /chemical|water quality|turbidity|chlorine|ph|conductivity/i,
    causes: [
      "Chemical feed rate changed",
      "Water source condition changed",
      "Sensor calibration drift",
      "Mixing pattern changed",
      "Process demand changed",
      "Recent maintenance activity",
    ],
  },
];

function formatInsightTitle(value) {
  return formatSubsystemName(value)
    .replace(/\s+/g, " ")
    .trim();
}

function formatSubsystemName(value) {
  return cleanDisplayText(value)
    .replace(/\s+\/\s+/g, " & ")
    .replace(/\bSubsystem\b/g, "subsystem")
    .replace(/\bSystem\b/g, "system")
    .trim();
}

function whatChangedBriefing(insight, relationships) {
  const system = formatSubsystemName(insight.system || "subsystem");
  if (relationships.length > 0) {
    const count = relationships.length;
    return [
      `${system} no longer follows its historical operating pattern.`,
      count === 1 ? "One operating relationship shifted." : "Multiple operating relationships shifted together.",
    ];
  }
  const lines = briefingSentences(firstDistinctText(insight.summary, insight.whatHappened, insight.whatChanged, insight.summary), 2);
  return lines.length ? lines : ["Subsystem behavior changed from its historical operating pattern."];
}

function operatorSummaryBriefing(insight, relationships) {
  return dedupeText(whatChangedBriefing(insight, relationships)).slice(0, 2);
}

function whyItMattersBriefing(insight) {
  const lines = briefingSentences(firstText(insight.possibleConsequence, insight.whyItMatters, insight.whyNeraiumThinks), 2);
  if (lines.length) return lines;
  return [
    "When several operating relationships change together, the subsystem may have shifted operating state.",
    "This often appears before a single sensor clearly identifies the underlying cause.",
  ];
}

function operationalCauseHypotheses(insight) {
  const direct = dedupeText(toList(insight.possibleOperationalCauses).flatMap(splitPriorityText).map(cleanBriefingText));
  const searchText = [insight.system, insight.summary, insight.whatHappened, insightRelationshipLabels(insight).join(" ")].join(" ");
  const matched = OPERATIONAL_CAUSE_SETS.find((item) => item.pattern.test(searchText));
  return dedupeText([...direct, ...(matched?.causes ?? []), ...DEFAULT_OPERATIONAL_CAUSES]).slice(0, 6);
}

function insightRelationshipLabels(insight) {
  if (Array.isArray(insight.affectedRelationships) && insight.affectedRelationships.length) {
    return insight.affectedRelationships;
  }
  if (Array.isArray(insight.contributingRelationships) && insight.contributingRelationships.length) {
    return relationshipContributionLabels(insight.contributingRelationships);
  }
  return [];
}

function formatRelationshipObservedLabel(value) {
  return cleanRelationshipLabel(value)
    .replace(/\s*<->\s*/g, " ↔ ")
    .replace(/\s+\/\s+/g, " ↔ ")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanBriefingText(value) {
  return cleanDisplayText(value)
    .replace(/\bincreasing filter resistance\b/gi, "Filter loading")
    .replace(/\bfilter resistance increasing\b/gi, "Filter loading")
    .replace(/\bbaseline\/current comparison\b/gi, "historical comparison")
    .replace(/\bbaseline window\b/gi, "historical pattern")
    .replace(/\bcurrent window\b/gi, "analysis period")
    .replace(/\bversus baseline\b/gi, "from normal")
    .replace(/\bby\s+[-+]?\d+(?:\.\d+)?\s*%/gi, "")
    .replace(/\b[-+]?\d+(?:\.\d+)?\s*%\b/g, "")
    .replace(/\brelationship missing\b/gi, "")
    .replace(/\bcorrelation delta\b/gi, "")
    .replace(/\brelationship strength\b/gi, "")
    .replace(/\bconfidence score\b/gi, "")
    .replace(/\s+([.,;:!?])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function briefingSentences(value, max = 2) {
  const text = cleanBriefingText(value);
  if (!text) return [];
  const sentences = text.match(/[^.!?]+[.!?]?/g) ?? [text];
  return sentences.map((item) => ensureSentence(item.trim())).filter(Boolean).slice(0, max);
}

function ensureSentence(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

function formatConfidenceLevel(label, score) {
  const cleanLabel = firstText(label)
    .split("_")
    .join(" ")
    .toLowerCase();
  if (cleanLabel.includes("high") || cleanLabel.includes("confirmed") || cleanLabel.includes("strong")) return "High";
  if (cleanLabel.includes("moderate") || cleanLabel.includes("medium") || cleanLabel.includes("likely") || cleanLabel.includes("present")) return "Moderate";
  if (cleanLabel.includes("low") || cleanLabel.includes("weak") || cleanLabel.includes("developing") || cleanLabel.includes("pending")) return "Low";
  const percent = confidencePercent(score);
  if (percent === null) return cleanLabel ? cleanLabel.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Low";
  if (percent >= 82) return "High";
  if (percent >= 62) return "Moderate";
  return "Low";
}

function operatorEvidenceSummary(...values) {
  const text = operatorText(...values);
  if (!text) return "";
  if (/^(percent change|absolute change|calculated delta|baseline average|current average)\s*:/i.test(text)) {
    return "Supporting measurements are available in Evidence.";
  }
  if (/\bcorrelation delta\b/i.test(text)) return "Supporting relationship measurements are available in Evidence.";
  return text;
}

function operatorText(...values) {
  return cleanDisplayText(firstText(...values));
}

function formatPercent(value) {
  const percent = value * 100;
  if (percent < 1) return `${percent.toFixed(1)}%`;
  return `${Math.round(percent)}%`;
}

function formatList(items) {
  if (items.length <= 1) return firstText(items[0]);
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
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
  const hasIntelligenceData = Boolean(result?.analysis_result || result?.sii_intelligence || result?.engine_result);
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

function hasTelemetry(result, snapshot, liveOps) {
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
