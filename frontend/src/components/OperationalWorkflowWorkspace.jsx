import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import PageContainer from "./layout/PageContainer";
import AdvancedDetailsView from "./operational/AdvancedDetailsView";
import CommandCenterView from "./operational/CommandCenterView";
import DataSourcesView from "./operational/DataSourcesView";
import FingerprintView from "./operational/FingerprintView";
import InsightsView from "./operational/InsightsView";
import SystemsView from "./operational/SystemsView";
import { FALLBACK_SYSTEMS } from "../config/workspaces";
import { sanitizeOperatorText } from "../viewModels/operatorFinding";
import "../styles/operational-workflow.css";

const NAV_ITEMS = [
  { id: "command-center", label: "Command Center" },
  { id: "systems", label: "Systems" },
  { id: "insights", label: "Insights" },
  { id: "fingerprint", label: "Operational Fingerprint" },
  { id: "data-sources", label: "Data Sources" },
  { id: "advanced", label: "Advanced" },
];

const MOBILE_PRIMARY_NAV = NAV_ITEMS;
const ACTIVE_SECTION_STORAGE_KEY = "neraium.operational.active_section";
const SELECTED_INSIGHT_STORAGE_KEY = "neraium.operational.selected_insight";

const UNASSIGNED_SYSTEM_NAME = "Unassigned System";

// Known-bad literal strings that have previously leaked through as fallback
// system/insight names. Kept as an exact-match fast path, but NOT relied on
// as the only defense -- see isBackendFallbackLabel below, which also runs a
// structural/pattern check so that a slightly reworded fallback sentence
// from the backend doesn't silently slip through this filter again.
const GENERIC_FALLBACK_LABELS = new Set([
  "observed system behavior changed",
  "observed subsystem behavior changed",
  "subsystem behavior changed subsystem",
  "subsystem behavher changed system",
  "subsystem behavior changed system",
]);
const FALLBACK_SYSTEM_NAMES = new Set(FALLBACK_SYSTEMS.map((system) => system.name.toLowerCase()));

// Structural pattern for the same class of fallback text. This exists
// because pattern-matching specific known-bad strings is inherently
// brittle: if the backend's template wording shifts even slightly (e.g.
// "Observed subsystem behavior shifted" instead of "changed"), an
// exact-match Set silently stops catching it. This regex targets the
// *shape* of the fallback sentence (subject = generic "system"/"subsystem"
// noun, verb = behavior changed/shifted) rather than one fixed phrasing.
const GENERIC_FALLBACK_PATTERN = /^(observed\s+)?(system|subsystem)(\s+behavior)?\s+(changed|shifted)(\s+(system|subsystem))?$/;

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
  label: "Awaiting Initial Baseline",
  detail: "Connect telemetry or analyze historical data to establish the facility's Operational Fingerprint.",
  commandTitle: "Awaiting Initial Baseline",
  commandDetail: "The facility has not yet established an Operational Fingerprint.",
  fileStatus: "No source connected",
  cta: "Analyze Historical Data",
  secondaryCta: "Connect Live Telemetry",
  headerStatus: "Waiting for telemetry",
};
const NO_TELEMETRY_STATUS = {
  label: "Ready to Build Operational Fingerprint",
  tone: "ready",
  statusKey: "ready",
  detail: EMPTY_TELEMETRY_COPY.detail,
};
const WAITING_FOR_TELEMETRY_STATUS = {
  label: "Waiting for telemetry",
  tone: "ready",
  statusKey: "waiting",
  detail: EMPTY_TELEMETRY_COPY.detail,
};
const READY_TO_ANALYZE_STATUS = {
  label: "Ready to Analyze Historical Telemetry",
  tone: "ready",
  statusKey: "ready",
  detail: "Telemetry is ready for analysis.",
};
const ANALYZING_STATUS = {
  label: "Building Operational Fingerprint...",
  tone: "learning",
  statusKey: "learning",
  detail: "Neraium is comparing current relationships against historical operating behavior.",
};
const ANALYSIS_COMPLETE_STATUS = {
  label: "System Online",
  tone: "active",
  statusKey: "active",
  detail: "Result ready.",
};
const MONITORING_LIVE_STATUS = {
  label: "Monitoring Active",
  tone: "active",
  statusKey: "active",
  detail: "Live telemetry is connected and current behavior is being monitored.",
};
const NO_BASELINE_AVAILABLE = {
  label: "Not analyzed",
  tone: "unknown",
  detail: "Run analysis to compare operating behavior.",
};
const SYSTEMS_PENDING = {
  title: "0 Systems Discovered",
  countLabel: "0 Discovered",
  summary: "Systems will be identified automatically after the first successful telemetry analysis.",
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
  resultsNavigationKey = 0,
  onTelemetrySelected,
  onCsvSelected,
  onResumePreviousSession,
  onReopenHistoricalAnalysis,
  onDeleteHistoricalAnalysis,
  onSignOut,
}) {
  const [activeSection, setActiveSection] = useState(() => readStoredOperationalSection());
  const [selectedInsightId, setSelectedInsightId] = useState(() => readStoredSelectedInsightId());
  const overviewUploadInputRef = useRef(null);
  const resultsNavigationHandledRef = useRef(resultsNavigationKey);

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

  useEffect(() => {
    if (!resultsNavigationKey || resultsNavigationHandledRef.current === resultsNavigationKey || !model.resultTabsReady) return;
    resultsNavigationHandledRef.current = resultsNavigationKey;
    const firstInsight = model.insights[0] ?? null;
    if (firstInsight) {
      setSelectedInsightId(firstInsight.id);
      setActiveSection("insights");
      return;
    }
    setActiveSection("systems");
  }, [model.insights, model.resultTabsReady, resultsNavigationKey]);

  const selectedInsight = model.insights.find((item) => item.id === selectedInsightId) ?? model.insights[0] ?? null;

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ACTIVE_SECTION_STORAGE_KEY, activeSection);
  }, [activeSection]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (selectedInsight?.id) {
      window.localStorage.setItem(SELECTED_INSIGHT_STORAGE_KEY, selectedInsight.id);
    } else {
      window.localStorage.removeItem(SELECTED_INSIGHT_STORAGE_KEY);
    }
  }, [selectedInsight?.id]);
  const viewHelpers = useMemo(() => ({
    DetailGrid,
    EmptyOperationalState,
    EvidencePanel,
    InsightDetail,
    InsightList,
    PanelHeader,
    QualityList,
    StatusBadge,
    SummaryRows,
    Timeline,
    formatActiveInsightCount,
    formatConfidenceDisplay,
    formatInsightTitle,
    insightRelationshipLabels,
    operatorSummaryBriefing,
    prioritizeEvidenceGroups,
    severityToTone,
  }), []);
  const navMetrics = {
    "command-center": model.commandCenterTabMetric,
    systems: model.systemsTabMetric,
    insights: model.insightsTabMetric,
    fingerprint: model.fingerprintTabMetric,
    "data-sources": model.dataSourcesTabMetric,
    advanced: model.advancedTabMetric,
  };
  const visibleSection = activeSection;
  const shellClassName = "operational-workflow";

  function navigate(sectionId) {
    setActiveSection(sectionId);
  }

  function openInsight(insightId) {
    const resolvedInsight = model.insights.find((item) => item.id === insightId) ?? model.insights[0] ?? null;
    setSelectedInsightId(resolvedInsight?.id ?? null);
    navigate("insights");
  }

  function openOverviewFilePicker() {
    overviewUploadInputRef.current?.click();
  }

  function handleOverviewFileSelection(event) {
    const files = Array.from(event?.target?.files ?? []);
    if (!files.length) {
      if (event?.target) event.target.value = "";
      return;
    }
    const csvSelectionHandler = onCsvSelected ?? onTelemetrySelected;
    if (typeof csvSelectionHandler === "function") {
      csvSelectionHandler(files);
    }
    setActiveSection("data-sources");
    if (event?.target) event.target.value = "";
  }

  function analyzeSystem() {
    if (model.uiState.key === "analyzing") return;
    setActiveSection("data-sources");
  }

  function viewSystems() {
    navigate("systems");
  }

  function viewFingerprint() {
    navigate("fingerprint");
  }

  function connectLiveData() {
    navigate("data-sources");
  }

  return (
    <PageContainer className={shellClassName}>
      <aside className="operational-sidebar" aria-label="Neraium navigation">
        <div className="operational-sidebar__brand">
          <span className="section-token">Neraium</span>
          <strong>{model.siteLabel}</strong>
          <p>Read-only operational intelligence layer</p>
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
          <small>Neraium Operational Intelligence</small>
          <small>Last analysis: {model.lastAnalysis}</small>
          {typeof onSignOut === "function" ? (
            <button type="button" className="operational-link-button" onClick={onSignOut}>Sign out</button>
          ) : null}
        </div>
      </aside>

      <main className="operational-main" aria-label="Neraium operational workspace">
        <input data-testid="overview-csv-upload-input" ref={overviewUploadInputRef} accept=".csv,text/csv" type="file" className="intake-flow__input" style={hiddenFileInputStyle} onChange={handleOverviewFileSelection} />
        <header className="operational-topbar">
          <div>
            <p className="section-token">{model.headerEyebrow}</p>
            <h1>{model.headerTitle}</h1>
            <p className="operational-topbar__context">{model.headerSubtitle}</p>
          </div>
          <div className="operational-topbar__status">
            <StatusBadge label={model.dashboardStatus.label} tone={model.dashboardStatus.tone} statusKey={model.dashboardStatus.statusKey} />
          </div>
        </header>

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

        {visibleSection === "command-center" ? (
          <CommandCenterView
            model={model}
            helpers={viewHelpers}
            onOpenInsight={openInsight}
            onAnalyzeHistoricalData={openOverviewFilePicker}
            onConnectLiveData={connectLiveData}
            onResumePreviousSession={onResumePreviousSession}
            onViewSystems={viewSystems}
            onViewFingerprint={viewFingerprint}
          />
        ) : null}

        {visibleSection === "systems" ? <SystemsView model={model} helpers={viewHelpers} onOpenInsight={openInsight} /> : null}

        {visibleSection === "insights" ? (
          <InsightsView model={model} helpers={viewHelpers} selectedInsight={selectedInsight} onSelectInsight={setSelectedInsightId} />
        ) : null}

        {visibleSection === "fingerprint" ? <FingerprintView model={model} helpers={viewHelpers} /> : null}

        {visibleSection === "data-sources" ? (
          <DataSourcesView model={model} helpers={viewHelpers} onAnalyzeHistoricalData={openOverviewFilePicker} onSelectCsv={openOverviewFilePicker} />
        ) : null}

        {visibleSection === "advanced" ? (
          <AdvancedDetailsView model={model} helpers={viewHelpers} selectedInsightId={selectedInsightId} onAnalyzeSystem={analyzeSystem} onResumePreviousSession={onResumePreviousSession} onReopenHistoricalAnalysis={onReopenHistoricalAnalysis} onDeleteHistoricalAnalysis={onDeleteHistoricalAnalysis} />
        ) : null}
      </main>
    </PageContainer>
  );
}

function readStoredOperationalSection() {
  if (typeof window === "undefined") return "command-center";
  const stored = window.localStorage.getItem(ACTIVE_SECTION_STORAGE_KEY);
  return NAV_ITEMS.some((item) => item.id === stored) ? stored : "command-center";
}

function readStoredSelectedInsightId() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(SELECTED_INSIGHT_STORAGE_KEY) || null;
}

