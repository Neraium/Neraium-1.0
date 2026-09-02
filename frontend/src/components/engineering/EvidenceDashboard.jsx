import React from "react";
import "../../styles/evidence-dashboard.css";

const ICON_GRAPHICS = {
  system: (
    <>
      <path d="M3 19V7l6-4v16M9 9h8v10M2 19h18" />
      <path d="M12 12h2M12 15h2" />
    </>
  ),
  status: (
    <>
      <path d="M12 3 21 19H3L12 3Z" />
      <path d="M12 9v4M12 16h.01" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 10h18" />
    </>
  ),
  magnitude: (
    <>
      <path d="m3 17 5-5 4 3 8-9" />
      <path d="M15 6h5v5" />
    </>
  ),
  persistence: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  context: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" />
    </>
  ),
  confidence: (
    <>
      <path d="M12 3 20 6v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3Z" />
      <path d="m8 12 3 3 5-6" />
    </>
  ),
  cause: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.8 9a2.4 2.4 0 1 1 3.3 2.2c-.8.4-1.1.9-1.1 1.8M12 17h.01" />
    </>
  ),
};

const UNSUPPORTED_METRIC_PATTERN = /^(?:not established|insufficient evidence|unavailable)$/i;
const NEUTRAL_STATUS_PATTERN = /\b(?:stable|insufficient|unavailable|not established)\b/i;
const ATTENTION_STATUS_PATTERN = /\b(?:change|shift|persistent|material|attention|review|degrad)/i;

function Icon({ name }) {
  return (
    <svg
      className="evidence-dashboard__icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_GRAPHICS[name]}
    </svg>
  );
}

function trimFractionZeros(value) {
  const decimalIndex = value.indexOf(".");
  if (decimalIndex === -1) return value;

  let end = value.length;
  while (end > decimalIndex + 1 && value[end - 1] === "0") end -= 1;
  if (end === decimalIndex + 1) end = decimalIndex;
  return value.slice(0, end);
}

function numericValue(value, signed) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const precision = Math.abs(number) > 0 && Math.abs(number) < 0.01 ? 3 : 2;
  const formatted = trimFractionZeros(number.toFixed(precision));
  return signed && number > 0 ? `+${formatted}` : formatted;
}

function ContextCell({ icon, label, value, exactStart, exactEnd, tone }) {
  const hasExactBoundary = exactStart || exactEnd;

  return (
    <div className="evidence-dashboard__context-cell" data-tone={tone}>
      <Icon name={icon} />
      <div>
        <span>{label}</span>
        <strong>
          {hasExactBoundary ? <time dateTime={exactStart || undefined}>{value}</time> : value}
        </strong>
      </div>
      {exactStart && exactEnd ? (
        <span className="sr-only">
          Exact evidence window: {exactStart} through {exactEnd}
        </span>
      ) : null}
    </div>
  );
}

function Metric({ icon, label, metric, tone }) {
  const number = numericValue(metric?.value, metric?.signed);
  const displayValue = number ?? metric?.label ?? metric?.value ?? "Not established";
  const supported = !UNSUPPORTED_METRIC_PATTERN.test(String(displayValue));

  return (
    <div className="evidence-dashboard__metric" data-tone={tone} data-supported={supported}>
      <div className="evidence-dashboard__metric-label">
        <Icon name={icon} />
        <span>{label}</span>
      </div>
      <strong>{displayValue}</strong>
      <small>{metric?.description}</small>
    </div>
  );
}

function isValidSparklinePoint(point) {
  return point
    && Number.isFinite(Number(point.value))
    && !Number.isNaN(new Date(point.timestamp).getTime());
}

function sparklinePoints(values) {
  const minimum = Math.min(...values);
  const span = Math.max(Math.max(...values) - minimum, Number.EPSILON);

  return values
    .map((value, index) => `${(index / (values.length - 1)) * 92 + 4},${26 - ((value - minimum) / span) * 20}`)
    .join(" ");
}

function sparklineDirection(values) {
  if (values.at(-1) > values[0]) return "rises";
  if (values.at(-1) < values[0]) return "falls";
  return "ends unchanged";
}

