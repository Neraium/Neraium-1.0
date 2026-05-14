import MetricGrid from "../../layout/MetricGrid";
import SectionCard from "../../layout/SectionCard";

function toneForMetric(metric) {
  if (metric.state) {
    return metric.state;
  }

  const label = String(metric.label ?? "").toLowerCase();
  const value = String(metric.value ?? "").toLowerCase();
  const content = `${label} ${value}`;

  if (metric.priority || label.includes("severity")) {
    if (content.includes("stable") || content.includes("nominal")) {
      return "stable";
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
    return "stable";
  }

  if (content.includes("inspect") || content.includes("hours") || content.includes("urgent")) {
    return "watch";
  }
  if (content.includes("stable") || content.includes("weeks") || content.includes("overview")) {
    return "stable";
  }
  return "neutral";
}

export default function SystemMetricGrid({ metrics }) {
  return (
    <MetricGrid className="system-body-metric-grid">
      {metrics.map((metric) => {
        const state = toneForMetric(metric);

        return (
          <SectionCard
            className={`system-body-metric system-body-metric--${state} ui-state-surface ui-state-surface--${state}${metric.priority ? " system-body-metric--priority" : ""}`}
            key={metric.label}
          >
            <span className="section-label">{metric.label}</span>
            <strong className={`metric-value${metric.priority ? " metric-value--priority" : ""}`}>{metric.value}</strong>
          </SectionCard>
        );
      })}
    </MetricGrid>
  );
}
