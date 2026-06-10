import { useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";
import HealthOrb from "./HealthOrb";

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

function normalizeObservationStatus(run) {
  if (String(run?.status ?? "").toLowerCase() === "failed") return "failed";
  if (run?.latest_feedback_category) return "resolved";
  return String(run?.observation_status ?? "open").toLowerCase();
}

function observationTypeLabel(value) {
  const text = String(value ?? "").replaceAll("_", " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Observation";
}

function formatDurationFrom(dateText) {
  if (!dateText) return "-";
  const ms = Date.now() - new Date(dateText).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "-";
  const hours = Math.round(ms / 3600000);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function numberOrDash(value, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : "-";
}

function displayVariable(name, aliases) {
  const alias = aliases?.[name];
  return alias ? `${alias} (${name})` : name;
}

function displayPatternLabel(label, fallback = "Baseline pattern") {
  const text = String(label ?? "").trim();
  if (!text || text === "State Group A") return fallback;
  return text;
}

function driftToneFor(run) {
  const drift = Number(run?.drift_metrics?.baseline_distance ?? run?.drift_metrics?.drift_index ?? 0);
  if (!Number.isFinite(drift) || drift < 0.24) return "stable";
  if (drift < 0.72) return "watch";
  return "alert";
}

function summarizeObservation(run, aliases) {
  if (!run) return "No observation selected.";
  const variables = (run?.variables ?? []).slice(0, 2).map((item) => displayVariable(item, aliases));
  const type = String(run?.observation_type ?? "");
  const duration = formatDurationFrom(run?.deformation_started_at);
  if (type === "coupling_change" && variables.length >= 2) {
    return `The relationship between ${variables[0]} and ${variables[1]} has shifted away from baseline${duration !== "-" ? ` for ${duration}` : ""}.`;
  }
  if (type === "recovery_elongation") {
    return `Recovery back to baseline is taking longer${duration !== "-" ? ` and has stayed elongated for ${duration}` : ""}.`;
  }
  if (type === "trajectory_drift") {
    return `The system trajectory is continuing to move away from its usual state pattern${duration !== "-" ? ` for ${duration}` : ""}.`;
  }
  if (type === "covariance_shift") {
    return `The overall relationship structure has shifted away from the baseline pattern${duration !== "-" ? ` for ${duration}` : ""}.`;
  }
  return (run?.evidence_summary ?? [])[0] ?? "A persistent structural change has been recorded.";
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

function relationshipSketch(run) {
  const strength = Math.max(2.2, Math.min(8, Number(run?.drift_metrics?.coupling_delta ?? run?.drift_metrics?.baseline_distance ?? 0.4) * 2.2));
  const tone = driftToneFor(run);
  const edgeStroke = tone === "alert"
    ? "rgba(184, 110, 58, 0.9)"
    : tone === "watch"
      ? "rgba(197, 146, 60, 0.84)"
      : "rgba(59, 122, 140, 0.82)";
  const edgeDash = tone === "stable" ? undefined : tone === "watch" ? "5 7" : "3 5";
  return (
    <svg viewBox="0 0 176 52" className="observation-history-card__sketch" aria-hidden="true">
      <line x1="34" y1="26" x2="142" y2="26" stroke={edgeStroke} strokeWidth={strength} strokeLinecap="round" strokeDasharray={edgeDash} opacity="0.9" />
      <circle cx="34" cy="26" r="10" fill="rgba(11, 25, 41, 0.96)" stroke="rgba(59, 122, 140, 0.68)" />
      <circle cx="142" cy="26" r="10" fill="rgba(11, 25, 41, 0.96)" stroke="rgba(168, 138, 75, 0.72)" />
    </svg>
  );
}

export default function ObservationCenterWorkspace({
  apiFetch,
  accessCode,
  onBackToGate = null,
  onWorkspaceNavigate = null,
}) {
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
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

  const variables = useMemo(() => {
    const values = new Set();
    runs.forEach((run) => {
      (run?.variables ?? []).forEach((item) => {
        if (item) values.add(String(item));
      });
    });
    return [...values];
  }, [runs]);

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
    return runs.filter((run) => {
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
      const statusMatch = statusFilter === "all" || normalizeObservationStatus(run) === statusFilter;
      const typeMatch = typeFilter === "all" || String(run?.observation_type ?? "") === typeFilter;
      return queryMatch && statusMatch && typeMatch;
    });
  }, [query, runs, statusFilter, typeFilter]);

  const selectedRun = useMemo(
    () => filteredRuns.find((run) => run.run_id === selectedRunId) ?? filteredRuns[0] ?? null,
    [filteredRuns, selectedRunId],
  );

  const latestRun = runs[0] ?? null;
  const hasRecordedObservations = runs.length > 0;
  const selectedRunSummary = useMemo(() => summarizeObservation(selectedRun, aliases), [aliases, selectedRun]);
  const selectedRunHistoricalFact = selectedRun?.historical_fact ?? "";
  const gateOrbState = driftToneFor(latestRun);
  const activeObservationCount = useMemo(
    () => runs.filter((run) => normalizeObservationStatus(run) === "open").length,
    [runs],
  );

  const silenceHealth = useMemo(() => {
    const now = Date.now();
    const lastDay = runs.filter((run) => now - new Date(run.created_at).getTime() <= 86400000);
    const lastWeek = runs.filter((run) => now - new Date(run.created_at).getTime() <= 7 * 86400000);
    const weeklyRate = Number((lastWeek.length / 7).toFixed(2));
    const state = lastDay.length > Math.max(3, weeklyRate * 2) ? "Noisy" : lastWeek.length === 0 ? "Silent" : "Quiet";
    return {
      lastDay: lastDay.length,
      lastWeek: lastWeek.length,
      weeklyRate,
      state,
    };
  }, [runs]);

  const sourceSnapshots = useMemo(() => {
    const latestBySource = new Map();
    runs.forEach((run) => {
      const key = String(run?.source_name || run?.source_type || run?.run_id);
      if (!latestBySource.has(key)) {
        latestBySource.set(key, run);
      }
    });
    return [...latestBySource.values()].slice(0, 6);
  }, [runs]);

  const relationshipSeries = useMemo(() => {
    const [left, right] = selectedVariables;
    if (!left || !right) return [];
    return [...runs]
      .reverse()
      .filter((run) => (run?.variables ?? []).includes(left) && (run?.variables ?? []).includes(right))
      .map((run) => ({
        runId: run.run_id,
        createdAt: run.created_at,
        value: run?.drift_metrics?.coupling_delta ?? run?.drift_metrics?.baseline_distance ?? run?.drift_metrics?.drift_index ?? 0,
        type: run?.observation_type ?? "observation",
      }));
  }, [runs, selectedVariables]);

  async function submitFeedback() {
    if (!selectedRun?.run_id) return;
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

  function saveAlias() {
    if (!selectedAliasVariable) return;
    setAliases((current) => ({
      ...current,
      [selectedAliasVariable]: aliasDraft.trim(),
    }));
  }

  function downloadRun(runId, format) {
    const href = `/api/evidence/export/${encodeURIComponent(runId)}?format=${encodeURIComponent(format)}`;
    window.open(href, "_blank", "noopener,noreferrer");
  }

  const backControl = (
    <div className="observation-center__back-control">
      <button
        type="button"
        className="system-gate__settings-action"
        onClick={() => onBackToGate?.()}
      >
        Back to Gate
      </button>
      <button
        type="button"
        className="system-gate__settings-action"
        onClick={() => onWorkspaceNavigate?.("help-changelog")}
      >
        Help / Changelog
      </button>
    </div>
  );

  if (loading) {
    return (
      <section className="workspace-surface">
        {backControl}
        <Panel title="Observation Center" subtitle="Loading structural observation history..." />
      </section>
    );
  }

  if (error) {
    return (
      <section className="workspace-surface">
        {backControl}
        <EmptyState title="Observation Center Unavailable" body={error} />
      </section>
    );
  }

  const relationshipPoints = lineChartPoints(relationshipSeries);
  const distinctTypes = [...new Set(runs.map((run) => run?.observation_type).filter(Boolean))];
  const currentPatternLabel = hasRecordedObservations ? displayPatternLabel(latestRun?.regime_label) : "No observations recorded";
  const timelineEmptyTitle = runs.length === 0 ? "No observations recorded" : "No observations";
  const timelineEmptyBody = runs.length === 0
    ? "No structural observations have been recorded yet. Upload telemetry or run a replay to generate observation history."
    : "No observations match the current search and filters.";
  const relationshipEmptyBody = runs.length === 0
    ? "Relationship history will appear after telemetry or replay data produces reviewable structural observations."
    : "Select two variables that have appeared together in recorded observations.";

  return (
    <section className="workspace-surface observation-center">
      {backControl}
      <div className="observation-center__hero">
        <section className="observation-center__snapshot" aria-label="Current structural snapshot">
          <div className="observation-center__snapshot-orb">
            <HealthOrb systemState={gateOrbState} intensity={Math.min(1, Number(latestRun?.drift_metrics?.baseline_distance ?? latestRun?.drift_metrics?.drift_index ?? 0.18))} />
          </div>
          <div className="observation-center__snapshot-copy">
            <p className="section-token">Stability Snapshot</p>
            <strong>{currentPatternLabel}</strong>
            <span>Drift index {numberOrDash(latestRun?.drift_metrics?.baseline_distance ?? latestRun?.drift_metrics?.drift_index)}</span>
            <span>{activeObservationCount} active observations</span>
          </div>
        </section>
        <section className="observation-center__summary" aria-label="Current instrument summary">
          <p className="section-token">Instrument State</p>
          <h1>Observation Center</h1>
          <p>
            {hasRecordedObservations
              ? "The instrument stays quiet until system behavior changes. Review structural observations, record what you found, and keep the original evidence available."
              : "The instrument is quiet because no reviewable structural changes have been recorded."}
          </p>
          <MetricGrid
            metrics={[
              { label: "Current behavior pattern", value: currentPatternLabel },
              { label: "Structural drift", value: numberOrDash(latestRun?.drift_metrics?.baseline_distance ?? latestRun?.drift_metrics?.drift_index) },
              { label: "Pattern age", value: formatDurationFrom(latestRun?.deformation_started_at) },
              { label: "Instrument status", value: silenceHealth.state },
            ]}
            compact
          />
          <p className="narrative-text">Pattern age means how long the current structural behavior has been present in the available telemetry.</p>
        </section>
      </div>

      <div className="workspace-grid workspace-grid--console observation-center__grid">
        <Panel title="Observation Timeline" className="span-7 observation-center__panel observation-center__panel--timeline">
          <div className="intake-flow__controls" style={{ marginBottom: 12 }}>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search variable, source, date, or observation text" />
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="failed">Failed</option>
            </select>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="all">All types</option>
              {distinctTypes.map((type) => <option key={type} value={type}>{observationTypeLabel(type)}</option>)}
            </select>
          </div>
          {filteredRuns.length === 0 ? (
            <EmptyState title={timelineEmptyTitle} body={timelineEmptyBody} compact />
          ) : (
            <div className="feed-list">
              {filteredRuns.map((run) => (
                <button
                  key={run.run_id}
                  type="button"
                  className={`intervention-card intervention-card--${selectedRun?.run_id === run.run_id ? "selected" : "review"} observation-history-card`}
                  onClick={() => setSelectedRunId(run.run_id)}
                  style={{ textAlign: "left", width: "100%" }}
                >
                  <div className="intervention-card__header">
                    <div>
                      <span>{run.source_name || run.source_type}</span>
                      <strong>{observationTypeLabel(run.observation_type)}</strong>
                    </div>
                    <span className={`observation-history-card__status observation-history-card__status--${normalizeObservationStatus(run)}`}>{normalizeObservationStatus(run)}</span>
                  </div>
                  {relationshipSketch(run)}
                  <p>{summarizeObservation(run, aliases)}</p>
                  <div className="intervention-card__footer">
                    <span>{run.created_at}</span>
                    <span>{(run.variables ?? []).slice(0, 2).map((item) => displayVariable(item, aliases)).join(" | ") || "No variables listed"}</span>
                    <span className="observation-history-card__review">Review</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Observation Review" className="span-5 observation-center__panel observation-center__panel--detail">
          {!selectedRun ? (
            <EmptyState title="No observation selected" body="Select an observation from the history to inspect and annotate it." compact />
          ) : (
            <>
              <div className="observation-detail-callout">
                <span className="section-token">Observation</span>
                <strong>{selectedRunSummary}</strong>
                {selectedRunHistoricalFact ? <p>{selectedRunHistoricalFact}</p> : null}
              </div>
              <MetricGrid
                metrics={[
                  { label: "Status", value: normalizeObservationStatus(selectedRun) },
                  { label: "Type", value: observationTypeLabel(selectedRun.observation_type) },
                  { label: "State", value: selectedRun.structural_state ?? selectedRun.operating_state },
                  { label: "Behavior pattern", value: displayPatternLabel(selectedRun.regime_label) },
                  { label: "Drift magnitude", value: numberOrDash(selectedRun?.drift_metrics?.baseline_distance ?? selectedRun?.drift_metrics?.drift_index) },
                  { label: "Time since start", value: formatDurationFrom(selectedRun.deformation_started_at) },
                ]}
                compact
              />
              <div className="observation-pair-visual" aria-label="Relationship deformation sketch">
                <svg viewBox="0 0 320 120" role="img" aria-label="Structural relationship sketch">
                  <defs>
                    <linearGradient id="observationEdge" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="rgba(105, 183, 198, 0.78)" />
                      <stop offset="100%" stopColor="rgba(211, 170, 103, 0.88)" />
                    </linearGradient>
                  </defs>
                  <line
                    x1="88"
                    y1="60"
                    x2="232"
                    y2="60"
                    stroke="url(#observationEdge)"
                    strokeWidth={Math.max(3, Math.min(10, Number(selectedRun?.drift_metrics?.coupling_delta ?? selectedRun?.drift_metrics?.baseline_distance ?? 4) * 2.8))}
                    strokeLinecap="round"
                    opacity="0.74"
                  />
                  <circle cx="88" cy="60" r="20" fill="rgba(13, 23, 29, 0.96)" stroke="rgba(105, 183, 198, 0.72)" />
                  <circle cx="232" cy="60" r="20" fill="rgba(15, 18, 21, 0.96)" stroke="rgba(211, 170, 103, 0.78)" />
                  <text x="88" y="94" textAnchor="middle" fill="rgba(224, 236, 234, 0.92)" fontSize="10">
                    {displayVariable((selectedRun.variables ?? [])[0] ?? "Variable A", aliases)}
                  </text>
                  <text x="232" y="94" textAnchor="middle" fill="rgba(224, 236, 234, 0.92)" fontSize="10">
                    {displayVariable((selectedRun.variables ?? [])[1] ?? "Variable B", aliases)}
                  </text>
                </svg>
              </div>
              <div className="compact-list-block">
                <p className="section-token">Variables</p>
                <ul className="compact-list">
                  {(selectedRun.variables ?? []).map((item) => <li key={item}>{displayVariable(item, aliases)}</li>)}
                </ul>
              </div>
              <div className="compact-list-block">
                <p className="section-token">Evidence</p>
                <ul className="compact-list">
                  {(selectedRun.evidence_summary ?? []).length > 0
                    ? selectedRun.evidence_summary.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                    : <li>No evidence summary recorded.</li>}
                </ul>
              </div>
              <div className="compact-list-block">
                <p className="section-token">Data Conditions</p>
                <ul className="compact-list">
                  {(selectedRun.data_conditions ?? []).length > 0
                    ? selectedRun.data_conditions.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                    : <li>No data conditions recorded.</li>}
                </ul>
              </div>
              <div className="intake-flow__controls">
                <button type="button" className="secondary-command-button" onClick={() => downloadRun(selectedRun.run_id, "markdown")}>Export Markdown</button>
                <button type="button" className="secondary-command-button" onClick={() => downloadRun(selectedRun.run_id, "json")}>Export JSON</button>
                <button type="button" className="secondary-command-button" onClick={() => downloadRun(selectedRun.run_id, "csv")}>Export CSV</button>
              </div>
              <div className="why-panel__section guidance-checks">
                <span className="section-token">What did you find?</span>
                <select value={feedbackCategory} onChange={(event) => setFeedbackCategory(event.target.value)}>
                  {FEEDBACK_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
                </select>
                <textarea value={feedbackNote} onChange={(event) => setFeedbackNote(event.target.value)} placeholder="Optional note about what the operator found." rows={4} />
                <div className="intake-flow__controls">
                  <button type="button" className="command-button" onClick={submitFeedback}>Record to Memory</button>
                  {feedbackState.message ? <span className="observation-feedback-state">{feedbackState.message}</span> : null}
                </div>
              </div>
            </>
          )}
        </Panel>

        <Panel title="Variable Explorer" className="span-7 observation-center__panel observation-center__panel--explorer">
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
          {relationshipSeries.length === 0 ? (
            <EmptyState title="No relationship history" body={relationshipEmptyBody} compact />
          ) : (
            <>
              <svg viewBox="0 0 420 120" className="observation-explorer__chart">
                <polyline fill="none" stroke="rgba(59, 122, 140, 0.92)" strokeWidth="3" points={relationshipPoints} />
              </svg>
              <ul className="compact-list">
                {relationshipSeries.slice(-6).reverse().map((item) => (
                  <li key={item.runId}>{item.createdAt}: {observationTypeLabel(item.type)} with coupling metric {numberOrDash(item.value)}</li>
                ))}
              </ul>
            </>
          )}
        </Panel>

        <Panel title="Instrument Quiet and Notifications" className="span-5 observation-center__panel">
          <MetricGrid
            metrics={[
              { label: "Observations / 24h", value: silenceHealth.lastDay },
              { label: "Observations / 7d", value: silenceHealth.lastWeek },
              { label: "Instrument state", value: silenceHealth.state },
            ]}
            compact
          />
          <div className="setup-grid">
            <label>
              <span>Notification mode</span>
              <select
                value={notificationPrefs.enabled ? "on" : "off"}
                onChange={async (event) => {
                  const enabled = event.target.value === "on";
                  if (enabled && notificationAllowed() && Notification.permission === "default") {
                    await Notification.requestPermission();
                  }
                  setNotificationPrefs((current) => ({ ...current, enabled }));
                }}
              >
                <option value="off">Off</option>
                <option value="on">In-browser</option>
              </select>
            </label>
            <label>
              <span>Quiet hours start</span>
              <input type="time" value={notificationPrefs.quietStart} onChange={(event) => setNotificationPrefs((current) => ({ ...current, quietStart: event.target.value }))} />
            </label>
            <label>
              <span>Quiet hours end</span>
              <input type="time" value={notificationPrefs.quietEnd} onChange={(event) => setNotificationPrefs((current) => ({ ...current, quietEnd: event.target.value }))} />
            </label>
          </div>
          <div className="observation-trust-note">
            <strong>Default silence is preserved.</strong>
            <p>Notifications stay operator-controlled, quiet hours are respected, and ignored observations remain open without reminders or escalation.</p>
          </div>
        </Panel>

        <Panel title="Variable Aliases" className="span-5 observation-center__panel">
          <div className="setup-grid">
            <label>
              <span>Variable</span>
              <select value={selectedAliasVariable} onChange={(event) => setSelectedAliasVariable(event.target.value)}>
                {variables.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label>
              <span>Friendly label</span>
              <input value={aliasDraft} onChange={(event) => setAliasDraft(event.target.value)} placeholder="Optional local alias" />
            </label>
          </div>
          <div className="intake-flow__controls">
            <button type="button" className="command-button" onClick={saveAlias}>Save Alias</button>
          </div>
          <ul className="compact-list">
            {Object.entries(aliases).filter(([, value]) => String(value ?? "").trim()).map(([key, value]) => (
              <li key={key}>{value} ({key})</li>
            ))}
          </ul>
        </Panel>

        <Panel title="Multi-Source Snapshot" className="span-7 observation-center__panel">
          <div className="telemetry-grid telemetry-grid--compact">
            {sourceSnapshots.map((run) => (
              <div className="telemetry-card" key={run.run_id}>
                <div className="telemetry-card__header">
                  <span className="telemetry-card__eyebrow">{run.source_name || run.source_type}</span>
                  <span>{normalizeObservationStatus(run)}</span>
                </div>
                <strong>{run.structural_state ?? run.operating_state ?? "Monitoring"}</strong>
                <p>{observationTypeLabel(run.observation_type)}</p>
                <div className="telemetry-card__footer">
                  <span>{displayPatternLabel(run.regime_label)}</span>
                  <span>{numberOrDash(run?.drift_metrics?.baseline_distance ?? run?.drift_metrics?.drift_index)}</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>
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
  const notification = new Notification("Neraium observation", { body });
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

function insideQuietHours(start, end) {
  const [startHour, startMinute] = String(start || "22:00").split(":").map(Number);
  const [endHour, endMinute] = String(end || "06:00").split(":").map(Number);
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes();
  const startMinutes = (startHour * 60) + startMinute;
  const endMinutes = (endHour * 60) + endMinute;
  if (startMinutes === endMinutes) return false;
  if (startMinutes < endMinutes) {
    return minutes >= startMinutes && minutes < endMinutes;
  }
  return minutes >= startMinutes || minutes < endMinutes;
}
