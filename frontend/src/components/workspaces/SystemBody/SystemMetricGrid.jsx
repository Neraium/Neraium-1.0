import MetricGrid from "../../layout/MetricGrid";
import SectionCard from "../../layout/SectionCard";

function toneForMetric(metric) {
  const label = String(metric.label ?? "").toLowerCase();
  const value = String(metric.value ?? "").toLowerCase();
  const content = `${label} ${value}`;

  if (metric.priority || label.includes("severity")) {
    if (content.includes("stable") || content.includes("nominal")) {
      return "active";
    }
    if (
      content.includes("drift")
      || content.includes("review")
      || content.includes("separation")
      || content.includes("elevated")
      || content.includes("unstable")
    ) {
      return "warning";
    }
    return "active";
  }

  if (content.includes("inspect") || content.includes("hours") || content.includes("urgent")) {
    return "warning";
  }
  if (content.includes("stable") || content.includes("weeks") || content.includes("overview")) {
    return "active";
  }
  return "neutral";
}

export default function SystemMetricGrid({ metrics }) {
  return (
    <MetricGrid className="system-body-metric-grid">
      {metrics.map((metric) => (
        <SectionCard
          className={`system-body-metric system-body-metric--${toneForMetric(metric)}${metric.priority ? " system-body-metric--priority" : ""}`}
          key={metric.label}
        >
          <span className="section-label">{metric.label}</span>
          <strong className={`metric-value${metric.priority ? " metric-value--priority" : ""}`}>{metric.value}</strong>
        </SectionCard>
      ))}
    </MetricGrid>
  );
}
