import { useMemo, useState } from "react";

import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";
import FindingClassificationSummary from "./FindingClassificationSummary";

function severityLabel(value) {
  const clean = String(value ?? "").trim().toLowerCase();
  if (clean.includes("critical")) return "Critical";
  if (clean.includes("high") || clean.includes("unstable")) return "High";
  if (clean.includes("moderate") || clean.includes("review") || clean.includes("elevated")) return "Moderate";
  if (clean.includes("low")) return "Low";
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
  if (label.includes("moderate") || label.includes("medium")) return 70;
  if (label.includes("low")) return 45;
  return 0;
}

function rankedInsights(insights) {
  return [...(Array.isArray(insights) ? insights : [])].filter(Boolean).sort((left, right) =>
    severityRank(right?.severity) - severityRank(left?.severity)
    || confidenceRank(right) - confidenceRank(left)
    || String(left?.summary ?? left?.id ?? "").localeCompare(String(right?.summary ?? right?.id ?? ""))
  );
}

function firstSentence(value, fallback) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return fallback;
  const sentence = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
  return /[.!?]$/.test(sentence) ? sentence : `${sentence}.`;
}

function titleFor(insight, helpers) {
  return helpers.formatInsightTitle(insight) || insight?.summary || "Operating behavior changed";
}

function evidenceFor(insight, helpers) {
  const relationships = helpers.insightRelationshipLabels(insight);
  const summary = helpers.operatorSummaryBriefing(insight, relationships)[0]
    || insight?.whatChanged
    || insight?.whatHappened
    || insight?.evidenceSummary;
  return firstSentence(summary, "Recorded behavior changed from the learned baseline.");
}

function nextCheckFor(insight) {
  const structured = insight?.investigationGuidance?.[0]?.check;
  const legacy = insight?.recommendedFirstAction
    || insight?.recommendedAction
    || insight?.operatorCheck
    || insight?.recommendedInvestigation?.[0];
  return firstSentence(structured || legacy, "Review the source data and affected relationship.");
}

function isSerious(insight) {
  const presentation = normalizeFindingPresentation(insight);
  const status = String(insight?.reviewStatus ?? insight?.hypothesisStatus ?? insight?.status ?? "").toLowerCase();
  return severityRank(insight?.severity) >= 3
    || presentation.type === "unexplained_systemic_change"
    || /strengthen|escalat|critical|urgent/.test(status);
}

function isInstrumentation(insight) {
  return normalizeFindingPresentation(insight).type === "possible_instrumentation_issue";
}

function isMonitoring(insight, acknowledgedIds) {
  if (acknowledgedIds.has(insight?.id)) return true;
  const status = String(insight?.reviewStatus ?? insight?.hypothesisStatus ?? insight?.status ?? "").toLowerCase();
  return /acknowledged|monitor|resolved|closed/.test(status)
    || normalizeFindingPresentation(insight).type === "known_operational_change";
}

function normalizedSystems(model) {
  return model?.analysisComplete && Array.isArray(model?.dashboardSystemCards)
    ? model.dashboardSystemCards.filter(Boolean)
    : [];
}

function FindingActions({ insight, acknowledged, onReview, onAcknowledge, onViewEvidence }) {
  return (
    <div className="shift-finding-card__actions" aria-label={`Actions for ${insight?.system || "finding"}`}>
      <button type="button" className="command-button" onClick={onReview}>Review</button>
      <button
        type="button"
        className="secondary-command-button secondary-command-button--quiet"
        onClick={onAcknowledge}
        aria-pressed={acknowledged}
      >
        {acknowledged ? "Acknowledged" : "Acknowledge"}
      </button>
      <button type="button" className="operational-link-button" onClick={onViewEvidence}>View evidence</button>
    </div>
  );
}

