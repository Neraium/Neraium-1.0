import { lazy, Suspense } from "react";

import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";
import FindingClassificationSummary from "./FindingClassificationSummary";

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
  if (typeof value === "object") return text(value.description ?? value.summary ?? value.what_changed ?? value.whatChanged);
  return "";
}

function unique(values, key = (value) => text(value).toLowerCase()) {
  const seen = new Set();
  return values.filter((value) => {
    const clean = key(value);
    if (!clean || seen.has(clean)) return false;
    seen.add(clean);
    return true;
  });
}

function sentenceCase(value) {
  const clean = text(value).replace(/_/g, " ").replace(/\s+/g, " ").trim();
  if (!clean) return "";
  const lower = clean.toLowerCase();
  return `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`
    .replace(/\borp\b/gi, "ORP")
    .replace(/\bph\b/gi, "pH")
    .replace(/\bvfd\b/gi, "VFD");
}

function signalName(value) {
  return sentenceCase(value)
    .replace(/\bFilter (?:dp|differential pressure)\b/i, "Filter differential pressure")
    .replace(/\bPump speed rpm\b/i, "Pump speed")
    .replace(/\bDp\b/g, "differential pressure")
    .replace(/\s+rpm\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

function lowerFirst(value) {
  const clean = text(value);
  return clean ? `${clean.charAt(0).toLowerCase()}${clean.slice(1)}` : "";
}

function cleanSentence(value) {
  const clean = text(value)
    .replace(/\bFilter dp\b/gi, "Filter differential pressure")
    .replace(/\bPump speed rpm\b/gi, "Pump speed")
    .replace(/\b(increased|decreased)\s+(?:by\s+)?[+-](?=\d)/gi, "$1 ")
    .replace(/\s+([,.!?;:])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  if (!clean) return "";
  return /[.!?]$/.test(clean) ? clean : `${clean}.`;
}

function parseMetricObservation(value) {
  const clean = cleanSentence(value).replace(/[.]$/, "");
  const match = clean.match(/^(.+?)\s+(increased|decreased)\s+(?:by\s+)?([+-]?\d+(?:\.\d+)?)%$/i);
  if (!match) return null;
  const amount = Math.abs(Number(match[3]));
  if (!Number.isFinite(amount)) return null;
  return {
    signal: signalName(match[1]),
    direction: match[2].toLowerCase(),
    amount: Number.isInteger(amount) ? String(amount) : amount.toFixed(1).replace(/\.0$/, ""),
  };
}

function metricSentence(metric) {
  return `${metric.signal} ${metric.direction} ${metric.amount}%`;
}

function relationshipEndpoints(value, index = 0) {
  if (value && typeof value === "object") {
    const columns = toList(
      value.display_columns,
      value.displayColumns,
      value.source_tag_display_names,
      value.sourceTagDisplayNames,
      value.columns,
      value.source_columns,
      value.sourceColumns,
      value.source,
      value.target,
    ).map(signalName).filter(Boolean);
    if (columns.length >= 2) return columns.slice(0, 2);
  }

  let raw = text(value)
    .replace(/^The historical relationship between\s+/i, "")
    .replace(/^The relationship between\s+/i, "")
    .replace(/^A (?:new|stronger) relationship (?:emerged )?between\s+/i, "")
    .replace(/\s+operating coupling\b.*$/i, "")
    .replace(/\s+(?:weakened|shifted|changed|emerged|no longer follows)\b.*$/i, "")
    .replace(/[.]$/, "");
  const parts = raw.split(/\s*↔\s*|\s*<->\s*|\s+\/\s+|\s+and\s+/i).map(signalName).filter(Boolean);
  return parts.length >= 2 ? parts.slice(0, 2) : [`Relationship ${index + 1}`];
}

function strengthWord(value) {
  if (value === null || value === undefined || value === "") return "";
  const clean = text(value).toLowerCase();
  if (["strong", "moderate", "weak"].includes(clean)) return clean;
  const numeric = Math.abs(Number(value));
  if (!Number.isFinite(numeric)) return "";
  if (numeric >= 0.65) return "strong";
  if (numeric >= 0.35) return "moderate";
  return "weak";
}

function relationshipMeasurement(evidence, relationship = {}) {
  const candidates = [
    relationship,
    ...toList(
      evidence?.relationship_delta,
      evidence?.relationshipDelta,
      evidence?.metric_delta,
      evidence?.metricDelta,
      evidence?.relevant_metric_changes,
      evidence?.relevantMetricChanges,
    ),
  ];

  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "object") continue;
    const baseline = Number(candidate.baseline_strength ?? candidate.baselineStrength ?? candidate.baseline_correlation ?? candidate.baselineCoupling);
    const current = Number(candidate.current_strength ?? candidate.currentStrength ?? candidate.current_correlation ?? candidate.recent_correlation ?? candidate.currentCoupling);
    const delta = Number(candidate.correlation_delta ?? candidate.correlationDelta ?? candidate.coupling_delta ?? candidate.couplingDelta);
    if (Number.isFinite(baseline) || Number.isFinite(current) || Number.isFinite(delta)) {
      return {
        delta: Number.isFinite(delta) ? Math.abs(delta) : null,
        baseline: Number.isFinite(baseline) ? baseline : null,
        current: Number.isFinite(current) ? current : null,
      };
    }
  }
  return { delta: null, baseline: null, current: null };
}

function relationshipSentence(value, evidence, index = 0) {
  const endpoints = relationshipEndpoints(value, index);
  const pair = endpoints.length >= 2 ? `${lowerFirst(endpoints[0])} and ${lowerFirst(endpoints[1])}` : lowerFirst(endpoints[0]);
  const raw = text(value);
  const changeType = text(value?.change_type ?? value?.changeType)
    .toLowerCase()
    || (raw.match(/operating coupling\s+(missing|new|weakened|strengthened|inverted|disrupted|changed)/i)?.[1] ?? "changed").toLowerCase();
  const measurement = relationshipMeasurement(evidence, value && typeof value === "object" ? value : {});
  const baseline = strengthWord(value?.baseline_strength ?? value?.baselineStrength ?? value?.baseline_correlation ?? measurement.baseline);
  const current = strengthWord(value?.current_strength ?? value?.currentStrength ?? value?.current_correlation ?? value?.recent_correlation ?? measurement.current);

  if (["new", "strengthened"].includes(changeType)) return `A stronger relationship emerged between ${pair}.`;
  const reversed = measurement.baseline !== null && measurement.current !== null
    && Math.sign(measurement.baseline) !== 0 && Math.sign(measurement.current) !== 0
    && Math.sign(measurement.baseline) !== Math.sign(measurement.current);
  if (["inverted", "reversed"].includes(changeType) || reversed) return `The relationship between ${pair} reversed direction.`;
  if (["missing", "weakened"].includes(changeType)) {
    if (baseline && current && baseline !== current) return `The relationship between ${pair} weakened from ${baseline} to ${current}.`;
    return `The relationship between ${pair} weakened from its learned baseline.`;
  }
  if (changeType === "disrupted") return `The relationship between ${pair} no longer follows its established operating pattern.`;
  return `The relationship between ${pair} changed from its learned baseline.`;
}

function relationshipDetails(insight, evidence) {
  const source = toList(insight?.contributingRelationships, insight?.contributing_relationships);
  const relationships = source.length ? source : toList(insight?.affectedRelationships, insight?.affected_relationships);
  return unique(relationships.map((relationship, index) => {
    const endpoints = relationshipEndpoints(relationship, index);
    return {
      raw: relationship,
      endpoints,
      evidence: evidence[index],
      sentence: relationshipSentence(relationship, evidence[index], index),
    };
  }), (item) => item.endpoints.map((endpoint) => endpoint.toLowerCase()).sort().join("|"));
}

function countWord(count) {
  const words = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
  return words[count] ?? String(count);
}

function isHydraulic(insight, metrics, relationships) {
  const context = [
    insight?.system,
    insight?.summary,
    ...metrics.map((item) => item.signal),
    ...relationships.flatMap((item) => item.endpoints),
  ].join(" ").toLowerCase();
  return /pump|flow|pressure|hydraulic|valve|filter/.test(context);
}

function supportingEvidence(insight, evidence, relationships) {
  const facts = unique(toList(
    insight?.observedFacts,
    insight?.observed,
    insight?.observed_facts,
    ...evidence.flatMap((item) => toList(item?.supporting_signals, item?.supportingSignals)),
  ).map(cleanSentence));
  const metrics = unique(facts.map(parseMetricObservation).filter(Boolean), (item) => item.signal.toLowerCase());
  const used = new Set();
  const bullets = [];
  const power = metrics.find((item) => /pump power/.test(item.signal.toLowerCase()));
  const flow = metrics.find((item) => /^flow$|\bflow\b/.test(item.signal.toLowerCase()));
  if (power && flow) {
    bullets.push(`${metricSentence(power)} while ${lowerFirst(metricSentence(flow))}.`);
    used.add(power);
    used.add(flow);
  }
  for (const metric of metrics) {
    if (used.has(metric) || bullets.length >= 3) continue;
    bullets.push(`${metricSentence(metric)}.`);
  }

  if (!bullets.length) {
    const fallback = facts.filter((item) => !/relationship|operating coupling|observed during|started around|drift trajectory/i.test(item));
    bullets.push(...fallback.slice(0, 3));
  }

  const changedCount = Number(insight?.changedRelationshipCount ?? insight?.changed_relationship_count) || relationships.length;
  if (changedCount) {
    const qualifier = isHydraulic(insight, metrics, relationships) ? " hydraulic" : "";
    bullets.push(`${countWord(changedCount)} learned${qualifier} relationship${changedCount === 1 ? "" : "s"} weakened or changed.`);
  }
  return { bullets: unique(bullets).slice(0, 4), metrics };
}

function metricByName(metrics, pattern) {
  return metrics.find((item) => pattern.test(item.signal.toLowerCase()));
}

function whatChangedSummary(insight, metrics, relationships) {
  const power = metricByName(metrics, /pump power/);
  const flow = metricByName(metrics, /\bflow\b/);
  const pressure = metrics.find((item) => /pressure/.test(item.signal.toLowerCase()) && !/filter differential/.test(item.signal.toLowerCase()));
  if (power?.direction === "decreased" && flow?.direction === "increased" && pressure?.direction === "decreased") {
    return "The system produced more flow while recorded pump power and pressure decreased relative to the learned baseline.";
  }
  const supplied = cleanSentence(insight?.whatChanged ?? insight?.what_changed ?? insight?.whatHappened ?? insight?.rawSummary);
  if (supplied && !/operating coupling|related relationships shifted|historical relationship between/i.test(supplied)) return supplied;
  if (metrics.length >= 2) return `${metricSentence(metrics[0])} while ${lowerFirst(metricSentence(metrics[1]))} relative to the learned baseline.`;
  if (relationships.length) return "The system response changed relative to its learned operating baseline.";
  return cleanSentence(insight?.summary) || "Recorded behavior changed relative to the learned baseline.";
}

function whyItMattersSummary(insight, metrics, relationships) {
  if (isHydraulic(insight, metrics, relationships)) {
    const power = metricByName(metrics, /pump power/);
    const flow = metricByName(metrics, /\bflow\b/);
    const lowerPressure = metrics.some((item) => /pressure/.test(item.signal.toLowerCase()) && item.direction === "decreased");
    if (power?.direction === "decreased" && flow?.direction === "increased" && lowerPressure) {
      return "The hydraulic system is producing more flow with less recorded pump power and lower pressure readings than during the learned baseline. This may reflect a change in operating mode, valve position, instrumentation, or equipment configuration.";
    }
    return "The hydraulic response no longer matches its historical operating pattern. This may reflect an operating-mode change, valve-position change, instrumentation issue, or equipment configuration change.";
  }
  return cleanSentence(insight?.behaviorInterpretation ?? insight?.whyItMatters ?? insight?.whyThisMatters)
    || "The response no longer matches its historical operating pattern. Confirm the operating context before treating the change as an equipment fault.";
}



function limitationCopy(insight) {
  const limitations = toList(insight?.limitations, insight?.qualityWarnings, insight?.quality_warnings).map(text).filter(Boolean);
  const unmapped = toList(insight?.unmappedColumns, insight?.unmapped_columns).map(text).filter(Boolean);
  if (unmapped.length || limitations.some((item) => /could not be mapped|unmapped|classif/i.test(item))) {
    return "Some telemetry fields could not be classified, which limits how specifically Neraium can interpret the change.";
  }
  return limitations[0] ? cleanSentence(limitations[0]) : "";
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateTimePart(value, facilityTimezone) {
  const date = parseDate(value);
  if (!date) return text(value);
  const options = { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" };
  if (facilityTimezone) options.timeZone = facilityTimezone;
  try {
    const parts = new Intl.DateTimeFormat("en-US", options).formatToParts(date);
    const read = (type) => parts.find((part) => part.type === type)?.value ?? "";
    return `${read("month")} ${read("day")} at ${read("hour")}:${read("minute")} ${read("dayPeriod")}`.trim();
  } catch {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
  }
}

function comparisonWindow(insight, evidence) {
  const ranges = [
    ...toList(insight?.sourceTimeRanges, insight?.source_time_ranges),
    ...evidence.flatMap((item) => toList(item?.source_time_ranges, item?.sourceTimeRanges)),
  ].filter((item) => item && typeof item === "object");
  const starts = ranges.map((item) => item.current_start ?? item.currentStart ?? item.start).map(parseDate).filter(Boolean).sort((a, b) => a - b);
  const ends = ranges.map((item) => item.current_end ?? item.currentEnd ?? item.end).map(parseDate).filter(Boolean).sort((a, b) => b - a);
  if (!starts.length || !ends.length) return "";
  const zone = text(insight?.facilityTimezone ?? insight?.facility_timezone);
  return `${dateTimePart(starts[0], zone)} – ${dateTimePart(ends[0], zone)}`;
}

function Disclosure({ title, children, className = "", defaultOpen = false }) {
  return (
    <details className={`insight-disclosure ${className}`.trim()} open={defaultOpen}>
      <summary><span>{title}</span><span className="insight-disclosure__chevron" aria-hidden="true">v</span></summary>
      <div className="insight-disclosure__body">{children}</div>
    </details>
  );
}

function DiagnosticValue({ value }) {
  if (Array.isArray(value)) return <ul className="operator-briefing-list operator-briefing-list--code">{value.map((item, index) => <li key={`${text(item)}-${index}`}><code>{typeof item === "object" ? JSON.stringify(item) : text(item)}</code></li>)}</ul>;
  if (value && typeof value === "object") return <code>{JSON.stringify(value)}</code>;
  return <>{text(value)}</>;
}

function usefulDiagnosticEntries(evidence) {
  return [
    ["Evidence reference", evidence?.evidence_id ?? evidence?.id],
    ["Time window", evidence?.time_window ?? evidence?.timeWindow],
    ["Source ranges", evidence?.source_time_ranges ?? evidence?.sourceTimeRanges],
    ["Source row anchors", evidence?.source_row_anchors ?? evidence?.sourceRowAnchors ?? evidence?.row_anchors ?? evidence?.rowAnchors ?? evidence?.source_rows],
    ["Persistence / duration", evidence?.persistence_duration ?? evidence?.persistenceDuration],
    ["Calculated percent change", evidence?.calculated_percent_delta ?? evidence?.calculatedPercentDelta],
    ["Signal identifiers", toList(evidence?.source_columns, evidence?.sourceColumns, evidence?.source_metrics, evidence?.sourceMetrics, evidence?.source_tags, evidence?.sourceTags)],
    ["Internal metric names", toList(evidence?.metric_delta, evidence?.relevant_metric_changes, evidence?.relevantMetricChanges)],
    ["Analysis reference", evidence?.source_upload_id ?? evidence?.upload_id ?? evidence?.analysis_id],
  ].filter(([, value]) => Array.isArray(value) ? value.length : Boolean(value && (typeof value !== "object" || Object.keys(value).length)));
}

function WaterIntelligencePanel({ insight }) {
  const observed = toList(insight?.observedEvidence, insight?.observed_evidence).map(text).filter(Boolean);
  const derived = toList(insight?.derivedMetrics, insight?.derived_metrics).map((item) => text(item?.explanation ?? item?.name ?? item)).filter(Boolean);
  const explanations = toList(insight?.possibleExplanations, insight?.possible_explanations).map((item) => text(item?.explanation ?? item)).filter(Boolean);
  const checks = toList(insight?.recommendedChecksStructured, insight?.recommended_checks).map((item) => text(item?.check ?? item)).filter(Boolean);
  const confidence = insight?.confidenceAndUncertainty ?? insight?.confidence_and_uncertainty;
  if (!observed.length && !derived.length && !explanations.length && !checks.length && !confidence) return null;
  return <section className="technical-evidence-section"><div className="technical-evidence-section__header"><span>Water intelligence</span></div>{observed.length ? <><h5>Observed</h5><ul>{observed.map((item) => <li key={item}>{item}</li>)}</ul></> : null}{derived.length ? <><h5>Derived</h5><ul>{derived.map((item) => <li key={item}>{item}</li>)}</ul></> : null}{explanations.length ? <><h5>Possible explanation</h5><ul>{explanations.map((item) => <li key={item}>{item}</li>)}</ul></> : null}{checks.length ? <><h5>Recommended check</h5><ul>{checks.map((item) => <li key={item}>{item}</li>)}</ul></> : null}{confidence?.explanation ? <p>{text(confidence.explanation)}</p> : null}</section>;
}

function timelineWhen(event, facilityTimezone) {
  if (event.periodLabel) return event.periodLabel;
  if (event.time) return dateTimePart(event.time, facilityTimezone);
  if (event.start && event.end) return `${dateTimePart(event.start, facilityTimezone)} – ${dateTimePart(event.end, facilityTimezone)}`;
  if (event.start) return `From ${dateTimePart(event.start, facilityTimezone)}`;
  if (event.end) return `Through ${dateTimePart(event.end, facilityTimezone)}`;
  return "";
}

function guidanceCategory(value) {
  return sentenceCase(value || "documentation");
}

function sensorConditionLabel(value) {
  return sentenceCase(value || "Signal-health condition");
}

function shortSentence(value) {
  const clean = cleanSentence(value);
  return clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? clean;
}

function GuidanceList({ items, start = 1 }) {
  return (
    <ol className="investigation-guidance-list" start={start}>
      {items.map((item, index) => (
        <li key={`${item.rank}-${item.check}`}>
          <span className="investigation-guidance-list__rank" aria-hidden="true">{item.rank || start + index}</span>
          <div><strong>{item.check}</strong><p>{shortSentence(item.reason)}</p><span className="investigation-guidance-list__category">{guidanceCategory(item.category)}</span></div>
        </li>
      ))}
    </ol>
  );
}

function AuditHistory({ entries }) {
  if (!entries.length) return <p className="evidence-page__unavailable">No audit or replay events were recorded on this finding.</p>;
  return <ul className="operator-briefing-list operator-briefing-list--code">{entries.map((entry, index) => <li key={`${text(entry)}-${index}`}><DiagnosticValue value={entry} /></li>)}</ul>;
}

export default function OperatorInsightDetail({ insight, defaultOpen = false, inline = false, focusMode = false }) {
  const evidence = Array.isArray(insight?.evidence) ? insight.evidence : [];
  const relationships = relationshipDetails(insight, evidence);
  const support = supportingEvidence(insight, evidence, relationships);
  const summary = whatChangedSummary(insight, support.metrics, relationships);
  const interpretation = whyItMattersSummary(insight, support.metrics, relationships);
  const presentation = normalizeFindingPresentation(insight);
  const limitation = limitationCopy(insight);
  const window = comparisonWindow(insight, evidence);
  const subsystem = text(insight?.system || insight?.rawSystemName) || "Unassigned system";
  const dataset = text(insight?.sourceName ?? insight?.source_name) || "Unassigned dataset";
  const relationshipModels = relationships.map((item) => ({ label: item.endpoints.join(" and "), evidence: item.evidence, measurement: relationshipMeasurement(item.evidence, item.raw) }));
  const scope = relationships.length || support.metrics.length ? "Narrowed" : "Broad";
  const technicalLimitations = unique(toList(insight?.qualityWarnings, insight?.quality_warnings).map(text))
    .filter((item) => !/could not be mapped|unmapped|classif/i.test(item));
  const unmappedColumns = unique(toList(insight?.unmappedColumns, insight?.unmapped_columns).map(text));
  const limitations = unique([
    ...presentation.dataLimitations,
    limitation,
    presentation.certaintyLimit,
  ].map(cleanSentence).filter(Boolean));
  const facilityTimezone = text(insight?.facilityTimezone ?? insight?.facility_timezone);
  const visibleGuidance = presentation.investigationGuidance.slice(0, 3);
  const additionalGuidance = presentation.investigationGuidance.slice(3);
  const visibleEvidence = support.bullets.slice(0, 3);
  const additionalEvidence = support.bullets.slice(3);
  const auditEntries = toList(
    insight?.auditHistory,
    insight?.audit_history,
    insight?.reviewHistory,
    insight?.review_history,
    insight?.replayReferences,
    insight?.replay_references,
  );
  const whyBullets = unique([
    shortSentence(interpretation),
    presentation.persistence.persistent ? `The change persisted.` : "",
    presentation.operatingMode.match !== "Unavailable" ? `Operating-mode match is ${presentation.operatingMode.match.toLowerCase()}.` : "",
  ].filter(Boolean)).slice(0, 3);

  const body = (
    <div className="insight-layered evidence-page">
      <FindingClassificationSummary finding={insight} showDefinition={false} />

      <section id="insight-situation" className="evidence-page__section" aria-labelledby="insight-situation-title" tabIndex={-1}>
        <h4 id="insight-situation-title">What changed</h4>
        <p>{summary}</p>
      </section>

      <section className="evidence-page__section" aria-labelledby="why-it-matters-title">
        <h4 id="why-it-matters-title">Why it matters</h4>
        <ul className="operator-briefing-list">{whyBullets.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>

      <section id="recommended-investigation" className="evidence-page__section evidence-page__start" aria-labelledby="recommended-investigation-title" tabIndex={-1}>
        <h4 id="recommended-investigation-title">Highest-value next checks</h4>
        {visibleGuidance.length ? <GuidanceList items={visibleGuidance} /> : <p>No evidence-linked next check was recorded for this finding.</p>}
        {additionalGuidance.length ? <Disclosure title="Show all checks" className="evidence-page__all-checks"><GuidanceList items={additionalGuidance} start={4} /></Disclosure> : null}
      </section>

      <section className="evidence-page__section" aria-labelledby="relationship-timeline-title">
        <h4 id="relationship-timeline-title">Relationship timeline</h4>
        {presentation.timeline.length ? <ol className="relationship-evidence-timeline">{presentation.timeline.map((event, index) => (
          <li key={`${event.eventType}-${event.time || event.start || event.periodLabel}-${index}`}>
            <time>{timelineWhen(event, facilityTimezone)}</time>
            <strong>{event.title}</strong>
            {event.detail ? <p>{event.detail}</p> : null}
          </li>
        ))}</ol> : <p className="evidence-page__unavailable">No source-bounded timeline milestones were recorded for this finding.</p>}
      </section>

      <section id="insight-evidence" className="evidence-page__section" aria-labelledby="key-evidence-title" tabIndex={-1}>
        <h4 id="key-evidence-title">Supporting evidence</h4>
        {visibleEvidence.length ? <ul className="operator-briefing-list evidence-page__evidence">{visibleEvidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="evidence-page__unavailable">No additional supporting observations were recorded.</p>}
        {additionalEvidence.length ? <Disclosure title="Show all supporting evidence"><ul className="operator-briefing-list">{additionalEvidence.map((item) => <li key={item}>{item}</li>)}</ul></Disclosure> : null}
        {relationships.length ? <Disclosure title="Open relationship evidence" className="evidence-page__relationship-disclosure">
          <ul className="operator-briefing-list evidence-page__relationships">{relationships.map((item) => <li key={item.sentence}>{item.sentence}</li>)}</ul>
          <section id="relationship-explorer" className="technical-evidence-section" tabIndex={-1}>
            <div className="technical-evidence-section__header"><span>Relationship measurements</span></div>
            <Suspense fallback={<p>Loading relationship evidence...</p>}><RelationshipExplorer relationships={relationshipModels} /></Suspense>
          </section>
        </Disclosure> : null}
      </section>

      <div className="evidence-page__disclosures" aria-label="Additional investigation detail">
        <Disclosure title="Why Neraium classified it this way">
          <p>{presentation.meaning}</p>
          <ul className="operator-briefing-list">{presentation.reasons.map((item) => <li key={item}>{cleanSentence(item)}</li>)}</ul>
        </Disclosure>

        <Disclosure title="Operating-mode comparison details">
          <dl className="evidence-context-grid evidence-context-grid--mode">
            <div><dt>Baseline mode</dt><dd>{presentation.operatingMode.baseline}</dd></div>
            <div><dt>Recent mode</dt><dd>{presentation.operatingMode.recent}</dd></div>
            <div><dt>Mode match</dt><dd>{presentation.operatingMode.match}</dd></div>
            <div><dt>Comparison confidence</dt><dd>{presentation.operatingMode.confidence}</dd></div>
          </dl>
          {presentation.operatingMode.differences.length ? <ul className="operator-briefing-list">{presentation.operatingMode.differences.map((item, index) => <li key={`${item.feature}-${index}`}><strong>{sentenceCase(item.feature)}:</strong> {item.reason || "A recorded operating-mode difference was present."}</li>)}</ul> : null}
          {presentation.operatingMode.reasons.length ? <ul className="operator-briefing-list">{presentation.operatingMode.reasons.map((item) => <li key={item}>{cleanSentence(item)}</li>)}</ul> : null}
        </Disclosure>

        <Disclosure title="Sensor-health details">
          <dl className="evidence-context-grid"><div><dt>Data confidence</dt><dd>{presentation.dataConfidence.rating}</dd></div><div><dt>Summary</dt><dd>{presentation.dataConfidence.summary}</dd></div></dl>
          {presentation.sensorHealth.length ? <ul className="sensor-health-list">{presentation.sensorHealth.map((sensor) => (
            <li key={sensor.signal} className={`sensor-health-list__item sensor-health-list__item--${sensor.health.toLowerCase()}`}>
              <div><strong>{sentenceCase(sensor.signal)}</strong><span>{sentenceCase(sensor.health)}</span></div>
              {sensor.conditions.length ? <ul>{sensor.conditions.map((condition, index) => <li key={`${condition.type}-${index}`}><strong>{sensorConditionLabel(condition.type)}:</strong> {condition.evidence || "No supporting condition detail was recorded."}</li>)}</ul> : <p>No signal-health warning was recorded.</p>}
            </li>
          ))}</ul> : <p className="evidence-page__unavailable">Sensor-health conditions were not recorded for this finding.</p>}
        </Disclosure>

        <Disclosure title="Alternative explanations">
          {presentation.alternativeExplanations.length ? <ul className="operator-briefing-list">{presentation.alternativeExplanations.map((item) => <li key={item}>{cleanSentence(item)}</li>)}</ul> : <p className="evidence-page__unavailable">No alternative explanations were recorded.</p>}
        </Disclosure>

        <Disclosure title="Data limitations">
          {limitations.length ? <ul className="operator-briefing-list">{limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="evidence-page__unavailable">No additional limitations were recorded.</p>}
        </Disclosure>

        <Disclosure title="Source metadata">
          <dl className="operational-detail-grid">
            <div><dt>Dataset</dt><dd>{dataset}</dd></div>
            <div><dt>System</dt><dd>{subsystem}</dd></div>
            <div><dt>Evidence scope</dt><dd>{scope}</dd></div>
            {window ? <div><dt>Comparison window</dt><dd>{window}</dd></div> : null}
            {facilityTimezone ? <div><dt>Facility timezone</dt><dd>{facilityTimezone}</dd></div> : null}
          </dl>
        </Disclosure>

        <Disclosure title="Technical analysis details" className="evidence-page__technical">
          {unmappedColumns.length ? <section className="technical-evidence-section"><div className="technical-evidence-section__header"><span>Unmapped columns</span></div><ul className="operator-briefing-list operator-briefing-list--code">{unmappedColumns.map((item) => <li key={item}><code>{item}</code></li>)}</ul></section> : null}
          {technicalLimitations.length ? <section className="technical-evidence-section"><div className="technical-evidence-section__header"><span>Data-quality warnings</span></div><ul className="operator-briefing-list">{technicalLimitations.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
          {evidence.map((item, index) => {
            const rows = usefulDiagnosticEntries(item);
            return rows.length ? <div className="insight-evidence-item" key={item?.evidence_id ?? item?.id ?? index}><dl className="operational-detail-grid operational-detail-grid--technical">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd><DiagnosticValue value={value} /></dd></div>)}</dl></div> : null;
          })}
          <WaterIntelligencePanel insight={insight} />
          <Disclosure title="Raw analysis payload" className="insight-disclosure--raw"><pre><code>{JSON.stringify(insight, null, 2)}</code></pre></Disclosure>
        </Disclosure>

        <Disclosure title="Audit history"><AuditHistory entries={auditEntries} /></Disclosure>
      </div>
    </div>
  );

  if (inline) return <div className={focusMode ? "insight-detail-card insight-detail-card--selected" : "insight-detail-card"} role="region" aria-label="Selected investigation detail">{body}</div>;
  return <details className="insight-detail-card" aria-label="Insight detail" open={defaultOpen}><summary>Insight detail</summary>{body}</details>;
}
