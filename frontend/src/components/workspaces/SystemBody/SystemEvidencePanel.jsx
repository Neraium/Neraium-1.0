import SectionCard from "../../layout/SectionCard";

export default function SystemEvidencePanel({ evidenceItems, timelineItems }) {
  return (
    <section className="system-body-evidence-block">
      <div className="system-body-evidence-grid">
        {evidenceItems.map((item) => (
          <SectionCard key={item.label}>
            <span className="section-label">{item.label}</span>
            <p className="narrative-text">{item.value}</p>
          </SectionCard>
        ))}
      </div>
      <SectionCard className="system-body-timeline-card">
        <span className="section-label">Operational timeline</span>
        <ul className="system-body-timeline-list">
          {timelineItems.map((item) => (
            <li key={item.label}>
              <span className="metadata-text">{item.label}</span>
              <strong>{item.value}</strong>
            </li>
          ))}
        </ul>
      </SectionCard>
    </section>
  );
}
