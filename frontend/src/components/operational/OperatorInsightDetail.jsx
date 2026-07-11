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
    if (columns.length >= 2) return columns[0] + " ↔ " + columns[1];
    return text(relationship) || "Supporting relationship " + (itemIndex + 1);
  }).filter(Boolean);
}

function couplingInterpretation(baseline, current) {
  const baselineSign = Math.sign(baseline);
  const currentSign = Math.sign(current);
  if (baselineSign !== 0 && currentSign !== 0 && baselineSign !== currentSign) return "the relationship reversed direction";
  const strengthChange = Math.abs(baseline) - Math.abs(current);
  if (strengthChange >= 0.5) return "the relationship weakened sharply toward little linear coupling";
  if (strengthChange >= 0.2) return "the relationship weakened materially";
  if (strengthChange > 0.05) return "the relationship weakened";
  if (strengthChange <= -0.2) return "the relationship strengthened materially";
  if (strengthChange < -0.05) return "the relationship strengthened";
  return "the relationship remained similar in strength";
}

function evidenceSummary(evidence, index, labels = []) {
  const label = labels[index] || text(evidence?.description ?? evidence?.summary) || "Supporting relationship " + (index + 1);
  const { baseline, current, delta } = relationshipMeasurement(evidence);
  if (baseline !== null && current !== null) {
    const magnitude = delta !== null ? " Overall change magnitude: " + delta.toFixed(2) + "." : "";
    return label + ": Unitless coupling score changed from " + baseline.toFixed(2) + " to " + current.toFixed(2) + "; " + couplingInterpretation(baseline, current) + "." + magnitude;
  }
  if (delta !== null) return label + ": Relationship change magnitude: " + delta.toFixed(2) + ".";
  return label + ": change detected, but no quantitative measurement was included in this result.";
}

function evidenceSummaries(insight, evidence) {
  const labels = relationshipLabels(insight);
  const count = Math.max(evidence.length, labels.length);
  return Array.from({ length: count }, (_, itemIndex) => evidenceSummary(evidence[itemIndex], itemIndex, labels));
}

