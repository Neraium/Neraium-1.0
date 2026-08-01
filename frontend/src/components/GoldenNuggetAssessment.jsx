import { useEffect, useMemo, useState } from "react";
import { buildApiUrl } from "../config";

const FEEDBACK_OPTIONS = [
  ["useful", "Useful"],
  ["not_useful", "Not useful"],
  ["known_operational_change", "Known operational change"],
  ["possible_sensor_issue", "Possible sensor issue"],
  ["needs_investigation", "Needs investigation"],
];

const LEGACY_PUMP_FLOW_TITLE = "Pump demand no longer matches hydraulic response";
const PUMP_FLOW_TITLE = "Pump demand no longer matches expected flow response";
const PUMP_FLOW_OPERATIONAL_SUMMARY = "The system required a different level of pump demand to produce the hydraulic response learned during the baseline period.";

function responseJson(response) {
  return response?.json?.().catch(() => ({})) ?? Promise.resolve({});
}

function dateTime(value) {
  if (!value) return "Not available";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(parsed);
}

function metricDateTime(value) {
  if (!value) return "Not available";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "UTC",
  }).formatToParts(parsed).map((part) => [part.type, part.value]));
  return `${parts.month} ${parts.day}, ${parts.year} ${parts.hour}:${parts.minute} UTC`;
}

