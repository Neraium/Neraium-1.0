import { useMemo, useRef } from "react";

import OperatorInsightDetail from "./OperatorInsightDetail";

function confidencePercent(insight) {
  const score = Number(insight?.confidenceScore ?? insight?.confidence_score);
  if (!Number.isFinite(score)) return "";
  const normalized = score > 1 ? score : score * 100;
  return `${Math.round(Math.max(0, Math.min(100, normalized)))}%`;
}

function severityLabel(value) {
  const text = String(value ?? "").trim().toLowerCase();
  if (text.includes("critical")) return "Critical";
  if (text.includes("high") || text.includes("unstable")) return "High";
  if (text.includes("moderate") || text.includes("review") || text.includes("elevated")) return "Moderate";
  if (text.includes("low")) return "Low";
  return value ? String(value) : "Low";
}

function severityRank(value) {
  return { critical: 4, high: 3, moderate: 2, low: 1 }[severityLabel(value).toLowerCase()] ?? 1;
}

function confidenceRank(insight) {
  const score = Number(insight?.confidenceScore ?? insight?.confidence_score);
  if (Number.isFinite(score)) return score > 1 ? score : score * 100;
  const label = String(insight?.confidence ?? "").toLowerCase();
  if (label.includes("high")) return 90;
  if (label.includes("moderate")) return 70;
  if (label.includes("low")) return 45;
  return 0;
}

function rankedInsights(insights) {
  return [...(insights ?? [])].sort((left, right) =>
    severityRank(right?.severity) - severityRank(left?.severity)
    || confidenceRank(right) - confidenceRank(left)
    || String(left?.summary ?? left?.id ?? "").localeCompare(String(right?.summary ?? right?.id ?? ""))
  );
}

function operationalStatus(model, queue) {
  if (model.uiState?.key === "analyzing") return { label: "Changing", tone: "loading", explanation: "Comparing current operation with the learned baseline." };
  if (!model.analysisComplete) return { label: "Watching", tone: "neutral", explanation: model.commandCenterMessage || "Import telemetry to establish the operating baseline." };
  const critical = queue.filter((item) => severityLabel(item?.severity) === "Critical").length;
  const high = queue.filter((item) => severityLabel(item?.severity) === "High").length;
  if (critical || high > 1) return { label: "Urgent", tone: "critical", explanation: "The highest-severity behavioral changes should be reviewed promptly." };
  if (queue.length || model.behaviorState === "Behavior Shift Detected") return { label: "Investigation Recommended", tone: "warning", explanation: "Current operation differs from the learned behavior baseline." };
  return { label: "Stable", tone: "healthy", explanation: "Current operation remains aligned with learned operating relationships." };
}

function titleFor(insight, helpers) {
  return helpers.formatInsightTitle(insight) || insight?.summary || "Operating behavior changed";
}

function summaryFor(insight, helpers) {
  const relationships = helpers.insightRelationshipLabels(insight);
  return helpers.operatorSummaryBriefing(insight, relationships)[0] || insight?.whatHappened || "Operating behavior changed from the learned baseline.";
}

function firstAction(insight) {
  return insight?.recommendedFirstAction || insight?.recommendedAction || insight?.operatorCheck || insight?.recommendedInvestigation?.[0] || "Review the supporting evidence and compare the affected signals with current operating context.";
}

function OperationalFingerprintSummary({ model, status, queue, topInsight, helpers, onConnectLiveData }) {
  const affected = topInsight?.system || model.dashboardSystemCards?.find((system) => Number(system.activeInsights) > 0)?.name;
  const coverage = model.dataCoveragePercent;
  return (
    <section className={`command-section fingerprint-summary command-section--${status.tone}`} aria-labelledby="fingerprint-summary-heading">
      <div className="command-section__header">
        <p className="command-section__label">Operational Fingerprint</p>
        <h2 id="fingerprint-summary-heading">Operational Fingerprint Summary</h2>
        <p>{status.explanation}</p>
      </div>
      <div className="fingerprint-summary__status"><span>Overall status</span><strong>{status.label}</strong></div>
      <dl className="fingerprint-summary__facts">
        <div><dt>Active findings</dt><dd>{queue.length}</dd></div>
        {affected ? <div><dt>Most affected subsystem</dt><dd>{affected}</dd></div> : null}
        {topInsight ? <div><dt>Highest-priority finding</dt><dd>{titleFor(topInsight, helpers)}</dd></div> : null}
        <div><dt>Last analysis</dt><dd>{model.lastAnalysis}</dd></div>
        <div><dt>Data quality</dt><dd>{model.telemetryStatus?.label || "Unavailable"}</dd></div>
        {coverage !== null && coverage !== undefined ? <div><dt>Data coverage</dt><dd>{coverage}%</dd></div> : null}
      </dl>
      {!model.analysisComplete && status.tone !== "loading" ? <div className="operational-actions fingerprint-summary__actions"><button type="button" className="command-button" onClick={onConnectLiveData}>Import and Analyze Dataset</button><button type="button" className="secondary-command-button" onClick={onConnectLiveData}>Connect Live Telemetry</button></div> : null}
    </section>
  );
}

