export default function SystemMetricGrid({ metrics }) {
  return (
    <div className="system-body-metric-grid">
      {metrics.map((metric) => (
        <article
          className={`system-body-metric${metric.priority ? " system-body-metric--priority" : ""}`}
          key={metric.label}
        >
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </article>
      ))}
    </div>
  );
}