function FindingCard({ insight, helpers, acknowledged, onReview, onAcknowledge, onViewEvidence, prominent = false }) {
  const visibleFinding = acknowledged ? { ...insight, status: "Acknowledged" } : insight;
  return (
    <article
      className={prominent ? "shift-finding-card shift-finding-card--prominent" : "shift-finding-card"}
      data-testid="compact-finding-card"
      data-finding-id={insight?.id}
    >
      <header className="shift-finding-card__header">
        <span className="section-token">{insight?.system || "Unassigned system"}</span>
        <h3>{titleFor(insight, helpers)}</h3>
      </header>
      <FindingClassificationSummary finding={visibleFinding} compact />
      <p className="shift-finding-card__evidence">{evidenceFor(insight, helpers)}</p>
      <div className="shift-finding-card__next">
        <span>Next check</span>
        <p>{nextCheckFor(insight)}</p>
      </div>
      <FindingActions
        insight={insight}
        acknowledged={acknowledged}
        onReview={onReview}
        onAcknowledge={onAcknowledge}
        onViewEvidence={onViewEvidence}
      />
    </article>
  );
}

function EmptyShiftStart({ onImportDataset, onConnectLiveData }) {
  return (
    <section className="shift-start-summary shift-start-summary--empty" aria-labelledby="shift-start-title">
      <span className="section-token">Shift start</span>
      <h2 id="shift-start-title">Baseline not established</h2>
      <p>Import telemetry to begin comparison.</p>
      <div className="shift-start-summary__actions">
        <button type="button" className="command-button" onClick={onImportDataset}>Import dataset</button>
        <button type="button" className="secondary-command-button secondary-command-button--quiet" onClick={onConnectLiveData}>Connect telemetry</button>
      </div>
    </section>
  );
}

function ShiftStartSummary({ model, seriousFinding, instrumentationCount, queueCount, helpers, acknowledged, onReview, onAcknowledge, onViewEvidence, onConnectLiveData }) {
  if (!model.analysisComplete) {
    const analyzing = model.uiState?.key === "analyzing";
    return (
      <section className="shift-start-summary" aria-labelledby="shift-start-title">
        <span className="section-token">Shift start</span>
        <h2 id="shift-start-title">{analyzing ? "Analysis in progress" : "Baseline not established"}</h2>
        <p>{analyzing ? "Comparing current operation with the learned baseline." : "Connect telemetry or import a dataset."}</p>
        {!analyzing ? <button type="button" className="command-button" onClick={onConnectLiveData}>Add data source</button> : null}
      </section>
    );
  }

  if (seriousFinding) {
    return (
      <section className="shift-start-summary shift-start-summary--attention" aria-labelledby="shift-start-title">
        <div className="shift-start-summary__heading">
          <span className="section-token">Needs attention</span>
          <h2 id="shift-start-title">Escalated engineering review</h2>
        </div>
        <FindingCard
          insight={seriousFinding}
          helpers={helpers}
          prominent
          acknowledged={acknowledged}
          onReview={onReview}
          onAcknowledge={onAcknowledge}
          onViewEvidence={onViewEvidence}
        />
      </section>
    );
  }

  const secondary = instrumentationCount
    ? `${instrumentationCount} instrumentation issue${instrumentationCount === 1 ? " remains" : "s remain"} under review.`
    : queueCount
      ? `${queueCount} lower-priority finding${queueCount === 1 ? " remains" : "s remain"} under review.`
      : "All monitored systems are quiet.";
  return (
    <section className="shift-start-summary shift-start-summary--quiet" aria-labelledby="shift-start-title" role="status">
      <span className="section-token">Shift start</span>
      <h2 id="shift-start-title">No new unexplained system changes.</h2>
      <p>{secondary}</p>
    </section>
  );
}

function FindingSection({ title, findings, helpers, acknowledgedIds, onReview, onAcknowledge, onViewEvidence }) {
  if (!findings.length) return null;
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return (
    <section className="shift-finding-section" aria-labelledby={`${slug}-title`}>
      <div className="shift-finding-section__header">
        <h2 id={`${slug}-title`}>{title}</h2>
        <span aria-label={`${findings.length} findings`}>{findings.length}</span>
      </div>
      <div className="shift-finding-grid">
        {findings.slice(0, 3).map((insight, index) => (
          <FindingCard
            key={insight.id || `${slug}-${index}`}
            insight={insight}
            helpers={helpers}
            acknowledged={acknowledgedIds.has(insight.id)}
            onReview={() => onReview(insight.id)}
            onAcknowledge={() => onAcknowledge(insight.id)}
            onViewEvidence={() => onViewEvidence(insight.id)}
          />
        ))}
      </div>
      {findings.length > 3 ? <p className="shift-finding-section__remaining">{findings.length - 3} more available in Engineering Findings.</p> : null}
    </section>
  );
}