function SubsystemBehavior({ systems }) {
  return (
    <section className="command-section subsystem-behavior" aria-labelledby="subsystem-behavior-heading">
      <div className="command-section__header"><h2 id="subsystem-behavior-heading">Subsystem Behavior</h2><p>Current state by area, based on analyzed relationships.</p></div>
      {systems.length ? <div className="subsystem-behavior__list" role="list">{systems.map((system) => (
        <div className="subsystem-behavior__row" role="listitem" key={system.id}>
          <span className={`subsystem-behavior__indicator subsystem-behavior__indicator--${system.status.toLowerCase().replace(/\s+/g, "-")}`} aria-hidden="true" />
          <strong>{system.name}</strong><span className="subsystem-behavior__state">{system.status}</span>
          {Number(system.activeInsights) > 0 ? <small>{system.activeInsights} active finding{String(system.activeInsights) === "1" ? "" : "s"}</small> : null}
        </div>
      ))}</div> : <p className="operational-findings-empty">Subsystem behavior will appear after a completed telemetry analysis.</p>}
    </section>
  );
}

function PriorityFinding({ insight, model, helpers, onOpen }) {
  if (!insight) return null;
  const confidence = confidencePercent(insight) || helpers.formatConfidenceDisplay(insight.confidence, insight.confidenceScore);
  const supportingCount = new Set([...(insight.observedFacts ?? []), ...(insight.publicEvidenceItems ?? [])].filter(Boolean)).size;
  return (
    <section className="command-section priority-finding" aria-labelledby="priority-finding-heading">
      <div className="command-section__header"><p className="command-section__label">Review first</p><h2 id="priority-finding-heading">Prioritized Finding</h2><p>Highest severity and confidence are reviewed first.</p></div>
      <article className="priority-finding__card">
        <div className="priority-finding__heading"><div><span>Affected subsystem</span><p>{insight.system || "Unavailable"}</p><h3>{titleFor(insight, helpers)}</h3></div><span className={`priority-finding__severity priority-finding__severity--${helpers.severityToTone(insight.severity)}`}>{severityLabel(insight.severity)}</span></div>
        <p className="priority-finding__explanation">{summaryFor(insight, helpers)}</p>
        <dl className="priority-finding__trust">
          <div><dt>Severity</dt><dd>{severityLabel(insight.severity)}</dd></div>
          {confidence ? <div><dt>Confidence</dt><dd>{confidence}</dd></div> : null}
          <div><dt>First detected</dt><dd>{insight.detectedAt || "Unavailable"}</dd></div>
          {model.telemetryStatus?.label ? <div><dt>Evidence quality</dt><dd>{model.telemetryStatus.label}</dd></div> : null}
          {model.dataCoveragePercent !== null && model.dataCoveragePercent !== undefined ? <div><dt>Data coverage</dt><dd>{model.dataCoveragePercent}%</dd></div> : null}
          {supportingCount > 0 ? <div><dt>Supporting observations</dt><dd>{supportingCount}</dd></div> : null}
          {Number(insight.changedRelationshipCount) > 0 ? <div><dt>Changed relationships</dt><dd>{insight.changedRelationshipCount}</dd></div> : null}
        </dl>
        <div className="priority-finding__action"><span>Recommended first action</span><strong>{firstAction(insight)}</strong></div>
        <button type="button" className="command-button" onClick={onOpen}>Open finding</button>
      </article>
    </section>
  );
}

function EngineeringFindings({ insights, selectedInsight, onSelectInsight, helpers }) {
  const queueRef = useRef(null);
  function handleKeyDown(event) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = Array.from(queueRef.current?.querySelectorAll("[data-priority-item='true']") ?? []);
    const index = buttons.indexOf(event.target); if (index < 0) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : event.key === "ArrowDown" ? Math.min(buttons.length - 1, index + 1) : Math.max(0, index - 1);
    buttons[next]?.focus();
  }
  return <section className="command-section command-section--findings" aria-labelledby="engineering-findings-heading">
    <div className="command-section__header"><h2 id="engineering-findings-heading">Engineering Findings</h2><p>{insights.length ? "Remaining findings, highest priority first." : "None active"}</p></div>
    {insights.length ? <div className="operational-findings-list" role="list" ref={queueRef} onKeyDown={handleKeyDown}>{insights.map((insight, index) => <div role="listitem" className="operational-finding-row-wrap" key={insight.id || index}><button type="button" className={selectedInsight?.id === insight.id ? "operational-finding-row is-selected" : "operational-finding-row"} data-priority-item="true" onClick={() => onSelectInsight?.(insight.id)}><span className="operational-finding-row__title">{titleFor(insight, helpers)}</span><span className={`operational-finding-row__severity operational-finding-row__severity--${helpers.severityToTone(insight.severity)}`}>{severityLabel(insight.severity)}</span><span className="operational-finding-row__confidence">{confidencePercent(insight) ? `Confidence ${confidencePercent(insight)}` : "Confidence unavailable"}</span><span className="operational-finding-row__summary">{summaryFor(insight, helpers)}</span></button></div>)}</div> : <div className="operational-empty operational-empty--inline"><p className="operational-findings-empty">{selectedInsight ? "No additional findings require review." : "Import telemetry to establish the baseline."}</p></div>}
  </section>;
}

