import React from "react";

export default function ObservationInterpretationBlock({ observation, interpretation, conclusion, limitations = [] }) {
  return (
    <div className="reasoning-separation" aria-label="Observation, interpretation, conclusion, and limitations">
      <section><span className="reasoning-label reasoning-label--measured">Observation</span><p>{observation || "No supported observation is available."}</p></section>
      <section><span className="reasoning-label reasoning-label--inferred">Interpretation</span><p>{interpretation || "Neraium is withholding interpretation until mapped evidence is available."}</p></section>
      <section><span className="reasoning-label reasoning-label--conclusion">Conclusion</span><p>{conclusion || "No bounded operational conclusion is available."}</p></section>
      <section><span className="reasoning-label reasoning-label--limit">Limitations</span>{limitations.length ? <ul>{limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No material limitation was supplied with this result.</p>}</section>
    </div>
  );
}
