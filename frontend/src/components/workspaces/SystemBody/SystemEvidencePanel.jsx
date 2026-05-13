import SectionCard from "../../layout/SectionCard";

export default function SystemEvidencePanel({ evidenceItems }) {
  return (
    <div className="system-body-evidence-grid">
      {evidenceItems.map((item) => (
        <SectionCard key={item.label}>
          <span className="section-label">{item.label}</span>
          <p className="narrative-text">{item.value}</p>
        </SectionCard>
      ))}
    </div>
  );
}
