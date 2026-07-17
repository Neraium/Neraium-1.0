import { formatOperatorActionLabel } from "../viewModels/operationalHelpers";
import { normalizeOperationalState } from "../viewModels/operationalUiState";
import { EMPTY_VALUE, formatEmptyValue } from "../viewModels/emptyValue";

export function Card({ as: Component = "section", className = "", children, ...props }) {
  return (
    <Component className={`ui-card ${className}`.trim()} {...props}>
      {children}
    </Component>
  );
}

export function Button({ variant = "primary", className = "", children, ...props }) {
  const variantClass = variant === "secondary" ? "secondary-command-button" : "command-button";
  return (
    <button className={`${variantClass} ui-button ui-button--${variant} ${className}`.trim()} type="button" {...props}>
      {children}
    </button>
  );
}

export function TextInput({ className = "", ...props }) {
  return <input className={`ui-input ${className}`.trim()} {...props} />;
}

export function Panel({ title, subtitle, className = "", children }) {
  return (
    <Card className={`ops-panel ${className}`.trim()}>
      <div className="ops-panel__header">
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      <div className="ops-panel__body">{children}</div>
    </Card>
  );
}

export function WorkflowStages({ items }) {
  return (
    <div className="workflow-list">
      {items.map((item) => (
        <div className="workflow-step" key={item.title}>
          <StatusDot tone={item.tone} />
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
          <span>{item.state}</span>
        </div>
      ))}
    </div>
  );
}

export function MetricGrid({ metrics, compact = false }) {
  return (
    <div className={`metric-grid ${compact ? "metric-grid--compact" : ""}`}>
      {metrics.map((metric) => (
        <div className="metric-cell" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{formatEmptyValue(metric.value)}</strong>
        </div>
      ))}
    </div>
  );
}

