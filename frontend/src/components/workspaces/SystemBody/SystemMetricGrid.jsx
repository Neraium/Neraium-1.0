import MetricGrid from "../../layout/MetricGrid";
import SectionCard from "../../layout/SectionCard";

export default function SystemMetricGrid({ metrics }) {
  return (
    <MetricGrid className="system-body-metric-grid">
      {metrics.map((metric) => (
        <SectionCard
          className={`system-body-metric${metric.priority ? " system-body-metric--priority" : ""}`}
          key={metric.label}
        >
          <span className="section-label">{metric.label}</span>
          <strong className={`metric-value${metric.priority ? " metric-value--priority" : ""}`}>{metric.value}</strong>
        </SectionCard>
      ))}
    </MetricGrid>
  );
}
