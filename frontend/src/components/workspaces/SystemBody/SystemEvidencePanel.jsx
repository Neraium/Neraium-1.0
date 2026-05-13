export default function SystemEvidencePanel({ evidenceItems }) {
  return (
    <div className="system-body-evidence-grid">
      {evidenceItems.map((item) => (
        <article key={item.label}>
          <span>{item.label}</span>
          <p>{item.value}</p>
        </article>
      ))}
    </div>
  );
}
