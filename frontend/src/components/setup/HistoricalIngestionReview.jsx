import { useEffect, useMemo, useState } from "react";

import {
  fetchHistoricalIngestionProfile,
  fetchUploadJobProgress,
  submitHistoricalIngestionReview,
} from "../../services/api/uploadApi";
import JobProgressPanel from "./JobProgressPanel";


const SUPPORTED_ROLES = [
  "process_variable", "process_rate", "flow", "pressure", "differential_pressure",
  "temperature", "return_temperature", "supply_temperature", "environmental_temperature",
  "power", "energy", "valve_command", "valve_position", "pump_status", "equipment_state",
  "speed", "frequency", "setpoint", "demand", "load", "control_command",
];
const SUPPORTED_UNITS = ["degF", "degC", "psi", "kPa", "bar", "gpm", "L/s", "L/min", "m3/h", "W", "kW", "MW", "kWh", "%", "fraction", "RPM", "Hz"];

function label(value) {
  return String(value || "Not available").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function readinessCopy(outcome) {
  return {
    ready: "Ready for analysis",
    ready_with_limitations: "Ready with documented limitations",
    review_required: "Focused review required",
    insufficient_trustworthy_data: "Not enough trustworthy data",
  }[outcome] || "Readiness pending";
}

function summaryItems(profile) {
  const counts = profile?.summary?.signal_counts ?? profile?.signal_counts ?? {};
  return [
    ["Signals detected", counts.detected],
    ["Confidently mapped", counts.confidently_mapped],
    ["Need review", counts.need_review],
    ["Excluded", counts.excluded],
    ["Unit conflicts", counts.unit_conflicts],
    ["Duplicate candidates", counts.duplicate_candidates],
    ["Timestamp gaps", counts.timestamp_gaps],
    ["Configuration boundaries", counts.configuration_boundaries],
  ];
}

function ReviewDecisionRow({ item, signal, value, onChange }) {
  const isUnit = item.type === "unit";
  return (
    <li className="historical-review__item">
      <div>
        <strong>{signal?.source_column || item.source_column || "Timestamp record"}</strong>
        <p>{item.reason}</p>
        {signal?.proposed_canonical_role ? <small>Proposed role: {label(signal.proposed_canonical_role)}</small> : null}
      </div>
      {isUnit ? (
        <label>
          <span>Confirmed source unit</span>
          <select
            aria-label={`Confirmed source unit for ${signal?.source_column || "signal"}`}
            value={value?.unit || ""}
            onChange={(event) => onChange({ unit: event.target.value || undefined })}
          >
            <option value="">Leave unresolved</option>
            {SUPPORTED_UNITS.map((unit) => <option key={unit} value={unit}>{unit}</option>)}
          </select>
        </label>
      ) : item.type === "semantic_mapping" ? (
        <div className="historical-review__mapping-controls">
          <label>
            <span>Decision</span>
            <select
              aria-label={`Mapping decision for ${signal?.source_column || "signal"}`}
              value={value?.mapping_action || ""}
              onChange={(event) => onChange({ mapping_action: event.target.value || undefined, canonical_role: undefined })}
            >
              <option value="">Choose a decision</option>
              {signal?.proposed_canonical_role ? <option value="accept">Accept proposal</option> : null}
              <option value="choose_role">Choose supported role</option>
              <option value="leave_unresolved">Leave unresolved</option>
              <option value="exclude">Exclude from analysis</option>
            </select>
          </label>
          {value?.mapping_action === "choose_role" ? (
            <label>
              <span>Canonical role</span>
              <select
                aria-label={`Canonical role for ${signal?.source_column || "signal"}`}
                value={value?.canonical_role || ""}
                onChange={(event) => onChange({ canonical_role: event.target.value || undefined })}
              >
                <option value="">Choose role</option>
                {SUPPORTED_ROLES.map((role) => <option key={role} value={role}>{label(role)}</option>)}
              </select>
            </label>
          ) : null}
        </div>
      ) : (
        <span className="historical-review__evidence-label">Review evidence</span>
      )}
    </li>
  );
}

export default function HistoricalIngestionReview({
  datasetId,
  initialProfile = null,
  apiFetch,
  accessCode,
  onUpdated = null,
}) {
  const [profile, setProfile] = useState(initialProfile);
  const [state, setState] = useState(initialProfile ? "ready" : "idle");
  const [message, setMessage] = useState("");
  const [decisions, setDecisions] = useState({});
  const [reviewJob, setReviewJob] = useState(null);

  useEffect(() => {
    if (!datasetId || typeof apiFetch !== "function") return undefined;
    let active = true;
    setState((current) => (current === "saving" ? current : "loading"));
    fetchHistoricalIngestionProfile({ datasetId, apiFetch, accessCode })
      .then((next) => {
        if (!active) return;
        setProfile(next);
        setState("ready");
        setMessage("");
      })
      .catch((error) => {
        if (!active) return;
        setState(initialProfile ? "ready" : "error");
        setMessage(error?.message || "The ingestion profile could not be loaded.");
      });
    return () => { active = false; };
  }, [accessCode, apiFetch, datasetId, initialProfile]);

  useEffect(() => {
    if (state !== "saving" || !datasetId || typeof apiFetch !== "function") return undefined;
    let active = true;
    let timer = null;

    const poll = async () => {
      try {
        const next = await fetchUploadJobProgress({ jobId: datasetId, apiFetch, accessCode });
        if (!active) return;
        setReviewJob(next);
      } catch {
        if (!active) return;
        setReviewJob((current) => current ? {
          ...current,
          poll_connection_state: "retrying",
          message: "The progress connection was interrupted. Retrying while the review continues.",
        } : current);
      }
      if (active) timer = window.setTimeout(poll, 1500);
    };

    timer = window.setTimeout(poll, 150);
    return () => {
      active = false;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [accessCode, apiFetch, datasetId, state]);

  const signalById = useMemo(() => Object.fromEntries(
    (profile?.signal_profiles || []).map((signal) => [signal.canonical_signal_id, signal]),
  ), [profile]);
  const signals = profile?.signal_profiles || [];
  const excludedSignals = signals.filter((signal) => !signal.included_for_analysis);
  const qualitySignals = signals.filter((signal) => (signal.quality?.findings || []).length);
  const duplicateChannels = profile?.duplicate_channels || [];
  const timestampWarnings = profile?.timestamp_profile?.warnings || [];
  const configurationBoundaries = profile?.configuration_profile?.boundaries || [];
  const actionableItems = (profile?.review?.items || []).filter((item) => ["semantic_mapping", "unit"].includes(item.type));
  const evidenceItems = (profile?.review?.items || []).filter((item) => !["semantic_mapping", "unit"].includes(item.type));
  const outcome = profile?.readiness?.outcome ?? profile?.summary?.readiness?.outcome;
  const changedDecisions = Object.entries(decisions).flatMap(([signalId, decision]) => {
    const clean = Object.fromEntries(Object.entries(decision || {}).filter(([, value]) => value !== undefined && value !== ""));
    if (!Object.keys(clean).length) return [];
    if (clean.mapping_action === "choose_role" && !clean.canonical_role) return [];
    return [{ signal_id: signalId, ...clean }];
  });

  async function saveReview() {
    if (!changedDecisions.length) return;
    setState("saving");
    setMessage("");
    setReviewJob(null);
    try {
      const next = await submitHistoricalIngestionReview({ datasetId, decisions: changedDecisions, apiFetch, accessCode });
      setProfile(next);
      if (next?.job_progress?.contract_version === "job-progress.v1") {
        setReviewJob({
          job_id: datasetId,
          status: "COMPLETE",
          processing_state: "complete",
          execution_state: "completed",
          job_progress: next.job_progress,
        });
      }
      setDecisions({});
      setState("ready");
      setMessage("Review saved. The canonical dataset revision is ready for reanalysis.");
      onUpdated?.(next);
    } catch (error) {
      setState("error");
      setMessage(error?.message || "The ingestion review could not be saved.");
    }
  }

  if (!profile && state === "loading") {
    return <section className="historical-review" role="status" aria-live="polite"><p>Loading ingestion profile…</p></section>;
  }
  if (!profile) {
    return message ? <section className="historical-review historical-review--error" role="alert"><p>{message}</p></section> : null;
  }

  return (
    <section className="historical-review" aria-labelledby="historical-review-heading" aria-busy={state === "saving"}>
      <header className="historical-review__header">
        <div>
          <p className="historical-review__eyebrow">Historical data trust</p>
          <h3 id="historical-review-heading">{readinessCopy(outcome)}</h3>
          <p>Neraium preserved the source, profiled uncertainty, and kept unresolved signals out of methods that require them.</p>
        </div>
        <span className={`historical-review__readiness historical-review__readiness--${outcome || "pending"}`}>{label(outcome)}</span>
      </header>

      {reviewJob ? <JobProgressPanel uploadJob={reviewJob} /> : state === "saving" ? (
        <p className="historical-review__progress-waiting" role="status" aria-live="polite">
          Waiting for the first persisted backend progress update…
        </p>
      ) : null}

      <dl className="historical-review__counts" aria-label="Ingestion trust summary">
        {summaryItems(profile).map(([name, value]) => (
          <div key={name}><dt>{name}</dt><dd>{Number(value || 0).toLocaleString()}</dd></div>
        ))}
      </dl>

      {(profile?.readiness?.limitations || []).length ? (
        <div className="historical-review__limitations">
          <strong>Limitations carried into analysis</strong>
          <ul>{profile.readiness.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      ) : null}

      {actionableItems.length ? (
        <div className="historical-review__queue">
          <h4>Review only what needs attention</h4>
          <ul>
            {actionableItems.map((item, index) => {
              const signal = signalById[item.signal_id];
              const decision = decisions[item.signal_id] || {};
              return (
                <ReviewDecisionRow
                  key={`${item.type}-${item.signal_id}-${index}`}
                  item={item}
                  signal={signal}
                  value={decision}
                  onChange={(change) => setDecisions((current) => ({
                    ...current,
                    [item.signal_id]: { ...current[item.signal_id], ...change },
                  }))}
                />
              );
            })}
          </ul>
          <button type="button" className="command-button" disabled={!changedDecisions.length || state === "saving"} onClick={saveReview}>
            {state === "saving" ? "Saving Review…" : "Save Review Decisions"}
          </button>
        </div>
      ) : (
        <p className="historical-review__clear"><span aria-hidden="true">✓</span> No mapping or unit decisions are required for the currently usable signals.</p>
      )}

      <details className="historical-review__details">
        <summary>Inspect timestamp, quality, exclusions, and configuration evidence</summary>
        <div className="historical-review__dimensions">
          {(profile?.trust_dimensions || []).map((dimension) => (
            <article key={dimension.dimension}>
              <span>{label(dimension.status)}</span>
              <h4>{label(dimension.dimension)}</h4>
              <p>{dimension.reasons?.[0] || "No material concern recorded."}</p>
            </article>
          ))}
        </div>
        {evidenceItems.length ? (
          <ul className="historical-review__evidence-list">
            {evidenceItems.map((item, index) => <li key={`${item.type}-${index}`}><strong>{label(item.type)}:</strong> {item.reason}</li>)}
          </ul>
        ) : null}
        {timestampWarnings.length ? (
          <section className="historical-review__evidence-section" aria-labelledby="historical-timestamp-evidence">
            <h4 id="historical-timestamp-evidence">Timestamp concerns</h4>
            <ul>{timestampWarnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </section>
        ) : null}
        {excludedSignals.length ? (
          <section className="historical-review__evidence-section" aria-labelledby="historical-exclusions">
            <h4 id="historical-exclusions">Excluded signals</h4>
            <ul>{excludedSignals.map((signal) => (
              <li key={signal.canonical_signal_id}><strong>{signal.source_column}</strong>: {(signal.exclusion_reasons || ["Not eligible for the current analytical methods."]).join(" ")}</li>
            ))}</ul>
          </section>
        ) : null}
        {duplicateChannels.length ? (
          <section className="historical-review__evidence-section" aria-labelledby="historical-duplicates">
            <h4 id="historical-duplicates">Duplicate candidates</h4>
            <ul>{duplicateChannels.map((duplicate, index) => (
              <li key={`${duplicate.type}-${index}`}><strong>{label(duplicate.type)}</strong>: {duplicate.evidence}</li>
            ))}</ul>
          </section>
        ) : null}
        {qualitySignals.length ? (
          <section className="historical-review__evidence-section" aria-labelledby="historical-quality-findings">
            <h4 id="historical-quality-findings">Signal-quality findings</h4>
            <ul>{qualitySignals.map((signal) => (
              <li key={signal.canonical_signal_id}><strong>{signal.source_column}</strong>: {signal.quality.findings.map((finding) => finding.detail).join(" ")}</li>
            ))}</ul>
          </section>
        ) : null}
        {configurationBoundaries.length ? (
          <section className="historical-review__evidence-section" aria-labelledby="historical-configuration-boundaries">
            <h4 id="historical-configuration-boundaries">Configuration boundaries</h4>
            <ul>{configurationBoundaries.map((boundary) => (
              <li key={boundary.boundary_id}><strong>{boundary.source_column}</strong>: {boundary.evidence}</li>
            ))}</ul>
          </section>
        ) : null}
        {signals.length ? (
          <details className="historical-review__signal-inventory">
            <summary>Inspect all signal mappings</summary>
            <ul>{signals.map((signal) => (
              <li key={signal.canonical_signal_id}>
                <strong>{signal.source_column}</strong>
                <span>{label(signal.mapping_state)} · {label(signal.proposed_canonical_role)} · {signal.unit?.normalized_unit || signal.unit?.inferred_unit || "Unit unresolved"}</span>
              </li>
            ))}</ul>
          </details>
        ) : null}
        <p className="historical-review__identity">Canonical dataset: <code>{String(profile.dataset_identity || "unavailable").slice(0, 16)}</code> · revision {profile.revision || 1}</p>
      </details>
      {message ? <p className={state === "error" ? "upload-error-message" : "historical-review__saved"} role={state === "error" ? "alert" : "status"} aria-live="polite">{message}</p> : null}
    </section>
  );
}
