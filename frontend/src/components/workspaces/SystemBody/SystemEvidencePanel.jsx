import SectionCard from "../../layout/SectionCard";

export default function SystemEvidencePanel({ evidenceItems, timelineItems, uiState }) {
  const visibleEvidence = evidenceItems.filter((item) => hasOperatorValue(item.value)).slice(0, 3);
  const visibleTimeline = timelineItems.filter((item) => hasOperatorValue(item.value)).slice(0, 4);

  return (
    <section className="system-body-evidence-block" aria-label="Evidence and progression">
      {visibleEvidence.length > 0 ? (
        <SectionCard className={`system-body-evidence-card system-body-evidence-card--drivers ui-state-surface ui-state-surface--${uiState}`}>
          <span className="section-label">Structural Drivers</span>
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

      {visibleTimeline.length > 0 ? (
        <SectionCard className={`system-body-timeline-card ui-state-surface ui-state-surface--${uiState}`}>
          <span className="section-label">System Progression</span>
          <ul className="system-body-timeline-list">
            {visibleTimeline.map((item) => (
              <li className={`ui-state-indicator ui-state-indicator--${item.state ?? uiState}`} key={item.label}>
                <span className="metadata-text">{item.label}</span>
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