function formatActiveInsightCount(value) {
  const count = Number(value);
  if (!Number.isFinite(count)) return String(value ?? "No Active Insights");
  if (count <= 0) return "No Active Insights";
  return String(count) + " Active Insight" + (count === 1 ? "" : "s");
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
  const detectedSystems = collectIdentifiedSystems({ liveOps, result, primarySystem, analysisExplanation });
  const identifiedSystems = analysisComplete ? detectedSystems.filter((system) => !isPlaceholderResortSystem(system)) : [];
  const identifiedSystemCount = identifiedSystems.length;
  const signals = buildSignals(result);
  const insights = analysisComplete ? buildInsights({ finding, liveOps, result, primarySystem, telemetryStatus, lastAnalysis, analysisExplanation, systems: identifiedSystems, signals }) : [];
  const activeInsightSystemCount = countActiveInsightSystems(insights);
  const evidenceGroups = analysisComplete ? buildEvidenceGroups({ insights, fingerprintEvidence, fingerprintDrift }) : [];
  const systemCards = analysisComplete ? buildSystemCards({ systems: identifiedSystems, primarySystem, insights }) : buildPlaceholderSystemCards();
  const systemSummary = buildSystemSummary({ analysisComplete, identifiedSystemCount, telemetryConnected });
  const historyItems = buildHistoryItems({ liveOps, snapshot, result, insights, analysisComplete });
  const analysisHistory = Array.isArray(liveOps?.analysisHistory) ? liveOps.analysisHistory : [];
  const domainLabel = formatDomainLabel(domainDetection?.mode ?? result?.domain_detection?.mode ?? result?.detected_schema?.mode ?? "Water system");
  const facilityName = firstMeaningfulText(result?.facility_name, snapshot?.facility_name, liveOps?.facilityName, liveOps?.facility_name, currentSession?.facilityName, currentSession?.facility_name);
  const siteLabel = facilityName || "Operational Intelligence";
  const headerTitle = facilityName || (analysisComplete ? ANALYSIS_COMPLETE_STATUS.label : "Command Center");
  const sourceLabel = deriveSourceLabel({ uiState, result, snapshot, liveOps });
  const contextLabel = "Site: " + siteLabel + " | Data source: " + sourceLabel;
  const sourceRowCount = deriveSourceRowCount({ result, snapshot });
  const overviewState = deriveOverviewState(uiState.key);
  const behaviorState = overallBehaviorState(fingerprintDrift);
  const headerSubtitle = (facilityName || analysisComplete) ? dashboardHeaderSubtitle({ analysisComplete, analysisRunning, insights, behaviorState }) : EMPTY_TELEMETRY_COPY.detail;
  const highestSeverity = analysisComplete ? deriveHighestSeverity({ insights, fingerprintDrift }) : "Not available";
  const overviewSummaryRows = buildOverviewSummaryRows({
    analysisComplete,
    uiState,
    sourceLabel,
    identifiedSystemCount,
    insights,
    highestSeverity,
    behaviorState,
  });
  const lastUpdated = deriveLastUpdatedLabel({ liveOps, snapshot, result });
  const dashboardStatus = deriveDashboardStatus({ uiState, analysisComplete, behaviorState, insights });
  const commandCenterTitle = analysisComplete ? "Operational Status" : EMPTY_TELEMETRY_COPY.commandTitle;
  const commandCenterStatus = dashboardStatus;
  const dashboardSummaryRows = buildDashboardSummaryRows({
    dashboardStatus,
    analysisComplete,
    identifiedSystemCount,
    activeInsightSystemCount,
    activeInsightCount: insights.length,
    highestSeverity,
    lastAnalysis,
    lastUpdated,
    telemetryConnected,
  });
  const dashboardFingerprintRows = buildDashboardFingerprintRows({ analysisComplete, fingerprintDrift, lastUpdated, relationshipRows });
  const dashboardSystemCards = buildDashboardSystemCards({
    analysisComplete,
    systemCards,
    detectedSystems,
    primarySystem,
    uiState,
  });
  const dashboardActivityItems = buildDashboardActivityItems({
    historyItems,
    insights,
    analysisComplete,
    analysisRunning,
    lastAnalysis,
  });
  const overviewSummarySentence = buildOverviewSummarySentence({ analysisComplete, insights, identifiedSystemCount, activeInsightSystemCount, behaviorState });
  const advancedRelationshipDetails = buildAdvancedRelationshipDetails(relationshipRows);
  const orb = deriveOrbState({ uiState, analysisComplete, fingerprintDrift, telemetryConnected, insights });
  const fingerprintRows = buildFingerprintRows({ fingerprintDrift, analysisComplete, baselineAvailable, behaviorState, relationshipRows });
  const relationshipChangeRows = buildRelationshipChangeRows(relationshipRows);
  const dataSourceRows = buildDataSourceRows({ sourceLabel, telemetryStatus, lastAnalysis, sourceRowCount, telemetryConnected });
  const commandCenterMessage = buildCommandCenterMessage({ uiState, analysisComplete, insights, behaviorState });
  const emptyInsightMessage = analysisComplete ? "Current relationships remain within the learned operating fingerprint." : "Insights are generated automatically once an Operational Fingerprint has been established.";

  const resultTabsReady = analysisComplete;

  return {
    siteLabel,
    domainLabel,
    sourceLabel,
    contextLabel,
    headerEyebrow: "Status",
    headerTitle,
    headerSubtitle,
    overviewState,
    commandCenterTabMetric: "Overview",
    systemsTabMetric: systemSummary.tabMetric,
    insightsTabMetric: analysisComplete ? String(insights.length) : "0 Insights",
    fingerprintTabMetric: analysisComplete ? fingerprintDrift.label : "Pending",
    dataSourcesTabMetric: telemetryConnected ? "Connected" : sourceLabel === "None" ? "Not Connected" : "Import",
    advancedTabMetric: resultTabsReady ? "Raw" : "Ready",
    resultTabsReady,
    sourceStatusLabel: uiState.sourceStatusLabel,
    sourceRowCount,
    storyProgressLabel: uiState.storyProgressLabel,
    primaryCtaLabel: uiState.primaryCtaLabel,
    analyzeDisabled: uiState.key === "analyzing",
    overviewSummaryRows,
    commandCenterTitle,
    commandCenterStatus,
    commandCenterMessage,
    emptyInsightMessage,
    orb,
    dashboardStatus,
    dashboardSummaryRows,
    dashboardFingerprintRows,
    dashboardSystemCards,
    dashboardActivityItems,
    overviewSummarySentence,
    behaviorState,
    highestSeverity,
    dataQualityNotice,
    advancedRelationshipDetails,
    uiState,
    heroStatus,
    telemetryStatus,
    lastAnalysis,
    analysisComplete,
    baselineAvailable,
    telemetryConnected,
    identifiedSystemCount,
    fingerprintDrift,
    fingerprintStatusLabel: fingerprintDrift.label === "Not analyzed" ? EMPTY_TELEMETRY_COPY.label : fingerprintDrift.label,
    fingerprintSummary: fingerprintDrift.detail,
    fingerprintRows,
    relationshipChangeRows,
    dataSourceRows,
    behaviorWindowRows: buildBehaviorWindowRows(analysisExplanation),
    rawResultJson: compactJson({ result, snapshot, analysisExplanation }),
    analysisMetadataRows: buildAnalysisMetadataRows({ result, snapshot, analysisExplanation }),
    systemCards,
    systemsSectionTitle: systemSummary.sectionTitle,
    systemsSectionSubtitle: systemSummary.sectionSubtitle,
    insights,
    evidenceGroups,
    relationshipRows,
    signals,
    historyItems,
    analysisHistory,
    qualityWarnings: quality.warnings,
    missingValues: quality.missingValues,
    timestampNotes: quality.timestampNotes,
    canResumePrevious: isAnalysisResumable({ liveOps, currentSession, result, snapshot, gateProcessing }),
    currentSession,
  };
}


function countHighSeverityInsights(insights) {
  return (insights ?? []).filter((insight) => ["High", "Critical"].includes(normalizeSeverity(insight?.severity))).length;
}

function buildOrbHotspots(insights, count) {
  const fallbackPositions = [
    { x: 70, y: 34, scale: 1 },
    { x: 38, y: 66, scale: 0.84 },
    { x: 62, y: 70, scale: 1.12 },
    { x: 31, y: 39, scale: 0.76 },
    { x: 77, y: 57, scale: 0.92 },
  ];
  const driftInsights = (insights ?? []).filter(Boolean);
  return Array.from({ length: count }, (_, index) => {
    const insight = driftInsights[index % Math.max(driftInsights.length, 1)] ?? {};
    const fallback = fallbackPositions[index % fallbackPositions.length];
    return {
      ...fallback,
      subsystem: firstText(insight.system, insight.rawSystemName, insight.metricName, `Drift ${index + 1}`),
    };
  });
}

function deriveOrbState({ uiState, analysisComplete, fingerprintDrift, telemetryConnected, insights }) {
  if (uiState.key === "analyzing") {
    return { key: "analyzing", status: "learning", label: "Learning", tone: "learning", visualLabel: "Operational Fingerprint" };
  }
  if (!analysisComplete) {
    return { key: "no-data", status: "awaiting", label: EMPTY_TELEMETRY_COPY.commandTitle, tone: "ready", visualLabel: "Operational Status" };
  }

  const hasDrift = insights.length || fingerprintDrift.tone === "changed" || fingerprintDrift.tone === "investigate";
  if (hasDrift) {
    const highSeverityCount = countHighSeverityInsights(insights);
    const status = highSeverityCount > 1 ? "critical" : highSeverityCount === 1 ? "elevated" : "warning";
    const hotspotCount = status === "critical"
      ? Math.min(5, Math.max(3, highSeverityCount))
      : Math.min(2, Math.max(1, highSeverityCount || insights.length || 1));
    return {
      key: status === "critical" ? "multiple-critical-systems" : status === "elevated" ? "elevated-risk" : "investigation-recommended",
      status,
      label: status === "critical" ? "Immediate Investigation Recommended" : status === "elevated" ? "Operational Changes Detected" : "Investigation Recommended",
      tone: "drift",
      visualLabel: "Operational Fingerprint",
      hotspotCount,
      hotspots: buildOrbHotspots(insights, hotspotCount),
    };
  }

  if (telemetryConnected) {
    return { key: "monitoring", status: "healthy", label: ANALYSIS_COMPLETE_STATUS.label, tone: "active", visualLabel: "Operational Fingerprint" };
  }
  return { key: "stable", status: "healthy", label: ANALYSIS_COMPLETE_STATUS.label, tone: "active", visualLabel: "Operational Fingerprint" };
}

function buildFingerprintRows({ fingerprintDrift, analysisComplete, baselineAvailable, behaviorState, relationshipRows }) {
  return [
    ["Fingerprint status", analysisComplete ? fingerprintDrift.label : "Pending"],
    ["Baseline status", baselineAvailable ? "Available" : "Waiting for telemetry"],
    ["Drift status", analysisComplete ? behaviorState : "Waiting for telemetry"],
    ["Relationship changes", analysisComplete ? String(relationshipRows.length) : "0"],
    ["Read-only enforcement", "Decision support only"],
  ];
}

function buildDashboardFingerprintRows({ analysisComplete, fingerprintDrift, lastUpdated, relationshipRows }) {
  return [
    ["Status", analysisComplete ? "Established" : "Pending"],
    ["Current state", analysisComplete ? fingerprintDrift.label : "Waiting for telemetry"],
    ["Relationship changes", analysisComplete ? String(relationshipRows.length) : "0"],
    ["Last updated", analysisComplete ? lastUpdated : "Not updated yet"],
  ];
}

function buildRelationshipChangeRows(relationshipRows) {
  return relationshipRows
    .map((row, index) => relationshipDisplayName(row, index))
    .filter(Boolean)
    .slice(0, 12);
}

function buildDataSourceRows({ sourceLabel, lastAnalysis, telemetryConnected }) {
  return [
    ["Historical Source", sourceLabel === "None" ? "Not Connected" : sourceLabel],
    ["Live Telemetry", telemetryConnected ? "Connected" : "Not Connected"],
    ["Last Analysis", lastAnalysis === "No analysis yet" || lastAnalysis === "Not analyzed yet" ? "No Analysis Yet" : lastAnalysis],
    ["Writeback", "Disabled (Read Only)"],
  ];
}

function buildCommandCenterMessage({ uiState, analysisComplete, insights, behaviorState }) {
  if (uiState.key === "analyzing") return ANALYZING_STATUS.detail;
  if (!analysisComplete) return EMPTY_TELEMETRY_COPY.commandDetail;
  if (insights.length) return "Highest-severity insight indicates a relationship no longer follows its learned operating behavior.";
  if (behaviorState === "Stable") return "Current operation remains aligned with the learned operating fingerprint.";
  return "Current operation is moving away from its established operating pattern.";
}


function deriveOverviewState(uiStateKey) {
  if (uiStateKey === "noTelemetry") return "noTelemetrySource";
  if (uiStateKey === "readyToAnalyze") return "telemetrySourceReady";
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
      primaryCtaLabel: "Analyzing",
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
      primaryCtaLabel: "Analyze New Dataset",
    };
  }
  if (analysisComplete) {
    return {
      key: "analysisComplete",
      status: ANALYSIS_COMPLETE_STATUS,
      sourceStatusLabel: "Operational assessment ready",
      storyProgressLabel: "Assessment based on selected telemetry",
      primaryCtaLabel: "Analyze New Dataset",
    };
  }
  return {
    key: "readyToAnalyze",
    status: READY_TO_ANALYZE_STATUS,
    sourceStatusLabel: telemetryConnected ? "Live telemetry connected" : "Telemetry loaded",
    storyProgressLabel: "Telemetry loaded; analysis not run",
    primaryCtaLabel: "Analyze New Dataset",
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
    uiState.key === "monitoringLive" ? "Live telemetry" : "Telemetry import"
  );
}

function deriveLastAnalysisLabel({ uiState, liveOps, snapshot, result }) {
  if (uiState.key === "noTelemetry") return "No analysis yet";
  if (uiState.key === "readyToAnalyze") return "Not analyzed yet";
  if (uiState.key === "analyzing") return "Analysis in progress";
  return formatOperationalTimestamp(firstText(snapshot?.processed_at, snapshot?.last_processed_at, result?.processed_at, result?.timestamp_profile?.last_timestamp, liveOps?.connectionSummary, "Analysis complete"));
}

function formatOperationalTimestamp(value) {
  const text = firstText(value);
  const passthrough = /^(now|pending|previous period|current period|analysis complete|no analysis yet|not analyzed yet|analysis in progress|not updated yet)$/i;
  if (!text || passthrough.test(text)) return text;
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  const dateLabel = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date);
  const timeLabel = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" }).format(date);
  return dateLabel + ", " + timeLabel;
}

function isPlaceholderResortSystem(system) {
  if (!system || typeof system !== "object") return false;
  const name = firstText(system.name, system.label, system.system_name);
  const sourceType = firstText(system.source, system.type, system.connector_type, system.connectorType, system.category, system.status).toLowerCase();
  return Boolean(
    system.placeholder
      || system.isPlaceholder
      || system.example
      || system.detected === false
      || sourceType.includes("placeholder")
      || FALLBACK_SYSTEM_NAMES.has(name.toLowerCase())
  );
}

