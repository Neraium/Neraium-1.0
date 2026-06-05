import { useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";

const FEEDBACK_OPTIONS = [
  { id: "confirmed_issue", label: "Confirmed developing issue" },
  { id: "known_operational_change", label: "Known operational change" },
  { id: "sensor_or_data_problem", label: "Sensor or data problem" },
  { id: "environmental_cause", label: "Environmental cause" },
  { id: "nothing_meaningful", label: "Nothing meaningful" },
];

const NOTIFICATION_STORAGE_KEY = "neraium.observation_notifications.v1";
const VARIABLE_ALIAS_STORAGE_KEY = "neraium.variable_aliases.v1";

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
  onBackToGate = null,
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
        if (latestSeenRunId.current && newestRun && newestRun !== latestSeenRunId.current) {
          maybeNotifyForObservation(nextRuns[0], notificationPrefs, aliases);
        }
        latestSeenRunId.current = newestRun;
        setRuns(nextRuns);
        setSelectedRunId((current) => current || newestRun || "");
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
      setFeedbackState({ status: "saved", message: "Feedback recorded." });
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
    <button
      type="button"
      className="system-gate__settings-action"
      onClick={() => onBackToGate?.()}
      style={{
        position: "sticky",
        top: "max(10px, env(safe-area-inset-top, 0px))",
        left: 0,
        zIndex: 40,
        width: "fit-content",
        marginBottom: "10px",
        paddingInline: "12px",
      }}
    >
      Back to Gate
    </button>
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

  return (
    <section className="workspace-surface">
      {backControl}
      <Panel title="Observation Center" subtitle="History, structural snapshot, feedback, export, and quiet-instrument diagnostics.">
        <MetricGrid
          metrics={[
            { label: "Current regime", value: latestRun?.regime_label ?? "State Group A" },
            { label: "Structural drift", value: numberOrDash(latestRun?.drift_metrics?.baseline_distance ?? latestRun?.drift_metrics?.drift_index) },
            { label: "Active observations", value: activeObservationCount },
            { label: "Deformation age", value: formatDurationFrom(latestRun?.deformation_started_at) },
            { label: "Silence health", value: silenceHealth.state },
            { label: "Observation rate / week", value: silenceHealth.weeklyRate },
          ]}
        />
      </Panel>

      <div className="workspace-grid workspace-grid--console">
        <Panel title="Observation History" className="span-7">
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
            <EmptyState title="No observations" body="No observations match the current search and filters." compact />
          ) : (
            <div className="feed-list">
              {filteredRuns.map((run) => (
                <button
                  key={run.run_id}
                  type="button"
                  className={`intervention-card intervention-card--${selectedRun?.run_id === run.run_id ? "selected" : "review"}`}
                  onClick={() => setSelectedRunId(run.run_id)}
                  style={{ textAlign: "left", width: "100%" }}
                >
                  <div className="intervention-card__header">
                    <div>
                      <span>{run.source_name || run.source_type}</span>
                      <strong>{observationTypeLabel(run.observation_type)}</strong>
                    </div>
                    <span>{normalizeObservationStatus(run)}</span>
                  </div>
                  <p>{(run.evidence_summary ?? [])[0] ?? run.structural_state ?? "Structural observation recorded."}</p>
                  <div className="intervention-card__footer">
                    <span>{run.created_at}</span>
                    <span>{(run.variables ?? []).slice(0, 2).map((item) => displayVariable(item, aliases)).join(" | ") || "No variables listed"}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Observation Detail" className="span-5">
          {!selectedRun ? (
            <EmptyState title="No observation selected" body="Select an observation from the history to inspect and annotate it." compact />
          ) : (
            <>
              <MetricGrid
                metrics={[
                  { label: "Status", value: normalizeObservationStatus(selectedRun) },
                  { label: "Type", value: observationTypeLabel(selectedRun.observation_type) },
                  { label: "State", value: selectedRun.structural_state ?? selectedRun.operating_state },
                  { label: "Regime", value: selectedRun.regime_label ?? "State Group A" },
                  { label: "Drift magnitude", value: numberOrDash(selectedRun?.drift_metrics?.baseline_distance ?? selectedRun?.drift_metrics?.drift_index) },
                  { label: "Time since start", value: formatDurationFrom(selectedRun.deformation_started_at) },
                ]}
                compact
              />
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
                  <button type="button" className="command-button" onClick={submitFeedback}>Record Feedback</button>
                  {feedbackState.message ? <span>{feedbackState.message}</span> : null}
                </div>
              </div>
            </>
          )}
        </Panel>

        <Panel title="Relationship Explorer" className="span-7">
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
            <EmptyState title="No relationship history" body="Select two variables that have appeared together in recorded observations." compact />
          ) : (
            <>
              <svg viewBox="0 0 420 120" style={{ width: "100%", height: 140, background: "rgba(255,255,255,0.02)", borderRadius: 12 }}>
                <polyline fill="none" stroke="currentColor" strokeWidth="3" points={relationshipPoints} />
              </svg>
              <ul className="compact-list">
                {relationshipSeries.slice(-6).reverse().map((item) => (
                  <li key={item.runId}>{item.createdAt}: {observationTypeLabel(item.type)} with coupling metric {numberOrDash(item.value)}</li>
                ))}
              </ul>
            </>
          )}
        </Panel>

        <Panel title="Instrument Quiet and Notifications" className="span-5">
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
        </Panel>

        <Panel title="Variable Aliases" className="span-5">
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

        <Panel title="Multi-Source Snapshot" className="span-7">
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
                  <span>{run.regime_label ?? "State Group A"}</span>
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
  new Notification("Neraium observation", { body });
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
