import { memo, useState } from "react";

function strength(value) {
  return Number.isFinite(value) ? value.toFixed(2) : "Not measured";
}

function RelationshipExplorer({ relationships }) {
  const [selected, setSelected] = useState(0);
  const active = relationships[selected];
  if (!relationships.length) return <p>No mapped relationship evidence is available for this insight.</p>;
  return <div className="relationship-explorer">
    <div className="relationship-explorer__list" role="list" aria-label="Affected relationships">
      {relationships.map((relationship, index) => <button type="button" aria-pressed={selected === index} key={relationship.label} onClick={() => setSelected(index)}>{relationship.label}</button>)}
    </div>
    <section className="relationship-explorer__detail" aria-live="polite">
      <h5>{active.label}</h5>
      <div className="relationship-strengths"><span>Historical strength <strong>{strength(active.measurement.baseline)}</strong></span><span>Current strength <strong>{strength(active.measurement.current)}</strong></span></div>
      <p>Compare the historical and current strengths to validate the relationship change.</p>
    </section>
  </div>;
}

export default memo(RelationshipExplorer);
