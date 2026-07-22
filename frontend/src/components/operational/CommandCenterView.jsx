import { useMemo, useRef } from "react";

import AnalysisRecordDetails from "./AnalysisRecordDetails";

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

function findingConfidenceLabel(insight) {
  const explicit = String(insight?.confidence ?? "").trim().toLowerCase();
  const score = Number(insight?.confidenceScore ?? insight?.confidence_score);
  const percent = Number.isFinite(score) ? Math.round(Math.max(0, Math.min(100, score > 1 ? score : score * 100))) : null;
  let label = "Unavailable";
  if (explicit.includes("high")) label = "High";
  else if (explicit.includes("moderate")) label = "Moderate";
  else if (explicit.includes("low")) label = "Low";
  else if (Number.isFinite(score)) {
    const normalized = score > 1 ? score / 100 : score;
    label = normalized >= 0.85 ? "High" : normalized >= 0.6 ? "Moderate" : "Low";
  }
  return percent === null ? label : label + " · " + percent + "%";
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
  if (!model.analysisComplete) return { label: "Watching", tone: "neutral", explanation: model.commandCenterMessage || "Connect telemetry to establish the operating baseline." };
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

function normalizedSystemCards(model) {
  return model?.analysisComplete && Array.isArray(model?.dashboardSystemCards)
    ? model.dashboardSystemCards.filter(Boolean)
    : [];
}

function formatDetectedAt(value) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

function countSupportingObservations(insight) {
  return new Set([...(insight?.observedFacts ?? []), ...(insight?.publicEvidenceItems ?? []), ...(insight?.evidence ?? [])].filter(Boolean)).size;
}

function evidenceQuality(model) {
  if (model?.dataQualityNotice?.tone === "warning") {
    return { label: "Reduced", reason: model.dataQualityNotice.detail || "One or more monitored signals contained quality limitations." };
  }
  if (model?.telemetryStatus?.label) {
    return { label: model.telemetryStatus.label, reason: model.telemetryStatus.detail || "Operational data was sufficient for review." };
  }
  return { label: "Unavailable", reason: "Evidence quality has not been reported for this analysis." };
}

function EmptyOperatingStateSummary({ onConnectLiveData }) {
  return (
    <section className="command-section operating-state-card operating-state-card--empty command-section--neutral" aria-label="Operational Status">
      <h2 id="operating-state-heading" className="sr-only">Current state</h2>
      <div className="operating-state-card__main">
        <p className="command-section__label">Current state</p>
        <strong className="operating-state-card__status">Watching</strong>
      </div>
      <dl className="operating-state-card__meta">
        <div><dt>Baseline</dt><dd>Not established</dd></div>
        <div><dt>Evidence quality</dt><dd>No telemetry</dd></div>
      </dl>
      <div className="operating-state-card__actions">
        <div className="operating-state-card__action-group">
          <span>Primary action</span>
          <button type="button" className="command-button" onClick={onConnectLiveData}>Connect telemetry</button>
        </div>
        <div className="operating-state-card__action-group">
          <span>Secondary action</span>
          <button type="button" className="secondary-command-button secondary-command-button--quiet" onClick={onConnectLiveData}>Import dataset</button>
        </div>
      </div>
    </section>
  );
}

function OperatingStateSummary({ model, status, topInsight, helpers, systems, onConnectLiveData, onOpenInvestigation, onViewEvidence, emptyState }) {
  if (emptyState) return <EmptyOperatingStateSummary onConnectLiveData={onConnectLiveData} />;

  const affected = topInsight?.system || systems.find((system) => Number(system.activeInsights) > 0)?.name;
  const summary = topInsight && affected
    ? `The ${affected} subsystem moved away from its learned operating baseline.`
    : status.explanation;
  const quality = evidenceQuality(model);
  const coverage = model.dataCoveragePercent;
  const primaryAction = topInsight ? firstAction(topInsight) : "Connect telemetry or import operational data to establish the first behavior baseline.";

  return (
    <section className={`command-section operating-state-card command-section--${status.tone}`} aria-label="Operational Status">
      <h2 id="operating-state-heading" className="sr-only">Operational Fingerprint Summary</h2>
      <div className="operating-state-card__main">
        <p className="command-section__label">Current operating state</p>
        <strong className="operating-state-card__status">{status.label}</strong>
        {!model.analysisComplete ? <span className="operating-state-card__baseline-needed">Baseline Needed</span> : null}
        <p>{summary}</p>
      </div>
      <dl className="operating-state-card__meta">
        {topInsight ? <div><dt>Highest-priority finding</dt><dd>{titleFor(topInsight, helpers)}</dd></div> : null}
        {affected ? <div><dt>Affected subsystem</dt><dd>{affected}</dd></div> : null}
        {topInsight ? <div><dt>Severity</dt><dd>{severityLabel(topInsight.severity)}</dd></div> : null}
        {topInsight ? <div><dt>Finding confidence</dt><dd>{findingConfidenceLabel(topInsight)}</dd></div> : null}
        {topInsight ? <div><dt>First detected</dt><dd>{formatDetectedAt(topInsight.detectedAt)}</dd></div> : null}
        {coverage !== null && coverage !== undefined ? <div><dt>Data coverage</dt><dd>{coverage}%</dd></div> : null}
        <div><dt>Evidence quality</dt><dd>{quality.label}</dd></div>
      </dl>
      <div className="operating-state-card__action">
        <span>Primary recommended action</span>
        <strong>{primaryAction}</strong>
        <div className="operating-state-card__buttons">
          {topInsight ? <button type="button" className="command-button" onClick={onOpenInvestigation}>Open investigation</button> : <button type="button" className="command-button" onClick={onConnectLiveData}>Connect Live Telemetry</button>}
          {topInsight ? <button type="button" className="secondary-command-button secondary-command-button--quiet" onClick={onViewEvidence}>View supporting evidence</button> : <button type="button" className="secondary-command-button secondary-command-button--quiet" onClick={onConnectLiveData}>Import and Analyze Dataset</button>}
        </div>
      </div>
      <p className="operating-state-card__quality-note">Evidence quality is separate from finding confidence. {quality.reason}</p>
      {!model.analysisComplete && status.tone !== "loading" ? <p className="operating-state-card__quality-note">Neraium monitors connected telemetry, historians, databases, APIs, sensors, and imported datasets as read-only operational data sources.</p> : null}
    </section>
  );
}

function subsystemTone(system) {
  const status = String(system?.status || "").toLowerCase();
  const active = Number(system?.activeInsights) > 0;
  if (/critical|high|urgent/.test(status)) return "high";
  if (/investigation|changing|degrad|drift|review/.test(status)) return "investigation";
  if (/watch|elevated|moderate/.test(status) || active) return "watch";
  return "normal";
}

function subsystemStatus(system) {
  const status = String(system?.status || "").trim();
  if (!status) return Number(system?.activeInsights) > 0 ? "Watch" : "Normal";
  if (/critical/i.test(status)) return "High severity";
  if (/stable|healthy|normal/i.test(status)) return "Normal";
  if (/changing|investigation|review|degrad|drift/i.test(status)) return "Investigation recommended";
  return status;
}

function SubsystemBehavior({ systems = [], emptyState = false }) {
  if (emptyState) {
    return (
      <section className="command-section subsystem-behavior subsystem-behavior--empty" aria-labelledby="subsystem-behavior-heading">
        <div className="command-section__header"><h2 id="subsystem-behavior-heading">Subsystems</h2></div>
        <strong className="command-empty-status">No active status available</strong>
      </section>
    );
  }

  const safeSystems = Array.isArray(systems) ? systems.filter(Boolean) : [];
  return (
    <section className="command-section subsystem-behavior" aria-labelledby="subsystem-behavior-heading">
      <div className="command-section__header"><h2 id="subsystem-behavior-heading">Subsystem Behavior</h2><p>Compact view of active findings by subsystem.</p></div>
      {safeSystems.length ? <div className="subsystem-behavior__list" role="list">{safeSystems.map((system, index) => {
        const activeCount = Number(system.activeInsights) || 0;
        return (
          <div className={`subsystem-behavior__row subsystem-behavior__row--${subsystemTone(system)}`} role="listitem" key={system.id || system.name || `subsystem-${index}`}>
            <span className="subsystem-behavior__indicator" aria-hidden="true" />
            <div className="subsystem-behavior__identity"><strong>{system.name || "Unnamed subsystem"}</strong><span>{activeCount > 0 ? "Trend changed" : "Aligned"}</span></div>
            <span className="subsystem-behavior__state">{subsystemStatus(system)}</span>
            <small>{activeCount} active finding{activeCount === 1 ? "" : "s"}</small>
          </div>
        );
      })}</div> : <div><strong>None active</strong><p className="operational-findings-empty">Subsystem status will appear after connected telemetry or operational data is analyzed.</p></div>}
    </section>
  );
}

function PriorityFinding({ insight, model, helpers, onOpen }) {
  if (!insight) return null;
  const supportingCount = countSupportingObservations(insight);
  const changedCount = Number(insight.changedRelationshipCount) || 0;
  const quality = evidenceQuality(model);
  return (
    <section className="command-section priority-finding" aria-labelledby="priority-finding-heading">
      <div className="command-section__header"><p className="command-section__label">Review first</p><h2 id="priority-finding-heading">Prioritized Finding</h2><p>Highest operator priority based on severity and confidence.</p></div>
      <article className="priority-finding__card">
        <div className="priority-finding__heading"><div><span>Affected subsystem</span><p>{insight.system || "Unavailable"}</p><h3>{titleFor(insight, helpers)}</h3></div><span className={`priority-finding__severity priority-finding__severity--${helpers.severityToTone(insight.severity)}`}>{severityLabel(insight.severity)}</span></div>
        <p className="priority-finding__explanation">{summaryFor(insight, helpers)}</p>
        <dl className="priority-finding__trust">
          <div><dt>Finding confidence</dt><dd>{findingConfidenceLabel(insight)}</dd></div>
          <div><dt>First detected</dt><dd>{formatDetectedAt(insight.detectedAt)}</dd></div>
          <div><dt>Changed relationships</dt><dd>{changedCount || "Not reported"}</dd></div>
          <div><dt>Supporting observations</dt><dd>{supportingCount || "Not reported"}</dd></div>
        </dl>
        <div className="priority-finding__action"><span>Recommended first action</span><strong>{firstAction(insight)}</strong></div>
        <div className="priority-finding__footer">
          <button type="button" className="command-button" onClick={onOpen}>Open finding</button>
          <details className="priority-finding__details">
            <summary>Analysis details</summary>
            <dl>
              <div><dt>Severity</dt><dd>{severityLabel(insight.severity)}</dd></div>
              <div><dt>Evidence quality</dt><dd>{quality.label}</dd></div>
              {model.dataCoveragePercent !== null && model.dataCoveragePercent !== undefined ? <div><dt>Data coverage</dt><dd>{model.dataCoveragePercent}%</dd></div> : null}
              {model.telemetryStatus?.label ? <div><dt>Data quality</dt><dd>{model.telemetryStatus.label}</dd></div> : null}
            </dl>
          </details>
        </div>
      </article>
    </section>
  );
}

function EngineeringFindings({ insights, selectedInsight, onSelectInsight, helpers, emptyState = false }) {
  const queueRef = useRef(null);
  function handleKeyDown(event) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = Array.from(queueRef.current?.querySelectorAll("[data-priority-item='true']") ?? []);
    const index = buttons.indexOf(event.target); if (index < 0) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : event.key === "ArrowDown" ? Math.min(buttons.length - 1, index + 1) : Math.max(0, index - 1);
    buttons[next]?.focus();
  }
  if (emptyState) return <section className="command-section command-section--findings command-section--findings-empty" aria-labelledby="engineering-findings-heading">
    <div className="command-section__header"><h2 id="engineering-findings-heading">Engineering Findings</h2></div>
    <strong className="command-empty-status">None active</strong>
  </section>;

  return <section className="command-section command-section--findings" aria-labelledby="engineering-findings-heading">
    <div className="command-section__header"><h2 id="engineering-findings-heading">Engineering Findings</h2><p>{insights.length ? "Additional findings in priority order." : "No additional active findings."}</p></div>
    {insights.length ? <div className="operational-findings-list" role="list" ref={queueRef} onKeyDown={handleKeyDown}>{insights.map((insight, index) => <div role="listitem" className="operational-finding-row-wrap" key={insight.id || index}><button type="button" className={selectedInsight?.id === insight.id ? "operational-finding-row is-selected" : "operational-finding-row"} data-priority-item="true" onClick={() => onSelectInsight?.(insight.id)}><span className="operational-finding-row__title">{titleFor(insight, helpers)}</span><span className={`operational-finding-row__severity operational-finding-row__severity--${helpers.severityToTone(insight.severity)}`}>{severityLabel(insight.severity)}</span><span className="operational-finding-row__confidence">Finding confidence {findingConfidenceLabel(insight)}</span><span className="operational-finding-row__summary">{summaryFor(insight, helpers)}</span></button></div>)}</div> : <div className="operational-empty operational-empty--inline"><p className="operational-findings-empty">{selectedInsight ? "No additional findings require review." : "Connect telemetry to establish the baseline."}</p></div>}
  </section>;
}

