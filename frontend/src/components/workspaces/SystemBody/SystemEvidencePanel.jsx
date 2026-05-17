import SectionCard from "../../layout/SectionCard";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

export default function SystemEvidencePanel({ evidenceItems, timelineItems, uiState }) {
  const visibleEvidence = evidenceItems.filter((item) => hasOperatorValue(item.value)).slice(0, 3);
  const visibleTimeline = timelineItems.filter((item) => hasOperatorValue(item.value)).slice(0, 4);

  return (
    <section className="system-body-evidence-block" aria-label="Evidence and progression">
      {visibleEvidence.length > 0 ? (
        <SectionCard className={`system-body-evidence-card system-body-evidence-card--drivers ui-state-surface ui-state-surface--${uiState}`}>
          <span className="section-label">Observed Operational Pattern</span>
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
            {visibleTimeline.map((item) => (
              <li className={`ui-state-indicator ui-state-indicator--${item.state ?? uiState}`} key={item.label}>
                <span className="metadata-text">{item.label}</span>
                <em className="system-body-timeline-list__annotation">Evidence checkpoint</em>
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