function DetailRows({ rows = [], technical = false }) { const visible = rows.filter(([label, value]) => label && value !== null && value !== undefined && value !== ""); return visible.length ? <dl className={technical ? "dashboard-detail-rows dashboard-detail-rows--technical" : "dashboard-detail-rows"}>{visible.map(([label, value], index) => <div key={`${label}-${index}`}><dt>{label}</dt><dd>{technical ? <code>{String(value)}</code> : String(value)}</dd></div>)}</dl> : <p>No diagnostic details are available for this analysis yet.</p>; }
function AdvancedDashboardSection({ model }) { const history = model.analysisHistory?.length ? model.analysisHistory : model.historyItems; return <section className="command-section command-section--advanced" aria-labelledby="dashboard-advanced-heading"><div className="command-section__header"><h2 id="dashboard-advanced-heading">Analysis Details</h2><p>Supporting records and diagnostics.</p></div><div className="dashboard-advanced-stack"><details><summary>Analysis History</summary>{history?.length ? <ul className="dashboard-advanced-list">{history.slice(0, 6).map((item, index) => <li key={item.id ?? index}>{item.datasetName ?? item.title ?? item.detail ?? "Historical analysis"}</li>)}</ul> : <p>No saved analysis history is available.</p>}</details><details><summary>Dataset and Connector Details</summary><DetailRows rows={model.dataSourceRows} /></details><details><summary>Support Diagnostics</summary><DetailRows rows={[...model.analysisMetadataRows, ...model.behaviorWindowRows]} technical /></details><details><summary>Analysis Record</summary><pre className="advanced-json"><code>{model.rawResultJson}</code></pre></details></div></section>; }

export default function CommandCenterView({ model, helpers, selectedInsight, onSelectInsight, onConnectLiveData, onFocusInvestigation }) {
  const queue = useMemo(() => rankedInsights(model.insights), [model.insights]);
  const top = queue[0] ?? null;
  const active = selectedInsight && queue.some((item) => item.id === selectedInsight.id) ? selectedInsight : top;
  const status = useMemo(() => operationalStatus(model, queue), [model, queue]);
  const systems = model.analysisComplete ? model.dashboardSystemCards : [];
  const remaining = top ? queue.filter((item) => item.id !== top.id) : [];
  return <div className="operational-command-center" data-testid="operational-command-center">
    <OperationalFingerprintSummary model={model} status={status} queue={queue} topInsight={top} helpers={helpers} onConnectLiveData={onConnectLiveData} />
    <SubsystemBehavior systems={systems} />
    <PriorityFinding insight={top} model={model} helpers={helpers} onOpen={() => { onSelectInsight?.(top?.id); onFocusInvestigation?.(); }} />
    {top ? <div className="selected-investigation-panel"><OperatorInsightDetail insight={top} inline focusMode /></div> : null}
    <EngineeringFindings insights={remaining} selectedInsight={active?.id === top?.id ? null : active} onSelectInsight={onSelectInsight} helpers={helpers} />
    {active && active.id !== top?.id ? <div className="selected-investigation-panel"><OperatorInsightDetail insight={active} inline focusMode /></div> : null}
    <section className="command-section command-section--systems" aria-labelledby="system-overview-heading"><div className="command-section__header"><h2 id="system-overview-heading">Discovered Systems</h2><p>Detected in the dataset.</p></div>{systems.length ? <div className="system-overview-list" role="list">{systems.map((system) => <div className="system-overview-row" role="listitem" key={system.id}><strong>{system.name}</strong><span>{system.status}</span><span>{system.activeInsights} active finding{String(system.activeInsights) === "1" ? "" : "s"}</span></div>)}</div> : <p className="operational-findings-empty">No systems are listed because no completed telemetry analysis is active.</p>}</section>
    <AdvancedDashboardSection model={model} />
  </div>;
}