function evidenceMetricRows(insight, evidence) {
  const firstMeasurement = evidence.map(relationshipMeasurement).find((item) => item.baseline !== null || item.current !== null || item.delta !== null) ?? {};
  const rows = [];
  if (firstMeasurement.baseline !== null && firstMeasurement.baseline !== undefined) rows.push(["Baseline average", firstMeasurement.baseline.toFixed(2)]);
  if (firstMeasurement.current !== null && firstMeasurement.current !== undefined) rows.push(["Current average", firstMeasurement.current.toFixed(2)]);
  if (firstMeasurement.delta !== null && firstMeasurement.delta !== undefined) rows.push(["Percent change", firstMeasurement.delta.toFixed(2)]);
  const confidenceEvidence = evidence.find((item) => item?.confidence_score || item?.confidenceScore) ?? {};
  const confidence = Number(insight?.confidenceScore ?? confidenceEvidence.confidence_score ?? confidenceEvidence.confidenceScore);
  if (Number.isFinite(confidence)) rows.push(["Persistence score", confidence.toFixed(2)]);
  return rows;
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

function usefulDiagnosticEntries(evidence) {
  const rows = [
    ["Summary", text(evidence?.description ?? evidence?.summary)],
    ["Confidence", humanize(evidence?.confidence)],
    ["Time window", text(evidence?.time_window ?? evidence?.timeWindow)],
    ["Persistence / duration", text(evidence?.persistence_duration ?? evidence?.persistenceDuration)],
    ["Relationship measurements", evidence?.relationship_delta ?? evidence?.relationshipDelta],
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

function Section({ title, children }) {
  return (
    <section className="insight-briefing__section">
      <h4>{title}</h4>
      {children}
    </section>
  );
}

function BulletList({ items }) {
  const visible = unique(items.map(text)).slice(0, 6);
  if (!visible.length) return null;
  return <ul className="operator-briefing-list">{visible.map((item) => <li key={item}>{item}</li>)}</ul>;
}

function CauseList({ items }) {
  const visible = unique(items.map(text)).slice(0, 6);
  if (!visible.length) return null;
  const mostLikely = visible.slice(0, 3);
  const otherPossibilities = visible.slice(3);
  return (
    <div className="cause-group">
      {mostLikely.length ? <><h5>Most Likely</h5><BulletList items={mostLikely} /></> : null}
      {otherPossibilities.length ? <><h5>Other Possibilities</h5><BulletList items={otherPossibilities} /></> : null}
    </div>
  );
}

function ContextGrid({ rows }) {
  if (!rows.length) return null;
  return (
    <dl className="operational-detail-grid">
      {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
  );
}

export default function OperatorInsightDetail({ insight }) {
  const evidence = Array.isArray(insight?.evidence) ? insight.evidence : [];
  const evidenceLines = unique([
    ...evidenceSummaries(insight, evidence),
    ...toList(insight?.evidenceSummary, insight?.confidenceRationale).map(text),
  ]).slice(0, 8);
  const evidenceMetrics = evidenceMetricRows(insight, evidence);

  const actions = unique(toList(
    insight?.recommendedFirstAction,
    insight?.recommendedAction,
    insight?.recommendedInvestigation,
    insight?.operatorCheck,
    insight?.recommendedActions,
    insight?.recommended_actions
  ).flatMap((item) => text(item).split(/\n|;|•/g)).map((item) => item.trim())).slice(0, 6);

  const suppliedCauses = unique(toList(
    insight?.likelyCauses,
    insight?.possibleOperationalCauses,
    insight?.contributingFactors
  ).flatMap((item) => Array.isArray(item) ? item : [item]).map(text)).slice(0, 6);
  const causes = suppliedCauses.length ? suppliedCauses : [
    "Filter loading",
    "Pump operating point changed",
    "Valve position changed",
    "Process demand changed",
  ];

  const confidence = confidenceLabel(insight);
  const observedFacts = unique(toList(insight?.observedFacts, insight?.observed, insight?.observed_facts).flatMap((item) => Array.isArray(item) ? item : [item]).map(text)).slice(0, 8);
  const whatChanged = unique(toList(insight?.whatHappened, insight?.behaviorInterpretation, insight?.whyNeraiumThinks, insight?.rawSummary, insight?.summary).map(text)).slice(0, 3);
  const whyItMatters = unique(toList(insight?.whyThisMatters, insight?.whyItMatters, insight?.possibleConsequence).flatMap((item) => Array.isArray(item) ? item : [item]).map(text)).slice(0, 6);
  const changeContext = buildChangeContext(insight, evidence);
  const operationalMemory = buildOperationalMemory(insight);

  return (
    <details className="insight-detail-card" aria-label="Insight detail">
      <summary>Insight detail</summary>

      <div className="insight-briefing__header">
        <span className="section-token">{insight?.system || "Operational Insight"}</span>
        <h3>{insight?.summary || insight?.rawSummary || "Operational change detected"}</h3>
      </div>

      <dl className="insight-briefing__status" aria-label="Insight status">
        {insight?.severity ? <div><dt>Severity</dt><dd>{humanize(insight.severity)}</dd></div> : null}
        {confidence ? <div><dt>Confidence</dt><dd>{confidence}</dd></div> : null}
      </dl>

      <Section title="What Changed">
        {whatChanged.map((line) => <p key={line}>{line}</p>)}
      </Section>

      {observedFacts.length ? <Section title="Observed"><BulletList items={observedFacts} /></Section> : null}

      {changeContext.length ? <Section title="Change Context"><ContextGrid rows={changeContext} /></Section> : null}

      {whyItMatters.length ? <Section title="Why This Matters"><BulletList items={whyItMatters} /></Section> : null}

      {actions.length ? <Section title="Recommended Investigation"><BulletList items={actions} /></Section> : null}

      {causes.length ? <Section title="Likely Causes"><CauseList items={causes} /></Section> : null}

      {evidenceLines.length ? <Section title="Evidence"><BulletList items={evidenceLines} /></Section> : null}

      {evidenceMetrics.length ? <Section title="Evidence Metrics"><ContextGrid rows={evidenceMetrics} /></Section> : null}

      {operationalMemory.rows.length || operationalMemory.similarEvents.length ? (
        <Section title="Operational Memory">
          <ContextGrid rows={operationalMemory.rows} />
          <BulletList items={operationalMemory.similarEvents} />
        </Section>
      ) : null}

      {evidence.length || insight?.id || insight?.metricName ? (
        <details className="insight-evidence-drawer">
          <summary>Advanced Diagnostics <span className="sr-only">Technical Details</span></summary>
          <div className="insight-evidence-drawer__body">
            <dl className="operational-detail-grid operational-detail-grid--technical">
              {insight?.id ? <div><dt>Insight identifier</dt><dd><code>{insight.id}</code></dd></div> : null}
              {insight?.metricName ? <div><dt>Signal identifier</dt><dd><code>{text(insight.metricName)}</code></dd></div> : null}
              {insight?.confidenceRationale ? <div><dt>Diagnostic metadata</dt><dd>{text(insight.confidenceRationale)}</dd></div> : null}
            </dl>

            {evidence.map((item, index) => {
              const rows = usefulDiagnosticEntries(item);
              if (!rows.length) return null;
              return (
                <div className="insight-evidence-item" key={item?.evidence_id ?? index}>
                  <dl className="operational-detail-grid operational-detail-grid--technical">
                    {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd><DiagnosticValue value={value} /></dd></div>)}
                  </dl>
                </div>
              );
            })}
          </div>
        </details>
      ) : null}
    </details>
  );
}
