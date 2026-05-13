import SectionCard from "../../layout/SectionCard";

export default function SystemNarrativePanel({ summaryKicker, summaryTitle, items }) {
  return (
    <SectionCard className="system-body-summary-card system-body-summary-card--primary">
      <p className="system-body-summary-card__kicker section-label">{summaryKicker}</p>
      <h2 className="panel-title">{summaryTitle}</h2>
      <div className="system-body-narrative-grid">
        {items.map((item) => (
          <article className="system-body-narrative-item" key={item.label}>
            <span className="section-label">{item.label}</span>
            <p className="narrative-text">{item.value}</p>
          </article>
        ))}
      </div>
    </SectionCard>
  );
}
