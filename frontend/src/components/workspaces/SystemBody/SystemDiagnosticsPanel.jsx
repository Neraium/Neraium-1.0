import SectionCard from "../../layout/SectionCard";

export default function SystemDiagnosticsPanel({ metrics, uiState }) {
  const visibleMetrics = (metrics ?? []).filter((metric) => hasOperatorValue(metric?.value));
  if (visibleMetrics.length === 0) {
    return null;
  }

  return (
    <details className={`system-body-diagnostics ui-state-surface ui-state-surface--${uiState}`}>
      <summary>
        <span className="section-label">Technical Diagnostics</span>
        <strong>Engineer-facing metrics</strong>
      </summary>
      <div className="system-body-diagnostics__grid">
        {visibleMetrics.map((metric) => (
          <SectionCard className="system-body-diagnostics__metric" key={metric.label}>
            <span className="section-label">{metric.label}</span>
            <p>{metric.value}</p>
          </SectionCard>
        ))}
      </div>
    </details>
  );
}

function hasOperatorValue(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  return Boolean(normalized && normalized !== "none" && normalized !== "n/a" && normalized !== "na");
}