function buildSystemSummary({ analysisComplete, identifiedSystemCount, telemetryConnected }) {
  if (!analysisComplete) {
    return {
      tabMetric: SYSTEMS_PENDING.countLabel,
      title: SYSTEMS_PENDING.title,
      label: SYSTEMS_PENDING.summary,
      countLabel: SYSTEMS_PENDING.countLabel,
      descriptor: "Waiting for telemetry",
      sectionTitle: SYSTEMS_PENDING.title,
      sectionSubtitle: SYSTEMS_PENDING.summary,
    };
  }

  const noun = identifiedSystemCount === 1 ? "system" : "systems";
  const descriptor = telemetryConnected ? "systems monitored" : "systems reviewed";
  const label = telemetryConnected
    ? `${identifiedSystemCount} ${noun} monitored`
    : `${identifiedSystemCount} ${noun} reviewed`;

  return {
    tabMetric: String(identifiedSystemCount),
    title: "Systems",
    label,
    countLabel: String(identifiedSystemCount),
    descriptor,
    sectionTitle: telemetryConnected ? "Systems Monitored" : "Operational Systems Identified",
    sectionSubtitle: "",
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

function buildBehaviorWindowRows(analysisExplanation) {
  const metadata = analysisExplanation?.analysis_metadata ?? {};
  return [
    ["Baseline window", formatBehaviorWindow(analysisExplanation?.stable_window ?? metadata.baseline_window)],
    ["Current window", formatBehaviorWindow(analysisExplanation?.current_state_window ?? analysisExplanation?.deviation_window ?? metadata.current_window)],
    ["Change onset", analysisExplanation?.change_onset],
    ["Comparison method", metadata.comparison_method ?? metadata.method],
  ];
}

function dashboardHeaderSubtitle({ analysisComplete, analysisRunning, insights, behaviorState }) {
  if (analysisRunning) return ANALYZING_STATUS.label;
  if (!analysisComplete) return EMPTY_TELEMETRY_COPY.detail;
  if (insights.length || behaviorState === "Behavior Shift Detected") return "Investigation Recommended";
  return ANALYSIS_COMPLETE_STATUS.label;
}

function deriveDashboardStatus({ uiState, analysisComplete, behaviorState, insights }) {
  if (uiState.key === "analyzing") return ANALYZING_STATUS;
  if (!analysisComplete) return NO_TELEMETRY_STATUS;
  if (insights.length > 0) return { label: "Investigation Recommended", tone: "drift", statusKey: "drift" };
  if (behaviorState === "Behavior Shift Detected") return { label: "Investigation Recommended", tone: "drift", statusKey: "drift" };
  return ANALYSIS_COMPLETE_STATUS;
}

function buildDashboardSummaryRows({ dashboardStatus, analysisComplete, identifiedSystemCount, activeInsightSystemCount, activeInsightCount, lastAnalysis, lastUpdated, telemetryConnected }) {
  if (!analysisComplete) {
    return [
      ["Connection State", "Not Connected"],
      ["Telemetry", "Waiting for telemetry"],
      ["Systems", SYSTEMS_PENDING.countLabel],
      ["Operational Fingerprint", "Pending"],
      ["Insights", "0 Insights"],
    ];
  }

  return [
    ["Operating Baseline", "Established"],
    [telemetryConnected ? "Systems Monitored" : "Operational Systems", String(identifiedSystemCount)],
    ["Systems with Active Insights", String(activeInsightSystemCount)],
    ["Active Insights", String(activeInsightCount)],
    ["Last Analysis", lastAnalysis],
    ["Data Source Updated", lastUpdated],
  ];
}

function buildDashboardSystemCards({ analysisComplete, systemCards }) {
  if (analysisComplete && systemCards.length) return systemCards;
  return [];
}

function buildPlaceholderSystemCards() {
  return [];
}

function activityDetailForInsight(insight) {
  const context = [insight?.system, insight?.summary, insightRelationshipLabels(insight).join(" ")].join(" ").toLowerCase();
  const relationships = insightRelationshipLabels(insight);
  if (relationships.length) return relationshipActivitySentence(relationships[0]);
  if (/pump|flow|pressure|valve|vfd|filter|hydraulic/.test(context)) return "Flow and pressure correlation changed.";
  if (/chemical|chlor|dose|quality|ph|orp|conductivity/.test(context)) return "Water quality relationship changed.";
  if (/cool|chill|tower|thermal|condenser/.test(context)) return "Thermal relationship changed.";
  return "Operating relationship changed.";
}

function activityTitleForInsight(insight) {
  const relationshipContext = insightRelationshipLabels(insight).join(" ").toLowerCase();
  const context = [insight?.system, insight?.summary, relationshipContext].join(" ").toLowerCase();
  if (/conductivity|chemical|chlor|dose|quality|ph|orp/.test(relationshipContext)) return "Water Quality relationship change detected";
  if (/(flow|pressure|dp|differential pressure)/.test(relationshipContext)) return "Flow and Pressure relationship change detected";
  if (/pump|valve|vfd|filter|hydraulic/.test(context)) return "Pumping System relationship change detected";
  if (/chemical|chlor|dose|quality|ph|orp|conductivity/.test(context)) return "Water Quality relationship change detected";
  if (/cool|chill|tower|thermal|condenser/.test(context)) return "Thermal System relationship change detected";
  return `${formatSubsystemName(insight?.system)} relationship change detected`;
}

function buildDashboardActivityItems({ historyItems, insights, analysisComplete, analysisRunning, lastAnalysis }) {
  if (analysisRunning) {
    return [{ id: "analysis-running", title: "Operational behavior analysis running", time: "Now", detail: "Telemetry is being evaluated against learned operating relationships." }];
  }
  if (analysisComplete) {
    const insightItems = insights.slice(0, 3).map((insight, index) => ({
      id: "insight-activity-entry-" + index,
      title: activityTitleForInsight(insight),
      time: insight.detectedAt ?? lastAnalysis,
      detail: activityDetailForInsight(insight),
    }));
    if (insightItems.length) {
      return [{
        id: "relationship-changes-detected",
        title: "Relationship Changes Detected",
        time: insights[0]?.detectedAt ?? lastAnalysis,
        detail: "Review the systems below for changes from normal operation.",
        entries: insightItems,
      }];
    }
    if (historyItems.length) return historyItems.slice(0, 3);
    return [{ id: "analysis-complete", title: "Analysis completed", time: lastAnalysis, detail: "No significant operational changes detected." }];
  }
  return [
    { id: "platform-initialized", icon: "✓", title: "Platform initialized", time: "Ready", detail: "Neraium Operational Intelligence is ready to build an operational fingerprint." },
    { id: "waiting-for-telemetry", icon: "⏳", title: "Waiting for telemetry", time: "Not Connected", detail: "Connect historical or live telemetry when the facility source is ready." },
    { id: "fingerprint-pending", icon: "○", title: "Operational Fingerprint pending", time: "Pending", detail: "The baseline will be created after the first successful telemetry analysis." },
  ];
}

function deriveLastUpdatedLabel({ liveOps, snapshot, result }) {
  return formatOperationalTimestamp(firstText(
    liveOps?.connectionSummary,
    liveOps?.lastDataHeartbeat,
    snapshot?.updated_at,
    snapshot?.last_processed_at,
    result?.updated_at,
    result?.processed_at,
    "Not updated yet"
  ));
}

function buildOverviewSummaryRows({ analysisComplete, uiState, sourceLabel, identifiedSystemCount, insights, highestSeverity, behaviorState }) {
  if (!analysisComplete) {
    return [
      ["Analysis Status", uiState.sourceStatusLabel],
      ["Telemetry Source", sourceLabel],
      ["Systems", "Not analyzed"],
      ["Insights", "Not analyzed"],
      ["Highest Severity", "Not available"],
      ["Overall Behavior State", uiState.status.label],
    ];
  }
  return [
    ["Analysis Status", "Complete"],
    ["Telemetry Source", sourceLabel],
    ["Systems", String(identifiedSystemCount)],
    ["Insights", String(insights.length)],
    ["Highest Severity", highestSeverity],
    ["Overall Behavior State", behaviorState],
  ];
}

function buildOverviewSummarySentence({ analysisComplete, insights, identifiedSystemCount, activeInsightSystemCount, behaviorState }) {
  if (!analysisComplete) return "Telemetry is ready for analysis.";
  if (insights.length > 0) {
    const activeSystems = activeInsightSystemCount || Math.min(insights.length, identifiedSystemCount || insights.length);
    if (identifiedSystemCount > 0) {
      return `${insights.length} active insight${insights.length === 1 ? "" : "s"} across ${activeSystems} of ${identifiedSystemCount} system${identifiedSystemCount === 1 ? "" : "s"}.`;
    }
    return `${insights.length} active insight${insights.length === 1 ? "" : "s"} across ${activeSystems || "available"} system${activeSystems === 1 ? "" : "s"}.`;
  }
  return behaviorState === "Stable" ? "No active insight was detected." : "Behavior changed, with no active insight selected.";
}

function countActiveInsightSystems(insights) {
  return new Set((insights ?? []).map((insight) => insight.system).filter((name) => name && name !== UNASSIGNED_SYSTEM_NAME)).size;
}

function deriveHighestSeverity({ insights, fingerprintDrift }) {
  const ranked = ["Low", "Moderate", "High"];
  const severities = insights.map((item) => normalizeSeverity(item.severity));
  if (!severities.length) return hasMeaningfulOperationalChange({ insights, fingerprintDrift }) ? "Moderate" : "Low";
  return severities.sort((left, right) => ranked.indexOf(right) - ranked.indexOf(left))[0];
}

function overallBehaviorState(fingerprintDrift) {
  const label = String(fingerprintDrift?.label ?? "").toLowerCase();
  const tone = String(fingerprintDrift?.tone ?? "").toLowerCase();
  if (tone === "changed" || tone === "investigate" || label.includes("change") || label.includes("drift")) return "Behavior Shift Detected";
  return "Stable";
}

function buildAnalysisMetadataRows({ result, snapshot, analysisExplanation }) {
  const metadata = analysisExplanation?.analysis_metadata ?? {};
  return [
    ["Analysis reference", firstText(analysisExplanation?.analysis_id, metadata.analysis_id, result?.analysis_id, result?.run_id, result?.job_id)],
    ["Analysis reference", firstText(analysisExplanation?.upload_id, metadata.upload_id, result?.upload_id, result?.job_id, snapshot?.upload_id)],
    ["Source", firstText(analysisExplanation?.source_file, result?.source_file, result?.filename, snapshot?.filename, snapshot?.current_upload?.filename)],
    ["Generated at", firstText(analysisExplanation?.generated_at, result?.completed_at, result?.last_processed_at, snapshot?.last_processed_at)],
    ["Rows", firstText(metadata.row_count, result?.row_count, snapshot?.rows_processed)],
    ["Columns", firstText(metadata.column_count, result?.column_count, snapshot?.columns_detected)],
  ];
}

function relationshipLabelFromValue(value, index = 0) {
  if (!value || typeof value !== "object") return firstText(value);
  return firstText(relationshipDisplayName(value, index), value.label, value.name, value.display_name, value.displayName);
}

function firstNonEmptyList(...values) {
  for (const value of values) {
    if (Array.isArray(value) && value.length) return value;
    if (value !== null && value !== undefined && value !== "" && !Array.isArray(value)) return [value];
  }
  return [];
}

function relationshipDisplayName(row, index = 0) {
  if (!row || typeof row !== "object") return "";
  const sourceTarget = row.source && row.target ? [row.source, row.target].map(cleanRelationshipEndpoint) : [];
  const displayColumns = firstNonEmptyList(row.display_columns, row.displayColumns, row.source_tag_display_names, row.sourceTagDisplayNames);
  const metadataColumns = toList(row.source_column_metadata, row.sourceColumnMetadata)
    .flatMap((item) => Array.isArray(item) ? item : [item])
    .filter((item) => item && typeof item === "object")
    .map((item, metadataIndex) => metricDisplayName(item, metadataIndex + 1));
  const rawColumns = firstNonEmptyList(row.columns, row.source_tags, row.sourceTags, row.supporting_metrics, row.supportingMetrics)
    .map((item, columnIndex) => metricDisplayName(item, columnIndex + 1));
  const rawLabel = firstText(row.raw_identifier, row.relationship, row.pair, rawColumns.join(" / "), sourceTarget.join(" / "));
  const displayLabel = firstText(displayColumns.join(" / "), metadataColumns.join(" / "), row.label, row.name, rawLabel);
  return publicRelationshipLabel(cleanRelationshipLabel(displayLabel), index);
}

function rawRelationshipDisplayName(row) {
  if (!row || typeof row !== "object") return "";
  const sourceTarget = row.source && row.target ? [row.source, row.target].map((item) => String(item).replace(/^tag:/, "").replace(/^metric:/, "")) : [];
  const rawColumns = Array.isArray(row.columns) ? row.columns : (Array.isArray(row.source_tags) ? row.source_tags : []);
  return cleanRelationshipLabel(firstText(row.raw_identifier, row.relationship, row.pair, rawColumns.join(" / "), sourceTarget.join(" / "), row.detail));
}

function publicRelationshipLabel(label, index = 0) {
  const clean = formatRelationshipObservedLabelRaw(label);
  if (isGenericRelationshipLabel(clean)) return `Relationship ${relationshipOrdinal(index)}`;
  return clean;
}

function cleanRelationshipEndpoint(value) {
  return String(value ?? "").replace(/^tag:/, "").replace(/^metric:/, "");
}

function relationshipOrdinal(index) {
  const safeIndex = Number.isFinite(Number(index)) ? Number(index) : 0;
  return String.fromCharCode("A".charCodeAt(0) + Math.max(0, Math.min(25, safeIndex)));
}

function isGenericRelationshipLabel(value) {
  const text = String(value ?? "").toLowerCase();
  return /\b(exogenous|numeric\s*\d+|delta\s*\d+|column\s*\d+|unknown|unnamed)\b/.test(text);
}

function buildAdvancedRelationshipDetails(rows) {
  if (!Array.isArray(rows)) return [];
  return rows
    .map((row, index) => {
      const raw = rawRelationshipDisplayName(row);
      if (!raw) return "";
      const label = relationshipDisplayName(row, index);
      if (isGenericRelationshipLabel(raw)) return "";
      return raw && raw !== label ? label + ": " + raw : "";
    })
    .filter(Boolean);
}

function suggestedInvestigationSteps({ subsystem, relationshipLabels, insight }) {
  const searchText = [subsystem, relationshipLabels.join(" "), insight?.summary].join(" ").toLowerCase();
  if (/flow|pressure|pump|valve|vfd|filter|hydraulic/.test(searchText)) {
    return [
      "Review recent maintenance activity and operator logs for changes affecting flow or pressure.",
      "Inspect filter condition and differential pressure trends for signs of fouling.",
      "Verify current pump loading and operating point against the expected performance curve.",
      "Review operating setpoints, valve positions, and VFD commands for this load condition.",
      "Compare current flow and pressure response with historical operation.",
    ];
  }
  if (/chemical|chlor|dose|feed|quality|ph|orp/.test(searchText)) {
    return [
      "Check chemical feed trends for dosing instability or step changes.",
      "Confirm dosing setpoints and feed pump status match the current treatment objective.",
      "Compare water quality readings against the normal operating range.",
      "Review recent chemical deliveries, dilution changes, and operator logs.",
      "Verify control commands match the expected treatment response.",
    ];
  }
  if (/thermal|cooling|heat|chiller|condenser|tower/.test(searchText)) {
    return [
      "Check heat-transfer and approach-temperature trends for fouling or degraded rejection.",
      "Confirm equipment staging and operating point match the current load.",
      "Compare flow, valve position, and temperature response against historical operation.",
      "Review recent maintenance, weather, and load changes that could explain the shift.",
      "Verify control commands match the expected cooling response.",
    ];
  }
  return [
    actionizeRecommendation(firstText(insight?.operatorCheck, insight?.recommendedAction, "Review the contributing signal trends.")),
    "Confirm current operating mode and setpoints match the intended sequence.",
    "Compare equipment states against historical operation for the same load condition.",
    "Review recent maintenance and operator logs for changes near the start of the shift.",
    "Monitor the next operating window to confirm whether the change persists.",
  ];
}

function normalizeSystemStatus(value) {
  const text = firstText(value).toLowerCase();
  if (text.includes("critical") || text.includes("unstable")) return "Critical";
  if (text.includes("review") || text.includes("attention") || text.includes("changed") || text.includes("drift") || text.includes("shift")) return "Investigation Recommended";
  if (text.includes("advisory") || text.includes("watch") || text.includes("warning")) return "Advisory";
  if (text.includes("normal") || text.includes("stable") || text.includes("baseline")) return "Normal";
  if (text.includes("connected") || text.includes("monitor")) return "Normal";
  return firstText(value, "Normal");
}

function operationalStateForSystem(activeInsightCount, topInsight, rawStatus) {
  if (activeInsightCount <= 0) return normalizeSystemStatus(rawStatus);
  const severity = normalizeSeverity(topInsight?.severity);
  if (severity === "High") return "Critical";
  if (severity === "Moderate") return "Investigation Recommended";
  return "Advisory";
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
      const name = formatDisplayName(firstText(system.name, system.label), "System " + (index + 1));
      return {
        ...system,
        id: system.id ?? system.name ?? "system-" + index,
        name,
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
      ...system,
      id: system.id ?? system.name ?? system.label ?? `system-${index}`,
      name: formatDisplayName(firstText(system.name, system.label, system.system_name), `System ${index + 1}`),
    }));
  }
  return [{ id: "primary", name: formatDisplayName(primarySystem, UNASSIGNED_SYSTEM_NAME) }];
}

