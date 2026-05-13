import SectionCard from "../../layout/SectionCard";

export default function SystemNarrativePanel({ summaryKicker, summaryTitle, summaryText }) {
  return (
    <SectionCard className="system-body-summary-card">
      <p className="system-body-summary-card__kicker">{summaryKicker}</p>
      <h2>{summaryTitle}</h2>
      <p>{summaryText}</p>
    </SectionCard>
  );
}
