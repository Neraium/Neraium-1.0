import "../../styles/finding-classification.css";
import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";

function displayLabel(value, fallback = "Unavailable") {
  const clean = String(value ?? "").trim();
  if (!clean) return fallback;
  return clean.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function confidenceLabel(finding, presentation) {
  const explicit = String(finding?.confidence ?? "").trim();
  if (explicit) {
    const numeric = Number(explicit);
    if (Number.isFinite(numeric)) {
      const normalized = numeric > 1 ? numeric / 100 : numeric;
      return normalized >= 0.85 ? "High" : normalized >= 0.6 ? "Moderate" : "Low";
    }
    return displayLabel(explicit);
  }
  if (presentation.classificationConfidence !== "Unavailable") return presentation.classificationConfidence;
  return presentation.dataConfidence.rating;
}

function detailedConfidenceLabel(finding, presentation) {
  const label = confidenceLabel(finding, presentation);
  const rawScore = finding?.confidenceScore ?? finding?.confidence_score;
  const score = Number(rawScore);
  if (!Number.isFinite(score)) return label;
  const percent = Math.round(Math.max(0, Math.min(1, score > 1 ? score / 100 : score)) * 100);
  return `${label} · ${percent}%`;
}

function statusLabel(finding, presentation) {
  const explicit = finding?.reviewStatus ?? finding?.review_status ?? finding?.hypothesisStatus ?? finding?.status;
  if (explicit) return displayLabel(explicit);
  if (presentation.persistence.persistent) return presentation.persistence.label;
  return "Open";
}

function evidenceTrendPhrase(value) {
  return ({
    increasing: "Evidence support increasing",
    stable: "Evidence support stable",
    decreasing: "Evidence support decreasing",
    sudden: "Evidence increased suddenly",
    gradual: "Evidence building gradually",
    "stable shift": "Evidence stable",
    strengthening: "Evidence support increasing",
    weakening: "Evidence support decreasing",
    recovering: "Evidence recovering",
    recurring: "Evidence recurring",
    intermittent: "Evidence intermittent",
  })[String(value ?? "").trim().toLowerCase()] || `Evidence ${String(value ?? "").trim().toLowerCase()}`;
}

function supportTrendForFinding(finding) {
  const explicit = String(finding?.supportTrend ?? "").trim().toLowerCase();
  if (["increasing", "stable", "decreasing"].includes(explicit)) return explicit;
  if (String(finding?.trajectory?.scope ?? "").trim().toLowerCase() !== "evidence_support") return "";
  return ({ strengthening: "increasing", increasing: "increasing", stable: "stable", steady: "stable", weakening: "decreasing", decreasing: "decreasing" })[String(finding?.trajectory?.state ?? "").trim().toLowerCase()] ?? "";
}

function operatingContextLabel(dimension, fallback) {
  const status = dimension?.status ?? ({ high: "comparable", medium: "partially_comparable", low: "different_from_baseline", unknown: "not_enough_context" }[String(dimension?.level ?? "").toLowerCase()]);
  const legacyMatch = ({ strong: "comparable", partial: "partially_comparable", moderate: "partially_comparable", weak: "different_from_baseline", mismatch: "different_from_baseline", different: "different_from_baseline", unavailable: "not_enough_context" }[String(fallback ?? "").toLowerCase()]);
  return displayLabel(status ?? legacyMatch, fallback);
}

function CompactSummary({ finding, presentation, ariaLabel }) {
  const confidence = confidenceLabel(finding, presentation);
  const status = statusLabel(finding, presentation);
  const supportTrend = supportTrendForFinding(finding);
  const dimensions = finding?.confidenceDimensions ?? {};
  const corroborationStrength = displayLabel(
    finding?.corroboration?.corroboration_strength ?? finding?.corroborationStrength,
    "",
  );
  const relationshipCount = Number(finding?.corroboration?.relationship_count ?? finding?.relationshipCount ?? 0);
  return (
    <section
      className={`finding-classification finding-classification--${presentation.tone} finding-classification--compact`}
      aria-label={ariaLabel}
      data-classification={presentation.type}
      data-testid="finding-classification-summary"
    >
      <ul className="finding-classification__chips">
        <li className="finding-classification__chip finding-classification__chip--classification">
          <span className="sr-only">Classification: </span>{presentation.label}
        </li>
        {dimensions.changeDetection ? <li className="finding-classification__chip"><span className="sr-only">Change detection confidence: </span>Change {displayLabel(dimensions.changeDetection.level)}</li> : <li className="finding-classification__chip"><span className="sr-only">Confidence: </span>{confidence} confidence</li>}
        {supportTrend ? <li className="finding-classification__chip"><span className="sr-only">Support trend: </span>{evidenceTrendPhrase(supportTrend)}</li> : null}
        {corroborationStrength ? <li className="finding-classification__chip"><span className="sr-only">Corroboration: </span>{corroborationStrength}{relationshipCount ? ` · ${relationshipCount}` : ""}</li> : null}
        <li className="finding-classification__chip">
          <span className="sr-only">Status: </span>{status}
        </li>
      </ul>
    </section>
  );
}

export default function FindingClassificationSummary({ finding, presentation: suppliedPresentation = null, compact = false, showDefinition = true }) {
  const presentation = suppliedPresentation ?? normalizeFindingPresentation(finding);
  const dimensions = finding?.confidenceDimensions ?? {};
  const supportTrend = supportTrendForFinding(finding);
  const ariaLabel = [
    `Classification: ${presentation.label}`,
    dimensions.changeDetection ? `Change detection confidence: ${displayLabel(dimensions.changeDetection.level)}` : `Classification confidence: ${presentation.classificationConfidence}`,
    `Data confidence: ${presentation.dataConfidence.rating}`,
    `Operating context: ${operatingContextLabel(dimensions.operatingContext, presentation.operatingMode.match)}`,
    `Persistence: ${presentation.persistence.label}`,
    `Review priority: ${presentation.reviewPriority}`,
  ].join(". ");

  if (compact) return <CompactSummary finding={finding} presentation={presentation} ariaLabel={ariaLabel} />;

  return (
    <section
      className={`finding-classification finding-classification--${presentation.tone}`}
      aria-label={ariaLabel}
      data-classification={presentation.type}
      data-testid="finding-classification-summary"
    >
      <div className="finding-classification__identity">
        <span>Classification</span>
        <strong>{presentation.label}</strong>
        <p className="finding-classification__explanation">{presentation.meaning}</p>
      </div>
      <dl className="finding-classification__facts">
        {dimensions.changeDetection ? <div><dt>Change confidence</dt><dd>{displayLabel(dimensions.changeDetection.level)}</dd></div> : <div><dt>Evidence confidence</dt><dd>{detailedConfidenceLabel(finding, presentation)}</dd></div>}
        <div><dt>Evidence quality</dt><dd>{displayLabel(dimensions.evidenceQuality?.level, presentation.dataConfidence.rating)}</dd></div>
        <div><dt>Operating context</dt><dd>{operatingContextLabel(dimensions.operatingContext, presentation.operatingMode.match)}</dd></div>
        <div><dt>Persistence</dt><dd>{presentation.persistence.label}</dd></div>
        <div><dt>Operational state</dt><dd>{displayLabel(finding?.status)}</dd></div>
        {supportTrend ? <div><dt>Support trend</dt><dd>{displayLabel(supportTrend)}</dd></div> : null}
        {finding?.corroboration?.corroboration_strength ? <div><dt>Corroboration</dt><dd>{displayLabel(finding.corroboration.corroboration_strength)} · {finding.corroboration.relationship_count ?? 0} relationships</dd></div> : null}
        {finding?.reviewStatus || finding?.review_status || finding?.hypothesisStatus ? <div><dt>Review state</dt><dd>{statusLabel(finding, presentation)}</dd></div> : null}
        <div><dt>Priority</dt><dd>{presentation.reviewPriority}</dd></div>
      </dl>
      {showDefinition ? (
        <details className="finding-classification__meaning">
          <summary>What this means</summary>
          <p>{presentation.meaning}</p>
        </details>
      ) : null}
    </section>
  );
}