function DetailRows({ rows = [], technical = false }) { const visible = rows.filter(([label, value]) => label && value !== null && value !== undefined && value !== ""); return visible.length ? <dl className={technical ? "dashboard-detail-rows dashboard-detail-rows--technical" : "dashboard-detail-rows"}>{visible.map(([label, value], index) => <div key={`${label}-${index}`}><dt>{label}</dt><dd>{technical ? <code>{String(value)}</code> : String(value)}</dd></div>)}</dl> : <p>No diagnostic details are available for this analysis yet.</p>; }
function historyDisplayText(value) {
  if (value === null || value === undefined) return "";
  if (["string", "number", "boolean"].includes(typeof value)) return String(value).trim();
  if (Array.isArray(value)) return value.map(historyDisplayText).filter(Boolean).join(", ");
  if (typeof value === "object") return historyDisplayText(value.filename ?? value.last_filename ?? value.source_file ?? value.name ?? value.label ?? value.title ?? value.detail ?? value.status ?? value.value);
  return String(value ?? "").trim();
}

function historyItemLabel(item) {
  return historyDisplayText(item?.datasetName) || historyDisplayText(item?.title) || historyDisplayText(item?.detail) || "Historical analysis";
}

function AdvancedDashboardSection({ model }) { const history = model.analysisHistory?.length ? model.analysisHistory : model.historyItems; return <section className="command-section command-section--advanced" aria-labelledby="dashboard-advanced-heading"><div className="command-section__header"><h2 id="dashboard-advanced-heading">Analysis Details</h2><p>Supporting records and diagnostics.</p></div><div className="dashboard-advanced-stack"><details><summary>Analysis History</summary>{history?.length ? <ul className="dashboard-advanced-list">{history.slice(0, 6).map((item, index) => <li key={historyDisplayText(item?.id) || index}>{historyItemLabel(item)}</li>)}</ul> : <p>No saved analysis history is available.</p>}</details><details><summary>Dataset and Connector Details</summary><DetailRows rows={model.dataSourceRows} /></details><details><summary>Support Diagnostics</summary><DetailRows rows={[...model.analysisMetadataRows, ...model.behaviorWindowRows]} technical /></details><AnalysisRecordDetails summary="Analysis Record" payload={model.rawAnalysisPayload} fileName={model.rawAnalysisFilename} /></div></section>; }

