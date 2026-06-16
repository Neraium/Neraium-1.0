import { useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";
import SystemStateMark from "./SystemStateMark";
import { buildCanonicalFindingRun, OPERATOR_EMPTY_STATE, sanitizeOperatorText } from "../viewModels/operatorFinding";

const FEEDBACK_OPTIONS = [
  { id: "confirmed_issue", label: "Confirmed developing issue" },
  { id: "known_operational_change", label: "Known operational change" },
  { id: "sensor_or_data_problem", label: "Sensor or data problem" },
  { id: "environmental_cause", label: "Environmental cause" },
  { id: "nothing_meaningful", label: "Nothing meaningful" },
];

const NOTIFICATION_STORAGE_KEY = "neraium.observation_notifications.v1";
const VARIABLE_ALIAS_STORAGE_KEY = "neraium.variable_aliases.v1";
const PENDING_OBSERVATION_STORAGE_KEY = "neraium.pending_observation.v1";

function loadJsonStorage(key, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

function loadAliasStorage() {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(VARIABLE_ALIAS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function notificationAllowed() {
  return typeof window !== "undefined" && "Notification" in window;
}

function normalizeObservationStatus(run, persistedRunIds = null) {
  if (String(run?.status ?? "").toLowerCase() === "failed") return "failed";
  if (run?.latest_feedback_category) return "resolved";
  const hasPersistedRun = persistedRunIds instanceof Set && persistedRunIds.has(String(run?.run_id ?? ""));
  if (run?.synthetic_current_run && !hasPersistedRun) return "active";
  const workflowStatus = String(run?.status ?? "").toLowerCase();
  if (workflowStatus && !["complete", "completed", "success"].includes(workflowStatus)) return "processing";
  const observationStatus = String(run?.observation_status ?? "open").toLowerCase();
  if (observationStatus === "completed") return "recorded";
  return observationStatus || "open";
}

function canRecordFeedback(run, persistedRunIds) {
  if (!run?.run_id) return false;
  return persistedRunIds.has(String(run.run_id)) && normalizeObservationStatus(run, persistedRunIds) !== "processing";
}

function observationTypeLabel(value) {
  const text = String(value ?? "").replaceAll("_", " ").trim();
  if (!text) return "Finding";
  const normalized = text.toLowerCase();
  if (normalized === "coupling change") return "Relationship Pattern Shift";
  if (normalized === "recovery elongation") return "Slower Recovery";
  if (normalized === "trajectory drift") return "Behavior Change Continuing";
  if (normalized === "covariance shift") return "Relationship Pattern Shift";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatDurationFrom(dateText) {
  if (!dateText) return "-";
  const ms = Date.now() - new Date(dateText).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "-";
  const hours = Math.round(ms / 3600000);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function displayVariable(name, aliases) {
  const alias = aliases?.[name];
  return alias ? `${alias} (${name})` : name;
}

function displayPatternLabel(value) {
  const text = String(value ?? "").trim();
  if (!text || /^state group [a-z]$/i.test(text)) return "Usual pattern";
  return text;
}

function driftToneFor(run) {
  const drift = Number(run?.drift_metrics?.baseline_distance ?? run?.drift_metrics?.drift_index ?? 0);
  if (!Number.isFinite(drift) || drift < 0.24) return "stable";
  if (drift < 0.72) return "watch";
  return "alert";
}

function summarizeObservation(run, aliases) {
  if (!run) return "No finding selected.";
  const variables = (run?.variables ?? []).slice(0, 2).map((item) => displayVariable(item, aliases));
  const type = String(run?.observation_type ?? "");
  const duration = formatDurationFrom(run?.deformation_started_at);
  if (type === "coupling_change" && variables.length >= 2) {
    return `The relationship between ${variables[0]} and ${variables[1]} changed${duration !== "-" ? ` for ${duration}` : ""}.`;
  }
  if (type === "recovery_elongation") {
    return `Recovery is taking longer than usual${duration !== "-" ? ` and has stayed slow for ${duration}` : ""}.`;
  }
  if (type === "trajectory_drift") {
    return `The system behavior is continuing to move away from its usual pattern${duration !== "-" ? ` for ${duration}` : ""}.`;
  }
  if (type === "covariance_shift") {
    return `The overall relationship pattern changed${duration !== "-" ? ` for ${duration}` : ""}.`;
  }
  return (run?.evidence_summary ?? [])[0] ?? "A persistent system behavior change was found.";
}

function classifyChangeStrength(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "Pending";
  if (numeric < 0.24) return "Low";
  if (numeric < 0.72) return "Moderate";
  return "High";
}

function confidenceForFinding(run) {
  const value = Number(run?.confidence ?? run?.confidence_score ?? run?.evidence_confidence ?? run?.drift_metrics?.confidence);
  if (Number.isFinite(value)) {
    const normalized = value > 1 ? value / 100 : value;
    if (normalized >= 0.82) return "High";
    if (normalized >= 0.62) return "Moderate";
    return "Low";
  }
  const strength = classifyChangeStrength(run?.drift_metrics?.baseline_distance ?? run?.drift_metrics?.drift_index);
  if (strength === "High") return "High";
  if (strength === "Moderate") return "Moderate";
  return "Low";
}

function readPendingObservationRunId() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(PENDING_OBSERVATION_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function clearPendingObservationRunId() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(PENDING_OBSERVATION_STORAGE_KEY);
  } catch {
    // ignore local storage failures
  }
}

function lineChartPoints(values, width = 420, height = 120) {
  if (!values.length) return "";
  const numeric = values.map((item) => Number(item.value)).filter(Number.isFinite);
  const min = numeric.length ? Math.min(...numeric) : 0;
  const max = numeric.length ? Math.max(...numeric) : 1;
  const span = Math.max(max - min, 1);
  return values.map((item, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - (((Number(item.value) - min) / span) * height);
    return `${x},${y}`;
  }).join(" ");
}

export default function ObservationCenterWorkspace({
  apiFetch,
  accessCode,
  canonicalFinding = null,
  currentSession = null,
  onBackToGate = null,
  onReviewEvidence = null,
  onWorkspaceNavigate = null,
}) {
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query] = useState("");
  const [statusFilter] = useState("all");
  const [typeFilter] = useState("all");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [feedbackCategory, setFeedbackCategory] = useState(FEEDBACK_OPTIONS[0].id);
  const [feedbackNote, setFeedbackNote] = useState("");
  const [feedbackState, setFeedbackState] = useState({ status: "idle", message: "" });
  const [notificationPrefs, setNotificationPrefs] = useState(() => loadJsonStorage(NOTIFICATION_STORAGE_KEY, {
    enabled: false,
    quietStart: "22:00",
    quietEnd: "06:00",
  }));
  const [aliases, setAliases] = useState(loadAliasStorage);
  const [selectedAliasVariable, setSelectedAliasVariable] = useState("");
  const [aliasDraft, setAliasDraft] = useState("");
  const [selectedVariables, setSelectedVariables] = useState(["", ""]);
  const latestSeenRunId = useRef("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(notificationPrefs));
    }
  }, [notificationPrefs]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(VARIABLE_ALIAS_STORAGE_KEY, JSON.stringify(aliases));
    }
  }, [aliases]);

  useEffect(() => {
    let cancelled = false;
    async function loadRuns() {
      try {
        if (!cancelled) {
          setLoading(true);
          setError("");
        }
        const response = await apiFetch("/api/evidence/runs", { accessCode });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(String(payload?.detail ?? `Unexpected response: ${response.status}`));
        }
        if (cancelled) return;
        const nextRuns = Array.isArray(payload?.runs) ? payload.runs : [];
        const newestRun = nextRuns[0]?.run_id ?? "";
        const pendingRunId = readPendingObservationRunId();
        if (latestSeenRunId.current && newestRun && newestRun !== latestSeenRunId.current) {
          maybeNotifyForObservation(nextRuns[0], notificationPrefs, aliases);
        }
        latestSeenRunId.current = newestRun;
        setRuns(nextRuns);
        setSelectedRunId((current) => {
          const preferred = current || pendingRunId || newestRun || "";
          if (pendingRunId && nextRuns.some((run) => run.run_id === pendingRunId)) {
            clearPendingObservationRunId();
            return pendingRunId;
          }
          return preferred;
        });
      } catch (loadError) {
        if (cancelled) return;
        setError(String(loadError?.message ?? loadError));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadRuns();
    const timer = window.setInterval(loadRuns, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [accessCode, aliases, apiFetch, notificationPrefs]);

  const persistedRunIds = useMemo(
    () => new Set(runs.map((run) => String(run?.run_id ?? "")).filter(Boolean)),
    [runs],
  );

  const reviewRuns = useMemo(() => {
    const canonicalRun = buildCanonicalFindingRun({ canonicalFinding, currentSession });
    if (!canonicalRun) return runs;
    const persistedRun = runs.find((run) => run?.run_id === canonicalRun.run_id) ?? null;
    const mergedRun = persistedRun
      ? { ...canonicalRun, ...persistedRun, synthetic_current_run: false }
      : canonicalRun;
    const remainingRuns = runs.filter((run) => run?.run_id !== canonicalRun.run_id);
    return [mergedRun, ...remainingRuns];
  }, [canonicalFinding, currentSession, runs]);

  const variables = useMemo(() => {
    const values = new Set();
    reviewRuns.forEach((run) => {
      (run?.variables ?? []).forEach((item) => {
        if (item) values.add(String(item));
      });
    });
    return [...values];
  }, [reviewRuns]);

  useEffect(() => {
    if (!selectedAliasVariable && variables.length) {
      setSelectedAliasVariable(variables[0]);
      setAliasDraft(aliases[variables[0]] ?? "");
    }
  }, [aliases, selectedAliasVariable, variables]);

  useEffect(() => {
    if (selectedAliasVariable) {
      setAliasDraft(aliases[selectedAliasVariable] ?? "");
    }
  }, [aliases, selectedAliasVariable]);

  useEffect(() => {
    if (!selectedVariables[0] && variables.length >= 2) {
      setSelectedVariables([variables[0], variables[1]]);
    }
  }, [selectedVariables, variables]);

  const filteredRuns = useMemo(() => {
    return reviewRuns.filter((run) => {
      const haystack = [
        run?.run_id,
        run?.source_name,
        run?.observation_type,
        run?.structural_state,
        ...(run?.variables ?? []),
        ...(run?.evidence_summary ?? []),
        ...(run?.data_conditions ?? []),
        run?.latest_feedback_category,
      ].join(" ").toLowerCase();
      const queryMatch = !query.trim() || haystack.includes(query.trim().toLowerCase());
      const statusMatch = statusFilter === "all" || normalizeObservationStatus(run, persistedRunIds) === statusFilter;
      const typeMatch = typeFilter === "all" || String(run?.observation_type ?? "") === typeFilter;
      return queryMatch && statusMatch && typeMatch;
    });
  }, [persistedRunIds, query, reviewRuns, statusFilter, typeFilter]);

  const selectedRun = useMemo(
    () => filteredRuns.find((run) => run.run_id === selectedRunId) ?? filteredRuns[0] ?? null,
    [filteredRuns, selectedRunId],
  );

  const latestRun = reviewRuns[0] ?? null;
  const activeFinding = canonicalFinding ?? {
    exists: false,
    status: "Normal",
    confidence: "Low",
    summary: OPERATOR_EMPTY_STATE.title,
    whyItMatters: OPERATOR_EMPTY_STATE.subtitle,
    reviewNext: OPERATOR_EMPTY_STATE.detail,
    supportingEvidence: [],
    technicalDetails: [],
    dataQuality: { missingBaselineValues: [], missingRecentValues: [], unavailableTelemetry: [] },
    evidenceButtonLabel: "Review Evidence",
    emptyState: OPERATOR_EMPTY_STATE,
  };
  const hasCurrentFinding = Boolean(activeFinding.exists);
  const selectedRunSummary = useMemo(() => summarizeObservation(selectedRun, aliases), [aliases, selectedRun]);
  const selectedRunHistoricalFact = selectedRun?.historical_fact ?? "";
  const selectedRunStatus = normalizeObservationStatus(selectedRun, persistedRunIds);
  const selectedRunAllowsFeedback = canRecordFeedback(selectedRun, persistedRunIds);
  const gateOrbState = driftToneFor(latestRun);
  const sourceSnapshots = useMemo(() => {
    const latestBySource = new Map();
    reviewRuns.forEach((run) => {
      const key = String(run?.source_name || run?.source_type || run?.run_id);
      if (!latestBySource.has(key)) {
        latestBySource.set(key, run);
      }
    });
    return [...latestBySource.values()].slice(0, 6);
  }, [reviewRuns]);

  const relationshipSeries = useMemo(() => {
    const [left, right] = selectedVariables;
    if (!left || !right) return [];
    return [...reviewRuns]
      .reverse()
      .filter((run) => (run?.variables ?? []).includes(left) && (run?.variables ?? []).includes(right))
      .map((run) => ({
        runId: run.run_id,
        createdAt: run.created_at,
        value: run?.drift_metrics?.coupling_delta ?? run?.drift_metrics?.baseline_distance ?? run?.drift_metrics?.drift_index ?? 0,
        type: run?.observation_type ?? "observation",
      }));
  }, [reviewRuns, selectedVariables]);

  async function submitFeedback() {
    if (!selectedRun?.run_id || !selectedRunAllowsFeedback) return;
    try {
      setFeedbackState({ status: "saving", message: "" });
      const response = await apiFetch(`/api/evidence/runs/${encodeURIComponent(selectedRun.run_id)}/feedback`, {
        accessCode,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: feedbackCategory, note: feedbackNote || null }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(payload?.detail ?? `Unexpected response: ${response.status}`));
      }
      setRuns((current) => current.map((run) => (run.run_id === payload.run_id ? payload : run)));
      setFeedbackNote("");
      setFeedbackState({ status: "saved", message: "Recorded to system memory." });
    } catch (submitError) {
      setFeedbackState({ status: "error", message: String(submitError?.message ?? submitError) });
    }
  }

  const backControl = (
    <div className="observation-center__back-control">
      <button
        type="button"
        className="system-gate__settings-action"
        onClick={() => onBackToGate?.()}
      >
        Back to System Status
      </button>
      <button
        type="button"
        className="system-gate__settings-action"
        onClick={() => onWorkspaceNavigate?.("help-changelog")}
      >
        Help
      </button>
    </div>
  );

  if (loading) {
    return (
      <section className="workspace-surface">
        {backControl}
        <Panel title="Findings" subtitle="Loading findings..." />
      </section>
    );
  }

  if (error) {
    return (
      <section className="workspace-surface">
        {backControl}
        <EmptyState title="Findings Unavailable" body={error} />
      </section>
    );
  }

  const relationshipPoints = lineChartPoints(relationshipSeries);

  return (
    <section className="workspace-surface observation-center">
      {backControl}
      <div className="observation-center__hero">
        <section className="observation-center__snapshot" aria-label="Latest finding snapshot">
          <div className="observation-center__snapshot-orb">
            <SystemStateMark systemState={hasCurrentFinding ? gateOrbState : "stable"} intensity={hasCurrentFinding ? Math.min(1, Number(latestRun?.drift_metrics?.baseline_distance ?? latestRun?.drift_metrics?.drift_index ?? 0.18)) : 0.12} />
          </div>
          <div className="observation-center__snapshot-copy">
            <p className="section-token">Current Status</p>
            <strong>{activeFinding.status}</strong>
            <span>{activeFinding.confidence} confidence</span>
            <span>{hasCurrentFinding ? activeFinding.reviewNext : activeFinding.emptyState.detail}</span>
          </div>
        </section>
        <section className="observation-center__summary" aria-label="Current instrument summary">
          <p className="section-token">Current observation</p>
          <h1>Findings</h1>
          <p>{activeFinding.summary}</p>
          <MetricGrid
            metrics={[
              { label: "Confidence", value: activeFinding.confidence },
              { label: "Why it matters", value: activeFinding.whyItMatters },
            ]}
            compact
          />
          <div className="intake-flow__controls">
            <button type="button" className="command-button" onClick={() => onReviewEvidence?.()} disabled={!hasCurrentFinding}>
              {activeFinding.evidenceButtonLabel}
            </button>
          </div>
        </section>
      </div>

      <div className="workspace-grid workspace-grid--console observation-center__grid">
        <Panel title="Findings" className="span-7 observation-center__panel observation-center__panel--timeline">
          {!hasCurrentFinding ? (
            <div className="observation-detail-callout">
              <strong>{activeFinding.emptyState.title}</strong>
              <p>{activeFinding.emptyState.subtitle}</p>
              <p>{activeFinding.emptyState.detail}</p>
            </div>
          ) : (
            <div className="feed-list">
              <button
                type="button"
                className="intervention-card intervention-card--selected observation-history-card"
                style={{ textAlign: "left", width: "100%" }}
              >
                <div className="intervention-card__header">
                  <div>
                    <span>Current observation</span>
                    <strong>{activeFinding.status}</strong>
                  </div>
                  <span className="observation-history-card__status observation-history-card__status--open">{selectedRunStatus === "processing" ? "processing" : "active"}</span>
                </div>
                <p>{activeFinding.summary}</p>
                <div className="intervention-card__footer">
                  <span>Confidence {activeFinding.confidence}</span>
                  <span>{activeFinding.whyItMatters}</span>
                </div>
              </button>
            </div>
          )}
        </Panel>

        <Panel title="Review Finding" className="span-5 observation-center__panel observation-center__panel--detail">
          {!hasCurrentFinding ? (
            <div className="observation-detail-callout">
              <strong>{activeFinding.emptyState.title}</strong>
              <p>{activeFinding.emptyState.subtitle}</p>
              <p>{activeFinding.emptyState.detail}</p>
            </div>
          ) : (
            <>
              <div className="observation-detail-callout">
                <span className="section-token">Observation Summary</span>
                <strong>{activeFinding.summary}</strong>
                <p>{activeFinding.whyItMatters}</p>
              </div>
              <MetricGrid
                metrics={[
                  { label: "Status", value: activeFinding.status },
                  { label: "Confidence", value: activeFinding.confidence },
                  { label: "Review next", value: activeFinding.reviewNext },
                  { label: "Historical comparison", value: activeFinding.historicalComparison ?? OPERATOR_EMPTY_STATE.detail },
                ]}
                compact
              />
              <div className="intake-flow__controls">
                <button type="button" className="command-button" onClick={() => onReviewEvidence?.()}>{activeFinding.evidenceButtonLabel}</button>
              </div>
              <details className="compact-list-block" open>
                <summary className="section-token">Supporting Evidence</summary>
                <ul className="compact-list">
                  {(activeFinding.supportingEvidence ?? []).length > 0
                    ? activeFinding.supportingEvidence.map((item, index) => <li key={`${item}-${index}`}>{sanitizeOperatorText(item)}</li>)
                    : <li>{OPERATOR_EMPTY_STATE.detail}</li>}
                </ul>
              </details>
              <details className="compact-list-block">
                <summary className="section-token">Technical Details</summary>
                <ul className="compact-list">
                  {(activeFinding.technicalDetails ?? []).map((item) => <li key={item.label}>{item.label}: {sanitizeOperatorText(item.value)}</li>)}
                </ul>
              </details>
              <details className="compact-list-block">
                <summary className="section-token">Data Quality</summary>
                <ul className="compact-list">
                  {renderDataQualityRows(activeFinding.dataQuality)}
                </ul>
              </details>
              {selectedRun ? (
                <details className="compact-list-block">
                  <summary className="section-token">Historical comparison evidence</summary>
                  <ul className="compact-list">
                    <li>{sanitizeOperatorText(selectedRunSummary)}</li>
                    {selectedRunHistoricalFact ? <li>{sanitizeOperatorText(selectedRunHistoricalFact)}</li> : null}
                    <li>Confidence: {confidenceForFinding(selectedRun)}</li>
                  </ul>
                </details>
              ) : null}
              <div className="why-panel__section guidance-checks">
                <span className="section-token">Review outcome</span>
                <select value={feedbackCategory} onChange={(event) => setFeedbackCategory(event.target.value)}>
                  {FEEDBACK_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
                </select>
                <textarea value={feedbackNote} onChange={(event) => setFeedbackNote(event.target.value)} placeholder="Optional review note" rows={4} />
                <div className="intake-flow__controls">
                  <button type="button" className="command-button" onClick={submitFeedback} disabled={!selectedRunAllowsFeedback}>Save Review</button>
                  {feedbackState.message ? <span className="observation-feedback-state">{feedbackState.message}</span> : (!selectedRunAllowsFeedback && selectedRun ? <span className="observation-feedback-state">Review feedback unlocks after the evidence record is persisted.</span> : null)}
                </div>
              </div>
            </>
          )}
        </Panel>

        <details className="span-12 observation-center__advanced">
          <summary>Additional tools</summary>
          <div className="workspace-grid workspace-grid--console observation-center__advanced-grid">
        <Panel title="Pattern History" className="span-7 observation-center__panel observation-center__panel--explorer">
          <div className="intake-flow__controls" style={{ marginBottom: 12 }}>
            <select value={selectedVariables[0]} onChange={(event) => setSelectedVariables([event.target.value, selectedVariables[1]])}>
              <option value="">Select variable A</option>
              {variables.map((item) => <option key={item} value={item}>{displayVariable(item, aliases)}</option>)}
            </select>
            <select value={selectedVariables[1]} onChange={(event) => setSelectedVariables([selectedVariables[0], event.target.value])}>
              <option value="">Select variable B</option>
              {variables.map((item) => <option key={item} value={item}>{displayVariable(item, aliases)}</option>)}
            </select>
          </div>
          {relationshipSeries.length >= 2 ? (
            <svg className="observation-line-chart" viewBox="0 0 420 120" role="img" aria-label="Relationship history">
              <polyline points={relationshipPoints} fill="none" stroke="currentColor" strokeWidth="3" />
            </svg>
          ) : <p className="narrative-text">Select two variables with repeated observations to view pattern history.</p>}
        </Panel>

        <Panel title="Evidence Sources" className="span-7 observation-center__panel">
          <div className="telemetry-grid telemetry-grid--compact">
            {sourceSnapshots.map((run) => (
              <div className="telemetry-card" key={run.run_id}>
                <div className="telemetry-card__header">
                  <span className="telemetry-card__eyebrow">{run.source_name || run.source_type}</span>
                  <span>{normalizeObservationStatus(run, persistedRunIds)}</span>
                </div>
                <strong>{run.structural_state ?? run.operating_state ?? "Monitoring"}</strong>
                <p>{observationTypeLabel(run.observation_type)}</p>
                <div className="telemetry-card__footer">
                  <span>{displayPatternLabel(run.regime_label)}</span>
                  <span>{classifyChangeStrength(run?.drift_metrics?.baseline_distance ?? run?.drift_metrics?.drift_index)}</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>
          </div>
        </details>
      </div>
    </section>
  );
}

function maybeNotifyForObservation(run, prefs, aliases) {
  if (!prefs?.enabled || !notificationAllowed() || Notification.permission !== "granted") return;
  if (insideQuietHours(prefs.quietStart, prefs.quietEnd)) return;
  const variables = (run?.variables ?? []).slice(0, 2).map((item) => displayVariable(item, aliases)).join(" | ");
  const body = variables
    ? `${observationTypeLabel(run?.observation_type)} involving ${variables}`
    : `${observationTypeLabel(run?.observation_type)} recorded`;
  const notification = new Notification("Neraium finding", { body });
  notification.onclick = () => {
    try {
      window.localStorage.setItem(PENDING_OBSERVATION_STORAGE_KEY, String(run?.run_id ?? ""));
      window.focus?.();
    } catch {
      // ignore local storage failures
    }
    notification.close();
  };
}


function renderDataQualityRows(dataQuality) {
  const groups = dataQuality && typeof dataQuality === "object" ? dataQuality : {};
  const rows = [
    ...(groups.missingBaselineValues || []).map((item, index) => <li key={`baseline-${index}`}>Missing baseline values: {sanitizeOperatorText(item)}</li>),
    ...(groups.missingRecentValues || []).map((item, index) => <li key={`recent-${index}`}>Missing recent values: {sanitizeOperatorText(item)}</li>),
    ...(groups.unavailableTelemetry || []).map((item, index) => <li key={`telemetry-${index}`}>Unavailable telemetry: {sanitizeOperatorText(item)}</li>),
  ];
  return rows.length > 0 ? rows : [<li key="quality-none">No data quality warnings recorded.</li>];
}

function insideQuietHours(start, end) {
  const [startHour, startMinute] = String(start || "22:00").split(":").map(Number);
  const [endHour, endMinute] = String(end || "06:00").split(":").map(Number);
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes();
  const startMinutes = startHour * 60 + startMinute;
  const endMinutes = endHour * 60 + endMinute;
  if (startMinutes < endMinutes) return minutes >= startMinutes && minutes <= endMinutes;
  return minutes >= startMinutes || minutes <= endMinutes;
}
