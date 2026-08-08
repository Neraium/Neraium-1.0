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
  return Number.isFinite(total) && total >= 0
    ? `${completed.toLocaleString()} / ${total.toLocaleString()} ${unit}`
    : `${completed.toLocaleString()} ${unit} processed`;
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

export default function JobProgressPanel({ uploadJob, uploadTransfer = null }) {
  const progress = uploadJob?.job_progress;
  const transferAvailable = uploadTransfer && Number.isFinite(Number(uploadTransfer.percent));
  if (!progress || progress.contract_version !== "job-progress.v1") {
    if (!transferAvailable) return null;
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
  const currentOperation = progress.operations?.find((operation) => operation.id === progress.substage)
    ?? progress.operations?.find((operation) => ["processing", "retrying", "failed"].includes(operation.status));
  const operationModel = currentOperation ? { ...progress, ...currentOperation } : progress;
  const operationPercent = Number(operationModel.percent_complete);
  const measurable = operationModel.percent_complete !== null
    && operationModel.percent_complete !== undefined
    && Number.isFinite(operationPercent);
  const count = formatProgressCount(operationModel);
  const message = pollConnectionState === "retrying"
    ? uploadJob?.message
    : progress.visibility_message || currentOperation?.message || progress.message;
  const visualState = pollConnectionState === "retrying" ? "retrying" : uploadJob?.execution_state || progress.status;

  return (
    <section className="backend-progress" aria-label="Backend job progress">
      <div className="backend-progress__status" role="status" aria-live="polite" aria-atomic="true">
        <span className={`backend-progress__state backend-progress__state--${String(visualState)}`}>{stateLabel}</span>
        <strong>{currentOperation?.label || titleCase(progress.substage) || "Waiting for worker"}</strong>
        {message ? <p>{message}</p> : null}
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

      {transferAvailable ? (
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
        <div><dt>Worker heartbeat</dt><dd>{progress.last_worker_heartbeat_at ? <time dateTime={progress.last_worker_heartbeat_at} title={`${formatUtcTimestamp(progress.last_worker_heartbeat_at)} UTC`}>{formatDuration(progress.seconds_since_worker_heartbeat)} ago</time> : "Not received"}</dd></div>
      </dl>

      <ol className="backend-progress__workflow" aria-label="Overall workflow steps">
        {(progress.workflow_steps || []).map((step) => (
          <li key={step.id} className={`backend-progress__workflow-step backend-progress__workflow-step--${step.status}`}>
            <span aria-hidden="true">{step.status === "completed" ? "✓" : step.status === "failed" ? "!" : "•"}</span>
            <strong>{step.label}</strong>
            <small>{step.status === "completed" ? "100%" : `${step.percent_complete}% · ${step.status}`}</small>
          </li>
        ))}
      </ol>

      <ol className="backend-progress__operations" aria-label="Detailed backend operations">
        {(progress.operations || []).map((operation) => (
          <li key={operation.id} className={`backend-progress__operation backend-progress__operation--${operation.status}`}>
            <span aria-hidden="true">{operation.status === "completed" ? "✓" : operation.status === "failed" ? "!" : operation.status === "pending" ? "–" : "•"}</span>
            <strong>{operation.label}</strong>
            <small>
              {operation.status === "completed"
                ? "Complete"
                : operation.percent_complete === null || operation.percent_complete === undefined
                  ? titleCase(operation.status)
                  : `${operation.percent_complete}% · ${titleCase(operation.status)}`}
            </small>
          </li>
        ))}
      </ol>
    </section>
  );
}