function percent(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${Math.round(numeric * 100)}%` : "Not available";
}

function fixed(value, digits = 2) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : "Not available";
}

function findingTitle(finding) {
  return finding?.title === LEGACY_PUMP_FLOW_TITLE ? PUMP_FLOW_TITLE : finding?.title;
}

function findingOperationalSummary(finding) {
  if (finding?.operational_summary) return finding.operational_summary;
  return findingTitle(finding) === PUMP_FLOW_TITLE ? PUMP_FLOW_OPERATIONAL_SUMMARY : finding?.summary;
}

function median(values) {
  const ordered = values
    .map(Number)
    .filter(Number.isFinite)
    .sort((left, right) => left - right);
  if (!ordered.length) return null;
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2
    ? ordered[middle]
    : (ordered[middle - 1] + ordered[middle]) / 2;
}

function repairComparison(finding, repairTimestamp) {
  const repairTime = Date.parse(repairTimestamp ?? "");
  if (!Number.isFinite(repairTime)) return null;
  const windows = (finding?.relationships ?? []).flatMap((relationship) => relationship?.persistence?.windows ?? []);
  const before = median(windows
    .filter((window) => Date.parse(window.start) < repairTime && window.supports_change)
    .map((window) => window.deviation_score));
  const after = median(windows
    .filter((window) => Date.parse(window.start) >= repairTime)
    .map((window) => window.deviation_score));
  if (before === null || after === null) return null;
  const displayedBefore = Number(before.toFixed(2));
  const displayedAfter = Number(after.toFixed(2));
  const reduction = displayedBefore > 0
    ? ((displayedBefore - displayedAfter) / displayedBefore) * 100
    : null;
  return { before: displayedBefore, after: displayedAfter, reduction };
}

function qualityNote(warning) {
  const text = String(warning ?? "").trim().replace(/[.\s]+$/, "");
  const comparisonMatch = text.match(/^Comparison-period quality is limited for:\s*(.+)$/i);
  if (!comparisonMatch) return text;
  const signals = comparisonMatch[1].split(",").map((signal) => {
    const words = signal.trim().replace(/\s+(?:status|signal)$/i, "").split(/\s+/).filter(Boolean);
    if (words.length < 2) return words.join("");
    return `${words[0]}-${words.slice(1).join(" ").toLowerCase()}`;
  });
  const subject = signals.length > 1
    ? `${signals.slice(0, -1).join(", ")} and ${signals.at(-1)}`
    : signals[0];
  return `${subject} coverage was limited during the comparison period`;
}

function titleCase(value) {
  return String(value ?? "").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function findingStatus(finding, validation) {
  if (validation?.disappeared_after_repair === true) return "Resolved after repair";
  if (validation?.disappeared_after_repair === false) return "Still present after repair";
  return finding?.persisted ? "Active" : "Not persistent";
}

function baselineStatus(gate) {
  if (gate?.decision) return titleCase(gate.decision).replace(/^Baseline\s+/i, "");
  if (gate?.passed === true) return "Accepted";
  if (gate?.passed === false) return "Withheld";
  return "Not available";
}

function errorMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (typeof payload?.message === "string") return payload.message;
  return fallback;
}

function utcTimestamp(localValue) {
  if (!localValue) return null;
  return `${localValue.length === 16 ? localValue + ":00" : localValue}Z`;
}

function DatasetIssues({ label, schema }) {
  const issues = schema?.unusable_columns ?? [];
  return (
    <article className="golden-dataset-card">
      <div>
        <span>{label}</span>
        <strong>{schema?.row_count ?? 0} records · {schema?.column_count ?? 0} columns</strong>
      </div>
      <p>{issues.length ? `${issues.length} missing or unusable columns must be reviewed.` : "All non-timestamp columns are usable numeric candidates."}</p>
      {issues.length ? (
        <details>
          <summary>Show missing or unusable columns ({issues.length})</summary>
          <ul>{issues.map((item) => <li key={item.column}><strong>{item.column}</strong><span>{item.reasons.join(" ")}</span></li>)}</ul>
        </details>
      ) : null}
    </article>
  );
}

function MappingEditor({ assessment, mapping, setMapping, onValidate, busy }) {
  const baselineColumns = assessment.schemas.baseline.columns;
  const comparisonColumns = assessment.schemas.comparison.columns;
  const updateSignal = (index, key, value) => {
    setMapping((current) => ({
      ...current,
      signals: current.signals.map((signal, signalIndex) => signalIndex === index ? { ...signal, [key]: value } : signal),
    }));
  };
  return (
    <section className="golden-step" aria-labelledby="golden-mapping-title">
      <header className="golden-step__header"><span>2</span><div><p>Explicit mapping</p><h3 id="golden-mapping-title">Confirm what every field means</h3><small>Analysis stays locked until timestamps and at least two comparable signals are usable in both periods.</small></div></header>
      <div className="golden-timestamp-grid">
        <label><span>Baseline timestamp</span><select value={mapping.baseline_timestamp_column} onChange={(event) => setMapping((current) => ({ ...current, baseline_timestamp_column: event.target.value }))}><option value="">Select column</option>{baselineColumns.map((column) => <option key={column.name}>{column.name}</option>)}</select></label>
        <label><span>Comparison timestamp</span><select value={mapping.comparison_timestamp_column} onChange={(event) => setMapping((current) => ({ ...current, comparison_timestamp_column: event.target.value }))}><option value="">Select column</option>{comparisonColumns.map((column) => <option key={column.name}>{column.name}</option>)}</select></label>
      </div>
      <div className="golden-mapping-table" role="table" aria-label="Signal mapping">
        <div className="golden-mapping-table__header" role="row"><span>Use</span><span>Baseline column</span><span>Comparison column</span><span>Signal name</span><span>Unit</span><span>System</span><span>Role</span></div>
        {mapping.signals.map((signal, index) => (
          <div className="golden-mapping-row" role="row" key={signal.id}>
            <label className="golden-check"><input type="checkbox" checked={signal.include !== false} onChange={(event) => updateSignal(index, "include", event.target.checked)} /><span className="sr-only">Use {signal.name}</span></label>
            <span>{signal.baseline_column}</span>
            <label><span className="sr-only">Comparison column for {signal.name}</span><select value={signal.comparison_column} onChange={(event) => updateSignal(index, "comparison_column", event.target.value)}><option value="">Not mapped</option>{comparisonColumns.map((column) => <option key={column.name}>{column.name}</option>)}</select></label>
            <label><span className="sr-only">Signal name for {signal.baseline_column}</span><input value={signal.name} onChange={(event) => updateSignal(index, "name", event.target.value)} /></label>
            <label><span className="sr-only">Unit for {signal.name}</span><input value={signal.unit} placeholder="Unit" onChange={(event) => updateSignal(index, "unit", event.target.value)} /></label>
            <label><span className="sr-only">System for {signal.name}</span><input value={signal.system_name} onChange={(event) => updateSignal(index, "system_name", event.target.value)} /></label>
            <label><span className="sr-only">Role for {signal.name}</span><select value={signal.role} onChange={(event) => updateSignal(index, "role", event.target.value)}><option value="input">Input / demand</option><option value="response">Response</option><option value="signal">Other signal</option><option value="mode">Mode / staging</option><option value="context">Context only</option></select></label>
          </div>
        ))}
      </div>
      <button type="button" className="monitoring-button monitoring-button--quiet" onClick={onValidate} disabled={busy}>{busy ? "Validating…" : "Validate mapping"}</button>
    </section>
  );
}

function QualityGate({ gate }) {
  if (!gate) return null;
  const notes = (gate.data_quality_notes ?? gate.warnings ?? []).map(qualityNote).filter(Boolean);
  return (
    <details className="golden-dashboard-detail golden-dashboard-detail--quality">
      <summary>
        <h4>Data quality notes</h4>
        <span>{notes.length ? `${notes.length} recorded ${notes.length === 1 ? "note" : "notes"}` : gate.summary}</span>
      </summary>
      <div className="golden-dashboard-detail__body">
        <section className="golden-step golden-step--detail" aria-labelledby="quality-gate-title">
          <header className="golden-step__header"><span>3</span><div><p>Baseline quality gate</p><h3 id="quality-gate-title">{gate.summary}</h3><small>No confident baseline means no finding claim.</small></div></header>
          <div className={`golden-decision golden-decision--${gate.passed ? "accepted" : "withheld"}`} role="status">
            <strong>{gate.passed ? "Baseline accepted" : "Baseline withheld"}</strong>
            <span>{gate.passed ? `${gate.included_signal_count} independent signals passed the gate.` : "Analysis stopped before relationship scoring."}</span>
          </div>
          {gate.blocking_reasons?.length ? <ul className="golden-reasons">{gate.blocking_reasons.map((item) => <li key={item}>{item}</li>)}</ul> : null}
          <dl className="golden-period-facts">
            <div><dt>Baseline coverage</dt><dd>{percent(gate.baseline_period?.time_coverage)}</dd></div>
            <div><dt>Baseline records</dt><dd>{gate.baseline_period?.usable_timestamp_rows ?? 0}</dd></div>
            <div><dt>Comparison records</dt><dd>{gate.comparison_period?.usable_timestamp_rows ?? 0}</dd></div>
            <div><dt>Excluded signals</dt><dd>{gate.excluded_signal_count ?? 0}</dd></div>
          </dl>
          <div className="golden-quality-table" role="table" aria-label="Signal quality decisions">
            <div role="row"><span>Signal</span><span>Coverage</span><span>Checks</span><span>Decision and exact reason</span></div>
            {gate.signals?.map((signal) => (
              <div role="row" key={signal.id}>
                <strong>{signal.name}<small>{signal.system_name}</small></strong>
                <span>{percent(signal.baseline.coverage)}</span>
                <span>{signal.baseline.flags.length ? signal.baseline.flags.join(", ") : "Passed"}</span>
                <span className={signal.included ? "is-included" : "is-excluded"}>{signal.included ? "Included in baseline." : signal.exclusion_reasons.join(" ")}</span>
              </div>
            ))}
          </div>
          {notes.length ? (
            <section className="golden-data-quality-notes" aria-label="Recorded data quality notes">
              <strong>Recorded notes</strong>
              <ul>{notes.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          ) : null}
        </section>
      </div>
    </details>
  );
}

function OperatingModes({ modes, analysis }) {
  if (!modes?.length) return null;
  return (
    <details className="golden-dashboard-detail">
      <summary>
        <h4>Methodology</h4>
        <span>{analysis?.method ?? `${modes.length} operating ${modes.length === 1 ? "mode" : "modes"} assessed`}</span>
      </summary>
      <div className="golden-dashboard-detail__body">
        <section className="golden-step golden-step--detail" aria-labelledby="operating-modes-title">
          <header className="golden-step__header"><span>4</span><div><p>Comparable operation</p><h3 id="operating-modes-title">Like-for-like operating modes</h3><small>Startup, shutdown, and staging are separated so normal mode changes cannot become findings.</small></div></header>
          {analysis ? (
            <dl className="golden-method-facts">
              <div><dt>Method</dt><dd>{analysis.method ?? "Not available"}</dd></div>
              <div><dt>Relationships assessed</dt><dd>{analysis.relationship_candidates_assessed ?? "Not available"}</dd></div>
              <div><dt>Event timestamp used</dt><dd>{analysis.event_timestamp_used == null ? "Not available" : analysis.event_timestamp_used ? "Yes" : "No"}</dd></div>
            </dl>
          ) : null}
          <div className="golden-mode-grid">
            {modes.map((mode) => <article key={mode.mode}><strong>{titleCase(mode.mode)}</strong><span>{mode.baseline_records} baseline · {mode.comparison_records} comparison</span><small>{mode.comparable ? (mode.used_for_findings ? "Compared for findings" : "Separated from findings") : "Insufficient matched records"}</small></article>)}
          </div>
        </section>
      </div>
    </details>
  );
}

function RelationshipEvidence({ relationship, assessmentId }) {
  return (
    <article className="golden-relationship">
      <header><div><span>{titleCase(relationship.operating_mode)}</span><h4>{relationship.relationship}</h4></div><a href={buildApiUrl(relationship.exact_records.download_url || `/api/pilot-assessments/${assessmentId}/records/${relationship.relationship_id}.csv`)} download>Exact records ({relationship.exact_records.record_count})</a></header>
      <p>{relationship.what_changed}</p>
      <dl>
        <div><dt>Before behavior</dt><dd>Correlation {fixed(relationship.before_behavior.correlation)} · slope {fixed(relationship.before_behavior.slope, 3)}</dd></div>
        <div><dt>After behavior</dt><dd>Correlation {fixed(relationship.after_behavior.correlation)} · slope {fixed(relationship.after_behavior.slope, 3)}</dd></div>
        <div><dt>Magnitude</dt><dd>{fixed(relationship.magnitude.absolute_correlation_change)} correlation change · {relationship.magnitude.slope_change_percent == null ? "slope change unavailable" : `${fixed(relationship.magnitude.slope_change_percent, 1)}% slope change`}</dd></div>
        <div><dt>Persistence</dt><dd>{relationship.persistence.supporting_windows} of {relationship.persistence.assessed_windows} windows after onset</dd></div>
        <div><dt>Start time</dt><dd>{dateTime(relationship.start_time)}</dd></div>
        <div><dt>Record proof</dt><dd><code>{relationship.exact_records.sha256}</code></dd></div>
      </dl>
      <div className="golden-relationship__limit"><strong>Data quality notes</strong><span>{relationship.data_quality_limitations?.length ? relationship.data_quality_limitations.join(" ") : "No relationship-specific note recorded."}</span></div>
    </article>
  );
}

function CredibilitySection({ finding, validation }) {
  if (!validation) return null;
  const leadTime = fixed(Math.abs(validation.lead_time_hours), 2);
  const detection = validation.surfaced_before_event
    ? `Detected ${leadTime} hours before the recorded event`
    : `Detected ${leadTime} hours after the recorded event`;
  const persistence = validation.persisted_through_event == null
    ? "Persistence through the event was not observable"
    : validation.persisted_through_event ? "Persisted through the event" : "Did not persist through the event";
  const recovery = validation.disappeared_after_repair == null
    ? "Post-repair behavior was not observable"
    : validation.disappeared_after_repair ? "Disappeared after repair" : "Remained after repair";
  return (
    <section className="golden-credibility" aria-labelledby={`credibility-${finding.finding_id}`}>
      <h4 id={`credibility-${finding.finding_id}`}>Why this finding is credible</h4>
      <ul>
        <li>{detection}</li>
        <li>{persistence}</li>
        <li>Supported by {finding.evidence_count} changed {Number(finding.evidence_count) === 1 ? "relationship" : "relationships"}</li>
        <li>{recovery}</li>
      </ul>
    </section>
  );
}

function RepairComparison({ finding, repairTimestamp }) {
  const comparison = repairComparison(finding, repairTimestamp);
  if (!comparison) return null;
  const decreased = comparison.after <= comparison.before;
  return (
    <section className="golden-repair-comparison" aria-labelledby={`repair-comparison-${finding.finding_id}`}>
      <h4 id={`repair-comparison-${finding.finding_id}`}>Before-and-after repair comparison</h4>
      <p>Median behavioral deviation {decreased ? "decreased" : "increased"} from {fixed(comparison.before)} before repair to {fixed(comparison.after)} after repair.</p>
      {comparison.reduction !== null && decreased ? <strong>{fixed(comparison.reduction)}% reduction</strong> : null}
    </section>
  );
}

function FindingResult({ finding, assessmentId, validation, qualityGate, expanded, onToggle }) {
  const relationshipCount = Number(finding.evidence_count) || 0;
  const evidenceRegionId = `relationship-evidence-${finding.finding_id}`;
  const leadTimeHours = Number(validation?.lead_time_hours);
  const leadTimeAvailable = validation?.lead_time_hours != null && Number.isFinite(leadTimeHours);
  return (
    <article className="golden-finding">
      <header className="golden-finding__header">
        <div className="golden-finding__identity">
          <span className="golden-finding__status"><i aria-hidden="true" />{finding.persisted ? "Persistent Change Detected" : "Change Detected"}</span>
          <h3>{findingTitle(finding)}</h3>
          <span className="sr-only">{findingOperationalSummary(finding)}</span>
          <small>{finding.system_name}</small>
        </div>
        <button type="button" className="monitoring-button monitoring-button--primary" aria-expanded={expanded} aria-controls={evidenceRegionId} onClick={onToggle}>View relationship evidence</button>
      </header>
      <dl className="golden-finding__metrics" aria-label="Finding overview">
        <div><dt>First detected</dt><dd>{metricDateTime(finding.first_surfaced_at)}</dd></div>
        <div><dt>Lead time</dt><dd>{leadTimeAvailable ? `${fixed(Math.abs(leadTimeHours), 1)} hours` : "Not available"}</dd>{leadTimeAvailable ? <small>{validation.surfaced_before_event ? "Before recorded event" : "After recorded event"}</small> : null}</div>
        <div><dt>Evidence</dt><dd>{relationshipCount} supporting relationship {relationshipCount === 1 ? "change" : "changes"}</dd></div>
        <div><dt>Persistence</dt><dd>{finding.persisted ? "Confirmed" : "Not confirmed"}</dd></div>
        <div className="golden-finding__metric--status"><dt>Status</dt><dd>{findingStatus(finding, validation)}</dd></div>
        <div><dt>Baseline</dt><dd>{baselineStatus(qualityGate)}</dd></div>
      </dl>
      {expanded ? (
        <section id={evidenceRegionId} className="golden-evidence-drawer" aria-label="Supporting relationship evidence">
          <header><strong>Supporting relationship evidence</strong><span>{relationshipCount} {relationshipCount === 1 ? "change" : "changes"}</span></header>
          <div className="golden-evidence-list">{finding.relationships.map((relationship) => <RelationshipEvidence key={relationship.relationship_id} relationship={relationship} assessmentId={assessmentId} />)}</div>
        </section>
      ) : null}
    </article>
  );
}

function EventBacktest({ assessment, onUpdated, apiFetch, accessCode, busy, setBusy, setError }) {
  const [event, setEvent] = useState({ label: "Tower outage / work order", timestamp: "", repairTimestamp: "" });
  const backtest = assessment.event_backtest;
  async function submit(eventObject) {
    eventObject.preventDefault();
    setBusy("event");
    setError("");
    try {
      const response = await apiFetch(`/api/pilot-assessments/${assessment.assessment_id}/event`, {
        accessCode,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_label: event.label,
          event_timestamp: utcTimestamp(event.timestamp),
          repair_timestamp: utcTimestamp(event.repairTimestamp),
        }),
      });
      const payload = await responseJson(response);
      if (!response?.ok) throw new Error(errorMessage(payload, "The event backtest could not be completed."));
      onUpdated(payload);
    } catch (error) {
      setError(String(error?.message || "The event backtest could not be completed."));
    } finally {
      setBusy("");
    }
  }
  if (backtest) {
    return (
      <details className="golden-dashboard-detail golden-dashboard-detail--timeline">
        <summary>
          <h4>Detection timeline</h4>
          <span>{backtest.event_label} · {metricDateTime(backtest.event_timestamp)}</span>
        </summary>
        <div className="golden-dashboard-detail__body">
          <section className="golden-step golden-step--detail" aria-labelledby="event-backtest-title">
            <header className="golden-step__header"><span>6</span><div><p>Historical event backtest</p><h3 id="event-backtest-title">Blinded backtest result</h3><small>The analysis was locked before the recorded event was revealed.</small></div></header>
            <div className="golden-backtest">
              <span className="golden-blinded-proof">{backtest.analysis_was_blinded ? "Blinded analysis confirmed" : "Blinding could not be confirmed"}</span>
              {backtest.findings.length ? backtest.findings.map((result) => {
                const finding = assessment.analysis?.findings?.find((item) => item.finding_id === result.finding_id);
                return (
                  <div className="golden-timeline-result" key={result.finding_id}>
                    <dl>
                      <div><dt>First detected</dt><dd>{dateTime(result.first_surfaced_at)}</dd></div>
                      <div><dt>Recorded event</dt><dd>{dateTime(backtest.event_timestamp)}</dd></div>
                      <div><dt>Recorded repair</dt><dd>{dateTime(backtest.repair_timestamp)}</dd></div>
                      <div><dt>Lead time</dt><dd>{result.surfaced_before_event ? `${fixed(result.lead_time_hours)} hours before event` : `${fixed(Math.abs(result.lead_time_hours))} hours after event`}</dd></div>
                      <div><dt>Persisted to event</dt><dd>{result.persisted_through_event == null ? "Not observable" : result.persisted_through_event ? "Yes" : "No"}</dd></div>
                      <div><dt>After repair</dt><dd>{result.disappeared_after_repair == null ? "Not observable" : result.disappeared_after_repair ? "Finding disappeared" : "Finding remained"}</dd></div>
                    </dl>
                    {finding ? <CredibilitySection finding={finding} validation={result} /> : null}
                    {finding ? <RepairComparison finding={finding} repairTimestamp={backtest.repair_timestamp} /> : null}
                  </div>
                );
              }) : <p>No finding was available to compare against the event.</p>}
            </div>
          </section>
        </div>
      </details>
    );
  }
  return (
    <section className="golden-step" aria-labelledby="event-backtest-title">
      <header className="golden-step__header"><span>6</span><div><p>Historical event backtest</p><h3 id="event-backtest-title">Reveal the known event only now</h3><small>The analysis is complete and locked. Adding the event cannot change the finding.</small></div></header>
      <form className="golden-event-form" onSubmit={submit}>
        <label><span>Known event or work-order label</span><input required value={event.label} onChange={(change) => setEvent((current) => ({ ...current, label: change.target.value }))} /></label>
        <label><span>Known event timestamp (UTC)</span><input required type="datetime-local" value={event.timestamp} onChange={(change) => setEvent((current) => ({ ...current, timestamp: change.target.value }))} /></label>
        <label><span>Repair or recovery timestamp (UTC, optional)</span><input type="datetime-local" value={event.repairTimestamp} onChange={(change) => setEvent((current) => ({ ...current, repairTimestamp: change.target.value }))} /></label>
        <button type="submit" className="monitoring-button monitoring-button--primary" disabled={busy === "event"}>{busy === "event" ? "Calculating…" : "Run event backtest"}</button>
      </form>
    </section>
  );
}

function EngineerFeedback({ assessment, onUpdated, apiFetch, accessCode, busy, setBusy, setError }) {
  const [category, setCategory] = useState("useful");
  const [note, setNote] = useState("");
  const findings = assessment.analysis?.findings ?? [];
  const [findingId, setFindingId] = useState(findings[0]?.finding_id ?? "");
  async function submit(event) {
    event.preventDefault();
    setBusy("feedback");
    setError("");
    try {
      const response = await apiFetch(`/api/pilot-assessments/${assessment.assessment_id}/feedback`, {
        accessCode,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, note, finding_id: findingId || null }),
      });
      const payload = await responseJson(response);
      if (!response?.ok) throw new Error(errorMessage(payload, "Feedback could not be recorded."));
      onUpdated(payload);
      setNote("");
    } catch (error) {
      setError(String(error?.message || "Feedback could not be recorded."));
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="golden-step" aria-labelledby="engineer-feedback-title">
      <header className="golden-step__header"><span>7</span><div><p>Engineer feedback</p><h3 id="engineer-feedback-title">Record the engineering judgment</h3><small>Every response is appended with its author, note, and timestamp. Earlier entries cannot be overwritten.</small></div></header>
      <form className="golden-feedback-form" onSubmit={submit}>
        <fieldset><legend>Response</legend><div>{FEEDBACK_OPTIONS.map(([value, label]) => <label key={value} className={category === value ? "is-selected" : ""}><input type="radio" name="assessment-feedback" value={value} checked={category === value} onChange={() => setCategory(value)} />{label}</label>)}</div></fieldset>
        {findings.length > 1 ? <label><span>Finding</span><select value={findingId} onChange={(event) => setFindingId(event.target.value)}>{findings.map((finding) => <option key={finding.finding_id} value={finding.finding_id}>{findingTitle(finding)}</option>)}</select></label> : null}
        <label><span>Engineer notes</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Operational context, sensor observations, or next investigation step" /></label>
        <button type="submit" className="monitoring-button monitoring-button--quiet" disabled={busy === "feedback"}>{busy === "feedback" ? "Recording…" : "Append feedback"}</button>
      </form>
      {assessment.feedback_history?.length ? <ol className="golden-feedback-history">{assessment.feedback_history.map((item) => <li key={item.feedback_id}><strong>{titleCase(item.category)}</strong><span>{item.note || "No note supplied."}</span><small>{dateTime(item.recorded_at)} · {item.recorded_by}</small></li>)}</ol> : null}
    </section>
  );
}

export default function GoldenNuggetAssessment({ apiFetch, accessCode }) {
  const [assessment, setAssessment] = useState(null);
  const [mapping, setMapping] = useState(null);
  const [files, setFiles] = useState({ baseline: null, comparison: null });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [expandedFinding, setExpandedFinding] = useState("");
  const terminal = ["analysis_complete", "baseline_withheld"].includes(assessment?.status);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve(apiFetch?.("/api/pilot-assessments?limit=1", { accessCode, cache: "no-store" }))
      .then(async (response) => {
        const payload = await responseJson(response);
        if (!cancelled && response?.ok && payload.assessments?.length) setAssessment(payload.assessments[0]);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [accessCode, apiFetch]);

  useEffect(() => {
    if (assessment?.mapping) setMapping(JSON.parse(JSON.stringify(assessment.mapping)));
  }, [assessment?.assessment_id, assessment?.mapping, assessment?.updated_at]);

  const validation = assessment?.mapping_validation;
  const findings = assessment?.analysis?.findings ?? [];
  const canAnalyze = validation?.ready && ["mapping_required", "ready_to_analyze"].includes(assessment?.status);
  const datasetScope = useMemo(() => {
    if (!assessment) return "";
    return `${assessment.datasets.baseline.filename} → ${assessment.datasets.comparison.filename}`;
  }, [assessment]);

  async function intake(event) {
    event.preventDefault();
    if (!files.baseline || !files.comparison) return;
    setBusy("intake");
    setError("");
    const body = new FormData();
    body.append("baseline_file", files.baseline);
    body.append("comparison_file", files.comparison);
    try {
      const response = await apiFetch("/api/pilot-assessments/intake", { accessCode, method: "POST", body });
      const payload = await responseJson(response);
      if (!response?.ok) throw new Error(errorMessage(payload, "The datasets could not be inspected."));
      setAssessment(payload);
      setExpandedFinding("");
    } catch (uploadError) {
      setError(String(uploadError?.message || "The datasets could not be inspected."));
    } finally {
      setBusy("");
    }
  }

  async function validateMapping() {
    if (!assessment || !mapping) return null;
    setBusy("mapping");
    setError("");
    try {
      const response = await apiFetch(`/api/pilot-assessments/${assessment.assessment_id}/mapping`, {
        accessCode,
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mapping),
      });
      const payload = await responseJson(response);
      if (!response?.ok) throw new Error(errorMessage(payload, "The mapping could not be validated."));
      setAssessment(payload);
      return payload;
    } catch (mappingError) {
      setError(String(mappingError?.message || "The mapping could not be validated."));
      return null;
    } finally {
      setBusy("");
    }
  }

  async function analyze() {
    setBusy("analysis");
    setError("");
    try {
      let current = assessment;
      if (mapping) {
        const response = await apiFetch(`/api/pilot-assessments/${assessment.assessment_id}/mapping`, {
          accessCode,
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(mapping),
        });
        current = await responseJson(response);
        if (!response?.ok || !current.mapping_validation?.ready) throw new Error(errorMessage(current, "Complete the mapping before analysis."));
        setAssessment(current);
      }
      const response = await apiFetch(`/api/pilot-assessments/${assessment.assessment_id}/analyze`, { accessCode, method: "POST" });
      const payload = await responseJson(response);
      if (!response?.ok) throw new Error(errorMessage(payload, "The blinded assessment could not be completed."));
      setAssessment(payload);
      setExpandedFinding("");
    } catch (analysisError) {
      setError(String(analysisError?.message || "The blinded assessment could not be completed."));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="golden-assessment" data-testid="golden-nugget-assessment">
      <header className="golden-assessment__intro">
        <div><span className="monitoring-eyebrow">{terminal ? "Assessment overview" : "Golden Nugget workflow"}</span><h2>{terminal ? "Operations assessment" : "Historical outage assessment"}</h2><p>{terminal ? assessment.analysis?.conclusion : "Upload real tower telemetry, lock the analysis before revealing the known event, and produce a record-backed engineering report."}</p></div>
        {assessment ? <button type="button" className="monitoring-button monitoring-button--quiet" onClick={() => { setAssessment(null); setMapping(null); setFiles({ baseline: null, comparison: null }); setError(""); }}>Start new assessment</button> : null}
      </header>

      {error ? <div className="monitoring-notice monitoring-notice--error" role="alert"><strong>Assessment needs attention</strong><span>{error}</span></div> : null}

      {!assessment ? (
        <section className="golden-step" aria-labelledby="dataset-intake-title">
          <header className="golden-step__header"><span>1</span><div><p>Real dataset intake</p><h3 id="dataset-intake-title">Upload two distinct operating periods</h3><small>Do not include the outage date in a filename or note. It is entered only after analysis.</small></div></header>
          <form className="golden-intake" onSubmit={intake}>
            <label><span>Baseline period CSV</span><input required type="file" accept=".csv,text/csv" onChange={(event) => setFiles((current) => ({ ...current, baseline: event.target.files?.[0] ?? null }))} /><small>A period believed to represent normal operation.</small></label>
            <label><span>Later comparison period CSV</span><input required type="file" accept=".csv,text/csv" onChange={(event) => setFiles((current) => ({ ...current, comparison: event.target.files?.[0] ?? null }))} /><small>The later period to assess without event-date knowledge.</small></label>
            <button type="submit" className="monitoring-button monitoring-button--primary" disabled={!files.baseline || !files.comparison || busy === "intake"}>{busy === "intake" ? "Inspecting real records…" : "Inspect datasets"}</button>
          </form>
        </section>
      ) : (
        <>
          <div className="golden-scope"><span>Assessment {assessment.assessment_id}</span><strong>{datasetScope}</strong><small>{terminal ? `Analysis locked ${dateTime(assessment.analysis_completed_at)}` : "Known event remains hidden"}</small></div>
          {!terminal ? <section className="golden-step">
            <header className="golden-step__header"><span>1</span><div><p>Real dataset intake</p><h3>Column inspection complete</h3><small>Missing and unusable fields are visible before analysis.</small></div></header>
            <div className="golden-dataset-grid"><DatasetIssues label="Baseline period" schema={assessment.schemas.baseline} /><DatasetIssues label="Comparison period" schema={assessment.schemas.comparison} /></div>
          </section> : null}

          {!terminal && mapping ? <MappingEditor assessment={assessment} mapping={mapping} setMapping={setMapping} onValidate={validateMapping} busy={busy === "mapping"} /> : null}
          {!terminal && validation ? (
            <section className="golden-readiness">
              <div><strong>{validation.ready ? "Mapping ready" : "Mapping incomplete"}</strong><span>{validation.ready ? "The quality gate can now assess the baseline." : validation.errors.join(" ")}</span>{validation.warnings?.length ? <small>{validation.warnings.join(" ")}</small> : null}</div>
              <button type="button" className="monitoring-button monitoring-button--primary" onClick={analyze} disabled={!canAnalyze || Boolean(busy)}>{busy === "analysis" ? "Running blinded analysis…" : "Run blinded analysis"}</button>
            </section>
          ) : null}

          {terminal ? (
            <section className="golden-results" aria-labelledby="assessment-findings-title">
              <h2 className="sr-only" id="assessment-findings-title">Assessment findings overview</h2>
              {findings.length ? findings.map((finding) => (
                <FindingResult
                  key={finding.finding_id}
                  finding={finding}
                  assessmentId={assessment.assessment_id}
                  validation={assessment.event_backtest?.findings?.find((item) => item.finding_id === finding.finding_id)}
                  qualityGate={assessment.quality_gate}
                  expanded={expandedFinding === finding.finding_id}
                  onToggle={() => setExpandedFinding((current) => current === finding.finding_id ? "" : finding.finding_id)}
                />
              )) : <div className="golden-no-finding"><strong>No alert card was created.</strong><span>Neraium stays silent when evidence does not meet the persistence and comparable-mode thresholds.</span></div>}
            </section>
          ) : null}

          {terminal ? <QualityGate gate={assessment.quality_gate} /> : null}
          {terminal ? <OperatingModes modes={assessment.operating_modes} analysis={assessment.analysis} /> : null}
          {terminal ? <EventBacktest assessment={assessment} onUpdated={setAssessment} apiFetch={apiFetch} accessCode={accessCode} busy={busy} setBusy={setBusy} setError={setError} /> : null}
          {terminal ? <EngineerFeedback assessment={assessment} onUpdated={setAssessment} apiFetch={apiFetch} accessCode={accessCode} busy={busy} setBusy={setBusy} setError={setError} /> : null}
          {terminal ? (
            <section className="golden-report">
              <div><span className="monitoring-eyebrow">8 · Exportable pilot report</span><h3>Defensible assessment package</h3><p>Dataset scope, quality decisions, mode-matched findings, lead time, limitations, feedback, and exact-record hashes.</p></div>
              <a className="monitoring-button monitoring-button--primary" href={buildApiUrl(`/api/pilot-assessments/${assessment.assessment_id}/report.html`)} download>Export HTML report</a>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
