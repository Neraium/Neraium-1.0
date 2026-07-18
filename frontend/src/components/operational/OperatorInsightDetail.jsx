import { lazy, Suspense } from "react";

const RelationshipExplorer = lazy(() => import("./RelationshipExplorer"));

function toList(...values) {
  return values.flatMap((value) => {
    if (Array.isArray(value)) return value;
    if (value === null || value === undefined || value === "") return [];
    return [value];
  });
}

function text(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number") return String(value).trim();
  if (typeof value === "object") {
    return text(value.description ?? value.summary ?? value.what_changed ?? value.whatChanged);
  }
  return "";
}

function unique(values) {
  const seen = new Set();
  return values.filter((value) => {
    const clean = text(value);
    if (!clean || seen.has(clean.toLowerCase())) return false;
    seen.add(clean.toLowerCase());
    return true;
  });
}

function humanize(value) {
  return text(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function confidenceLabel(insight) {
  const explicit = humanize(insight?.confidence);
  if (explicit) return explicit;
  const score = Number(insight?.confidenceScore);
  if (!Number.isFinite(score)) return "";
  const normalized = score > 1 ? score / 100 : score;
  if (normalized >= 0.85) return "High";
  if (normalized >= 0.6) return "Moderate";
  return "Low";
}

function confidencePercent(insight) {
  const score = Number(insight?.confidenceScore ?? insight?.confidence_score);
  if (!Number.isFinite(score)) return "";
  const normalized = score > 1 ? score : score * 100;
  return `${Math.round(Math.max(0, Math.min(100, normalized)))}%`;
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value) {
  const date = parseDate(value);
  if (!date) return text(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatDuration(startValue, endValue) {
  const start = parseDate(startValue);
  const end = parseDate(endValue);
  if (!start || !end || end <= start) return "";
  const hours = Math.round((end.getTime() - start.getTime()) / 3600000);
  if (hours < 48) return `${hours} hours`;
  const days = Math.round(hours / 24);
  if (days < 60) return `${days} days`;
  const months = Math.round(days / 30.44);
  return `${months} months`;
}

function relationshipMeasurement(evidence) {
  const candidates = toList(
    evidence?.relationship_delta,
    evidence?.relationshipDelta,
    evidence?.metric_delta,
    evidence?.metricDelta,
    evidence?.relevant_metric_changes,
    evidence?.relevantMetricChanges
  );

  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "object") continue;
    const baseline = Number(candidate.baseline_strength ?? candidate.baselineStrength ?? candidate.baseline_coupling ?? candidate.baselineCoupling);
    const current = Number(candidate.current_strength ?? candidate.currentStrength ?? candidate.current_coupling ?? candidate.currentCoupling);
    const delta = Number(candidate.correlation_delta ?? candidate.correlationDelta ?? candidate.coupling_delta ?? candidate.couplingDelta);
    if (Number.isFinite(baseline) && Number.isFinite(current)) {
      return {
        delta: Number.isFinite(delta) ? Math.abs(delta) : null,
        baseline,
        current,
      };
    }
  }

  const delta = Number(evidence?.relationship_delta?.correlation_delta ?? evidence?.relationshipDelta?.correlationDelta);
  const metricItems = toList(evidence?.metric_delta, evidence?.relevant_metric_changes, evidence?.relevantMetricChanges);
  const metricText = metricItems.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join(" ");
  const baselineMatch = metricText.match(/Baseline operating coupling:\s*(-?\d+(?:\.\d+)?)/i);
  const currentMatch = metricText.match(/Current operating coupling:\s*(-?\d+(?:\.\d+)?)/i);
  return {
    delta: Number.isFinite(delta) ? Math.abs(delta) : null,
    baseline: baselineMatch ? Number(baselineMatch[1]) : null,
    current: currentMatch ? Number(currentMatch[1]) : null,
  };
}

function signalName(value) {
  return humanize(value).replace(/\bDp\b/g, "DP");
}

function relationshipLabels(insight) {
  const explicit = toList(insight?.affectedRelationships).map(text).filter(Boolean);
  if (explicit.length) return explicit;
  return toList(insight?.contributingRelationships).map((relationship, itemIndex) => {
    if (!relationship || typeof relationship !== "object") return text(relationship);
    const columns = toList(
      relationship.display_columns,
      relationship.displayColumns,
      relationship.columns,
      relationship.source_columns,
      relationship.sourceColumns
    ).map(signalName).filter(Boolean);
    if (columns.length >= 2) return `${columns[0]} \u2194 ${columns[1]}`;
    return text(relationship) || "Supporting relationship " + (itemIndex + 1);
  }).filter(Boolean);
}

function comparisonRanges(evidence) {
  return evidence.flatMap((item) => toList(item?.source_time_ranges, item?.sourceTimeRanges))
    .filter((range) => range && typeof range === "object");
}

function buildChangeContext(insight, evidence) {
  const ranges = comparisonRanges(evidence);
  const currentStarts = ranges.map((range) => range.current_start ?? range.currentStart).filter(Boolean);
  const currentEnds = ranges.map((range) => range.current_end ?? range.currentEnd).filter(Boolean);
  const baselineStarts = ranges.map((range) => range.baseline_start ?? range.baselineStart).filter(Boolean);
  const baselineEnds = ranges.map((range) => range.baseline_end ?? range.baselineEnd).filter(Boolean);

  const earliestCurrent = currentStarts
    .map(parseDate)
    .filter(Boolean)
    .sort((a, b) => a - b)[0];
  const latestCurrent = currentEnds
    .map(parseDate)
    .filter(Boolean)
    .sort((a, b) => b - a)[0];
  const earliestBaseline = baselineStarts
    .map(parseDate)
    .filter(Boolean)
    .sort((a, b) => a - b)[0];
  const latestBaseline = baselineEnds
    .map(parseDate)
    .filter(Boolean)
    .sort((a, b) => b - a)[0];

  const measurements = evidence.map(relationshipMeasurement);
  const deltas = measurements.map((item) => item.delta).filter((value) => value !== null);
  const largestDelta = deltas.length ? Math.max(...deltas) : null;
  const changedCount = Number(insight?.changedRelationshipCount);

  const rows = [];
  if (earliestCurrent) rows.push(["Current comparison window began", formatDateTime(earliestCurrent)]);
  if (latestCurrent) rows.push(["Observed through", formatDateTime(latestCurrent)]);
  const currentDuration = formatDuration(earliestCurrent, latestCurrent);
  if (currentDuration) rows.push(["Current comparison span", currentDuration]);
  if (earliestBaseline && latestBaseline) rows.push(["Historical baseline period", `${formatDateTime(earliestBaseline)} to ${formatDateTime(latestBaseline)}`]);
  if (Number.isFinite(changedCount) && changedCount > 0) rows.push(["Relationships changed together", String(changedCount)]);
  if (largestDelta !== null) rows.push(["Largest relationship change magnitude", largestDelta.toFixed(2)]);
  if (insight?.detectedAt) rows.push(["Insight generated", formatDateTime(insight.detectedAt)]);

  return rows;
}

function buildOperationalMemory(insight) {
  const priorOccurrences = Number(
    insight?.priorOccurrenceCount ?? insight?.prior_occurrence_count ?? insight?.recurrenceCount ?? insight?.recurrence_count
  );
  const similarEvents = toList(
    insight?.similarHistoricalEvents,
    insight?.similar_historical_events,
    insight?.priorMatches,
    insight?.prior_matches
  );
  const rows = [];
  if (Number.isFinite(priorOccurrences)) rows.push(["Prior matching occurrences", String(priorOccurrences)]);
  return { rows, similarEvents };
}

function cleanOperationalImpact(value) {
  return text(value)
    .replace(/^Operational impact:\s*/i, "")
    .replace(/^If this persists,\s*/i, "If nothing is done, ")
    .replace(/\bequipment degradation\b/gi, "degraded operating performance")
    .replace(/\brecent maintenance\b/gi, "recent operating changes")
    .replace(/\bmaintenance\b/gi, "operating changes");
}

function splitOperationalImpacts(values) {
  return unique(values.flatMap((value) => cleanOperationalImpact(value).split(/\n|;|\u2022/g))
    .flatMap((value) => value.split(/(?<=\.)\s+(?=[A-Z])/g))
    .map((item) => item.trim())
    .filter(Boolean));
}

function defaultOperationalImpacts(causes, relationships) {
  const causeText = causes.join(" ").toLowerCase();
  const relationshipText = relationships.join(" ").toLowerCase();
  if (/filter|dp|pressure|pump|flow|hydraulic/.test(`${causeText} ${relationshipText}`)) {
    return [
      "Operating behavior moved away from baseline",
      "Efficiency or capacity may be degrading under comparable load",
      "Downstream control assumptions may be less reliable",
    ];
  }
  return [
    "Continued movement away from baseline",
    "Downstream assumptions may be less reliable",
    "Higher likelihood of manual investigation on the next operating cycle",
  ];
}


function insightSeverityLabel(insight) {
  const severity = humanize(insight?.severity);
  if (/critical/i.test(severity)) return "Critical";
  if (/high|unstable/i.test(severity)) return "High";
  if (/moderate|review|elevated/i.test(severity)) return "Moderate";
  return severity || "Low";
}

function usefulDiagnosticEntries(evidence) {
  const rows = [
    ["Time window", text(evidence?.time_window ?? evidence?.timeWindow)],
    ["Persistence / duration", text(evidence?.persistence_duration ?? evidence?.persistenceDuration)],
    ["Calculated percent change", evidence?.calculated_percent_delta ?? evidence?.calculatedPercentDelta],
    ["Signal identifiers", toList(evidence?.source_columns, evidence?.sourceColumns, evidence?.source_metrics, evidence?.sourceMetrics, evidence?.source_tags, evidence?.sourceTags)],
    ["Internal metric names", toList(evidence?.metric_delta, evidence?.relevant_metric_changes, evidence?.relevantMetricChanges)],
  ];

  return rows.filter(([, value]) => {
    if (Array.isArray(value)) return value.length > 0;
    if (value && typeof value === "object") return Object.keys(value).length > 0;
    const clean = text(value);
    return clean && clean.toLowerCase() !== "not available";
  });
}

function DiagnosticValue({ value }) {
  if (Array.isArray(value)) {
    return <ul className="operator-briefing-list operator-briefing-list--code">{value.map((item, index) => <li key={`${text(item)}-${index}`}><code>{typeof item === "object" ? JSON.stringify(item) : text(item)}</code></li>)}</ul>;
  }
  if (value && typeof value === "object") return <code>{JSON.stringify(value)}</code>;
  return <>{text(value)}</>;
}

function BulletList({ items }) {
  const visible = unique(items.map(text)).slice(0, 6);
  if (!visible.length) return null;
  return <ul className="operator-briefing-list">{visible.map((item) => <li key={item}>{item}</li>)}</ul>;
}

function CheckedList({ items }) {
  const visible = unique(items.map(text)).slice(0, 6);
  if (!visible.length) return null;
  return <ul className="operator-briefing-list operator-briefing-list--checked">{visible.map((item) => <li key={item}>{item}</li>)}</ul>;
}

function ContextGrid({ rows }) {
  if (!rows.length) return null;
  return (
    <dl className="operational-detail-grid">
      {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
  );
}

function Disclosure({ title, children, className = "", defaultOpen = false }) {
  return (
    <details className={`insight-disclosure ${className}`.trim()} open={defaultOpen}>
      <summary><span>{title}</span><span className="insight-disclosure__chevron" aria-hidden="true">?</span></summary>
      <div className="insight-disclosure__body">{children}</div>
    </details>
  );
}

function PriorityActions({ actions, signals = [], impacts = [], explain = false }) {
  const labels = ["Priority 1", "Priority 2", "Priority 3"];
  const reasons = [
    "Tests the strongest observed relationship change directly before other conditions can obscure it.",
    "Determines whether an operating or control change explains the deviation.",
    "Rules out equipment or instrumentation effects if the first checks do not explain the change.",
  ];
  return (
    <ol className={explain ? "investigation-priorities investigation-priorities--explained" : "investigation-priorities"}>
      {actions.slice(0, 3).map((action, index) => (
        <li key={action} className="investigation-card">
          {explain ? <span>{labels[index]}</span> : null}
          <strong>{action}</strong>
          {explain ? <dl className="investigation-card__details">
            <div><dt>Estimated impact</dt><dd>{impacts[index] || (index === 0 ? "High - validates the primary operational risk" : "Moderate - narrows the likely cause")}</dd></div>
            <div><dt>Supporting signals</dt><dd>{signals[index] || signals[0] || "Relationship change evidence"}</dd></div>
            <div><dt>Expected validation</dt><dd>{index === 0 ? "Confirm whether the observed shift is present at the affected equipment." : "Confirm or rule out this cause against current operation."}</dd></div>
            <div><dt>Why this order</dt><dd>{reasons[index]}</dd></div>
          </dl> : null}
        </li>
      ))}
    </ol>
  );
}

function focusInvestigationSection(sectionId) {
  const target = document.getElementById(sectionId);
  if (!target) return;
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  target.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  target.focus({ preventScroll: true });
}

function InvestigationDecisionPath({ evidenceCount, relationshipCount }) {
  const steps = [
    ["1", "Understand change", "Confirm the affected subsystem and operating status."],
    ["2", "Verify evidence", `${relationshipCount || "No"} relationship${relationshipCount === 1 ? "" : "s"} and ${evidenceCount || "no"} evidence record${evidenceCount === 1 ? "" : "s"} support this finding.`],
    ["3", "Run checks", "Start with the highest-impact operator check before broad troubleshooting."],
    ["4", "Close the loop", "Export the report or inspect raw metrics if the decision needs escalation."],
  ];
  return (
    <nav className="investigation-decision-path" aria-label="Investigation decision path">
      {steps.map(([index, label, detail]) => (
        <button type="button" key={label} onClick={() => focusInvestigationSection(index === "2" ? "insight-evidence" : index === "3" ? "recommended-investigation" : index === "4" ? "relationship-explorer" : "insight-situation")}> 
          <span>{index}</span>
          <strong>{label}</strong>
          <small>{detail}</small>
        </button>
      ))}
    </nav>
  );
}

function OperatorActions({ insight, subsystem }) {
  const exportReport = () => {
    const blob = new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), subsystem, insight }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `neraium-investigation-${text(insight?.id) || "report"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  return <div className="operator-quick-actions" role="group" aria-label="Operator actions">
    <button type="button" onClick={() => focusInvestigationSection("insight-evidence")}>Inspect affected equipment</button>
    <button type="button" onClick={() => focusInvestigationSection("fingerprint-comparison")}>Compare baseline</button>
    <button type="button" onClick={() => focusInvestigationSection("relationship-explorer")}>Related systems</button>
    <button type="button" onClick={exportReport}>Export report</button>
  </div>;
}

export default function OperatorInsightDetail({ insight, defaultOpen = false, inline = false, focusMode = false }) {
  const evidence = Array.isArray(insight?.evidence) ? insight.evidence : [];
  const relationships = relationshipLabels(insight);
  const observedFacts = unique(toList(insight?.observedFacts, insight?.observed, insight?.observed_facts).map(text));
  const actions = unique(toList(
    insight?.recommendedFirstAction, insight?.recommendedAction, insight?.recommended_action,
    insight?.recommendedInvestigation, insight?.recommended_investigation, insight?.operatorCheck,
    insight?.operator_check, insight?.recommendedActions, insight?.recommended_actions,
    insight?.recommendedFirstChecks, insight?.recommended_first_checks, insight?.recommendedCheck,
    insight?.recommended_check
  ).flatMap((item) => text(item).split(/\n|;|\u2022/g)).map((item) => item.trim()));
  const investigationActions = (actions.length ? actions : [
    "Review the contributing signal trends for the selected operating window.",
    "Compare recent control and valve changes with the start of the deviation.",
    "Verify equipment performance and instrumentation health.",
  ]).slice(0, 3);
  const suppliedCauses = unique(toList(
    insight?.likelyCauses, insight?.possibleOperationalCauses, insight?.possible_operational_causes,
    insight?.contributingFactors, insight?.contributing_factors, insight?.likely_causes
  ).map(text));
  const causes = (suppliedCauses.length ? suppliedCauses : [
    "Operating mode change", "Hydraulic restriction", "Equipment wear", "Valve configuration change", "Instrumentation issue",
  ]).slice(0, 6);
  const severity = insightSeverityLabel(insight);
  const confidenceValue = confidencePercent(insight) || confidenceLabel(insight);
  const subsystem = text(insight?.system || insight?.rawSystemName) || "Operational subsystem";
  const measurements = evidence.map(relationshipMeasurement).filter((item) => item.delta !== null);
  const largestDelta = measurements.length ? Math.max(...measurements.map((item) => item.delta)) : null;
  const primaryRelationship = relationships[0];
  const suppliedImpacts = splitOperationalImpacts(toList(
    insight?.expectedOperationalImpact, insight?.expected_operational_impact,
    insight?.possibleOperationalConsequence, insight?.possible_operational_consequence,
    insight?.whyThisMatters, insight?.whyItMatters, insight?.possibleConsequence,
    insight?.possible_consequence
  ));
  const expectedImpacts = (suppliedImpacts.length ? suppliedImpacts : defaultOperationalImpacts(causes, relationships)).slice(0, 4);
  const historicalDetails = buildChangeContext(insight, evidence).filter(([label]) => !/Largest relationship change magnitude/.test(label));
  const operationalMemory = buildOperationalMemory(insight);
  const explicitSummary = text(insight?.behaviorInterpretation ?? insight?.whatHappened ?? insight?.rawSummary ?? insight?.summary);
  const behavioralSummary = explicitSummary || `The ${subsystem} subsystem moved off its operating baseline.`;
  const operationalStatus = severity === "Critical" ? "Critical" : severity === "High" ? "Investigation Recommended" : severity === "Moderate" ? "Watch" : "Normal";
  const relationshipModels = relationships.map((label, index) => ({ label, evidence: evidence[index], measurement: relationshipMeasurement(evidence[index]) }));
  const supportingSignals = unique(evidence.flatMap((item) => toList(item?.supporting_signals, item?.supportingSignals, item?.source_columns, item?.sourceColumns)).map(signalName));
  const relationshipCoverageNotes = relationshipModels.flatMap(({ label, measurement }) => {
    if (measurement.baseline === null && measurement.current === null && measurement.delta === null) {
      return [`${label}: no quantitative measurement was included in this result.`];
    }
    if (measurement.baseline !== null && measurement.current !== null && Math.sign(measurement.baseline) !== 0 && Math.sign(measurement.current) !== 0 && Math.sign(measurement.baseline) !== Math.sign(measurement.current)) {
      return [`${label}: the relationship reversed direction.`];
    }
    return [];
  });
  const supportingObservations = unique([
    ...observedFacts,
    ...evidence.map((item) => text(item?.description ?? item?.summary)),
    ...relationshipCoverageNotes,
  ]).filter((item) => {
    const observation = item.toLowerCase();
    const summary = behavioralSummary.toLowerCase();
    return observation !== summary && !summary.includes(observation) && !observation.includes(summary);
  }).slice(0, 4);
  const advancedMetadata = [
    insight?.id ? ["Insight identifier", text(insight.id)] : null,
    insight?.metricName ? ["Signal identifier", text(insight.metricName)] : null,
    Number.isFinite(Number(insight?.persistenceScore ?? insight?.persistence_score))
      ? ["Persistence score", Number(insight.persistenceScore ?? insight.persistence_score).toFixed(2)]
      : null,
  ].filter(Boolean);
  const historicalComparison = text(insight?.previousFingerprint)
    || text(insight?.healthyBaseline)
    || "Current operation is being compared with the baseline.";
  const confidenceRaises = unique(toList(
    insight?.confidenceIncreaseFactors,
    insight?.confidence_increase_factors,
    insight?.confidenceBreakdown,
    insight?.confidence_breakdown,
    insight?.confidenceRationale
  ).map(text)).slice(0, 5);
  const confidenceLowers = unique(toList(
    insight?.confidenceDecreaseFactors,
    insight?.confidence_decrease_factors,
    "Missing or delayed telemetry",
    "A short observation window",
    "Evidence that the change matches a planned operating mode"
  ).map(text)).slice(0, 4);

  const body = (
    <div className="insight-layered">
      <section id="insight-situation" className="insight-situation-card" aria-labelledby="insight-situation-title" tabIndex={-1}>
        <span className="insight-summary-card__eyebrow">What happened</span>
        <div className="insight-situation-card__meta">
          <span className={`insight-severity insight-severity--${severity.toLowerCase()}`}>{operationalStatus}</span>
          <span>Affected subsystem: {subsystem}</span>
          {confidenceValue ? <span>Confidence {confidenceValue}</span> : null}
        </div>
        <p id="insight-situation-title" className="insight-situation-card__summary">{behavioralSummary}</p>
      </section>

      <InvestigationDecisionPath evidenceCount={evidence.length} relationshipCount={relationships.length} />

      <section id="insight-evidence" className="insight-summary-card insight-summary-card--evidence" aria-labelledby="key-evidence-title" tabIndex={-1}>
        <span className="insight-summary-card__eyebrow">Why Neraium flagged this</span>
        <h4 id="key-evidence-title">Key evidence</h4>
        <div className="investigation-evidence-grid">
          <section>
            <span>Largest relationship change</span>
            <strong>{largestDelta !== null ? largestDelta.toFixed(2) : "Not measured"}</strong>
            {primaryRelationship ? <p>{primaryRelationship}</p> : null}
          </section>
          <section>
            <span>Primary signals</span>
            <BulletList items={supportingSignals.length ? supportingSignals : relationships} />
          </section>
          {supportingObservations.length ? <section>
            <span>Supporting observations</span>
            <BulletList items={supportingObservations} />
          </section> : null}
          <section>
            <span>Historical comparison</span>
            <p>{historicalComparison}</p>
          </section>
        </div>
      </section>

      <section id="recommended-investigation" className="insight-summary-card insight-summary-card--action" aria-labelledby="recommended-investigation-title" tabIndex={-1}>
        <span className="insight-summary-card__eyebrow">What to check next</span>
        <h4 id="recommended-investigation-title">Recommended checks</h4>
        <PriorityActions actions={investigationActions} signals={supportingSignals} impacts={expectedImpacts} explain />
      </section>

      <OperatorActions insight={insight} subsystem={subsystem} />

      <div className="insight-disclosure-stack" role="region" aria-label="Technical investigation detail">
        <Disclosure title="Technical evidence">
          <section id="fingerprint-comparison" className="technical-evidence-section fingerprint-comparison" tabIndex={-1}>
            <div className="technical-evidence-section__header"><span>Baseline comparison</span><p>Only material differences are shown.</p></div>
            <section><span>Current pattern</span><strong>{text(insight?.currentFingerprint) || "Current relationship strengths are in raw metrics."}</strong></section>
            <section><span>Previous pattern</span><strong>{text(insight?.previousFingerprint) || "Behavior was closer to baseline."}</strong></section>
            <section><span>Healthy baseline</span><strong>{text(insight?.healthyBaseline) || "Relationships remained inside range."}</strong></section>
          </section>
          <section id="relationship-explorer" className="technical-evidence-section" tabIndex={-1}>
            <div className="technical-evidence-section__header"><span>Relationships and raw metrics</span><p>Inspect source strengths for affected relationships.</p></div>
            <Suspense fallback={<p>Loading relationship explorer...</p>}><RelationshipExplorer relationships={relationshipModels} /></Suspense>
          </section>
          {historicalDetails.length || operationalMemory.rows.length || operationalMemory.similarEvents.length ? <section className="technical-evidence-section">
            <div className="technical-evidence-section__header"><span>Historical details</span></div>
            <ContextGrid rows={historicalDetails} />
            {operationalMemory.rows.length ? <ContextGrid rows={operationalMemory.rows} /> : null}
            <BulletList items={operationalMemory.similarEvents} />
          </section> : null}
        </Disclosure>

        <Disclosure title="Advanced details">
          <section className="technical-evidence-section">
            <div className="technical-evidence-section__header"><span>Possible causes to rule out</span></div>
            <BulletList items={causes} />
          </section>
          <div className="confidence-drivers">
            <section><h5>Raises confidence</h5><CheckedList items={confidenceRaises} /></section>
            <section><h5>Lowers confidence</h5><BulletList items={confidenceLowers} /></section>
          </div>
          {advancedMetadata.length ? <ContextGrid rows={advancedMetadata} /> : null}
          {evidence.map((item, index) => {
            const rows = usefulDiagnosticEntries(item);
            return rows.length ? (
              <div className="insight-evidence-item" key={item?.evidence_id ?? index}>
                <dl className="operational-detail-grid operational-detail-grid--technical">
                  {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd><DiagnosticValue value={value} /></dd></div>)}
                </dl>
              </div>
            ) : null;
          })}
        </Disclosure>

        <Disclosure title="Raw analysis payload" className="insight-disclosure--raw">
          <pre><code>{JSON.stringify(insight, null, 2)}</code></pre>
        </Disclosure>
      </div>
    </div>
  );

  if (inline) {
    return (
      <div className={focusMode ? "insight-detail-card insight-detail-card--selected" : "insight-detail-card"} role="region" aria-label="Selected investigation detail">
        {body}
      </div>
    );
  }

  return (
    <details className="insight-detail-card" aria-label="Insight detail" open={defaultOpen}>
      <summary>Insight detail</summary>
      {body}
    </details>
  );
}
