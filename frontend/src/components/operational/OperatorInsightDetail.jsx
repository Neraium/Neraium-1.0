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

function evidenceSummary(evidence, index) {
  const label = text(evidence?.description ?? evidence?.summary) || `Supporting relationship ${index + 1}`;
  const delta = Number(evidence?.relationship_delta?.correlation_delta ?? evidence?.relationshipDelta?.correlationDelta);
  if (!Number.isFinite(delta)) return label;
  return `${label} Change magnitude: ${Math.abs(delta).toFixed(2)}.`;
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

export default function OperatorInsightDetail({ insight }) {
  const evidence = Array.isArray(insight?.evidence) ? insight.evidence : [];
  const evidenceLines = unique([
    ...evidence.map(evidenceSummary),
    ...toList(insight?.evidenceSummary, insight?.confidenceRationale).map(text),
  ]).slice(0, 6);

  const actions = unique(toList(
    insight?.recommendedAction,
    insight?.operatorCheck,
    insight?.recommendedActions,
    insight?.recommended_actions
  ).flatMap((item) => text(item).split(/\n|;|•/g)).map((item) => item.trim())).slice(0, 6);

  const causes = unique(toList(
    insight?.possibleOperationalCauses,
    insight?.contributingFactors
  ).flatMap((item) => Array.isArray(item) ? item : [item]).map(text)).slice(0, 6);

  const confidence = confidenceLabel(insight);
  const whatChanged = unique(toList(insight?.whatHappened, insight?.rawSummary, insight?.summary).map(text)).slice(0, 2);
  const whyItMatters = unique(toList(insight?.whyItMatters, insight?.possibleConsequence).map(text)).slice(0, 3);

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

      <Section title="Executive Summary">
        {whatChanged.map((line) => <p key={line}>{line}</p>)}
      </Section>

      {whyItMatters.length ? <Section title="Why It Matters">{whyItMatters.map((line) => <p key={line}>{line}</p>)}</Section> : null}

      {actions.length ? <Section title="Recommended Actions"><BulletList items={actions} /></Section> : null}

      {causes.length ? <Section title="Possible Causes"><BulletList items={causes} /></Section> : null}

      {evidenceLines.length ? <Section title="Supporting Evidence"><BulletList items={evidenceLines} /></Section> : null}

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
