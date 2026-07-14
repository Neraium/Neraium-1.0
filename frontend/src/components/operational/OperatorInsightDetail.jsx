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
  const persistence = Number(insight?.persistenceScore ?? insight?.persistence_score);
  if (Number.isFinite(persistence)) rows.push(["Persistence score", persistence.toFixed(2)]);
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

function cleanOperationalImpact(value) {
  return text(value)
    .replace(/^Operational impact:\s*/i, "")
    .replace(/^If this persists,\s*/i, "If nothing is done, ");
}

function splitOperationalImpacts(values) {
  return unique(values.flatMap((value) => cleanOperationalImpact(value).split(/\n|;|•/g))
    .flatMap((value) => value.split(/(?<=\.)\s+(?=[A-Z])/g))
    .map((item) => item.trim())
    .filter(Boolean));
}

function defaultOperationalImpacts(causes, relationships) {
  const causeText = causes.join(" ").toLowerCase();
  const relationshipText = relationships.join(" ").toLowerCase();
  if (/filter|dp|pressure|pump|flow|hydraulic/.test(`${causeText} ${relationshipText}`)) {
    return [
      "Increased energy consumption",
      "Reduced filtration efficiency",
      "Elevated cavitation risk",
      "Potential accelerated pump wear",
    ];
  }
  return [
    "Continued movement away from the learned operating fingerprint",
    "Reduced confidence in downstream operating assumptions",
    "Higher likelihood of manual investigation on the next operating cycle",
  ];
}

function confidenceEvidenceItems(insight, evidence) {
  const supportingSignals = evidence.flatMap((item) => toList(
    item?.supporting_signals,
    item?.supportingSignals,
    item?.relevant_metric_changes,
    item?.relevantMetricChanges
  ));
  const relationshipItems = relationshipLabels(insight).map((label) => `${label} drift`);
  const rationaleItems = toList(insight?.confidenceBreakdown, insight?.confidence_breakdown, insight?.confidenceRationale)
    .flatMap((item) => text(item).split(/\n|;|,/g));
  const evidenceQuality = evidence.some((item) => humanize(item?.confidence).toLowerCase() === "high") ? ["High-confidence evidence source"] : [];
  const fallback = confidenceLabel(insight) ? ["Signal strength", "Relationship support", "Persistence evidence", "Telemetry quality acceptable"] : [];
  return unique([
    ...supportingSignals,
    ...relationshipItems,
    ...rationaleItems,
    ...evidenceQuality,
    ...fallback,
  ].map(text)).slice(0, 5);
}

function whyNeraiumBelievesThis(insight, observedFacts, evidence, relationships) {
  const explicit = text(
    insight?.whyNeraiumBelievesThis
    ?? insight?.why_neraium_believes_this
    ?? insight?.whyNeraiumThinks
    ?? insight?.why_neraium_thinks
  );
  if (explicit) return explicit;

  const observed = observedFacts[0];
  const relationship = relationships[0];
  const evidenceLine = evidenceSummaries(insight, evidence)[0];
  if (observed && relationship) {
    return `Neraium detected that ${observed.charAt(0).toLowerCase()}${observed.slice(1)} while the ${relationship} relationship moved away from its learned operating pattern. This combination most closely matches a real operational behavior change rather than normal demand movement.`;
  }
  if (relationship) {
    return `Neraium detected that the historical relationship between ${relationship.replace(" ↔ ", " and ")} changed compared with the learned operating pattern. This combination most closely matches a change in operating behavior rather than a single isolated reading.`;
  }
  if (evidenceLine) {
    return `Neraium generated this insight because the supporting evidence changed from the learned operating fingerprint: ${evidenceLine}`;
  }
  return "";
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
    insight?.recommended_action,
    insight?.recommendedInvestigation,
    insight?.recommended_investigation,
    insight?.operatorCheck,
    insight?.operator_check,
    insight?.recommendedActions,
    insight?.recommended_actions,
    insight?.recommendedFirstChecks,
    insight?.recommended_first_checks,
    insight?.recommendedCheck,
    insight?.recommended_check
  ).flatMap((item) => text(item).split(/\n|;|•/g)).map((item) => item.trim())).slice(0, 6);

  const suppliedCauses = unique(toList(
    insight?.likelyCauses,
    insight?.possibleOperationalCauses,
    insight?.possible_operational_causes,
    insight?.contributingFactors,
    insight?.contributing_factors,
    insight?.likely_causes
  ).flatMap((item) => Array.isArray(item) ? item : [item]).map(text)).slice(0, 6);
  const causes = suppliedCauses.length ? suppliedCauses : [
    "Filter fouling",
    "Valve position changed",
    "Pump efficiency degradation",
    "Instrument drift",
  ];

  const confidence = confidenceLabel(insight);
  const confidenceValue = confidencePercent(insight) || confidence;
  const observedFacts = unique(toList(insight?.observedFacts, insight?.observed, insight?.observed_facts).flatMap((item) => Array.isArray(item) ? item : [item]).map(text)).slice(0, 8);
  const whatChanged = unique(toList(insight?.whatHappened, insight?.behaviorInterpretation, insight?.whyNeraiumThinks, insight?.rawSummary, insight?.summary).map(text)).slice(0, 3);
  const relationships = relationshipLabels(insight);
  const suppliedImpacts = splitOperationalImpacts(toList(
    insight?.expectedOperationalImpact,
    insight?.expected_operational_impact,
    insight?.possibleOperationalConsequence,
    insight?.possible_operational_consequence,
    insight?.whyThisMatters,
    insight?.whyItMatters,
    insight?.possibleConsequence,
    insight?.possible_consequence
  ).flatMap((item) => Array.isArray(item) ? item : [item]));
  const expectedImpacts = (suppliedImpacts.length ? suppliedImpacts : defaultOperationalImpacts(causes, relationships)).slice(0, 6);
  const confidenceEvidence = confidenceEvidenceItems(insight, evidence);
  const whyGenerated = whyNeraiumBelievesThis(insight, observedFacts, evidence, relationships);
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
        {confidenceValue ? <div><dt>Overall Confidence</dt><dd>{confidenceValue}</dd></div> : null}
      </dl>

      <Section title="What Changed">
        {whatChanged.map((line) => <p key={line}>{line}</p>)}
      </Section>

      {observedFacts.length ? <Section title="Observed Behavior"><BulletList items={observedFacts} /></Section> : null}

      {changeContext.length ? <Section title="Change Context"><ContextGrid rows={changeContext} /></Section> : null}

      {expectedImpacts.length ? <Section title="Expected Operational Impact"><BulletList items={expectedImpacts} /></Section> : null}

      {actions.length ? <Section title="Recommended First Checks"><BulletList items={actions} /></Section> : null}

      {causes.length ? <Section title="Most Probable Operational Causes"><BulletList items={causes} /></Section> : null}

      {confidenceValue || confidenceEvidence.length ? (
        <Section title="Confidence Breakdown">
          {confidenceValue ? <div className="confidence-breakdown__score"><span>Overall Confidence</span><strong>{confidenceValue}</strong></div> : null}
          {confidenceEvidence.length ? (
            <>
              <p className="insight-briefing__list-label">Evidence supporting this assessment</p>
              <CheckedList items={confidenceEvidence} />
            </>
          ) : null}
        </Section>
      ) : null}

      {whyGenerated ? (
        <Section title="Why Neraium Believes This">
          <p>{whyGenerated}</p>
        </Section>
      ) : null}

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
