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

function buildDemoEvidence(scenario = "drift", tick = 0) {
  const now = Date.now();
  const state = scenario === "stable" ? "Nominal environmental stability" : scenario === "separation" ? "Structural separation" : "Relationship drift";
  const drift = scenario === "stable" ? "normal" : scenario === "separation" ? "elevated" : "watch";
  const baseScore = scenario === "stable" ? 0.89 : scenario === "separation" ? 0.41 : 0.67;
  const variance = ((tick % 6) - 2) * 0.01;
  const score = Number(Math.max(0.08, Math.min(0.98, baseScore + variance)).toFixed(3));

  const runs = Array.from({ length: 6 }).map((_, index) => {
    const completedAt = new Date(now - index * 6 * 60 * 1000).toISOString();
    const runScore = Number(Math.max(0.08, Math.min(0.98, score - index * 0.012)).toFixed(3));
    return {
      run_id: `demo-run-${tick}-${index + 1}`,
      source_name: `Demo telemetry ${index + 1}`,
      status: "completed",
      completed_at: completedAt,
      operating_state: state,
      drift_status: drift,
      neraium_score: runScore,
      sensors_detected: 12 + (index % 3),
      rows_accepted: 1400 - index * 47,
      rows_rejected: Math.max(0, 16 - index * 2),
      room: "Flower room 1",
      initiated_by: "demo",
      primary_drivers: scenario === "stable"
        ? ["Temperature-humidity coupling remains stable.", "Airflow response remains within baseline."]
        : scenario === "separation"
          ? ["Airflow-pressure coupling diverged from baseline.", "Humidity recovery lag increased across the review window."]
          : ["Humidity control drifted from baseline patterns.", "Irrigation response coupling changed during transition."],
      warnings: scenario === "stable" ? [] : ["Synthetic alert: operator review recommended."],
      errors: [],
      evidence_summary: [
        `Scenario: ${scenario}`,
        `Neraium score ${runScore}`,
        `Completed at ${completedAt}`,
      ],
      diff: {
        neraium_score_delta: Number((index === 0 ? variance : -0.012).toFixed(3)),
      },
    };
  });

  return { latestRun: runs[0], runs };
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
  isDemoMode = false,
  demoScenario = "drift",
  telemetryTick = 0,
  preferredRunId = null,
}) {
  const [runs, setRuns] = useState([]);
  const [latestRun, setLatestRun] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [exportBody, setExportBody] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!preferredRunId) {
      return;
    }
    setSelectedRunId(preferredRunId);
  }, [preferredRunId]);

  useEffect(() => {
    if (!isDemoMode) {
      return;
    }
    const demo = buildDemoEvidence(demoScenario, telemetryTick);
    setRuns(demo.runs);
    setLatestRun(demo.latestRun);
    setSelectedRunId((current) => current ?? demo.runs[0]?.run_id ?? null);
    setSelectedRun((current) => current ?? demo.runs[0] ?? null);
    setExportBody("");
    setError("");
  }, [demoScenario, isDemoMode, telemetryTick]);

  useEffect(() => {
    if (isDemoMode) {
      return undefined;
    }
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
  }, [accessCode, apiFetch, isDemoMode, normalizeErrorMessage, readJsonPayload, refreshKey, selectedRunId]);

  useEffect(() => {
    if (isDemoMode) {
      const match = runs.find((run) => run.run_id === selectedRunId) ?? null;
      setSelectedRun(match);
      return undefined;
    }
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
  }, [accessCode, apiFetch, isDemoMode, normalizeErrorMessage, readJsonPayload, runs, selectedRunId]);

  async function handleExport() {
    if (!selectedRunId) {
      return;
    }
    if (isDemoMode) {
      const active = runs.find((run) => run.run_id === selectedRunId) ?? latestRun;
      setExportBody(JSON.stringify({
        run_id: active?.run_id,
        source: active?.source_name,
        operating_state: active?.operating_state,
        drift_status: active?.drift_status,
        neraium_score: active?.neraium_score,
        evidence_summary: active?.evidence_summary ?? [],
      }, null, 2));
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
          <div className="operator-report-shell">
            <div className="operator-report-summary">
              <p className="section-token">Operator report ready</p>
              <strong>{selectedRun?.source_name ?? selectedRun?.run_id ?? "Evidence run"}</strong>
              <span>{selectedRun?.operating_state ?? "Operational state recorded"} · Score {selectedRun?.neraium_score ?? "n/a"}</span>
            </div>
            <details className="technical-summary-panel technical-summary-panel--raw">
              <summary>Expert mode: raw export payload</summary>
              <pre className="evidence-console evidence-console--static">{exportBody}</pre>
            </details>
          </div>
        ) : (
          <p className="empty-copy">Generate a customer-ready report for the selected run.</p>
        )}
        {error && <p className="form-error">{error}</p>}
      </Panel>
    </div>
  );
}
