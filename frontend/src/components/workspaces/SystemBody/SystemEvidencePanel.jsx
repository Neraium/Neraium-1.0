import SectionCard from "../../layout/SectionCard";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

export default function SystemEvidencePanel({ evidenceItems, timelineItems, uiState }) {
  const visibleEvidence = evidenceItems.filter((item) => hasOperatorValue(item.value)).slice(0, 3);
  const visibleTimeline = timelineItems.filter((item) => hasOperatorValue(item.value)).slice(0, 4);

  return (
    <section className="system-body-evidence-block" aria-label="Evidence and progression">
      {visibleEvidence.length > 0 ? (
        <SectionCard className={`system-body-evidence-card system-body-evidence-card--drivers ui-state-surface ui-state-surface--${uiState}`}>
          <span className="section-label">Primary Changes</span>
          <div className="system-body-driver-list">
            {visibleEvidence.map((item) => (
              <article className={`system-body-driver ui-state-indicator ui-state-indicator--${item.state ?? uiState}`} key={item.label}>
                <span>{item.label}</span>
                <p>{item.value}</p>
              </article>
            ))}
          </div>
        </SectionCard>
      ) : null}

      {uiState === "neutral" ? (
        <SectionCard className={`system-body-timeline-card ui-state-surface ui-state-surface--${uiState}`}>
          <span className="section-label">Structural Progression</span>
          <div className="empty-state compact">
            <strong>{EMPTY_VALUE}</strong>
            <p>{EMPTY_VALUE}</p>
          </div>
        </SectionCard>
      ) : visibleTimeline.length > 0 ? (
        <SectionCard className={`system-body-timeline-card ui-state-surface ui-state-surface--${uiState}`}>
          <span className="section-label">Structural Progression</span>
          <ul className="system-body-timeline-list">
            {visibleTimeline.map((item, index) => (
              <li className={`ui-state-indicator ui-state-indicator--${item.state ?? uiState}`} key={item.label}>
                <span className="metadata-text">Phase {index + 1}</span>
                <em className="system-body-timeline-list__annotation">{timelineAnnotation(item.label, index)}</em>
                <p>{item.label}</p>
                <strong>{item.value}</strong>
              </li>
            ))}
          </ul>
        </SectionCard>
      ) : null}
    </section>
  );
}

function hasOperatorValue(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  return Boolean(normalized && normalized !== "none" && normalized !== "n/a" && normalized !== "na");
}

function timelineAnnotation(label, index) {
  const text = String(label ?? "").toLowerCase();
  if (text.includes("initial") || text.includes("began")) return "Initial signal";
  if (text.includes("persistence")) return "Persistence checkpoint";
  if (text.includes("divergence")) return "Divergence trend";
  if (text.includes("escalation") || text.includes("pressure")) return "Escalation marker";
  return `Progression marker ${index + 1}`;
}