function QuietSystems({ systems }) {
  const quiet = systems.filter((system) => Number(system?.activeInsights) === 0);
  if (!quiet.length) return null;
  return (
    <section className="quiet-systems" aria-labelledby="quiet-systems-title">
      <div className="shift-finding-section__header">
        <h2 id="quiet-systems-title">Quiet systems</h2>
        <span>{quiet.length}</span>
      </div>
      <p>{quiet.slice(0, 5).map((system) => system.name).filter(Boolean).join(" · ")}</p>
      {quiet.length > 5 ? <small>+{quiet.length - 5} more</small> : null}
    </section>
  );
}

export default function CommandCenterView({ model, helpers, onOpenInvestigation, onImportDataset, onConnectLiveData }) {
  const queue = useMemo(() => rankedInsights(model.insights), [model.insights]);
  const [acknowledgedIds, setAcknowledgedIds] = useState(() => new Set());
  const systems = normalizedSystems(model);
  const emptyState = model.uiState?.key === "noTelemetry";

  const seriousFinding = queue.find((insight) => isSerious(insight) && !isMonitoring(insight, acknowledgedIds)) ?? null;
  const remaining = seriousFinding ? queue.filter((insight) => insight.id !== seriousFinding.id) : queue;
  const monitoring = remaining.filter((insight) => isMonitoring(insight, acknowledgedIds));
  const attention = remaining.filter((insight) => !isMonitoring(insight, acknowledgedIds) && (isSerious(insight) || isInstrumentation(insight)));
  const fresh = remaining.filter((insight) => !monitoring.includes(insight) && !attention.includes(insight));
  const instrumentationCount = queue.filter(isInstrumentation).length;

  function acknowledge(insightId) {
    setAcknowledgedIds((current) => {
      const next = new Set(current);
      next.add(insightId);
      return next;
    });
  }

  const review = (insightId) => onOpenInvestigation?.(insightId);
  const viewEvidence = (insightId) => onOpenInvestigation?.(insightId, { focusTarget: "insight-evidence" });

  return (
    <div className={emptyState ? "operational-command-center operational-command-center--empty" : "operational-command-center"} data-testid="operational-command-center">
      {emptyState ? (
        <EmptyShiftStart onImportDataset={onImportDataset} onConnectLiveData={onConnectLiveData} />
      ) : (
        <ShiftStartSummary
          model={model}
          seriousFinding={seriousFinding}
          instrumentationCount={instrumentationCount}
          queueCount={queue.length}
          helpers={helpers}
          acknowledged={seriousFinding ? acknowledgedIds.has(seriousFinding.id) : false}
          onReview={() => review(seriousFinding?.id)}
          onAcknowledge={() => acknowledge(seriousFinding?.id)}
          onViewEvidence={() => viewEvidence(seriousFinding?.id)}
          onConnectLiveData={onConnectLiveData}
        />
      )}
      {!emptyState ? <FindingSection title="New since last review" findings={fresh} helpers={helpers} acknowledgedIds={acknowledgedIds} onReview={review} onAcknowledge={acknowledge} onViewEvidence={viewEvidence} /> : null}
      {!emptyState ? <FindingSection title="Needs attention" findings={attention} helpers={helpers} acknowledgedIds={acknowledgedIds} onReview={review} onAcknowledge={acknowledge} onViewEvidence={viewEvidence} /> : null}
      {!emptyState ? <FindingSection title="Monitoring" findings={monitoring} helpers={helpers} acknowledgedIds={acknowledgedIds} onReview={review} onAcknowledge={acknowledge} onViewEvidence={viewEvidence} /> : null}
      {!emptyState ? <QuietSystems systems={systems} /> : null}
    </div>
  );
}
