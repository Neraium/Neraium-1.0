export default function SystemNarrativePanel({ summaryKicker, summaryTitle, summaryText }) {
  return (
    <article className="system-body-summary-card">
      <p className="system-body-summary-card__kicker">{summaryKicker}</p>
      <h2>{summaryTitle}</h2>
      <p>{summaryText}</p>
    </article>
  );
}
