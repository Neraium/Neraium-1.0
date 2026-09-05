import React from "react";

const insufficient = "Consequence not quantifiable from available evidence.";
const resources = {
  water: ["Water use", "gal"], electricity: ["Electricity use", "kWh"], steam: ["Steam use", "lb"],
  chemical: ["Chemical feed", "gal"], compressed_air: ["Compressed air use", "scf"],
};
const directions = { above_expected: "above expected", below_expected: "below expected", aligned: "aligned with expected" };
const array = (value) => Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
const amount = (value) => new Intl.NumberFormat("en-US", { maximumSignificantDigits: 8 }).format(value);
function timestamp(value) {
  if (value === null || value === undefined || value === "") return "Not supplied";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? "Not supplied" : date.toISOString();
}

export default function MeasurableConsequence({ result }) {
  const resource = resources[result?.resource_type];
  const direction = directions[result?.direction];
  const value = result?.cumulative_amount;
  const duration = result?.duration_seconds;
  const supported = result?.status === "quantified" && resource && direction
    && result.cumulative_unit === resource[1]
    && typeof value === "number" && Number.isFinite(value)
    && typeof duration === "number" && Number.isFinite(duration) && duration > 0
    && ((value > 0 && result.direction === "above_expected")
      || (value < 0 && result.direction === "below_expected")
      || (value === 0 && result.direction === "aligned"));
  const limitations = array(result?.limitations);
  const support = typeof result?.support_level === "string" && result.support_level.trim()
    ? result.support_level.charAt(0).toUpperCase() + result.support_level.slice(1) : "Not supplied";
  return (
    <section className="measurable-consequence" aria-label="Measurable consequence">
      <h2>Measurable consequence</h2>
      {supported ? <>
        <p className="measurable-consequence__label">{resource[0]} {direction}</p>
        <strong className="measurable-consequence__amount">{amount(value)} {result.cumulative_unit}</strong>
        <dl className="measurable-consequence__summary">
          <div><dt>Observed across</dt><dd>{(duration / 3600).toFixed(1)} hours</dd></div>
          <div><dt>Evidence support</dt><dd>{support}</dd></div>
        </dl>
      </> : <p>{insufficient}</p>}
      {result && (supported || limitations.length > 0) ? <details>
        <summary>Technical evidence</summary>
        <dl className="measurable-consequence__technical">
          {supported ? <div><dt>Calculation window (UTC)</dt><dd>{timestamp(result.start_timestamp)} → {timestamp(result.end_timestamp)}</dd></div> : null}
          <div><dt>Relationship IDs</dt><dd>{array(result.source_relationship_ids).join(" / ") || "Not supplied"}</dd></div>
          <div><dt>Source signals</dt><dd>{array(result.source_tag_ids).join(" / ") || "Not supplied"}</dd></div>
          <div><dt>Skipped intervals</dt><dd>{Number.isInteger(result.skipped_interval_count) && result.skipped_interval_count >= 0 ? result.skipped_interval_count : "Not supplied"}</dd></div>
          {supported ? <div><dt>Contributing duration</dt><dd>{amount(duration)} seconds; excluded intervals are not counted.</dd></div> : null}
          <div><dt>Methodology</dt><dd>{result.methodology || "Not supplied"}{result.methodology_version ? ` · ${result.methodology_version}` : ""}</dd></div>
          <div><dt>Limitations</dt><dd>{limitations.length ? <ul>{limitations.map((item, index) => <li key={index}>{item}</li>)}</ul> : "None recorded"}</dd></div>
        </dl>
      </details> : null}
    </section>
  );
}
