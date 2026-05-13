import SectionCard from "../../layout/SectionCard";

export default function SystemNarrativePanel({ summaryKicker, summaryTitle, summaryText }) {
  return (
    <SectionCard className="system-body-summary-card">
      <p className="system-body-summary-card__kicker section-label">{summaryKicker}</p>
      <h2 className="panel-title">{summaryTitle}</h2>
      <p className="narrative-text">{summaryText}</p>
    </SectionCard>
  );
}
