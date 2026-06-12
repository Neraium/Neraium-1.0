import { useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, Panel } from "./workspacePrimitives";

const FEEDBACK_OPTIONS = [
  { id: "confirmed_issue", label: "Confirmed issue" },
  { id: "known_operational_change", label: "Known change" },
  { id: "sensor_or_data_problem", label: "Sensor/data issue" },
  { id: "nothing_meaningful", label: "Not meaningful" },
];

const PENDING_OBSERVATION_STORAGE_KEY = "neraium.pending_observation.v1";

function normalizeObservationStatus(run) {
  if (String(run?.status ?? "").toLowerCase() === "failed") return "failed";
  if (run?.latest_feedback_category) return "reviewed";
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

function summarizeObservation(run) {
  if (!run) return "No observation selected.";
  const variables = (run?.variables ?? []).slice(0, 2).filter(Boolean);
  const type = String(run?.observation_type ?? "");
  const duration = formatDurationFrom(run?.deformation_started_at);
  if (type === "coupling_change" && variables.length >= 2) {
    return `${variables[0]} and ${variables[1]} changed relationship${duration !== "-" ? ` for ${duration}` : ""}.`;
  }
  if (type === "recovery_elongation") return `Recovery is taking longer${duration !== "-" ? ` for ${duration}` : ""}.`;
  if (type === "trajectory_drift") return `System behavior is moving away from its usual pattern${duration !== "-" ? ` for ${duration}` : ""}.`;
  if (type === "covariance_shift") return `Overall system relationships shifted away from baseline${duration !== "-" ? ` for ${duration}` : ""}.`;
  return (run?.evidence_summary ?? [])[0] ?? "A structural change was recorded.";
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

export default function ObservationCenterWorkspace({
  apiFetch,
  accessCode,
  onBackToGate = null,
}) {
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [feedbackCategory, setFeedbackCategory] = useState(FEEDBACK_OPTIONS[0].id);
  const [feedbackNote, setFeedbackNote] = useState("");
  const [feedbackState, setFeedbackState] = useState({ status: "idle", message: "" });
  const latestSeenRunId = useRef("");

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
        if (!response.ok) throw new Error(String(payload?.detail ?? `Unexpected response: ${response.status}`));
        if (cancelled) return;
        const nextRuns = Array.isArray(payload?.runs) ? payload.runs : [];
        const newestRun = nextRuns[0]?.run_id ?? "";
        const pendingRunId = readPendingObservationRunId();
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
        if (!cancelled) setError(String(loadError?.message ?? loadError));
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
  }, [accessCode, apiFetch]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.run_id === selectedRunId) ?? runs[0] ?? null,
    [runs, selectedRunId],
  );
  const openCount = useMemo(() => runs.filter((run) => normalizeObservationStatus(run) === "open").length, [runs]);
  const selectedSummary = useMemo(() => summarizeObservation(selectedRun), [selectedRun]);

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
      if (!response.ok) throw new Error(String(payload?.detail ?? `Unexpected response: ${response.status}`));
      setRuns((current) => current.map((run) => (run.run_id === payload.run_id ? payload : run)));
      setFeedbackNote("");
      setFeedbackState({ status: "saved", message: "Review saved." });
    } catch (submitError) {
      setFeedbackState({ status: "error", message: String(submitError?.message ?? submitError) });
    }
  }

  const backControl = (
    <div className="observation-center__back-control">
      <button type="button" className="system-gate__settings-action" onClick={() => onBackToGate?.()}>
        Back to Gate
      </button>
    </div>
  );

  if (loading) {
    return (
      <section className="workspace-surface">
        {backControl}
        <Panel title="Observation Center" subtitle="Loading observations..." />
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

  return (
    <section className="workspace-surface observation-center">
      {backControl}
      <div className="workspace-grid workspace-grid--console observation-center__grid">
        <Panel title="Observation Center" className="span-12 observation-center__panel">
          <div className="panel-body">
            <p className="narrative-text">
              Review changes Neraium recorded from uploaded telemetry. Original evidence remains available in the background.
            </p>
            <div className="onboarding-summary">
              <li><span>Open observations</span><strong>{openCount}</strong></li>
              <li><span>Total recorded</span><strong>{runs.length}</strong></li>
              <li><span>Status</span><strong>{runs.length ? "Ready for review" : "No observations yet"}</strong></li>
            </div>
          </div>
        </Panel>

        <Panel title="Observations" className="span-7 observation-center__panel observation-center__panel--timeline">
          {runs.length === 0 ? (
            <EmptyState title="No observations recorded" body="Upload telemetry to generate observation history." compact />
          ) : (
            <div className="feed-list">
              {runs.map((run) => (
                <button
                  key={run.run_id}
                  type="button"
                  className={`intervention-card intervention-card--${selectedRun?.run_id === run.run_id ? "selected" : "review"} observation-history-card`}
                  onClick={() => setSelectedRunId(run.run_id)}
                  style={{ textAlign: "left", width: "100%" }}
                >
                  <div className="intervention-card__header">
                    <div>
                      <span>{run.source_name || run.source_type || "Telemetry upload"}</span>
                      <strong>{observationTypeLabel(run.observation_type)}</strong>
                    </div>
                    <span className={`observation-history-card__status observation-history-card__status--${normalizeObservationStatus(run)}`}>{normalizeObservationStatus(run)}</span>
                  </div>
                  <p>{summarizeObservation(run)}</p>
                  <div className="intervention-card__footer">
                    <span>{run.created_at}</span>
                    <span>{(run.variables ?? []).slice(0, 2).join(" | ") || "Evidence available"}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Review" className="span-5 observation-center__panel observation-center__panel--detail">
          {!selectedRun ? (
            <EmptyState title="No observation selected" body="Select an observation to review it." compact />
          ) : (
            <div className="panel-body">
              <div className="observation-detail-callout">
                <span className="section-token">What changed</span>
                <strong>{selectedSummary}</strong>
                {selectedRun?.historical_fact ? <p>{selectedRun.historical_fact}</p> : null}
              </div>
              <div className="onboarding-summary">
                <li><span>Status</span><strong>{normalizeObservationStatus(selectedRun)}</strong></li>
                <li><span>Type</span><strong>{observationTypeLabel(selectedRun.observation_type)}</strong></li>
                <li><span>Drift</span><strong>{numberOrDash(selectedRun?.drift_metrics?.baseline_distance ?? selectedRun?.drift_metrics?.drift_index)}</strong></li>
                <li><span>Seen for</span><strong>{formatDurationFrom(selectedRun.deformation_started_at)}</strong></li>
              </div>
              <label className="observation-feedback__field">
                <span>Review result</span>
                <select value={feedbackCategory} onChange={(event) => setFeedbackCategory(event.target.value)}>
                  {FEEDBACK_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
                </select>
              </label>
              <label className="observation-feedback__field">
                <span>Note</span>
                <textarea value={feedbackNote} onChange={(event) => setFeedbackNote(event.target.value)} placeholder="Add what you found..." rows={4} />
              </label>
              <button type="button" className="command-button" onClick={submitFeedback} disabled={feedbackState.status === "saving"}>
                {feedbackState.status === "saving" ? "Saving" : "Save Review"}
              </button>
              {feedbackState.message ? <p className={`metadata-text metadata-text--${feedbackState.status}`}>{feedbackState.message}</p> : null}
            </div>
          )}
        </Panel>
      </div>
    </section>
  );
}
