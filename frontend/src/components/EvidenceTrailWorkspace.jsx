import { useEffect, useMemo, useState } from "react";

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
        const [latestResponse, runsResponse] = await Promise.all([
          apiFetch("/api/evidence/latest", { accessCode }),
          apiFetch("/api/evidence/runs", { accessCode }),
        ]);
        const [latestPayload, runsPayload] = await Promise.all([
          readJsonPayload(latestResponse),
          readJsonPayload(runsResponse),
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
    return () => {
      cancelled = true;
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
        const response = await apiFetch(`/api/evidence/runs/${selectedRunId}`, { accessCode });
        const payload = await readJsonPayload(response);
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
      const response = await apiFetch(`/api/evidence/export/${selectedRunId}`, { accessCode });
      const body = await response.text();
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
      <Panel title="Evidence Trail" className="span-12">
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
          <div className="feed-list">
            {runs.map((run) => (
              <button
                className={`workspace-nav__item ${selectedRunId === run.run_id ? "workspace-nav__item--active" : ""}`}
                key={run.run_id}
                type="button"
                onClick={() => setSelectedRunId(run.run_id)}
              >
                <span className="workspace-nav__label">{run.source_name ?? run.run_id}</span>
                <span className="workspace-nav__detail">
                  {run.completed_at ? formatClockTime(run.completed_at) : "Pending"} | {run.operating_state ?? "n/a"} | {run.neraium_score ?? "n/a"} | {run.status}
                </span>
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

      <Panel title="Export Evidence Report" className="span-12">
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
