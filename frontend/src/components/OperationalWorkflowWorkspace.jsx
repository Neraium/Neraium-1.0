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

const INVESTIGATION_STATUSES = ["Open", "Acknowledged", "Under Investigation", "Resolved"];
const AWAITING_ANALYSIS = {
  label: "Awaiting Analysis",
  tone: "unknown",
  detail: "SII has not completed analysis for this system yet.",
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

  function navigate(sectionId) {
    setActiveSection(sectionId);
  }

  function openInsight(insightId) {
    setSelectedInsightId(insightId);
    setActiveSection("insights");
  }

  function setInsightStatus(insightId, status) {
    setInsightStatuses((current) => ({ ...current, [insightId]: status }));
  }

  function setOperatorNote(insightId, note) {
    setOperatorNotes((current) => ({ ...current, [insightId]: note }));
  }

  function analyzeSystem() {
    if (typeof onWorkspaceNavigate === "function") {
      onWorkspaceNavigate("data-connections");
    }
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
              {item.label}
            </button>
          ))}
        </nav>
        <div className="operational-sidebar__footer">
          <StatusBadge label={model.telemetryIntegrity.label} tone={model.telemetryIntegrity.tone} />
          <small>Last analysis: {model.lastAnalysis}</small>
          {typeof onSignOut === "function" ? (
            <button type="button" className="operational-link-button" onClick={onSignOut}>Sign out</button>
          ) : null}
        </div>
      </aside>

      <main className="operational-main" aria-label="Neraium operational workspace">
        <header className="operational-topbar">
          <div>
            <p className="section-token">Operational Understanding</p>
            <h1>{sectionTitle(activeSection)}</h1>
          </div>
          <div className="operational-topbar__status">
            <StatusBadge label={model.overallStatus.label} tone={model.overallStatus.tone} />
            <StatusBadge label={`Telemetry ${model.telemetryIntegrity.label}`} tone={model.telemetryIntegrity.tone} />
          </div>
        </header>

        <div className="operational-mobile-nav" aria-label="Mobile workflow navigation">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={activeSection === item.id ? "is-active" : ""}
              onClick={() => navigate(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {activeSection === "overview" ? (
          <OverviewSection model={model} onOpenInsight={openInsight} onAnalyzeSystem={analyzeSystem} onResumePreviousSession={onResumePreviousSession} />
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

function OverviewSection({ model, onOpenInsight, onAnalyzeSystem, onResumePreviousSession }) {
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label="System health overview">
        <PanelHeader eyebrow="Overview" title="System Health" subtitle="Current behavioral status across monitored systems." />
        <div className="system-health-grid">
          {model.systemCards.map((system) => (
            <article className={`system-health-card system-health-card--${system.tone}`} key={system.id}>
              <div>
                <span className="section-token">{system.name}</span>
                <h3>{system.status}</h3>
              </div>
              <p>{system.summary}</p>
              <div className="system-health-card__footer">
                <span>{system.lastAnalysis}</span>
                <strong>{system.insightSummary}</strong>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="operational-panel" aria-label="System fingerprint drift">
        <PanelHeader eyebrow="SII" title="Fingerprint Drift" subtitle="Current behavior compared with historical baseline." />
        <FingerprintIndicator drift={model.fingerprintDrift} />
      </section>

      <section className="operational-panel" aria-label="Telemetry integrity">
        <PanelHeader eyebrow="Data" title="Telemetry Integrity" subtitle="Confidence in the inputs behind the current view." />
        <StatusBadge label={model.telemetryIntegrity.label} tone={model.telemetryIntegrity.tone} />
        <p className="operational-copy">{model.telemetryIntegrity.detail}</p>
        <small>Last analysis: {model.lastAnalysis}</small>
      </section>

      <section className="operational-panel operational-panel--wide" aria-label="Active insights summary">
        <PanelHeader eyebrow="Insights" title="Active Insights" subtitle="Current investigation priorities across monitored systems." />
        <InsightList
          insights={model.insights.slice(0, 5)}
          empty={model.analysisComplete ? "No active insights. Analyze telemetry to generate operational understanding." : "Awaiting Analysis. Analyze telemetry to generate operational understanding."}
          emptyTitle={model.analysisComplete ? "No active insights" : "Awaiting Analysis"}
          onOpenInsight={onOpenInsight}
        />
        <div className="operational-actions">
          <button type="button" className="command-button" onClick={onAnalyzeSystem}>Analyze System</button>
          {model.canResumePrevious && typeof onResumePreviousSession === "function" ? (
            <button type="button" className="secondary-command-button" onClick={onResumePreviousSession}>Resume Previous Analysis</button>
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
          empty={model.analysisComplete ? "No insights yet. Analyze telemetry to generate findings." : "Awaiting Analysis. Analyze telemetry to generate findings."}
          emptyTitle={model.analysisComplete ? "No insights yet" : "Awaiting Analysis"}
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
      <section className="operational-panel operational-panel--wide" aria-label="System selector">
        <PanelHeader eyebrow="Systems" title="Monitored Systems" subtitle="Per-system behavior and current investigation status." />
        <div className="system-health-grid">
          {model.systemCards.map((system) => (
            <button className={`system-health-card system-health-card--${system.tone}`} key={system.id} type="button">
              <span className="section-token">{system.name}</span>
              <h3>{system.status}</h3>
              <p>{system.summary}</p>
              <small>{system.lastAnalysis}</small>
            </button>
          ))}
        </div>
      </section>
      <section className="operational-panel" aria-label="Fingerprint panel">
        <PanelHeader eyebrow="Fingerprint" title="Current vs. Historical" subtitle="Behavioral baseline comparison." />
        <FingerprintIndicator drift={model.fingerprintDrift} />
      </section>
      <section className="operational-panel" aria-label="Signal relationship summary">
        <PanelHeader eyebrow="Relationships" title="Signal Relationship Summary" subtitle="Relationships with the largest behavior shift." />
        <RelationshipList rows={model.relationshipRows} />
      </section>
      <section className="operational-panel operational-panel--wide" aria-label="System insights">
        <PanelHeader eyebrow="Insights" title="Active System Insights" subtitle="Findings tied to the selected or primary system." />
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No active system insights." : "Awaiting Analysis. Analyze telemetry to generate system insights."}
          emptyTitle={model.analysisComplete ? "No active system insights" : "Awaiting Analysis"}
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
        <StatusBadge label={model.telemetryIntegrity.label} tone={model.telemetryIntegrity.tone} />
        <DetailGrid rows={[
          ["Source", model.sourceLabel],
          ["Last analysis", model.lastAnalysis],
          ["Detected data type", model.domainLabel],
        ]} />
      </section>
      <section className="operational-panel" aria-label="Signal browser">
        <PanelHeader eyebrow="Signals" title="Signal Browser" subtitle="Detected telemetry signals and integrity state." />
        <SignalList signals={model.signals} integrity={model.telemetryIntegrity} />
      </section>
      <section className="operational-panel operational-panel--wide" aria-label="Data quality warnings">
        <PanelHeader eyebrow="Integrity" title="Data Quality" subtitle="Warnings, missing values, and timestamp conditions." />
        <QualityList title="Warnings" items={model.qualityWarnings} empty={model.analysisComplete ? "No data quality warnings reported." : "Awaiting Analysis."} />
        <QualityList title="Missing values" items={model.missingValues} empty={model.analysisComplete ? "No missing value summary reported." : "Awaiting Analysis."} />
        <QualityList title="Timestamp quality" items={model.timestampNotes} empty={model.analysisComplete ? "Timestamp quality is acceptable or not yet reported." : "Awaiting Analysis."} />
        <div className="operational-actions">
          <button type="button" className="command-button" onClick={onAnalyzeSystem}>Analyze New Telemetry</button>
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
          empty={model.analysisComplete ? "No insight archive yet." : "Awaiting Analysis. Insight history will appear after SII analysis completes."}
          emptyTitle={model.analysisComplete ? "No insight archive yet" : "Awaiting Analysis"}
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
  const analysisComplete = hasCompletedSiiAnalysis({ result, snapshot, currentSession, liveOps });
  const telemetryIntegrity = deriveTelemetryIntegrity({ result, snapshot, quality, liveOps, analysisComplete });
  const finding = canonicalFinding ?? liveOps?.canonicalFinding ?? null;
  const hasFinding = analysisComplete && Boolean(finding?.exists || liveOps?.findings?.length);
  const primarySystem = firstText(roomContext?.primary, liveOps?.primaryWindow?.label, result?.system_name, "Primary Water System");
  const overallStatus = deriveOverallStatus({ hasFinding, telemetryIntegrity, gateProcessing, result, liveOps, analysisComplete });
  const lastAnalysis = firstText(liveOps?.connectionSummary, snapshot?.processed_at, snapshot?.last_processed_at, result?.processed_at, result?.timestamp_profile?.last_timestamp, "Awaiting analysis");
  const fingerprintDrift = deriveFingerprintDrift({ relationshipRows, result, hasFinding, analysisComplete });
  const insights = analysisComplete ? buildInsights({ finding, liveOps, result, primarySystem, telemetryIntegrity, lastAnalysis }) : [];
  const systemCards = buildSystemCards({ systems: liveOps?.systems, primarySystem, overallStatus, lastAnalysis, insights, fingerprintDrift, analysisComplete });
  const signals = buildSignals(result);
  const historyItems = buildHistoryItems({ liveOps, snapshot, result, replayFrame, insights, analysisComplete });
  const domainLabel = formatDomainLabel(domainDetection?.mode ?? result?.domain_detection?.mode ?? result?.detected_schema?.mode ?? "Water system");

  return {
    siteLabel: firstText(result?.facility_name, snapshot?.facility_name, "Current Site"),
    domainLabel,
    sourceLabel: firstText(result?.result_source, snapshot?.result_source, liveOps?.telemetrySession?.sessionMode, "Operational data"),
    overallStatus,
    lastAnalysis,
    telemetryIntegrity,
    analysisComplete,
    fingerprintDrift,
    systemCards,
    insights,
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

function buildInsights({ finding, liveOps, result, primarySystem, telemetryIntegrity, lastAnalysis }) {
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
        whyItMatters: firstText(item.whyItMatters, "The system is no longer matching its normal operating pattern and may require investigation."),
        systemBehavior: firstText(item.baselineContext, item.change, "Current behavior is being compared against the historical operating fingerprint."),
        investigationPriorities: priorities.length ? priorities : ["Verify supporting measurements", "Inspect affected equipment", "Compare current operation with recent maintenance activity"],
        supportingObservations: supporting.length ? supporting : ["Behavior changed from historical baseline", "Telemetry was analyzed for relationship changes"],
        telemetryNote: telemetryIntegrity.detail,
        detectedAt: lastAnalysis,
      };
    });

  if (insights.length > 0) return dedupeInsights(insights).slice(0, 8);

  return [];
}

function buildSystemCards({ systems, primarySystem, overallStatus, lastAnalysis, insights, fingerprintDrift, analysisComplete }) {
  const safeSystems = Array.isArray(systems) && systems.length > 0
    ? systems.slice(0, 6).map((system, index) => ({ id: system.id ?? system.name ?? `system-${index}`, name: system.name ?? system.label ?? `System ${index + 1}` }))
    : [{ id: "primary", name: primarySystem }];

  return safeSystems.map((system) => {
    const activeInsightCount = insights.filter((item) => item.system === system.name || safeSystems.length === 1).length;
    return {
      id: system.id,
      name: system.name,
      status: overallStatus.label,
      tone: overallStatus.tone,
      summary: fingerprintDrift.detail,
      lastAnalysis,
      activeInsightCount,
      insightSummary: analysisComplete
        ? `${activeInsightCount} active insight${activeInsightCount === 1 ? "" : "s"}`
        : AWAITING_ANALYSIS.label,
    };
  });
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

function deriveTelemetryIntegrity({ result, snapshot, quality, liveOps, analysisComplete }) {
  if (!analysisComplete) {
    return {
      ...AWAITING_ANALYSIS,
      detail: "Telemetry integrity will be classified after SII completes analysis.",
    };
  }
  const text = `${quality.warnings.join(" ")} ${quality.missingValues.join(" ")} ${liveOps?.connectionStatusLine ?? ""}`.toLowerCase();
  if (!result && !snapshot) return { label: "Missing", tone: "unknown", detail: "No telemetry has been analyzed yet." };
  if (text.includes("missing")) return { label: "Missing", tone: "warning", detail: "Some telemetry values or sources are missing." };
  if (text.includes("inconsistent") || text.includes("timestamp")) return { label: "Inconsistent", tone: "warning", detail: "Telemetry timing or source consistency needs review." };
  if (quality.warnings.length > 0 || quality.missingValues.length > 0 || String(liveOps?.connectionTone ?? "").includes("degraded")) {
    return { label: "Degraded", tone: "warning", detail: "Telemetry is usable, but one or more quality conditions should be reviewed." };
  }
  return { label: "Good", tone: "normal", detail: "Telemetry integrity appears acceptable for operational review." };
}

function deriveOverallStatus({ hasFinding, telemetryIntegrity, gateProcessing, result, liveOps, analysisComplete }) {
  if (!analysisComplete) return AWAITING_ANALYSIS;
  if (gateProcessing?.active) return { label: "Monitoring", tone: "unknown" };
  const text = `${result?.operating_state ?? ""} ${result?.drift_status ?? ""} ${liveOps?.facilityTone ?? ""}`.toLowerCase();
  if (text.includes("action") || text.includes("unstable") || text.includes("critical")) return { label: "Investigate", tone: "investigate" };
  if (hasFinding || text.includes("drift") || text.includes("changed") || text.includes("degrad")) return { label: "Changed", tone: "changed" };
  if (telemetryIntegrity.label === "Missing") return { label: "Monitoring", tone: "unknown" };
  return { label: "Normal", tone: "normal" };
}

function deriveFingerprintDrift({ relationshipRows, result, hasFinding, analysisComplete }) {
  if (!analysisComplete) {
    return {
      ...AWAITING_ANALYSIS,
      detail: "Fingerprint drift will be classified after SII completes analysis.",
    };
  }
  const magnitudes = relationshipRows.map((row) => Math.abs(Number(row.percent_change ?? row.absolute_change ?? row.pair_weight ?? row.change ?? 0))).filter(Number.isFinite);
  const max = magnitudes.length ? Math.max(...magnitudes) : 0;
  if (max > 30 || hasFinding || String(result?.drift_status ?? "").toLowerCase().includes("unstable")) {
    return { label: "Significant change", tone: "investigate", detail: "Current behavior is materially different from the historical baseline." };
  }
  if (max > 10 || String(result?.drift_status ?? "").toLowerCase().includes("review")) {
    return { label: "Drifting", tone: "changed", detail: "Current behavior is moving away from the historical baseline." };
  }
  if (relationshipRows.length === 0 && !result?.baseline_analysis && !result?.sii_intelligence) {
    return { label: "Waiting for baseline comparison", tone: "unknown", detail: "Analyze telemetry to compare current behavior with the operating fingerprint." };
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
      {rows.filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "").map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function FingerprintIndicator({ drift }) {
  return (
    <div className={`fingerprint-indicator fingerprint-indicator--${drift.tone}`}>
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
  if (section === "telemetry") return "Telemetry Integrity";
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

function formatDomainLabel(value) {
  return String(value ?? "Water system")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}