function resolveEvidenceRefs(item, analysisExplanation) {
  const index = analysisExplanation?.evidence_index ?? {};
  const refs = Array.isArray(item?.evidence_refs) ? item.evidence_refs : [];
  return refs
    .map((ref) => index?.[ref])
    .filter((entry) => entry && typeof entry === "object");
}

function summarizeEvidence(items) {
  return formatEvidenceItems(items).slice(0, 4).join("; ");
}

function resolveMetricName(insight, index = 0) {
  const direct = firstText(
    insight?.metric_name,
    insight?.metricName,
    insight?.metric,
    insight?.signal,
    insight?.source_metric,
    insight?.sourceMetric,
    insight?.source_tag,
    insight?.sourceTag
  );
  const fromMetric = Array.isArray(insight?.contributing_metrics) ? insight.contributing_metrics.map((item, metricIndex) => normalizeSignalName(item, metricIndex + 1)).find(Boolean) : "";
  const fromRelationship = toList(insight?.contributing_relationships)
    .flatMap(relationshipSignalCandidates)
    .map((item, signalIndex) => normalizeSignalName(item, signalIndex + 1))
    .find(Boolean);
  return normalizeSignalName(direct || fromMetric || fromRelationship, index + 1) || `Metric ${index + 1}`;
}

function firstMetricValue(metrics, key) {
  const metric = Array.isArray(metrics) ? metrics.find((item) => item && typeof item === "object") : null;
  if (!metric) return "";
  if (key === "baseline") return firstText(metric.baseline_value, metric.baselineValue, metric.baseline_range, metric.baselineRange, metric.baseline_average, metric.baselineAverage, metric.baseline);
  if (key === "current") return firstText(metric.current_value, metric.currentValue, metric.current_average, metric.currentAverage, metric.current);
  if (key === "direction") return firstText(metric.deviation_direction, metric.direction, metric.trend);
  return "";
}

function relationshipSignalCandidates(value) {
  if (!value || typeof value !== "object") return [value];
  return [
    ...toList(value.display_columns, value.displayColumns, value.source_tag_display_names, value.sourceTagDisplayNames),
    ...toList(value.columns, value.source_columns, value.sourceColumns, value.source_tags, value.sourceTags, value.supporting_metrics, value.supportingMetrics),
    ...toList(value.source, value.target),
    ...toList(value.source_column_metadata, value.sourceColumnMetadata).map((item, index) => metricDisplayName(item, index + 1)),
  ];
}

