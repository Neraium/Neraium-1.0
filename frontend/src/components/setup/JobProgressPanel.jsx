import { useEffect, useId, useState } from "react";

function clampPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function titleCase(value) {
  const text = String(value || "").trim().replaceAll("_", " ").replaceAll("-", " ");
  if (!text) return "";
  return text.replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatUtcTimestamp(value) {
  const date = new Date(String(value || ""));
  if (!Number.isFinite(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainder = Math.floor(value % 60);
  if (hours) return `${hours}h ${minutes}m ${remainder}s`;
  if (minutes) return `${minutes}m ${remainder}s`;
  return `${remainder}s`;
}

function formatProgressCount(progress) {
  const completed = progress?.completed_units === null || progress?.completed_units === undefined
    ? null
    : Number(progress.completed_units);
  const total = progress?.total_units === null || progress?.total_units === undefined
    ? null
    : Number(progress.total_units);
  if (completed === null || !Number.isFinite(completed)) return "";
  const unit = String(progress?.unit_type || "work units").replaceAll("_", " ");
  const boundedCompleted = Number.isFinite(total) && total >= 0
    ? Math.min(completed, total)
    : completed;
  return Number.isFinite(total) && total >= 0
    ? `${boundedCompleted.toLocaleString()} / ${total.toLocaleString()} ${unit}`
    : `${boundedCompleted.toLocaleString()} ${unit} processed`;
}

function progressStateLabel(progress, executionState, pollConnectionState) {
  if (pollConnectionState === "retrying" || progress?.status === "retrying") return "Retrying status connection";
  if (progress?.stalled) return "Waiting for worker progress";
  return ({
    queued: "Queued",
    processing: "Processing",
    waiting: "Waiting",
    completed: "Completed",
    failed: "Failed",
  })[executionState || progress?.status] || titleCase(progress?.status || executionState || "Processing");
}

function operationActivityLabel(operation, progressStatus) {
  if (!operation) return progressStatus === "completed" ? "All operations complete" : "Waiting for the current operation";
  const state = String(operation.status || "processing").toLowerCase();
  if (state === "completed") return `${operation.label} complete`;
  if (state === "failed") return `${operation.label} failed`;
  if (state === "pending") return `${operation.label} pending`;
  if (state === "queued") return `${operation.label} queued`;
  if (state === "waiting") return `${operation.label} waiting`;
  if (state === "retrying") return `${operation.label} retrying`;
  return `${operation.label} in progress`;
}

export default function JobProgressPanel({ uploadJob, uploadTransfer = null, statusDetail = "" }) {
  const progress = uploadJob?.job_progress;
  const operations = Array.isArray(progress?.operations) ? progress.operations : [];
  const failedOperation = operations.find((operation) => operation.status === "failed");
  const detailsId = useId();
  const [detailsExpanded, setDetailsExpanded] = useState(Boolean(failedOperation));
  const failedOperationId = failedOperation?.id ?? null;
  useEffect(() => {
    if (failedOperationId) setDetailsExpanded(true);
  }, [failedOperationId]);
  const transferAvailable = uploadTransfer && Number.isFinite(Number(uploadTransfer.percent));
  const transferActive = transferAvailable && clampPercent(uploadTransfer.percent) < 100;
  if (!progress || progress.contract_version !== "job-progress.v1") {
    if (!transferActive) return null;
    const transferPercent = clampPercent(uploadTransfer.percent);
    return (
      <section className="backend-progress" aria-label="File transfer progress">
        <p className="backend-progress__indeterminate" role="status">{uploadTransfer.label || uploadTransfer.message || "Sending telemetry."}</p>
        <div className="backend-progress__meter-row">
          <div><strong>File transfer</strong><span>{transferPercent}%</span></div>
          <progress aria-label="File transfer" max="100" value={transferPercent} />
        </div>
      </section>
    );
  }
  const overallPercent = clampPercent(progress.overall_percent_complete);
  const pollConnectionState = String(uploadJob?.poll_connection_state || "").toLowerCase();
  const stateLabel = progressStateLabel(progress, uploadJob?.execution_state, pollConnectionState);
  const currentOperation = operations.find((operation) => operation.id === progress.substage)
    ?? operations.find((operation) => ["processing", "retrying", "failed"].includes(operation.status));
  const operationModel = currentOperation ? { ...progress, ...currentOperation } : progress;
  const operationPercent = Number(operationModel.percent_complete);
  const measurable = operationModel.percent_complete !== null
    && operationModel.percent_complete !== undefined
    && Number.isFinite(operationPercent);
  const count = formatProgressCount(operationModel);
  const message = pollConnectionState === "retrying"
    ? uploadJob?.message
    : progress.visibility_message || currentOperation?.message || progress.message;
  const compactStatusDetail = String(statusDetail || "").trim();
  const showStatusDetail = compactStatusDetail
    && compactStatusDetail.toLowerCase() !== String(message || "").trim().toLowerCase();
  const visualState = pollConnectionState === "retrying" ? "retrying" : uploadJob?.execution_state || progress.status;
  const completedOperationCount = operations.filter((operation) => operation.status === "completed").length;
  const detailOperation = failedOperation ?? currentOperation;
  const detailState = operationActivityLabel(detailOperation, progress.status);
  const detailsSummary = `${completedOperationCount} of ${operations.length} operations complete · ${detailState}`;
  const heartbeatAge = Number(progress.seconds_since_worker_heartbeat);
  const heartbeatHealthy = Number.isFinite(heartbeatAge) && !progress.stalled;
  const showHeartbeat = Boolean(progress.last_worker_heartbeat_at);

  return (
    <section className="backend-progress" aria-label="Backend job progress">
      <div className="backend-progress__status" role="status" aria-live="polite" aria-atomic="true">
        <span className={`backend-progress__state backend-progress__state--${String(visualState)}`}>{stateLabel}</span>
        <strong>{currentOperation?.label || titleCase(progress.substage) || "Waiting for worker"}</strong>
        {message ? <p>{message}</p> : null}
        {showStatusDetail ? <p className="backend-progress__status-detail">{compactStatusDetail}</p> : null}
      </div>

      <div className="backend-progress__meter-row">
        <div><strong>Overall workflow</strong><span>{overallPercent}%</span></div>
        <div
          className="backend-progress__meter"
          role="progressbar"
          aria-label="Overall backend workflow"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={overallPercent}
          aria-valuetext={`${overallPercent} percent of backend operations complete`}
        >
          <span style={{ width: `${overallPercent}%` }} />
        </div>
      </div>

      {transferActive ? (
        <div className="backend-progress__meter-row">
          <div><strong>File transfer</strong><span>{clampPercent(uploadTransfer.percent)}%</span></div>
          <div className="backend-progress__meter" role="progressbar" aria-label="File transfer" aria-valuemin="0" aria-valuemax="100" aria-valuenow={clampPercent(uploadTransfer.percent)}>
            <span style={{ width: `${clampPercent(uploadTransfer.percent)}%` }} />
          </div>
        </div>
      ) : null}

      <div className="backend-progress__meter-row">
        <div>
          <strong>{currentOperation?.label || "Current operation"}</strong>
          <span>{measurable ? `${clampPercent(operationPercent)}%` : "Measuring work"}</span>
        </div>
        {measurable ? (
          <div
            className="backend-progress__meter"
            role="progressbar"
            aria-label={currentOperation?.label || "Current backend operation"}
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={clampPercent(operationPercent)}
            aria-valuetext={count || `${clampPercent(operationPercent)} percent complete`}
          >
            <span style={{ width: `${clampPercent(operationPercent)}%` }} />
          </div>
        ) : <p className="backend-progress__indeterminate">The backend has not established a safe total for this operation.</p>}
        {count ? <small>{count}</small> : null}
      </div>

      <dl className="backend-progress__timing">
        <div><dt>Elapsed</dt><dd>{formatDuration(progress.elapsed_seconds)}</dd></div>
        <div><dt>Last update</dt><dd><time dateTime={progress.updated_at} title={`${formatUtcTimestamp(progress.updated_at)} UTC`}>{formatDuration(progress.seconds_since_update)} ago</time></dd></div>
        {showHeartbeat ? (
          <div>
            <dt>Worker</dt>
            <dd>
              {heartbeatHealthy ? "Healthy · " : "Heartbeat · "}
              <time dateTime={progress.last_worker_heartbeat_at} title={`${formatUtcTimestamp(progress.last_worker_heartbeat_at)} UTC`}>{formatDuration(progress.seconds_since_worker_heartbeat)} ago</time>
            </dd>
          </div>
        ) : null}
      </dl>

      {operations.length ? (
        <section className={`backend-progress__details${failedOperation ? " backend-progress__details--failed" : ""}`}>
          <button
            type="button"
            className="backend-progress__details-toggle"
            aria-expanded={detailsExpanded}
            aria-controls={detailsId}
            aria-describedby={`${detailsId}-summary`}
            onClick={() => setDetailsExpanded((expanded) => !expanded)}
          >
            <span>Processing details</span>
            <i aria-hidden="true" />
          </button>
          <p id={`${detailsId}-summary`} className="backend-progress__details-summary">{detailsSummary}</p>
          <div id={detailsId} hidden={!detailsExpanded}>
            <ol className="backend-progress__operations" aria-label="Detailed backend operations">
              {operations.map((operation) => (
                <li key={operation.id} className={`backend-progress__operation backend-progress__operation--${operation.status}`}>
                  <span aria-hidden="true">{operation.status === "completed" ? "✓" : operation.status === "failed" ? "!" : operation.status === "pending" ? "–" : "•"}</span>
                  <strong>{operation.label}</strong>
                  <small>
                    {operation.status === "completed"
                      ? "Complete"
                      : operation.percent_complete === null || operation.percent_complete === undefined
                        ? ["processing", "retrying"].includes(operation.status)
                          ? `Measuring work · ${titleCase(operation.status)}`
                          : titleCase(operation.status)
                        : `${operation.percent_complete}% · ${titleCase(operation.status)}`}
                  </small>
                </li>
              ))}
            </ol>
          </div>
        </section>
      ) : null}
    </section>
  );
}