export function FeedList({ items, emptyText, inline = false }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No active items" body={emptyText} compact />;
  }

  return (
    <div className={`feed-list ${inline ? "feed-list--inline" : ""}`}>
      {items.map((item, index) => (
        <div className="feed-item" key={`${item.title ?? item}-${index}`}>
          <StatusDot tone={item.tone ?? "muted"} />
          <div>
            <strong>{item.title ?? item}</strong>
            {item.detail && <p>{item.detail}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function TimelineFeed({ items }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No timeline events" body="No completed upload yet." compact />;
  }

  return (
    <div className="timeline-list">
      {items.map((item, index) => (
        <div className="timeline-item" key={`${item.time}-${item.title}-${index}`}>
          <StatusDot tone={item.tone} />
          <span className="timeline-item__time">{item.time}</span>
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export function TelemetryCardGrid({ cards, compact = false, formatOperationalTone }) {
  if (!cards || cards.length === 0) {
    return <EmptyState title="No telemetry available" body="Upload telemetry to populate these system cards." compact />;
  }

  return (
    <div className={`telemetry-grid ${compact ? "telemetry-grid--compact" : ""}`}>
      {cards.map((card) => (
        <div className="telemetry-card" key={card.label}>
          <div className="telemetry-card__header">
            <span className="telemetry-card__eyebrow">{card.label}</span>
            <StatusDot tone={card.tone} />
          </div>
          <strong>{card.primary}</strong>
          <p>{card.secondary}</p>
          <MiniSeries values={card.series} tone={card.tone} />
          <div className="telemetry-card__footer">
            <span>{Array.isArray(card.series) ? `${card.series.length} samples` : "No live samples"}</span>
            <span>{formatOperationalTone(card.tone ?? "info")}</span>
          </div>
          {Array.isArray(card.technicalDetails) && card.technicalDetails.length > 0 && (
            <details className="technical-detail-panel technical-detail-panel--card">
              <summary>View evidence</summary>
              <div className="technical-detail-panel__lines">
                {card.technicalDetails.slice(0, 5).map((line, index) => (
                  <code key={`${line}-${index}`}>{line}</code>
                ))}
              </div>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}

export function MiniSeries({ values, tone }) {
  if (!values || values.length === 0) {
    return <div className="mini-series mini-series--empty">No series yet</div>;
  }

  const maxValue = Math.max(...values, 1);

  return (
    <div className="mini-series">
      {values.map((value, index) => (
        <span
          className={`mini-series__bar mini-series__bar--${tone}`}
          key={`${value}-${index}`}
          style={{ height: `${Math.max((value / maxValue) * 100, 16)}%` }}
        />
      ))}
    </div>
  );
}

export function DriftMonitor({ rows, detailed = false }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No segment trend review available" body="Upload telemetry to generate change review." compact />;
  }

  const maxMagnitude = Math.max(
    ...rows.map((row) => Math.abs(row.percent_change ?? row.absolute_change ?? 0)),
    1,
  );

  return (
    <div className="drift-list">
      {rows.map((row) => {
        const magnitude = Math.abs(row.percent_change ?? row.absolute_change ?? 0);
        const width = Math.max((magnitude / maxMagnitude) * 100, 6);

        return (
          <div className="drift-row" key={row.column}>
            <div className="drift-row__meta">
              <span>{row.column}</span>
              <strong>
                {row.percent_change === null ? row.absolute_change : `${row.percent_change}%`}
              </strong>
            </div>
            <div className="drift-row__track">
              <span
                className={`drift-row__fill drift-row__fill--${row.drift_flag}`}
                style={{ width: `${width}%` }}
              />
            </div>
            <div className="drift-row__status">
              <span>{row.direction}</span>
              <span className={`drift-row__flag drift-row__flag--${row.drift_flag}`}>{row.drift_flag}</span>
            </div>
            {detailed && row.warnings?.length > 0 && (
              <p className="drift-row__detail">{row.warnings.join(" ")}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function DriftFeed({ rows }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No segment trend feed" body="No completed upload yet." compact />;
  }

  return (
    <FeedList
      items={rows.map((row) => ({
        title: row.column,
        detail: `${row.direction} movement with ${row.percent_change === null ? row.absolute_change : `${row.percent_change}%`} change.`,
        tone: row.drift_flag,
      }))}
      emptyText="Awaiting segment trend output."
    />
  );
}

export function RelationshipMonitor({
  rows,
  formatRelationshipPair,
  relationshipDetail,
  relationshipConsistencyLabel,
}) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No consistency shifts" body="Awaiting paired variable telemetry." compact />;
  }

  return (
    <div className="relationship-list">
      {rows.map((row, index) => {
        const columns = row.columns ?? [];
        return (
          <div className="relationship-row" key={`${columns.join("-")}-${index}`}>
            <div className="relationship-row__header">
              <span>{formatRelationshipPair(columns, index)}</span>
              <StatusDot tone={row.tone ?? "info"} />
            </div>
            <strong>{formatEmptyValue(relationshipDetail(row))}</strong>
            <p>{relationshipConsistencyLabel(row)}</p>
            {Array.isArray(row.technicalDetails) && row.technicalDetails.length > 0 && (
              <details className="technical-detail-panel technical-detail-panel--compact">
                <summary>Analysis detail</summary>
                <div className="technical-detail-panel__lines">
                  {row.technicalDetails.slice(0, 4).map((line, detailIndex) => (
                    <code key={`${line}-${detailIndex}`}>{line}</code>
                  ))}
                </div>
              </details>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function SystemsMatrix({ systems, systemsState, roomContext, rows, systemRoomContext }) {
  const tableRows = rows ?? systems.map((system) => [
    system.name,
    system.scope,
    systemRoomContext(system.name, roomContext),
    systemsState === "ready" ? "Live telemetry sync" : "Analysis service unavailable",
  ]);

  return (
    <DataTable
      columns={["System", "Operational review scope", "Segment context", "Source state"]}
      rows={tableRows}
    />
  );
}

export function InterventionGrid({
  items,
  selectedId,
  onSelect,
  compact = false,
  limit = 6,
  buildGuidanceForItem,
  formatRoomDecisionState,
}) {
  if (!items || items.length === 0) {
    return <EmptyState title="No intervention windows available" body="Upload telemetry to activate intervention windows." compact />;
  }

  return (
    <div className={`intervention-grid ${compact ? "intervention-grid--compact-command" : ""}`}>
      {items.slice(0, limit).map((item, index) => {
        const guidance = buildGuidanceForItem(item);
        return (
          <button
            className={`intervention-card intervention-card--${item.tone} ${selectedId === item.id ? "intervention-card--selected" : ""}`}
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
          >
            <div className="intervention-card__header">
              <div>
                <span>{item.label}</span>
                <strong>{item.decisionLabel ?? formatRoomDecisionState(item.tone, index)}</strong>
              </div>
              <StatusDot tone={item.tone ?? "info"} />
            </div>
            <div className="intervention-card__window">
              <span>Time</span>
              <strong>{item.window}</strong>
            </div>
          <p>{formatEmptyValue(compact ? item.primaryAction ?? item.recommendation : guidance.primaryDriver)}</p>
            {!compact && (
              <div className="intervention-card__footer">
                <span className={`overview-pill overview-pill--${item.tone}`}>{item.primaryAction ?? item.recommendation}</span>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function WhyPanel({
  item,
  findings,
  actionStatus,
  onOperatorAction,
  compact = false,
  buildConfidenceBasis,
  buildStructuralExplanation,
  buildGuidanceForItem,
  formatRoomDecisionState,
  formatConfidenceLabel,
  formatClockTime,
}) {
  if (!item) {
    return <EmptyState title="No active explanation" body="Upload telemetry to generate the first explanation." compact />;
  }

  const confidenceBasis = item.confidenceBasis ?? buildConfidenceBasis(item, findings);
  const supportingEvidence = Array.isArray(item.supportingEvidence)
    ? item.supportingEvidence
    : Array.isArray(item.drivers)
      ? item.drivers
      : (findings ?? []).map((entry) => entry.detail).filter(Boolean).slice(0, 3);
  const contributingSignals = item.contributingSignals ?? [];
  const structuralExplanation = Array.isArray(item.structuralExplanation) && item.structuralExplanation.length > 0
    ? item.structuralExplanation
    : buildStructuralExplanation(item);
  const guidance = buildGuidanceForItem(item);
  const technicalDetails = Array.isArray(item.technicalDetails) ? item.technicalDetails : [];

  return (
    <div className={`why-panel ${compact ? "why-panel--compact" : ""}`}>
      <div className="why-panel__summary">
        <div>
          <span className="section-token">Selected segment</span>
          <h3>{item.label ?? item.shortTitle ?? item.title}</h3>
          <p>{item.decisionLabel ?? formatRoomDecisionState(item.tone)}. {item.window}</p>
        </div>
        <span className={`overview-pill overview-pill--${item.tone ?? "info"}`}>{item.primaryAction ?? item.recommendation}</span>
      </div>

      <div className="why-panel__section">
        <span className="section-token">Summary</span>
        <p className="why-panel__headline">{item.whyHeadline ?? item.summary ?? item.detail}</p>
      </div>

      <div className="why-panel__section guidance-driver">
        <span className="section-token">Starting point</span>
        <p>{guidance.primaryDriver}</p>
      </div>

      <div className="why-panel__section guidance-flag">
        <span className="section-token">Evidence</span>
        <p>{guidance.whyFlagged}</p>
      </div>

      {compact ? (
        <ProgressionStrip tone={item.tone ?? "info"} compact />
      ) : (
        <div className="why-panel__section observed-progression">
          <span className="section-token">Observed progression</span>
          <ProgressionStrip tone={item.tone ?? "info"} detailed />
        </div>
      )}

      {!compact && (
        <div className="why-panel__section structural-explanation">
          <span className="section-token">Operating pattern</span>
          {structuralExplanation.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      )}

      {!compact && item.likelyDriver && (
        <div className="why-panel__section">
          <span className="section-token">Possible driver</span>
          <p>{item.likelyDriver}</p>
          {contributingSignals.length > 0 && (
            <div className="signal-chip-row">
              {contributingSignals.map((signal) => (
                <span className="signal-chip" key={signal}>{signal}</span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="why-panel__section">
        <span className="section-token">Evidence basis</span>
        <p>{formatConfidenceLabel(item.confidence)} confidence. {confidenceBasis}</p>
      </div>

      {!compact && (
        <div className="why-panel__chain">
          {supportingEvidence.map((driver) => (
            <div className="why-panel__driver" key={driver}>
              <StatusDot tone={item.tone ?? "info"} />
              <span>{driver}</span>
            </div>
          ))}
        </div>
      )}

      <div className="why-panel__recommendation">
        <span>Next move</span>
        <strong>{item.primaryAction ?? item.recommendation ?? "Continue monitoring"}</strong>
      </div>

      <div className="why-panel__section guidance-checks">
        <span className="section-token">What to check</span>
        <ul>
          {(guidance.whatToCheck ?? ["Continue monitoring"]).slice(0, compact ? 3 : 4).map((check) => (
            <li key={check}>{check}</li>
          ))}
        </ul>
      </div>

      {technicalDetails.length > 0 && (
        <details className="technical-detail-panel">
          <summary>Analysis detail</summary>
          <div className="technical-detail-panel__lines">
            {technicalDetails.slice(0, compact ? 5 : 10).map((line, index) => (
              <code key={`${line}-${index}`}>{line}</code>
            ))}
          </div>
        </details>
      )}

      {onOperatorAction && (
        <OperatorActionControls
          actionStatus={actionStatus}
          targetId={item.targetId ?? item.id}
          onOperatorAction={onOperatorAction}
          formatClockTime={formatClockTime}
        />
      )}

      {!compact && (
        <div className="why-panel__baseline">
          <span className="section-token">Usual pattern</span>
          <p>{item.baselineContext ?? item.change ?? "Current telemetry state remains inside the expected operating band."}</p>
        </div>
      )}
      {actionStatus && !onOperatorAction && (
        <p className="why-panel__action-status">
          {actionStatus.action === "log"
            ? `Intervention logged at ${formatClockTime(actionStatus.at)} CT.`
            : "Pattern ignored for the current walkthrough."}
        </p>
      )}
    </div>
  );
}

export function OperatorActionControls({ actionStatus, targetId, onOperatorAction, formatClockTime }) {
  const actions = [
    { id: "acknowledge", label: "Acknowledge" },
    { id: "review", label: "Under review" },
    { id: "taken", label: "Action taken" },
  ];

  return (
    <div className="operator-action-controls" role="group" aria-label="Operator action status">
      {actions.map((action) => (
        <button
          className={`operator-action-button ${actionStatus?.action === action.id ? "operator-action-button--active" : ""}`}
          key={action.id}
          type="button"
          onClick={() => onOperatorAction(targetId, action.id)}
        >
          {action.label}
        </button>
      ))}
      {actionStatus && (
        <p className="operator-action-status">
          <span role="status" aria-live="polite">{formatOperatorActionLabel(actionStatus.action)} at {formatClockTime(actionStatus.at)} CT.</span>
        </p>
      )}
    </div>
  );
}

export function ProgressionStrip({ tone, compact = false, detailed = false }) {
  const stages = detailed
    ? [
        "Usual recovery",
        "Early relationship shift",
        "Persistent change formation",
        "Compressed intervention horizon",
      ]
    : ["Stable recovery", "Shift watch", "Change persistence", "Window tightening"];
  const activeIndex = tone === "unstable" ? 3 : tone === "elevated" ? 2 : tone === "review" ? 1 : 0;

  return (
    <div
      className={`progression-strip ${compact ? "progression-strip--compact" : ""} ${detailed ? "progression-strip--detailed" : ""}`}
      aria-label="Structural movement progression"
      role="list"
    >
      {stages.map((stage, index) => (
        <div
          className={`progression-strip__stage ${index <= activeIndex ? "progression-strip__stage--active" : ""}`}
          key={stage}
          role="listitem"
        >
          <span />
          <strong>{stage}</strong>
        </div>
      ))}
    </div>
  );
}

export function FleetSummary({ summary }) {
  return (
    <div className="fleet-summary">
      <div className={`fleet-summary__hero fleet-summary__hero--${summary.tone}`}>
        <span className="section-token">Structural score</span>
        <strong>{summary.score}</strong>
        <p>{summary.summary}</p>
      </div>
      <div className="fleet-summary__grid">
        {summary.metrics.map((metric) => (
          <div className={`overview-summary-cell overview-summary-cell--${metric.tone}`} key={metric.label}>
            <div className="overview-summary-cell__header">
              <span>{metric.label}</span>
              <StatusDot tone={metric.tone} />
            </div>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TargetSelector({ items, selectedId, onSelect, buildGuidanceForItem }) {
  return (
    <div className="target-selector">
      {items.slice(0, 5).map((item) => (
        <button
          className={`target-selector__item target-selector__item--${item.tone} ${selectedId === item.id ? "target-selector__item--selected" : ""}`}
          key={item.id}
          type="button"
          onClick={() => onSelect(item.id)}
        >
          <div className="target-selector__header">
            <span>{item.label}</span>
            <StatusDot tone={item.tone} />
          </div>
          <strong>{formatEmptyValue(item.window)}</strong>
          <p>{formatEmptyValue(item.primaryAction ?? item.recommendation)}</p>
          <p className="target-selector__driver">{formatEmptyValue(buildGuidanceForItem(item).primaryDriver)}</p>
        </button>
      ))}
    </div>
  );
}

export function CompactList({ items, emptyText, title, inline = false }) {
  return (
    <div className={`compact-list-block ${inline ? "compact-list-block--inline" : ""}`}>
      {title && <p className="section-token">{title}</p>}
      {items && items.length > 0 ? (
        <ul className={`compact-list ${inline ? "compact-list--inline" : ""}`}>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="empty-copy">{emptyText}</p>
      )}
    </div>
  );
}

export function EvidenceConsole({ lines, animated = false }) {
  return (
    <div className={`evidence-console ${animated ? "evidence-console--animated" : ""}`}>
      {lines.map((line, index) => (
        <div className="evidence-console__line" key={`${line}-${index}`}>
          <span>{formatEmptyValue(line)}</span>
        </div>
      ))}
    </div>
  );
}

export function EngineIdentityPanel({
  identity,
  latestUploadResult,
  intelligenceStatus,
  runnerTraceLines,
  processingTraceLines,
}) {
  const trace = latestUploadResult?.processing_trace ?? null;
  const runnerResult = latestUploadResult?.sii_runner_result ?? null;
  const version = identity?.engine_version ?? trace?.engine_version ?? "Awaiting analysis service identity";
  const modulePath = identity?.production_runner ?? identity?.engine_module ?? runnerResult?.runner_module ?? "Awaiting analysis service identity";
  const source = intelligenceStatus?.source ?? "none";
  const lastProcessed = intelligenceStatus?.last_processed_at ?? "Awaiting upload";
  const runnerAvailable = identity?.runner_available ?? runnerResult?.runner_used ?? false;

  return (
    <details className="engine-identity-panel">
      <summary>
        <span>
          <strong>{identity?.engine_name ?? "Neraium SII"}</strong>
          <small>{runnerAvailable ? "SII analysis engine available" : "SII analysis engine pending"}</small>
        </span>
        <span>{formatEmptyValue(source)}</span>
      </summary>
      <MetricGrid
        metrics={[
          { label: "Engine version", value: version },
          { label: "Core engine", value: identity?.core_engine ?? runnerResult?.core_engine ?? "SIIEngine" },
          { label: "Analysis engine path", value: modulePath },
          { label: "Source", value: source },
          { label: "Last processed", value: lastProcessed },
          {
            label: "Validation family",
            value: identity?.same_engine_family_as_validation ? "Yes" : "Pending",
          },
        ]}
      />
      <EvidenceConsole
        lines={
          runnerResult
            ? runnerTraceLines(runnerResult)
            : trace
              ? processingTraceLines(trace)
              : ["analysis_trace=awaiting_upload"]
        }
      />
    </details>
  );
}

export function DataTable({ columns, rows, caption = "Operational data" }) {
  return (
    <div className="table-shell">
      <table className="data-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${rowIndex}-${columns[0]}`}>
              {row.map((cell, cellIndex) => (
                <td
                  className={cellIndex === 0 ? "data-table__primary-cell" : ""}
                  key={`${rowIndex}-${cellIndex}`}
                  data-label={columns[cellIndex]}
                >
                  {formatEmptyValue(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EmptyState({ title, body, compact = false }) {
  const displayTitle = String(title ?? "").trim() || EMPTY_VALUE;
  const displayBody = String(body ?? "").trim() || EMPTY_VALUE;
  return (
    <div className={`empty-state ${compact ? "empty-state--compact" : ""}`}>
      <strong>{displayTitle}</strong>
      <p>{displayBody}</p>
    </div>
  );
}

export function StatusDot({ tone }) {
  const uiState = normalizeOperationalState(tone);

  return (
    <span className={`status-dot status-dot--${tone} status-dot--state-${uiState}`} aria-hidden="true">
      <span className="status-dot__halo" />
      <span className="status-dot__ring" />
      <span className="status-dot__core" />
    </span>
  );
}