function buildInsights({ finding, liveOps, result, primarySystem, telemetryStatus, lastAnalysis, analysisExplanation, systems = [], signals = [] }) {
  const explanatoryInsights = Array.isArray(analysisExplanation?.insights) ? analysisExplanation.insights : [];
  if (explanatoryInsights.length > 0) {
    const insights = explanatoryInsights.map((item, index) => {
      const resolvedEvidence = resolveEvidenceRefs(item, analysisExplanation);
      const evidence = resolvedEvidence.length ? resolvedEvidence : toList(item.evidence_items, item.evidence);
      const contributingRelationships = Array.isArray(item.contributing_relationships) ? item.contributing_relationships : [];
      const affectedRelationships = relationshipContributionLabels(contributingRelationships);
      const insight = {
        id: normalizeInsightId(item, index),
        rawSystemName: firstText(item.system, toList(item.affected_systems)[0], primarySystem),
        status: normalizeInsightStatus(item.status ?? item.severity),
        severity: normalizeSeverity(item.severity),
        rawSummary: firstText(item.title, item.explanation),
        whatHappened: operatorText(item.what_happened, item.what_changed, item.whatChanged, item.explanation),
        whyItMatters: operatorText(item.why_it_matters, item.possible_operational_consequence, item.possible_consequence, item.possibleConsequence, item.likely_cause, item.why_neraium_thinks_it_happened, item.why_neraium_thinks, item.likelyCause),
        whyNeraiumThinks: operatorText(item.why_neraium_thinks_it_happened, item.why_neraium_thinks, item.likely_cause, item.why_it_matters, item.likelyCause),
        possibleConsequence: operatorText(item.possible_operational_consequence, item.possible_consequence, item.possibleConsequence),
        recommendedAction: operatorText(firstDistinctText(firstText(item.operator_check, item.recommended_operator_check, item.recommended_check), item.recommended_action, item.recommendedAction, item.recommendation, item.recommended_check)),
        operatorCheck: operatorText(item.operator_check, item.operatorCheck, item.recommended_operator_check, item.recommended_check),
        possibleOperationalCauses: dedupeText(toList(item.possible_operational_causes, item.possibleOperationalCauses, item.possible_operational_causes_summary).flatMap(splitPriorityText).map(operatorText)),
        contributingFactors: dedupeText(toList(item.likely_contributors, item.contributing_factors, item.contributingFactors, item.source_tags).flatMap(formatEvidenceItems)),
        contributingRelationships,
        affectedRelationships,
        changedRelationshipCount: numberOrNull(item.changed_relationship_count ?? item.changedRelationshipCount) ?? affectedRelationships.length,
        contributingMetrics: Array.isArray(item.contributing_metrics) ? item.contributing_metrics : [],
        metricName: resolveMetricName(item, index),
        baselineValue: firstText(item.baseline_value, item.baselineValue, item.baseline_range, item.baselineRange, item.baseline, firstMetricValue(item.contributing_metrics, "baseline")),
        currentValue: firstText(item.current_value, item.currentValue, item.current, firstMetricValue(item.contributing_metrics, "current")),
        deviationDirection: formatDisplayName(firstText(item.deviation_direction, item.direction, firstMetricValue(item.contributing_metrics, "direction"))),
        evidence,
        publicEvidenceItems: formatEvidenceItems(evidence.length ? evidence : item.evidence_summary),
        hasEvidence: evidence.length > 0,
        evidenceSummary: operatorEvidenceSummary(item.evidence_summary, summarizeEvidence(resolvedEvidence)),
        sourceTimeRanges: Array.isArray(item.source_time_ranges) ? item.source_time_ranges : [],
        confidence: item.confidence,
        confidenceScore: item.confidence_score,
        confidenceRationale: operatorText(item.confidence_rationale),
        telemetryNote: telemetryStatus.detail,
        detectedAt: lastAnalysis,
        type: getInsightType(item),
      };
      insight.system = resolveSystemName(insight, systems, signals);
      insight.summary = formatInsightTitle(insight);
      return insight;
    }).filter((item) => item.summary);
    return dedupeInsights(insights).slice(0, 8);
  }

  const rawFindings = [];
  if (finding?.exists || finding?.summary || finding?.title) rawFindings.push(finding);
  if (Array.isArray(liveOps?.findings)) rawFindings.push(...liveOps.findings);

  const insights = rawFindings
    .filter(Boolean)
    .map((item, index) => {
      const summary = firstText(item.summary, item.detail, item.title, result?.operator_report?.summary);
      const supporting = formatEvidenceItems(toList(item.supportingEvidence, item.relationshipEvidence, result?.operator_report?.evidence_summary, result?.finding_evidence_chains));
      const evidence = supporting.length ? [{ supporting_signals: supporting }] : [];
      const insight = {
        id: normalizeInsightId(item, index),
        rawSystemName: firstText(item.label, item.affectedSubsystem, item.affected_system, primarySystem),
        status: normalizeInsightStatus(item.status ?? result?.operating_state),
        severity: normalizeSeverity(item.confidence ?? result?.drift_status),
        rawSummary: summary,
        whatHappened: operatorText(summary),
        whyItMatters: operatorText(item.whyItMatters, item.possibleConsequence),
        whyNeraiumThinks: operatorText(item.whyItMatters),
        possibleConsequence: operatorText(item.possibleConsequence),
        recommendedAction: operatorText(item.recommendation, item.reviewNext),
        operatorCheck: operatorText(item.operator_focus),
        possibleOperationalCauses: dedupeText(toList(item.possibleOperationalCauses, item.possible_operational_causes).flatMap(splitPriorityText).map(operatorText)),
        contributingRelationships: Array.isArray(item.contributing_relationships) ? item.contributing_relationships : [],
        affectedRelationships: relationshipContributionLabels(item.contributing_relationships),
        changedRelationshipCount: numberOrNull(item.changed_relationship_count ?? item.changedRelationshipCount),
        contributingMetrics: Array.isArray(item.contributing_metrics) ? item.contributing_metrics : [],
        metricName: resolveMetricName(item, index),
        baselineValue: firstText(item.baseline_value, item.baselineValue, item.baseline_range, item.baselineRange, item.baseline),
        currentValue: firstText(item.current_value, item.currentValue, item.current),
        deviationDirection: formatDisplayName(firstText(item.deviation_direction, item.direction)),
        evidence,
        publicEvidenceItems: supporting,
        hasEvidence: evidence.length > 0,
        telemetryNote: telemetryStatus.detail,
        detectedAt: lastAnalysis,
        type: getInsightType(item),
      };
      insight.system = resolveSystemName(insight, systems, signals);
      insight.summary = formatInsightTitle(insight);
      return insight;
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
      id: "behavior",
      title: "Behavior evidence",
      system: "Operating behavior",
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

function buildSystemOperationalSummary({ activeInsightCount, topInsight, relationships }) {
  if (activeInsightCount <= 0) return "No active operational changes require review.";
  const relationship = relationships[0] ?? insightRelationshipLabels(topInsight).slice(0, 1)[0];
  if (relationship) return relationshipBriefingSentence(relationship);
  const summary = conciseOperatorSentence(topInsight?.whatHappened, topInsight?.rawSummary, topInsight?.summary);
  return summary || "Current operation no longer matches the expected baseline.";
}

function buildSystemCards({ systems, primarySystem, insights }) {
  const safeSystems = Array.isArray(systems) && systems.length > 0
    ? systems.map((system, index) => ({ ...system, id: system.id ?? system.name ?? "system-" + index, name: formatDisplayName(firstText(system.name, system.label, system.system_name), "System " + (index + 1)) }))
    : [{ id: "primary", name: formatDisplayName(primarySystem, UNASSIGNED_SYSTEM_NAME) }];

  const cards = safeSystems.map((system) => {
    const relatedInsights = insights.filter((item) => item.system === system.name || safeSystems.length === 1);
    const activeInsightCount = relatedInsights.length;
    const rawStatus = firstText(system.health_status, system.status, "Stable");
    const relationships = relationshipContributionLabels(toList(system.relationships, system.relationship_summary));
    const topInsight = relatedInsights[0] ?? null;
    return {
      id: system.id,
      name: system.name,
      status: operationalStateForSystem(activeInsightCount, topInsight, rawStatus),
      scope: firstText(system.scope, system.description, "Detected from analyzed telemetry."),
      activeInsights: String(activeInsightCount),
      severity: activeInsightCount ? (topInsight?.severity ?? "Moderate") : "",
      hasActiveIssue: activeInsightCount > 0,
      relationshipDrift: activeInsightCount ? "Operating relationship changed" : "No active change",
      keyChangedRelationship: relationships[0] ?? insightRelationshipLabels(topInsight).slice(0, 1)[0] ?? "",
      operationalSummary: buildSystemOperationalSummary({ activeInsightCount, topInsight, relationships }),
      primaryInsightId: topInsight?.id ?? null,
      placeholder: false,
    };
  });
  return dedupeSystemCards(cards);
}

function collectQuality(result, snapshot) {
  const dataQuality = result?.analysis_result?.data_quality ?? result?.data_quality ?? {};
  const timestampProfile = result?.timestamp_profile ?? {};
  const qualityMetrics = dataQuality?.quality_metrics ?? result?.ingestion_report ?? {};
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
    rowsDropped: numberOrNull(qualityMetrics.rows_dropped ?? qualityMetrics.rowsDropped),
    rowsReceived: numberOrNull(qualityMetrics.rows_received ?? qualityMetrics.rowsReceived),
    rowsUsed: numberOrNull(qualityMetrics.rows_used ?? qualityMetrics.rowsUsed),
    invalidNumericRows: numberOrNull(qualityMetrics.rows_with_invalid_numeric ?? qualityMetrics.rowsWithInvalidNumeric),
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
  const fingerprintDetail = operatorText(fingerprint.meaning, fingerprint.explanation, fingerprint.plain_language_explanation);
  if (analysisComplete && (fingerprintDetail || fingerprint.drift_status || fingerprint.status)) {
    const driftStatus = String(fingerprint.drift_status ?? fingerprint.status ?? "").toLowerCase();
    const changed = driftStatus === "changed" || driftStatus === "drifting" || driftStatus === "review" || driftStatus === "unstable";
    return {
      label: changed ? "Changed" : "Stable",
      tone: changed ? "changed" : "normal",
      detail: fingerprintDetail || (changed ? "Operating behavior changed." : "Current behavior is stable."),
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
      detail: "Behavior comparison will populate after analysis completes.",
    };
  }
  const magnitudes = relationshipRows.map((row) => Math.abs(Number(row.percent_change ?? row.absolute_change ?? row.pair_weight ?? row.change ?? 0))).filter(Number.isFinite);
  const max = magnitudes.length ? Math.max(...magnitudes) : 0;
  if (max > 30 || hasFinding || String(result?.drift_status ?? "").toLowerCase().includes("unstable")) {
    return { label: "Significant Change", tone: "investigate", detail: "Current behavior is materially different from normal operation." };
  }
  if (max > 10 || String(result?.drift_status ?? "").toLowerCase().includes("review")) {
    return { label: "Drifting", tone: "changed", detail: "Current behavior is moving away from normal operation." };
  }
  return { label: "Stable", tone: "normal", detail: "Current behavior is stable." };
}

function buildSignals(result) {
  const columns = Array.isArray(result?.columns) ? result.columns : [];
  const detected = Array.isArray(result?.detected_columns) ? result.detected_columns : [];
  const normalizedTags = Array.isArray(result?.analysis_result?.normalized_telemetry?.tags)
    ? result.analysis_result.normalized_telemetry.tags.map((tag) => tag.display_name ?? tag.tag_name ?? tag.original_header)
    : [];
  return dedupeDisplayValues([...columns, ...detected, ...normalizedTags].map((item, index) => normalizeSignalName(item, index + 1)), signalDisplayKey).slice(0, 24);
}

function buildHistoryItems({ liveOps, snapshot, result, insights, analysisComplete }) {
  const items = [];
  const previous = Array.isArray(liveOps?.previousUploadHistory) ? liveOps.previousUploadHistory : [];
  previous.slice(0, 8).forEach((entry, index) => {
    items.push({
      id: `previous-${index}`,
      title: entry.filename ?? entry.job_id ?? "Previous analysis",
      time: formatOperationalTimestamp(entry.last_processed_at ?? entry.processed_at ?? "Previous period"),
      detail: "Previous telemetry analysis available for review.",
    });
  });
  if (analysisComplete && (snapshot?.processed_at || result?.processed_at || result?.last_processed_at || result?.completed_at)) {
    items.unshift({
      id: "current-analysis",
      title: insights.length ? "Current insight generated" : "Current analysis completed",
      time: formatOperationalTimestamp(snapshot?.processed_at ?? result?.processed_at ?? result?.last_processed_at ?? result?.completed_at ?? "Current period"),
      detail: insights[0]?.summary ? `Top finding: ${insights[0].summary}` : "Current telemetry was analyzed for system behavior changes.",
    });
  }
  return items;
}


function InsightList({ insights, empty, emptyTitle = "No active insights", onOpenInsight, selectedId }) {
  if (!insights.length) return <EmptyOperationalState title={emptyTitle} body={empty} />;
  return (
    <div className="insight-feed insight-feed--cards">
      {insights.map((insight) => {
        const selected = selectedId === insight.id;
        const title = formatInsightTitle(insight);
        const relationships = insightRelationshipLabels(insight).slice(0, 8);
        const summary = operatorSummaryBriefing(insight, relationships)[0] || title;
        const rows = insightCardRows(insight, relationships);
        return (
          <article
            key={insight.id}
            className={selected ? "insight-card insight-card--compact is-selected" : "insight-card insight-card--compact"}
            aria-current={selected ? "true" : undefined}
          >
            <div className="insight-card__header">
              <span className="section-token">{formatSubsystemName(insight.system)}</span>
              <div className="insight-card__badges">
                <LabeledStatusChip label="Severity" value={insight.severity} tone={severityToTone(insight.severity)} />
                <LabeledStatusChip label="Confidence" value={formatConfidenceLevel(insight.confidence, insight.confidenceScore)} tone="unknown" />
              </div>
            </div>
            <h3>{title}</h3>
            <DetailGrid rows={rows} />
            <p className="insight-card__summary">{summary}</p>
            <button type="button" className="secondary-command-button insight-card__open" onClick={() => onOpenInsight?.(insight.id)}>Open Insight</button>
          </article>
        );
      })}
    </div>
  );
}

function InsightDetail({ insight }) {
  const relationships = insightRelationshipLabels(insight).slice(0, 8);
  const causes = rankedOperationalCauses(insight);
  const evidenceSummary = prioritizedEvidenceMetrics(insight);
  const relationshipEvidence = evidenceBriefing(insight, relationships);
  const technicalEvidence = technicalEvidenceBriefing(insight, relationships);

  return (
    <details className="insight-detail-card" aria-label="Insight detail">
      <summary>Insight detail</summary>

      <div className="insight-briefing__header">
        <span className="section-token">
          {formatSubsystemName(insight.system)}
        </span>

        <h3>{formatInsightTitle(insight)}</h3>
      </div>

      <dl
        className="insight-briefing__status"
        aria-label="Insight status"
      >
        <div>
          <dt>Severity</dt>
          <dd>
            <StatusBadge
              label={insight.severity}
              tone={severityToTone(insight.severity)}
            />
          </dd>
        </div>

        <div>
          <dt>Confidence</dt>
          <dd>
            <StatusBadge
              label={formatConfidenceLevel(
                insight.confidence,
                insight.confidenceScore
              )}
              tone="unknown"
            />
          </dd>
        </div>
      </dl>

      <BriefingTextBlock
        title="What Changed"
        lines={operatorSummaryBriefing(
          insight,
          relationships
        )}
      />

      <BriefingTextBlock
        title="Why It Matters"
        lines={whyItMattersBriefing(insight)}
      />

      <BriefingList
        title="Evidence"
        items={relationshipEvidence}
        limit={8}
      />

      <EvidenceMetricCards
        title="Evidence Metrics"
        metrics={evidenceSummary}
      />

      <RankedCauseList causes={causes} />

      <BriefingList
        title="Recommended Actions"
        items={recommendedReviewItems(
          insight,
          relationships
        )}
        limit={6}
      />

      {technicalEvidence.length || insight.hasEvidence ? (
        <InsightEvidenceDrawer insight={insight} summaryItems={technicalEvidence} />
      ) : null}
    </details>
  );
}

function insightCardRows(insight, relationships) {
  const type = getInsightType(insight);
  if (type === "relationship_shift") {
    return [
      ["Key relationship", relationships[0]],
      shouldShowRelationshipCount(insight) ? ["Changed relationships", String(insight.changedRelationshipCount ?? relationships.length)] : null,
    ];
  }
  if (type === "metric_deviation") {
    return [
      ["Metric", normalizeSignalName(insight.metricName)],
      ["Baseline value/range", insight.baselineValue],
      ["Current value", insight.currentValue],
      ["Deviation direction", insight.deviationDirection],
    ];
  }
  return relationships.length ? [["Key relationship", relationships[0]]] : [];
}

function evidenceBriefing(insight, relationships = []) {
  const evidenceItems = Array.isArray(insight?.evidence)
    ? insight.evidence
    : [];

  if (relationships.length > 0) {
    return relationships
      .map((relationship, index) => {
        const relationshipName =
          formatRelationshipObservedLabel(relationship, index);

        const evidence = evidenceItems[index];

        const quantitativeSummary =
          relationshipEvidenceSummary(evidence);

        if (quantitativeSummary) {
          return `${relationshipName}: ${quantitativeSummary}`;
        }

        const fallbackEvidence =
          firstReadableEvidenceText(evidence);

        if (fallbackEvidence) {
          return `${relationshipName}: ${fallbackEvidence}`;
        }

        return `${relationshipName}: change detected, but no quantitative measurement was included in this result.`;
      })
      .filter(Boolean)
      .slice(0, 8);
  }

  const direct = formatEvidenceItems(
    insight.publicEvidenceItems
  )
    .map(cleanEvidenceText)
    .filter(Boolean);

  if (direct.length) {
    return direct.slice(0, 8);
  }

  return briefingSentences(
    firstText(
      insight.evidenceSummary,
      insight.whyNeraiumThinks,
      insight.whyItMatters
    ),
    3
  );
}

function prioritizedEvidenceMetrics(insight) {
  const rows = [
    {
      label: "Baseline average",
      value: firstEvidenceMetricValue(insight, "baseline_average", "baselineAverage", "baseline_value", "baselineValue", "baseline_strength", "baselineStrength", "baseline_coupling", "baselineCoupling", "baseline"),
      fallback: insight?.baselineValue,
    },
    {
      label: "Current average",
      value: firstEvidenceMetricValue(insight, "current_average", "currentAverage", "recent_average", "recentAverage", "current_value", "currentValue", "current_strength", "currentStrength", "current_coupling", "currentCoupling", "current"),
      fallback: insight?.currentValue,
    },
    {
      label: "Percent change",
      value: firstEvidenceMetricValue(insight, "percent_change", "percentChange", "calculated_percent_delta", "calculatedPercentDelta", "correlation_delta", "correlationDelta", "coupling_delta", "couplingDelta"),
      suffix: "%",
    },
    {
      label: "Persistence score",
      value: firstEvidenceMetricValue(insight, "persistence_score", "persistenceScore", "confidence_score", "confidenceScore"),
      fallback: insight?.confidenceScore,
    },
  ];

  return rows
    .map((row) => {
      const value = firstText(row.value, row.fallback);
      if (!hasDisplayValue(value)) return null;
      return {
        label: row.label,
        value: formatEvidenceMetricValue(value, row.suffix),
      };
    })
    .filter(Boolean);
}

function firstEvidenceMetricValue(insight, ...keys) {
  const sources = [
    insight,
    ...(Array.isArray(insight?.contributingMetrics) ? insight.contributingMetrics : []),
    ...(Array.isArray(insight?.evidence) ? insight.evidence : []),
  ];

  for (const source of sources) {
    const value = findMetricValue(source, keys);
    if (hasDisplayValue(value)) return value;
  }

  return "";
}

function findMetricValue(value, keys) {
  if (!value || typeof value !== "object") return "";

  for (const key of keys) {
    if (hasDisplayValue(value[key])) return value[key];
  }

  const nestedKeys = [
    "metric_delta",
    "metricDelta",
    "relevant_metric_changes",
    "relevantMetricChanges",
    "relationship_delta",
    "relationshipDelta",
  ];

  for (const nestedKey of nestedKeys) {
    const nested = value[nestedKey];
    if (Array.isArray(nested)) {
      for (const item of nested) {
        const found = findMetricValue(item, keys);
        if (hasDisplayValue(found)) return found;
      }
    } else {
      const found = findMetricValue(nested, keys);
      if (hasDisplayValue(found)) return found;
    }
  }

  return "";
}

function formatEvidenceMetricValue(value, suffix = "") {
  const number = numberOrNull(value);
  if (number === null) return renderDisplayValue(value);
  return suffix === "%" ? `${formatEvidenceNumber(number)}%` : formatEvidenceNumber(number);
}

function technicalEvidenceBriefing(insight, relationships = []) {
  const items = [
    ...relationships.map((relationship, index) => `Signal identifiers: ${formatRelationshipObservedLabel(relationship, index)}`),
    ...toList(insight?.metricName).map((item) => `Internal metric name: ${normalizeSignalName(item) || displayText(item)}`),
    ...evidenceBriefing(insight, relationships).map((item) => `Raw evidence: ${item}`),
    ...toList(insight?.confidenceRationale).map((item) => `Diagnostic metadata: ${cleanBriefingText(item)}`),
  ];

  return dedupeText(items).filter(Boolean);
}

function EvidenceMetricCards({ title, metrics }) {
  const visibleMetrics = toList(metrics)
    .filter((item) => item?.label && hasDisplayValue(item?.value))
    .slice(0, 4);
  if (!visibleMetrics.length) return null;
  return (
    <section className="insight-briefing__section insight-briefing__section--evidence">
      <h4>{title}</h4>
      <dl className="evidence-metric-cards">
        {visibleMetrics.map((item) => (
          <div className="evidence-metric-card" key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function RankedCauseList({ causes }) {
  const mostLikely = toList(causes?.mostLikely).slice(0, 3);
  const otherPossibilities = toList(causes?.otherPossibilities).slice(0, 5);
  if (!mostLikely.length && !otherPossibilities.length) return null;
  return (
    <section className="insight-briefing__section insight-briefing__section--causes">
      <h4>Possible Causes</h4>
      {mostLikely.length ? <CauseGroup title="Most Likely" items={mostLikely} featured /> : null}
      {otherPossibilities.length ? <CauseGroup title="Other Possibilities" items={otherPossibilities} /> : null}
    </section>
  );
}

function CauseGroup({ title, items, featured = false }) {
  return (
    <div className={featured ? "cause-group cause-group--featured" : "cause-group"}>
      <h5>{title}</h5>
      <ul className="operator-briefing-list">
        {items.map((item) => <li key={item}>{cleanBriefingText(item)}</li>)}
      </ul>
    </div>
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
function firstReadableEvidenceText(evidence) {
  if (!evidence || typeof evidence !== "object") {
    return "";
  }

  const candidates = [
    evidence.description,
    evidence.summary,
    evidence.what_changed,
    evidence.whatChanged,
  ];

  for (const candidate of candidates) {
    const text = cleanEvidenceText(candidate);

    if (text) {
      return text;
    }
  }

  const supportingSignals = formatEvidenceItems(
    toList(
      evidence.supporting_signals,
      evidence.supportingSignals
    )
  )
    .map(cleanEvidenceText)
    .filter(Boolean);

  if (supportingSignals.length > 0) {
    return supportingSignals.join("; ");
  }

  return "";
}

function cleanEvidenceText(value) {
  return cleanBriefingText(value)
    .replace(/^\s*[;,]+\s*/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function relationshipEvidenceSummary(evidence) {
  const measurement =
    extractRelationshipMeasurement(evidence);

  if (!measurement) {
    return "";
  }

  const { baseline, current, delta } =
    measurement;

  const interpretation =
    interpretCouplingChange(
      baseline,
      current
    );

  const changeMagnitude =
    delta !== null
      ? ` Overall change magnitude: ${formatEvidenceNumber(
          Math.abs(delta)
        )}.`
      : "";

  return (
    `Unitless coupling score changed from ` +
    `${formatEvidenceNumber(baseline)} to ` +
    `${formatEvidenceNumber(current)}; ` +
    `${interpretation}.${changeMagnitude}`
  );
}

function extractRelationshipMeasurement(evidence) {
  if (!evidence || typeof evidence !== "object") {
    return null;
  }

  const candidates = [];

  appendMeasurementCandidates(
    candidates,
    evidence.metric_delta
  );

  appendMeasurementCandidates(
    candidates,
    evidence.relevant_metric_changes
  );

  appendMeasurementCandidates(
    candidates,
    evidence.relevantMetricChanges
  );

  appendMeasurementCandidates(
    candidates,
    evidence.relationship_delta
  );

  appendMeasurementCandidates(
    candidates,
    evidence.relationshipDelta
  );

  for (const candidate of candidates) {
    if (
      !candidate ||
      typeof candidate !== "object"
    ) {
      continue;
    }

    const baseline = numberOrNull(
      candidate.baseline_strength ??
        candidate.baselineStrength ??
        candidate.baseline_coupling ??
        candidate.baselineCoupling
    );

    const current = numberOrNull(
      candidate.current_strength ??
        candidate.currentStrength ??
        candidate.current_coupling ??
        candidate.currentCoupling
    );

    if (
      baseline === null ||
      current === null
    ) {
      continue;
    }

    const delta = numberOrNull(
      candidate.correlation_delta ??
        candidate.correlationDelta ??
        candidate.coupling_delta ??
        candidate.couplingDelta
    );

    return {
      baseline,
      current,
      delta,
    };
  }

  return null;
}

function appendMeasurementCandidates(
  destination,
  value
) {
  if (Array.isArray(value)) {
    value.forEach((item) => {
      appendMeasurementCandidates(
        destination,
        item
      );
    });

    return;
  }

  if (value && typeof value === "object") {
    destination.push(value);
  }
}

function interpretCouplingChange(
  baseline,
  current
) {
  const baselineSign = Math.sign(baseline);
  const currentSign = Math.sign(current);

  if (
    baselineSign !== 0 &&
    currentSign !== 0 &&
    baselineSign !== currentSign
  ) {
    return "the relationship reversed direction";
  }

  const strengthChange =
    Math.abs(baseline) - Math.abs(current);

  if (strengthChange >= 0.5) {
    return "the relationship weakened sharply toward little linear coupling";
  }

  if (strengthChange >= 0.2) {
    return "the relationship weakened materially";
  }

  if (strengthChange > 0.05) {
    return "the relationship weakened";
  }

  if (strengthChange <= -0.2) {
    return "the relationship strengthened materially";
  }

  if (strengthChange < -0.05) {
    return "the relationship strengthened";
  }

  return "the relationship remained similar in strength";
}

function formatEvidenceNumber(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "Not available";
  }

  return number.toFixed(2);
}

function formatQuantitativeValue(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return displayText(value);
  }

  return formatEvidenceNumber(number);
}

function BriefingList({ title, items, limit = 6, codeItems = false }) {
  const visibleItems = dedupeText(toList(items).map(codeItems ? displayText : cleanBriefingText)).slice(0, limit);
  if (!visibleItems.length) return null;
  return (
    <section className="insight-briefing__section">
      <h4>{title}</h4>
      <ul className={codeItems ? "operator-briefing-list operator-briefing-list--code" : "operator-briefing-list"}>
        {visibleItems.map((item) => <li key={item}>{codeItems ? <code>{item}</code> : item}</li>)}
      </ul>
    </section>
  );
}

function InsightEvidenceDrawer({ insight, summaryItems = [] }) {
  const evidenceItems = Array.isArray(insight.evidence) ? insight.evidence : [];
  const diagnosticRows = [
    ["Insight identifier", insight.id],
    ["Signal identifier", insight.metricName],
    ["Internal metric names", insight.contributingMetrics],
    ["Diagnostic metadata", insight.confidenceRationale],
  ];
  if (!evidenceItems.length && !summaryItems.length) return null;
  return (
    <details className="insight-evidence-drawer">
      <summary>Technical Details</summary>
      <div className="insight-evidence-drawer__body">
        {summaryItems.length ? <BriefingList title="Raw evidence" items={summaryItems} limit={10} codeItems /> : null}
        <DetailGrid rows={diagnosticRows} technical />
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
      <summary>Technical Details</summary>
      <EvidenceDetails evidence={evidence} />
    </details>
  );
}

function EvidenceDetails({ evidence }) {
  const supportingSignals = formatEvidenceItems(toList(evidence.description, evidence.supporting_signals, evidence.supportingSignals));
  const metricChanges = formatEvidenceItems(toList(evidence.metric_delta, evidence.relevant_metric_changes, evidence.relevantMetricChanges).flatMap(formatEvidenceDelta));
  const sourceColumns = toList(evidence.source_columns, evidence.sourceColumns, evidence.source_metrics, evidence.sourceMetrics, evidence.source_tags, evidence.sourceTags).flatMap(formatEvidenceItems).map((item, index) => normalizeSignalName(item, index + 1));
  const sourceRanges = Array.isArray(evidence.source_time_ranges) ? evidence.source_time_ranges.map(formatEvidenceRange).filter(Boolean) : [];
  return (
    <div className="evidence-details-body">
      <DetailGrid rows={[
        ["Summary", operatorText(evidence.description, evidence.summary)],
        ["Confidence", formatConfidenceDisplay(evidence.confidence, evidence.confidence_score)],
        ["Time window", evidence.time_window ?? evidence.timeWindow],
        ["Persistence / duration", evidence.persistence_duration ?? evidence.persistenceDuration],
        ["Calculated change", evidence.calculated_delta ?? evidence.calculatedDelta],
        ["Relationship measurements", evidence.relationship_delta],
        ["Calculated percent change", evidence.calculated_percent_delta ?? evidence.calculatedPercentDelta],
        ["Analysis reference", evidence.source_upload_id ?? evidence.upload_id],
        ["Analysis reference", evidence.analysis_id],
        ["Signal identifiers", toList(evidence.source_columns, evidence.sourceColumns, evidence.source_metrics, evidence.sourceMetrics, evidence.source_tags, evidence.sourceTags)],
        ["Internal metric names", toList(evidence.metric_delta, evidence.relevant_metric_changes, evidence.relevantMetricChanges)],
        ["Raw evidence", evidence],
      ]} technical />
      {sourceColumns.length ? <QualityList title="Source signals" items={sourceColumns} empty="" /> : null}
      {sourceRanges.length ? <QualityList title="Source time ranges" items={sourceRanges} empty="" /> : null}
      {supportingSignals.length ? <QualityList title="Supporting signals" items={supportingSignals} empty="" /> : null}
      {metricChanges.length ? <QualityList title="Relevant metric changes" items={metricChanges} empty="" /> : null}
    </div>
  );
}

function compactJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function hasDisplayValue(value) {
  if (value === "") return false;
  if (Array.isArray(value)) return value.some((item) => hasDisplayValue(item));
  return true;
}

function renderDisplayValue(value, options = {}) {
  if (value === null || value === undefined) return "Not available";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value.trim() || "Not available";
  if (Array.isArray(value)) {
    const items = value.map((item) => displayText(item)).filter(Boolean);
    return items.length ? items.join(", ") : "Not available";
  }
  if (isPlainObject(value)) {
    if (options.technical) return <TechnicalValue value={value} />;
    return plainObjectSummary(value) || "Details available in Advanced Details";
  }
  return displayText(value) || "Not available";
}

function TechnicalValue({ value }) {
  const entries = Object.entries(value ?? {})
    .filter(([, entryValue]) => hasDisplayValue(entryValue))
    .slice(0, 16);
  if (!entries.length) return <span>Not available</span>;
  return (
    <div className="technical-value" aria-label="Technical values">
      {entries.map(([key, entryValue]) => (
        <div key={key}>
          <code>{formatTechnicalKey(key)}</code>
          <span>{isPlainObject(entryValue) || Array.isArray(entryValue) ? <code>{compactJson(entryValue)}</code> : renderDisplayValue(entryValue)}</span>
        </div>
      ))}
    </div>
  );
}

function displayText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value.trim();
  if (Array.isArray(value)) return value.map(displayText).filter(Boolean).join(", ");
  if (isPlainObject(value)) return plainObjectSummary(value);
  return String(value ?? "").trim();
}

function plainObjectSummary(value) {
  if (!isPlainObject(value)) return "";
  return Object.entries(value)
    .filter(([, rowValue]) => hasDisplayValue(rowValue) && !isPlainObject(rowValue))
    .slice(0, 5)
    .map(([label, rowValue]) => `${formatTechnicalKey(label)}: ${displayText(rowValue)}`)
    .join("; ");
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return "Not available";
  if (Number.isInteger(value)) return String(value);
  return Number(value.toFixed(3)).toLocaleString("en-US");
}

function formatTechnicalKey(value) {
  return String(value ?? "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatEvidenceDelta(value) {
  if (Array.isArray(value)) {
    return value
      .flatMap(formatEvidenceDelta)
      .filter(Boolean);
  }
  if (!value || typeof value !== "object") {
    return value
      ? [cleanEvidenceText(String(value))]
      : [];
  }
  const label = metricDisplayName(value);
  const baselineStrength = numberOrNull(
    value.baseline_strength ??
      value.baselineStrength ??
      value.baseline_coupling ??
      value.baselineCoupling
  );
  const currentStrength = numberOrNull(
    value.current_strength ??
      value.currentStrength ??
      value.current_coupling ??
      value.currentCoupling
  );
  const correlationDelta = numberOrNull(
    value.correlation_delta ??
      value.correlationDelta ??
      value.coupling_delta ??
      value.couplingDelta
  );
  if (
    baselineStrength !== null &&
    currentStrength !== null
  ) {
    const interpretation =
      interpretCouplingChange(
        baselineStrength,
        currentStrength
      );
    const magnitude =
      correlationDelta !== null
        ? ` Overall change magnitude: ${formatEvidenceNumber(
            Math.abs(correlationDelta)
          )}.`
        : "";
    const summary =
      `Unitless coupling score changed from ` +
      `${formatEvidenceNumber(baselineStrength)} to ` +
      `${formatEvidenceNumber(currentStrength)}; ` +
      `${interpretation}.${magnitude}`;
    return [
      label
        ? `${label}: ${summary}`
        : summary,
    ];
  }
  const details = [
    value.percent_change !== undefined
      ? `Percent change: ${formatQuantitativeValue(
          value.percent_change
        )}%`
      : "",
    value.absolute_change !== undefined
      ? `Absolute change: ${formatQuantitativeValue(
          value.absolute_change
        )}`
      : "",
    value.baseline_average !== undefined
      ? `Baseline average: ${formatQuantitativeValue(
          value.baseline_average
        )}`
      : "",
    value.current_average !== undefined
      ? `Current average: ${formatQuantitativeValue(
          value.current_average
        )}`
      : "",
    correlationDelta !== null
      ? `Operating pattern change magnitude: ${formatEvidenceNumber(
          Math.abs(correlationDelta)
        )}`
      : "",
  ]
    .filter(Boolean)
    .join("; ");
  if (!details) {
    return [
      firstText(
        label,
        compactJson(value)
      ),
    ];
  }
  return [
    label
      ? `${label}: ${details}`
      : details,
  ];
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
      {items.map((item) => (
        <li key={item.id}>
          <div className="operational-timeline__meta">
            {item.icon ? <span className="operational-timeline__icon" aria-hidden="true">{item.icon}</span> : null}
            <span>{item.time}</span>
          </div>
          <strong>{item.title}</strong>
          <p>{item.detail}</p>
          {Array.isArray(item.entries) && item.entries.length ? (
            <ul className="operational-timeline__entries">
              {item.entries.map((entry) => (
                <li key={entry.id}>
                  <strong>{entry.time ? entry.time + " - " + entry.title : entry.title}</strong>
                  <p>{entry.detail}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function QualityList({ title, items, empty, codeItems = false }) {
  return (
    <section className="operational-block">
      <h3>{title}</h3>
      {items.length ? (
        <ul className={codeItems ? "compact-list compact-list--code" : "compact-list"}>
          {items.map((item) => <li key={item}>{codeItems ? <code>{item}</code> : renderDisplayValue(item)}</li>)}
        </ul>
      ) : <p>{empty}</p>}
    </section>
  );
}

function DetailGrid({ rows, technical = false }) {
  const visibleRows = rows
    .filter((row) => row && row.length >= 2)
    .filter(([, value]) => hasDisplayValue(value));
  return (
    <dl className={technical ? "operational-detail-grid operational-detail-grid--technical" : "operational-detail-grid"}>
      {visibleRows.map(([label, value], index) => (
        <div key={`${label}-${index}`}>
          <dt>{label}</dt>
          <dd>{renderDisplayValue(value, { technical })}</dd>
        </div>
      ))}
    </dl>
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

function StatusBadge({ label, tone, statusKey }) {
  const classes = Array.from(new Set(["operational-status", `operational-status--${tone}`, statusKey ? `operational-status--${statusKey}` : ""].filter(Boolean))).join(" ");
  return <span className={classes}><span className="operational-status__icon" aria-hidden="true" />{label}</span>;
}

function LabeledStatusChip({ label, value, tone, statusKey }) {
  return (
    <span className="labeled-status-chip">
      <span className="labeled-status-chip__label">{label}</span>
      <StatusBadge label={value} tone={tone} statusKey={statusKey} />
    </span>
  );
}

function EmptyOperationalState({ title, body }) {
  return <div className="operational-empty"><strong>{title}</strong><p>{body}</p></div>;
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

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
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

function formatDisplayName(value, fallback = "") {
  const text = cleanDisplayText(value)
    .replace(/^[\s,;:]+/, "")
    .replace(/\s+([,;:!?])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  if (!text || isBackendFallbackLabel(text)) return fallback;
  return text;
}

function normalizeSignalName(value, index = 0) {
  const raw = value && typeof value === "object" ? metricDisplayName(value, index) : value;
  const label = formatDisplayName(raw, index ? `Signal ${index}` : "");
  if (!label) return "";
  if (isGenericRelationshipLabel(label)) return index ? `Signal ${index}` : "";
  return label;
}

function resolveSystemName(insight, systems = [], signals = []) {
  const candidates = [
    insight?.rawSystemName,
    insight?.systemName,
    insight?.system_name,
    insight?.system,
    insight?.affectedSystem,
    insight?.affected_system,
    ...toList(insight?.affectedSystems, insight?.affected_systems),
  ];
  const byId = systems.find((system) => candidates.some((candidate) => normalizeDisplayKey(candidate) && normalizeDisplayKey(candidate) === normalizeDisplayKey(system?.id)));
  if (byId) return formatDisplayName(firstText(byId.name, byId.label, byId.system_name), UNASSIGNED_SYSTEM_NAME);
  const direct = candidates.map((item) => formatDisplayName(item)).find(Boolean);
  if (direct) return direct;

  const relatedSignals = dedupeText([
    ...toList(signals).map((item, index) => normalizeSignalName(item, index + 1)),
    ...toList(insight?.contributingMetrics).map((item, index) => normalizeSignalName(item, index + 1)),
    ...toList(insight?.contributingRelationships).flatMap(relationshipSignalCandidates).map((item, index) => normalizeSignalName(item, index + 1)),
    ...toList(insight?.affectedRelationships).map((item, index) => normalizeSignalName(item, index + 1)),
  ]);
  const matchedSystem = systems.find((system) => {
    const systemKey = normalizeDisplayKey(firstText(system?.name, system?.label, system?.system_name));
    return systemKey && relatedSignals.some((signal) => {
      const signalKey = normalizeDisplayKey(signal);
      return signalKey.includes(systemKey) || systemKey.includes(signalKey);
    });
  });
  if (matchedSystem) return formatDisplayName(firstText(matchedSystem.name, matchedSystem.label, matchedSystem.system_name), UNASSIGNED_SYSTEM_NAME);

  const inferred = inferSystemNameFromSignals(relatedSignals);
  return inferred || UNASSIGNED_SYSTEM_NAME;
}

function inferSystemNameFromSignals(signals) {
  const tokenRows = signals
    .map((signal) => normalizeDisplayKey(signal).split(" ").filter(Boolean))
    .filter((tokens) => tokens.length > 1);
  if (!tokenRows.length) return "";
  const common = [];
  for (let index = 0; index < Math.min(...tokenRows.map((tokens) => tokens.length)); index += 1) {
    const token = tokenRows[0][index];
    if (!tokenRows.every((tokens) => tokens[index] === token)) break;
    common.push(token);
  }
  const useful = common.filter((token) => !/^(signal|numeric|column|delta|value|current|baseline|temp|temperature|pressure|flow|speed|status|level|rate)$/.test(token));
  if (!useful.length) return "";
  return formatDisplayName(useful.join(" ").replace(/\b(ahu|vav|vfd|chw)\s*(\d+)\b/gi, (match, prefix, number) => `${prefix.toUpperCase()} ${number}`));
}

function formatEvidenceItems(evidence) {
  if (Array.isArray(evidence)) return dedupeText(evidence.flatMap(formatEvidenceItems));
  if (evidence === null || evidence === undefined || evidence === "") return [];
  if (typeof evidence === "object") {
    return formatEvidenceItems(toList(
      evidence.description,
      evidence.summary,
      evidence.what_changed,
      evidence.whatChanged,
      evidence.supporting_signals,
      evidence.supportingSignals,
      evidence.relevant_metric_changes,
      evidence.relevantMetricChanges,
      evidence.metric_delta
    ));
  }
  return String(evidence)
    .split(/\n|;|\u2022/g)
    .map((item) => formatDisplayName(item.replace(/^[\s,;:.-]+/, "")))
    .filter(Boolean)
    .filter((item) => !isBackendFallbackLabel(item));
}

function getInsightType(insight) {
  const text = [
    insight?.type,
    insight?.insight_type,
    insight?.insightType,
    insight?.category,
    insight?.change_type,
    insight?.rawSummary,
    insight?.title,
    insight?.summary,
    insight?.whatHappened,
    insight?.what_changed,
    insight?.explanation,
  ].map((item) => String(item ?? "").toLowerCase()).join(" ");
  const relationships = toList(insight?.contributing_relationships, insight?.contributingRelationships, insight?.affectedRelationships);
  const changedRelationshipCount = numberOrNull(insight?.changedRelationshipCount ?? insight?.changed_relationship_count);
  if (/relationship|correlation|coupling|interaction|pair/.test(text) || relationships.length > 0 || (changedRelationshipCount ?? 0) > 0) return "relationship_shift";
  if (/metric|signal|deviation|deviat|anomaly|threshold|baseline|current value/.test(text) || toList(insight?.contributing_metrics, insight?.contributingMetrics, insight?.metric, insight?.metric_name).length > 0) return "metric_deviation";
  return "behavior_change";
}

function shouldShowRelationshipCount(insight) {
  return getInsightType(insight) === "relationship_shift" && Number(insight?.changedRelationshipCount ?? insightRelationshipLabels(insight).length) > 0;
}

// Hardened fallback-label detector.
//
// Previously this only checked an exact Set of known-bad literal strings.
// The problem with that approach: it only catches phrasing the team has
// already seen leak through once. If the backend's generator produces a
// slightly different fallback sentence (different verb, different word
// order, a system vs subsystem swap), the exact-match Set misses it
// silently and the bug resurfaces under a new guise.
//
// This version keeps the Set as a fast, cheap first check, but backs it
// with a structural regex that targets the *shape* of a generic
// system/subsystem fallback sentence rather than one fixed wording. That
// makes the filter resilient to small copy changes on the backend without
// needing a UI patch every time a new fallback phrasing appears.
function isBackendFallbackLabel(value) {
  const key = normalizeDisplayKey(value);
  if (!key) return false;
  if (GENERIC_FALLBACK_LABELS.has(key)) return true;
  return GENERIC_FALLBACK_PATTERN.test(key);
}

function cleanDisplayText(value) {
  const text = sanitizeOperatorText(firstText(value))
    .replace(/^tag:/i, "")
    .replace(/^metric:/i, "")
    .replace(/\btag[-_\s]?pair\b/gi, "relationship")
    .replace(/\bColumn\s+(\d+)\b/gi, (match, number) => "Signal " + number)
    .replace(/_+/g, " ")
    .replace(/\s+\/\s+/g, " / ")
    .replace(/\b(The)\s+\1\b/gi, "$1")
    .replace(/\.\s+(has|have|had|is|are|was|were)\b/g, " $1")
    .replace(/\s+([,.!?;:])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  return text || firstText(value);
}

function metricDisplayName(value, index = 0) {
  if (!value || typeof value !== "object") return cleanDisplayText(value);
  return cleanDisplayText(firstText(
    value.display_name,
    value.displayName,
    value.label,
    value.name,
    value.tag_name,
    value.original_header,
    value.source_counter_display_name,
    value.source_column,
    value.source_counter,
    value.column,
    value.change_type,
    index ? "Signal " + index : ""
  ));
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
  return dedupeText(values.map((item, index) => {
    if (!item || typeof item !== "object") return publicRelationshipLabel(cleanRelationshipLabel(item), index);
    return relationshipDisplayName(item, index);
  }).filter(Boolean));
}


const DEFAULT_POTENTIAL_OPERATIONAL_CAUSES = [
  "Operating setpoint modification",
  "Control sequence adjustment",
  "Process demand change",
  "Equipment operating state change",
  "Recent maintenance activity",
  "Sensor calibration change",
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

function rankedOperationalCauses(insight) {
  const candidates = operationalCauseHypotheses(insight);
  const context = [
    insight?.system,
    insight?.summary,
    insight?.rawSummary,
    insight?.metricName,
    insightRelationshipLabels(insight).join(" "),
    evidenceBriefing(insight, insightRelationshipLabels(insight)).join(" "),
  ].join(" ").toLowerCase();

  const scored = candidates.map((cause, index) => ({
    cause,
    score: operationalCauseScore(cause, context) - index * 0.01,
  }));

  const ordered = scored
    .sort((left, right) => right.score - left.score)
    .map((item) => item.cause);

  return {
    mostLikely: ordered.slice(0, 3),
    otherPossibilities: ordered.slice(3),
  };
}

function operationalCauseScore(cause, context) {
  const text = String(cause ?? "").toLowerCase();
  let score = 0;
  const keywordGroups = [
    ["filter", "foul", "loading", "differential pressure"],
    ["pump", "vfd", "speed", "operating point", "curve"],
    ["valve", "position", "damper"],
    ["load", "demand", "process"],
    ["maintenance", "operator"],
    ["sensor", "calibration", "drift"],
    ["tower", "chiller", "condenser", "heat exchanger", "cooling"],
    ["chemical", "feed", "water quality", "dose"],
  ];

  keywordGroups.forEach((group, groupIndex) => {
    const causeMatches = group.some((keyword) => text.includes(keyword));
    const contextMatches = group.some((keyword) => context.includes(keyword));
    if (causeMatches && contextMatches) score += 10 - groupIndex * 0.2;
  });

  if (/filter|pump|valve|tower|chiller|heat exchanger|chemical|sensor/.test(text)) score += 2;
  if (/maintenance|operator|recent/.test(text)) score -= 1;
  return score;
}

function actionizeRecommendation(value) {
  const text = cleanBriefingText(value);
  if (!text) return "Review the contributing signal trends.";
  if (/^(check|confirm|compare|review|verify|monitor|inspect|trend|validate)\b/i.test(text)) return text;
  return `Review ${text.charAt(0).toLowerCase()}${text.slice(1)}`;
}

function formatInsightTitle(value) {
  if (value && typeof value === "object") {
    const context = insightTitleContext(value);
    const type = getInsightType(value);
    const relationshipTitle = relationshipTitleFromLabels(insightRelationshipLabels(value));
    if (type === "relationship_shift") {
      if (relationshipTitle) return relationshipTitle;
      if (/water quality|chemical|chlor|dose|ph|orp|conductivity/i.test(context)) return "Water Quality Relationship Changed";
      if (/flow|pressure/i.test(context)) return "Flow and Pressure Relationship Changed";
      if (/pump|valve|vfd|filter|hydraulic/i.test(context)) return "Pump Performance Relationship Changed";
      return `${formatSubsystemName(value.system)} Operating Relationship Changed`;
    }
    if (type === "metric_deviation") {
      if (/chiller|cooling|thermal|tower|condenser/i.test(context)) return "Chiller Operating Behavior Changed";
      if (/pump|flow|pressure|valve|vfd|filter|hydraulic/i.test(context)) return "Hydraulic Performance Changed";
      return `${formatSubsystemName(value.system)} Operating Behavior Changed`;
    }
    if (/chiller|cooling|thermal|tower|condenser/i.test(context)) return "Chiller Operating Behavior Changed";
    if (/pump|flow|pressure|valve|vfd|filter|hydraulic/i.test(context)) return "Hydraulic Performance Changed";
    return `${formatSubsystemName(value.system)} Operating Behavior Changed`;
  }
  return formatDisplayName(value)
    .replace(/\s+/g, " ")
    .trim();
}

function relationshipTitleFromLabels(relationships = []) {
  const label = relationships
    .map((item, index) => formatRelationshipObservedLabel(item, index))
    .find((item) => item && !/^Relationship [A-Z]$/.test(item));
  if (!label) return "";
  const endpoints = label.split(/\s*↔\s*|\s+\/\s+|\s+and\s+/i).map(titleEndpoint).filter(Boolean);
  if (endpoints.length >= 2) return `${endpoints[0]} and ${endpoints[1]} Relationship Changed`;
  return `${titleEndpoint(label)} Relationship Changed`;
}

function titleEndpoint(value) {
  return formatDisplayName(value)
    .replace(/\b[a-z]/g, (letter) => letter.toUpperCase())
    .replace(/Dp/gi, "DP")
    .replace(/Ph/gi, "pH")
    .replace(/Orp/gi, "ORP")
    .replace(/Vfd/gi, "VFD")
    .trim();
}

function formatOperationalSignalName(value) {
  return titleEndpoint(value)
    .replace(/\bDP\b/g, "Differential Pressure")
    .replace(/\bUs Cm\b/gi, "uS/cm")
    .replace(/\bU S Cm\b/gi, "uS/cm")
    .trim();
}

function relationshipEndpointLabels(value, index = 0) {
  const label = formatRelationshipObservedLabel(value, index);
  return label
    .split(/\s*↔\s*|\s+\/\s+|\s+and\s+/i)
    .map(formatOperationalSignalName)
    .filter(Boolean)
    .slice(0, 2);
}

function relationshipBriefingSentence(value, index = 0) {
  const endpoints = relationshipEndpointLabels(value, index);
  if (endpoints.length >= 2) return `The relationship between ${endpoints[0]} and ${endpoints[1]} has shifted from its established operational baseline.`;
  return `The ${relationshipSentenceLabel(value, index)} relationship no longer follows its established operating pattern.`;
}


function emergingRelationshipSentence(value, index = 0) {
  const endpoints = relationshipEndpointLabels(value, index);
  if (endpoints.length >= 2) return `A new operating relationship emerged between ${endpoints[0]} and ${endpoints[1]}.`;
  return `A new operating relationship emerged in ${relationshipSentenceLabel(value, index)}.`;
}

function relationshipActivitySentence(value, index = 0) {
  const endpoints = relationshipEndpointLabels(value, index);
  if (endpoints.length >= 2) return `${endpoints[0]} and ${endpoints[1]} relationship changed.`;
  return `${relationshipSentenceLabel(value, index)} relationship changed.`;
}

function insightTitleContext(insight) {
  return [
    insight?.system,
    insight?.rawSystemName,
    insight?.metricName,
    insight?.summary,
    insight?.rawSummary,
    insightRelationshipLabels(insight).join(" "),
  ].join(" ");
}

function formatSubsystemName(value) {
  return formatDisplayName(value, UNASSIGNED_SYSTEM_NAME)
    .replace(/\s+\/\s+/g, " & ")
    .replace(/\bsubsystem\b/gi, "system")
    .replace(/\s+/g, " ")
    .trim();
}

function whatChangedBriefing(insight, relationships) {
  const system = formatSubsystemName(insight.system);
  if (relationships.length > 0) {
    const insightContext = [insight.summary, insight.whatHappened, insight.whatChanged, insight.rawSummary, insight.title].join(" ");
    const emergingRelationship = /\b(new operating relationship|new relationship|emerged)\b/i.test(insightContext);
    const relationshipText = relationships.length === 1
      ? emergingRelationship ? emergingRelationshipSentence(relationships[0], 0) : relationshipBriefingSentence(relationships[0], 0)
      : emergingRelationship ? "New operating relationships emerged in " + system + "." : "Multiple " + system + " operating relationships changed from their normal operating pattern.";
    const scopeText = relationships.length === 1
      ? "One operating relationship changed enough to warrant field review."
      : relationships.length + " operating relationships changed together, which may point to a system-level behavior change.";
    return [relationshipText, scopeText];
  }

  const metric = normalizeSignalName(insight.metricName);
  const direction = String(insight.deviationDirection ?? "").toLowerCase();
  const directionText = direction.includes("down") || direction.includes("low") || direction.includes("below")
    ? "below"
    : "above";
  const baselineText = metric
    ? `The ${metric} is operating significantly ${directionText} its learned operating range.`
    : `The ${system} is operating significantly ${directionText} its learned operating range.`;
  const supplied = briefingSentences(firstDistinctText(insight.summary, insight.whatHappened, insight.whatChanged, insight.rawSummary), 1)
    .filter((line) => !/moved\s+(up|down)\s+from\s+the\s+historical\s+pattern\s+to\s+the\s+analysis\s+period/i.test(line));
  return supplied.length ? [baselineText, ...supplied].slice(0, 2) : [baselineText];
}

function operatorSummaryBriefing(insight, relationships) {
  return dedupeText(whatChangedBriefing(insight, relationships)).slice(0, 2);
}

function whyItMattersBriefing(insight) {
  const supplied = briefingSentences(firstText(insight?.whyItMatters, insight?.possibleConsequence), 2);
  if (supplied.length) return supplied;
  return ["This change may indicate reduced operating efficiency or a change in operating conditions."];
}

function operationalCauseHypotheses(insight) {
  const relationships = insightRelationshipLabels(insight);
  const direct = dedupeText(toList(insight.possibleOperationalCauses).flatMap(splitPriorityText).map(cleanBriefingText));
  const context = [insight.system, insight.summary, relationships.join(" ")].join(" ");
  const matched = OPERATIONAL_CAUSE_SETS.find((set) => set.pattern.test(context));
  return dedupeText([...direct, ...(matched?.causes ?? DEFAULT_POTENTIAL_OPERATIONAL_CAUSES)]).slice(0, 6);
}

function recommendedReviewItems(insight, relationships = []) {
  return dedupeText(suggestedInvestigationSteps({
    subsystem: insight?.system,
    relationshipLabels: relationships,
    insight,
  }).map(cleanBriefingText)).slice(0, 6);
}

function insightRelationshipLabels(insight) {
  if (!insight) return [];
  if (Array.isArray(insight.affectedRelationships) && insight.affectedRelationships.length) {
    return insight.affectedRelationships;
  }
  if (Array.isArray(insight.contributingRelationships) && insight.contributingRelationships.length) {
    return relationshipContributionLabels(insight.contributingRelationships);
  }
  return [];
}

function formatRelationshipObservedLabel(value, index = 0) {
  const label = value && typeof value === "object" ? relationshipLabelFromValue(value, index) : value;
  return publicRelationshipLabel(label, index);
}

function relationshipSentenceLabel(value, index = 0) {
  return formatRelationshipObservedLabel(value, index)
    .replace(/\s*↔\s*/g, " and ")
    .replace(/\s+\/\s+/g, " and ")
    .replace(/\s+/g, " ")
    .trim();
}

function formatRelationshipObservedLabelRaw(value) {
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
  return [...new Set(items.filter((item) => item !== null && item !== undefined).map((item) => displayText(item).trim()).filter(Boolean))];
}

function dedupeDisplayValues(items, keyFormatter = displayText) {
  const seen = new Set();
  const values = [];
  items.forEach((item) => {
    const label = cleanDisplayText(item);
    const key = keyFormatter(label);
    if (!label || seen.has(key)) return;
    seen.add(key);
    values.push(label);
  });
  return values;
}

function signalDisplayKey(value) {
  return normalizeDisplayKey(value)
    .replace(/\b(kw|kwh|psi|gpm|rpm|pct|percent|f|c|ph|orp)\b/g, "")
    .trim();
}

function normalizeDisplayKey(value) {
  return cleanDisplayText(value)
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeInsightId(item, index) {
  const directId = firstText(item?.id, item?.insight_id, item?.insightId).trim();
  if (directId) return directId;
  const basis = firstText(
    item?.title,
    item?.summary,
    item?.explanation,
    item?.what_changed,
    item?.whatChanged,
    item?.detail,
    item?.label,
    item?.system,
    toList(item?.affected_systems)[0],
  );
  const slug = normalizeDisplayKey(basis).replace(/\s+/g, "-").slice(0, 80);
  return slug ? `insight-${slug}-${index}` : `insight-${index}`;
}

function dedupeInsights(items) {
  const seen = new Set();
  return items.filter((item) => {
    const detailKey = firstText(item.whatHappened, item.whyItMatters, item.recommendedAction, insightRelationshipLabels(item).join("|"), item.id);
    const key = [item.system, item.summary, detailKey].join("::");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function dedupeSystemCards(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = [
      item.name,
      item.status,
      item.lastAnalysis,
      toList(item.relationships).join("|"),
      toList(item.whatChanged).join("|"),
    ].join("::");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function firstText(...values) {
  for (const value of values) {
    const text = displayText(value);
    if (text.trim() !== "") return text;
  }
  return "";
}

function firstMeaningfulText(...values) {
  const value = values.find((item) => !isPlaceholderValue(item));
  return value === undefined ? "" : displayText(value);
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

function isAnalysisResumable({ liveOps, currentSession, result, snapshot, gateProcessing }) {
  const statusText = [
    gateProcessing?.status,
    gateProcessing?.state,
    gateProcessing?.processing_state,
    currentSession?.status,
    currentSession?.state,
    liveOps?.latestStatus,
    liveOps?.uploadState,
    result?.status,
    result?.processing_state,
    snapshot?.status,
    snapshot?.processing_state,
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  return Boolean(
    currentSession?.paused === true
      || currentSession?.resumable === true
      || liveOps?.canResumePrevious === true
      || liveOps?.pausedUpload === true
      || liveOps?.resumableUpload === true
      || statusText.includes("paused")
      || statusText.includes("interrupted")
      || statusText.includes("resumable")
      || statusText.includes("incomplete")
  );
}

function hasCompletedSiiAnalysis({ result, snapshot, currentSession, liveOps }) {
  const hasIntelligenceData = Boolean(result?.analysis_result || result?.sii_intelligence || result?.engine_result);
  const statusText = [
    result?.status,
    result?.processing_state,
    snapshot?.status,
    snapshot?.processing_state,
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  const completed = Boolean(
    currentSession?.hasReliableOperatorEvidence === true
    || result?.sii_reliable_enough_to_show === true
    || result?.sii_completed === true
    || result?.processing_trace?.sii_completed === true
    || snapshot?.sii_completed === true
    || liveOps?.siiVerification?.verified === true
    || (/\b(complete|completed|ready|active|processed|success)\b/.test(statusText) && result?.analysis_result)
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
