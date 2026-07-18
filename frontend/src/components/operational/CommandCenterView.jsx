import { useMemo, useRef } from "react";

import OperatorInsightDetail from "./OperatorInsightDetail";
import OperationalOrb from "./OperationalOrb";

function confidenceFallback(severity) {
  const text = String(severity ?? "").toLowerCase();
  if (text.includes("high") || text.includes("critical")) return "High";
  if (text.includes("moderate") || text.includes("review")) return "Moderate";
  return "Low";
}

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
  const severity = severityLabel(value).toLowerCase();
  if (severity === "critical") return 4;
  if (severity === "high") return 3;
  if (severity === "moderate") return 2;
  return 1;
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

function dashboardInsightTitle(insight, relationships, fallback) {
  const supplied = String(insight?.summary || insight?.rawSummary || fallback || "").trim();
  if (supplied && !/relationships?\s+(changed|shifted)|behavior\s+changed/i.test(supplied)) return supplied;
  const relationshipContext = (relationships ?? []).join(" ").toLowerCase();
  const context = [insight?.system, insight?.rawSystemName, insight?.title, insight?.summary, relationshipContext].join(" ").toLowerCase();
  if (/conductivity|chemical|chlor|dose|quality|ph|orp/.test(relationshipContext)) return "Control relationship changed";
  if (/(filter|differential pressure|dp)/.test(relationshipContext)) return "Resistance relationship changed";
  if (/pump|vfd|motor|power/.test(context)) return "Power relationship changed";
  if (/(flow|pressure|hydraulic)/.test(relationshipContext)) return "Flow and pressure relationship changed";
  if (/cool|chill|tower|thermal|condenser/.test(context)) return "Thermal relationship changed";
  return String(fallback ?? "Operating behavior changed").replace(/Relationship Changed/i, "relationship changed");
}