export default function CommandCenterView({ model, helpers, selectedInsight, onOpenInvestigation, onConnectLiveData }) {
  const queue = useMemo(() => rankedInsights(model.insights), [model.insights]);
  const top = queue[0] ?? null;
  const active = selectedInsight && queue.some((item) => item.id === selectedInsight.id) ? selectedInsight : top;
  const status = useMemo(() => operationalStatus(model, queue), [model, queue]);
  const systems = normalizedSystemCards(model);
  const remaining = top ? queue.filter((item) => item.id !== top.id) : [];
  const emptyState = !model.analysisComplete && status.tone !== "loading";
  const openTop = () => onOpenInvestigation?.(top?.id);
  const viewEvidence = () => onOpenInvestigation?.(top?.id, { focusTarget: "insight-evidence" });

  return <div className={emptyState ? "operational-command-center operational-command-center--empty" : "operational-command-center"} data-testid="operational-command-center">
    <OperatingStateSummary model={model} status={status} topInsight={top} helpers={helpers} systems={systems} onConnectLiveData={onConnectLiveData} onOpenInvestigation={openTop} onViewEvidence={viewEvidence} emptyState={emptyState} />
    <SubsystemBehavior systems={systems} emptyState={emptyState} />
    <PriorityFinding insight={top} model={model} helpers={helpers} onOpen={openTop} />
    <EngineeringFindings insights={remaining} selectedInsight={active?.id === top?.id ? null : active} onSelectInsight={(insightId) => onOpenInvestigation?.(insightId)} helpers={helpers} emptyState={emptyState} />
    {!emptyState ? <section className="command-section command-section--systems" aria-labelledby="system-overview-heading"><div className="command-section__header"><h2 id="system-overview-heading">Discovered Systems</h2><p>Detected in the operational data.</p></div>{systems.length ? <div className="system-overview-list" role="list">{systems.map((system) => <div className="system-overview-row" role="listitem" key={system.id}><strong>{system.name}</strong><span>{subsystemStatus(system)}</span><span>{Number(system.activeInsights) || 0} active finding{String(Number(system.activeInsights) || 0) === "1" ? "" : "s"}</span></div>)}</div> : <p className="operational-findings-empty">No systems are listed because no completed telemetry analysis is active.</p>}</section> : null}
    {!emptyState ? <AdvancedDashboardSection model={model} /> : null}
  </div>;
}
