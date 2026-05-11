import { useEffect, useMemo, useState } from "react";
import { exportEvidenceRun, fetchEvidenceRun, fetchEvidenceRuns, fetchLatestEvidence } from "../services/evidenceApi";

const EVIDENCE_REFRESH_MS = 5000;

function formatRunStatusTone(status) {
  switch ((status ?? "").toLowerCase()) {
    case "completed":
    case "complete":
    case "active":
      return "nominal";
    case "processing":
    case "queued":
    case "pending":
      return "review";
    case "failed":
    case "error":
      return "elevated";
    default:
      return "muted";
  }
}

export default function EvidenceTrailWorkspace({
  apiFetch,
  readJsonPayload,
  normalizeErrorMessage,
  formatClockTime,
  Panel,
  MetricGrid,
  CompactList,
  EmptyState,
  accessCode,
  refreshKey,
}) {
  const [runs, setRuns] = useState([]);
  const [latestRun, setLatestRun] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [exportBody, setExportBody] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadEvidence() {
      try {
        const [latestPayload, runsPayload] = await Promise.all([
          fetchLatestEvidence({ apiFetch, readJsonPayload, accessCode }),
          fetchEvidenceRuns({ apiFetch, readJsonPayload, accessCode }),
        ]);
        if (cancelled) {
          return;
        }
        const nextRuns = runsPayload?.runs ?? [];
        setRuns(nextRuns);
        setLatestRun(latestPayload?.run ?? null);
        const nextSelectedId = selectedRunId ?? nextRuns[0]?.run_id ?? null;
        setSelectedRunId(nextSelectedId);
        setError("");
      } catch (loadError) {
        if (!cancelled) {
          setError(normalizeErrorMessage(loadError?.message ?? loadError));
        }
      }
    }
    loadEvidence();
    const intervalId = window.setInterval(loadEvidence, EVIDENCE_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [accessCode, apiFetch, normalizeErrorMessage, readJsonPayload, refreshKey, selectedRunId]);

  useEffect(() => {
    let cancelled = false;
    async function loadSelectedRun() {
      if (!selectedRunId) {
        setSelectedRun(null);
        return;
      }
      try {
        const payload = await fetchEvidenceRun({ apiFetch, readJsonPayload, accessCode, runId: selectedRunId });
        if (!cancelled) {
          setSelectedRun(payload);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(normalizeErrorMessage(loadError?.message ?? loadError));
        }
      }
    }
    loadSelectedRun();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch, normalizeErrorMessage, readJsonPayload, selectedRunId]);

  async function handleExport() {
    if (!selectedRunId) {
      return;
    }
    try {
      const body = await exportEvidenceRun({ apiFetch, accessCode, runId: selectedRunId });
      setExportBody(body);
      setError("");
    } catch (exportError) {
      setError(normalizeErrorMessage(exportError?.message ?? exportError));
    }
  }

  const diffValue = latestRun?.diff?.neraium_score_delta;
  const latestMetrics = useMemo(() => ([
    { label: "Status", value: latestRun?.status ?? "No evidence yet" },
    { label: "Source", value: latestRun?.source_name ?? "Awaiting upload" },
    { label: "Processed", value: latestRun?.completed_at ? formatClockTime(latestRun.completed_at) : "Awaiting upload" },
    { label: "Score", value: latestRun?.neraium_score ?? "n/a" },
    { label: "State", value: latestRun?.operating_state ?? "n/a" },
    { label: "Drift", value: latestRun?.drift_status ?? "n/a" },
    { label: "Sensors", value: latestRun?.sensors_detected ?? 0 },
    { label: "Rows", value: `${latestRun?.rows_accepted ?? 0} / ${latestRun?.rows_rejected ?? 0}` },
    { label: "Change", value: typeof diffValue === "number" ? `${diffValue > 0 ? "+" : ""}${diffValue}` : "n/a" },
  ]), [diffValue, formatClockTime, latestRun]);

  if (!latestRun && runs.length === 0 && !error) {
    return (
      <div className="workspace-grid workspace-grid--console">
        <Panel title="Evidence Trail" className="span-12">
          <EmptyState
            title="No evidence trail yet"
            body="Connect data or upload telemetry to generate the first evidence record."
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Evidence Summary" className="span-12 workspace-hero-panel">
        <MetricGrid metrics={latestMetrics} />
      </Panel>

      <Panel title="Primary Drivers" className="span-6">
        <CompactList
          items={latestRun?.primary_drivers ?? []}
          emptyText="No primary drivers recorded."
        />
      </Panel>

      <Panel title="Warnings and Errors" className="span-6">
        <CompactList
          items={[...(latestRun?.warnings ?? []), ...(latestRun?.errors ?? [])]}
          emptyText="No warnings or errors recorded."
        />
      </Panel>

      <Panel title="Run History" className="span-5">
        {runs.length === 0 ? (
          <EmptyState title="No run history" body="Completed and failed runs will appear here." compact />
        ) : (
          <div className="run-history-list">
            {runs.map((run) => (
              <button
                className={`run-history-item ${selectedRunId === run.run_id ? "run-history-item--active" : ""}`}
                key={run.run_id}
                type="button"
                onClick={() => setSelectedRunId(run.run_id)}
              >
                <div className="run-history-item__top">
                  <strong>{run.source_name ?? run.run_id}</strong>
                  <span className={`connector-status-pill connector-status-pill--${formatRunStatusTone(run.status)}`}>
                    {run.status ?? "Unknown"}
                  </span>
                </div>
                <div className="run-history-item__meta">
                  <span>{run.completed_at ? formatClockTime(run.completed_at) : "Pending"}</span>
                  <span>{run.operating_state ?? "n/a"}</span>
                  <span>Score {run.neraium_score ?? "n/a"}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Run Details" className="span-7">
        {selectedRun ? (
          <>
            <MetricGrid
              metrics={[
                { label: "Run ID", value: selectedRun.run_id },
                { label: "File", value: selectedRun.source_name ?? "Unknown" },
                { label: "Accepted", value: selectedRun.rows_accepted ?? 0 },
                { label: "Rejected", value: selectedRun.rows_rejected ?? 0 },
                { label: "Room", value: selectedRun.room ?? "Unknown" },
                { label: "Initiated By", value: selectedRun.initiated_by ?? "Unknown" },
              ]}
              compact
            />
            <CompactList
              title="Evidence Summary"
              items={selectedRun.evidence_summary ?? []}
              emptyText="No evidence summary recorded."
            />
          </>
        ) : (
          <EmptyState title="No run selected" body="Select a run to view details." compact />
        )}
      </Panel>

      <Panel title="Export Report" className="span-12">
        <div className="room-first-actions">
          <button className="command-button" type="button" onClick={handleExport} disabled={!selectedRunId}>
            Export Evidence Report
          </button>
        </div>
        {exportBody ? (
          <pre className="evidence-console evidence-console--static">{exportBody}</pre>
        ) : (
          <p className="empty-copy">Generate a customer-ready report for the selected run.</p>
        )}
        {error && <p className="form-error">{error}</p>}
      </Panel>
    </div>
  );
}