function sanitizeId(value, fallback = "item") {
  return String(value ?? fallback)
    .replace(/[^a-zA-Z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || fallback;
}

function rankedInsights(insights) {
  return [...(insights ?? [])].sort((left, right) => {
    const severityDelta = severityRank(right?.severity) - severityRank(left?.severity);
    if (severityDelta !== 0) return severityDelta;
    const confidenceDelta = confidenceRank(right) - confidenceRank(left);
    if (confidenceDelta !== 0) return confidenceDelta;
    return String(left?.summary ?? left?.id ?? "").localeCompare(String(right?.summary ?? right?.id ?? ""));
  });
}

function operationalStatus(model, queue) {
  if (model.uiState?.key === "analyzing") {
    return {
      label: "Analyzing operation",
      tone: "loading",
      orbStatus: "learning",
      stage: "Evidence → relationships → baseline",
      explanation: "Comparing current operation with the baseline.",
    };
  }

  if (!model.analysisComplete) {
    return {
      label: model.commandCenterTitle || "Baseline Needed",
      tone: "neutral",
      orbStatus: "awaiting",
      stage: null,
      explanation: model.commandCenterMessage || "Import telemetry to establish the operating baseline.",
    };
  }

  const criticalCount = queue.filter((insight) => severityLabel(insight?.severity) === "Critical").length;
  const highCount = queue.filter((insight) => severityLabel(insight?.severity) === "High").length;
  const topInsight = queue[0] ?? null;
  const explanation = topInsight
    ? statusExplanationForInsight(topInsight)
    : "Current operation remains aligned with learned operating relationships.";

  if (criticalCount > 0 || highCount > 1) {
    return {
      label: "Urgent Investigation",
      tone: "critical",
      orbStatus: "critical",
      stage: null,
      explanation,
    };
  }

  if (queue.length > 0 || model.behaviorState === "Behavior Shift Detected") {
    return {
      label: "Investigation Recommended",
      tone: "warning",
      orbStatus: "warning",
      stage: null,
      explanation,
    };
  }

  return {
    label: "Stable",
    tone: "healthy",
    orbStatus: "healthy",
    stage: null,
    explanation,
  };
}

function statusExplanationForInsight(insight) {
  const relationshipCount = Number(insight?.changedRelationshipCount ?? insight?.affectedRelationships?.length ?? insight?.contributingRelationships?.length ?? 0);
  if (relationshipCount > 1) return "Several relationships moved off baseline.";
  if (relationshipCount === 1) return "One key relationship moved off baseline.";
  return "Operating behavior changed.";
}

function OperationalStatusSection({ model, status, onConnectLiveData }) {
  return (
    <section className={`command-section command-section--status command-section--${status.tone}`} aria-labelledby="operational-status-heading">
      <h2 id="operational-status-heading">Operational Status</h2>
      <OperationalOrb
        minimal
        hideVisualLabel
        state={{ ...model.orb, label: status.label, visualLabel: "Operational Status" }}
        status={status.orbStatus}
      />
      {status.stage ? <p className="operational-status-stage">{status.stage}</p> : null}
      <p className="operational-status-value">{status.label}</p>
      <p className="operational-status-explanation">{status.explanation}</p>
      {!model.analysisComplete && status.tone !== "loading" ? (
        <div className="operational-actions operational-status-actions">
          <button type="button" className="command-button" onClick={onConnectLiveData}>Import and Analyze Dataset</button>
          <button type="button" className="secondary-command-button" onClick={onConnectLiveData}>Connect Live Telemetry</button>
        </div>
      ) : null}
    </section>
  );
}

function OperationalFindings({ insights, selectedInsight, onSelectInsight, helpers }) {
  const queueRef = useRef(null);
  const { formatConfidenceDisplay, formatInsightTitle, insightRelationshipLabels, operatorSummaryBriefing } = helpers;

  function handleKeyDown(event) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = Array.from(queueRef.current?.querySelectorAll("[data-priority-item='true']") ?? []);
    const currentIndex = buttons.indexOf(event.target);
    if (currentIndex === -1) return;
    event.preventDefault();
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? buttons.length - 1
        : event.key === "ArrowDown"
          ? Math.min(buttons.length - 1, currentIndex + 1)
          : Math.max(0, currentIndex - 1);
    buttons[nextIndex]?.focus();
  }

  if (!insights.length) {
    return (
      <section className="command-section command-section--findings" aria-labelledby="operational-findings-heading">
        <div className="command-section__header">
          <h2 id="operational-findings-heading">Operational Insights</h2>
          <p>None active</p>
        </div>
        <p className="operational-findings-empty">Import telemetry to establish the baseline.</p>
      </section>
    );
  }

  const selectedDetailId = selectedInsight ? `selected-investigation-${sanitizeId(selectedInsight.id)}` : undefined;

  return (
    <section className="command-section command-section--findings" aria-labelledby="operational-findings-heading">
      <div className="command-section__header">
        <h2 id="operational-findings-heading">Operational Insights</h2>
        <p>Highest priority first.</p>
      </div>
      <div className="operational-findings-list" role="list" ref={queueRef} onKeyDown={handleKeyDown}>
        {insights.map((insight, index) => {
          const selected = selectedInsight?.id === insight.id;
          const relationships = insightRelationshipLabels(insight);
          const title = dashboardInsightTitle(insight, relationships, formatInsightTitle(insight));
          const confidence = confidencePercent(insight) || formatConfidenceDisplay(insight.confidence, insight.confidenceScore) || confidenceFallback(insight.severity);
          const detailId = `selected-investigation-${sanitizeId(insight.id, index + 1)}`;
          const summary = operatorSummaryBriefing(insight, relationships)[0] || statusExplanationForInsight(insight);
          return (
            <div className="operational-finding-row-wrap" role="listitem" key={insight.id || index}>
              <button
                type="button"
                className={selected ? "operational-finding-row is-selected" : "operational-finding-row"}
                data-priority-item="true"
                aria-expanded={selected}
                aria-controls={detailId}
                onClick={() => onSelectInsight?.(insight.id)}
              >
                <span className="operational-finding-row__title">{title}</span>
                <span className={`operational-finding-row__severity operational-finding-row__severity--${helpers.severityToTone(insight.severity)}`}>{severityLabel(insight.severity)}</span>
                <span className="operational-finding-row__confidence">{confidence}</span>
                <span className="operational-finding-row__summary">{summary}</span>
              </button>
            </div>
          );
        })}
      </div>
      {selectedInsight ? (
        <div className="selected-investigation-panel" id={selectedDetailId}>
          <OperatorInsightDetail insight={selectedInsight} inline focusMode />
        </div>
      ) : null}
    </section>
  );
}

function SystemOverview({ systems, model }) {
  return (
    <section className="command-section command-section--systems" aria-labelledby="system-overview-heading">
      <div className="command-section__header">
        <h2 id="system-overview-heading">Discovered Systems</h2>
        <p>Detected in the dataset.</p>
      </div>
      {systems.length ? (
        <div className="system-overview-list" role="list">
          {systems.map((system) => (
            <div className="system-overview-row" role="listitem" key={system.id}>
              <strong>{system.name}</strong>
              <span>{system.status}</span>
              <span>{system.activeInsights} active insight{String(system.activeInsights) === "1" ? "" : "s"}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="operational-findings-empty">{model.systemsSectionTitle}: {model.systemsSectionSubtitle}</p>
      )}
    </section>
  );
}

function AdvancedDashboardSection({ model }) {
  const history = model.analysisHistory?.length ? model.analysisHistory : model.historyItems;
  return (
    <section className="command-section command-section--advanced" aria-labelledby="dashboard-advanced-heading">
      <div className="command-section__header">
        <h2 id="dashboard-advanced-heading">Analysis Details</h2>
        <p>History and diagnostics stay collapsed.</p>
      </div>
      <div className="dashboard-advanced-stack">
        <details>
          <summary>Analysis History</summary>
          {history?.length ? (
            <ul className="dashboard-advanced-list">
              {history.slice(0, 6).map((item, index) => <li key={item.id ?? index}>{item.datasetName ?? item.title ?? item.detail ?? "Historical analysis"}</li>)}
            </ul>
          ) : <p>No saved analysis history is available.</p>}
        </details>
        <details>
          <summary>Dataset and Connector Details</summary>
          <DetailRows rows={model.dataSourceRows} />
        </details>
        <details>
          <summary>Support Diagnostics</summary>
          <DetailRows rows={[...model.analysisMetadataRows, ...model.behaviorWindowRows]} technical />
        </details>
        <details>
          <summary>Analysis Record</summary>
          <pre className="advanced-json"><code>{model.rawResultJson}</code></pre>
        </details>
      </div>
    </section>
  );
}

function DetailRows({ rows = [], technical = false }) {
  const visibleRows = rows.filter(([label, value]) => label && value !== null && value !== undefined && value !== "");
  if (!visibleRows.length) return <p>No details available.</p>;
  return (
    <dl className={technical ? "dashboard-detail-rows dashboard-detail-rows--technical" : "dashboard-detail-rows"}>
      {visibleRows.map(([label, value], index) => (
        <div key={`${label}-${index}`}>
          <dt>{label}</dt>
          <dd>{technical ? <code>{String(value)}</code> : String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function CommandCenterView({ model, helpers, selectedInsight, onSelectInsight, onConnectLiveData }) {
  const queue = useMemo(() => rankedInsights(model.insights), [model.insights]);
  const activeInsight = selectedInsight && queue.some((item) => item.id === selectedInsight.id)
    ? selectedInsight
    : queue[0] ?? null;
  const status = useMemo(() => operationalStatus(model, queue), [model, queue]);
  const systems = model.analysisComplete ? model.dashboardSystemCards : [];

  return (
    <div className="operational-command-center" data-testid="operational-command-center">
      <OperationalStatusSection model={model} status={status} onConnectLiveData={onConnectLiveData} />
      <OperationalFindings insights={queue} selectedInsight={activeInsight} onSelectInsight={onSelectInsight} helpers={helpers} />
      <SystemOverview systems={systems} model={model} />
      <AdvancedDashboardSection model={model} />
    </div>
  );
}