function Sparkline({ data, relationshipLabel }) {
  if (!Array.isArray(data) || data.length < 2) return null;
  if (!data.every(isValidSparklinePoint)) return null;

  const ordered = [...data].sort(
    (left, right) => new Date(left.timestamp) - new Date(right.timestamp),
  );
  const values = ordered.map((point) => Number(point.value));
  const direction = sparklineDirection(values);

  return (
    <svg
      className="evidence-dashboard__sparkline"
      viewBox="0 0 100 30"
      role="img"
      aria-label={`${relationshipLabel} trend ${direction} across ${values.length} chronological evidence points.`}
    >
      <polyline points={sparklinePoints(values)} />
    </svg>
  );
}

function RelationshipRow({ relationship, rank }) {
  const magnitude = numericValue(relationship.magnitude, relationship.signed);

  return (
    <li>
      <span className="evidence-dashboard__rank" aria-label={`Rank ${rank}`}>
        {rank}
      </span>
      <strong>{relationship.label}</strong>
      <Sparkline data={relationship.sparkline} relationshipLabel={relationship.label} />
      <span className="evidence-dashboard__relationship-value">
        {magnitude ?? "Not supplied"}
      </span>
    </li>
  );
}

function InsufficientEvidenceDashboard({ insufficient }) {
  return (
    <section
      className="evidence-dashboard evidence-dashboard--insufficient"
      aria-labelledby="evidence-insufficient-title"
    >
      <span className="evidence-dashboard__kicker">Evidence record</span>
      <h1 id="evidence-insufficient-title">
        {insufficient?.title || "Insufficient evidence"}
      </h1>
      <p>
        {insufficient?.description
          || "The available evidence does not support a reliable behavioral-change conclusion."}
      </p>
    </section>
  );
}

export default function EvidenceDashboard({ summary, variant = "ready" }) {
  if (!summary) return null;
  if (variant === "insufficient" || summary.insufficient) {
    return <InsufficientEvidenceDashboard insufficient={summary.insufficient} />;
  }

  const metrics = summary.metrics ?? {};
  const status = summary.status || "Unavailable";
  const statusRequiresAttention = !NEUTRAL_STATUS_PATTERN.test(status)
    && ATTENTION_STATUS_PATTERN.test(status);

  return (
    <section className="evidence-dashboard" aria-labelledby="evidence-dashboard-title">
      <header className="evidence-dashboard__header">
        <span className="evidence-dashboard__kicker">Finding</span>
        <h1 id="evidence-dashboard-title">
          {summary.title || "Finding title unavailable"}
        </h1>
      </header>

      <div className="evidence-dashboard__context" aria-label="Finding context">
        <ContextCell
          icon="system"
          label="System"
          value={summary.system || "System not supplied"}
        />
        <ContextCell
          icon="status"
          label="Status"
          value={status}
          tone={statusRequiresAttention ? "attention" : undefined}
        />
        <ContextCell
          icon="calendar"
          label="Evidence window"
          value={summary.evidenceWindow?.label || "Unavailable"}
          exactStart={summary.evidenceWindow?.start}
          exactEnd={summary.evidenceWindow?.end}
        />
      </div>

      <div className="evidence-dashboard__metrics" aria-label="Evidence metrics">
        <Metric icon="magnitude" label="Magnitude" metric={metrics.magnitude} tone="change" />
        <Metric
          icon="persistence"
          label="Persistence"
          metric={metrics.persistence}
          tone="persistence"
        />
        <Metric
          icon="context"
          label="Operating context"
          metric={metrics.operatingContext}
          tone="context"
        />
        <Metric
          icon="confidence"
          label="Confidence"
          metric={metrics.confidence}
          tone="confidence"
        />
      </div>

      <section
        className="evidence-dashboard__relationships"
        aria-labelledby="evidence-relationships-title"
      >
        <h2 id="evidence-relationships-title">Strongest Relationship Changes</h2>
        {summary.relationships?.length ? (
          <ol>
            {summary.relationships.slice(0, 3).map((relationship, index) => (
              <RelationshipRow
                key={relationship.id || index}
                relationship={relationship}
                rank={index + 1}
              />
            ))}
          </ol>
        ) : (
          <p className="evidence-dashboard__empty">
            No authoritative relationship changes were supplied.
          </p>
        )}
      </section>

      <div className="evidence-dashboard__cause">
        <div>
          <Icon name="cause" />
          <strong>Cause established?</strong>
        </div>
        <span data-established={summary.cause?.established === true}>
          {summary.cause?.label || "No \u2014 investigation required"}
        </span>
      </div>
    </section>
  );
}
