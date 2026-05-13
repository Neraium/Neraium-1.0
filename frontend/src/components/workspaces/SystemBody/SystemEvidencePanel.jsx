import SectionCard from "../../layout/SectionCard";

export default function SystemEvidencePanel({ evidenceItems }) {
  return (
    <div className="system-body-evidence-grid">
      {evidenceItems.map((item) => (
        <SectionCard key={item.label}>
          <span>{item.label}</span>
          <p>{item.value}</p>
        </SectionCard>
      ))}
    </div>
  );
}
