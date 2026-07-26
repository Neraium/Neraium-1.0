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

function CompactSummary({ finding, presentation, ariaLabel }) {
  const confidence = confidenceLabel(finding, presentation);
  const status = statusLabel(finding, presentation);
  const trajectory = displayLabel(finding?.trajectory?.state, "");
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
        <li className="finding-classification__chip">
          <span className="sr-only">Confidence: </span>{confidence} confidence
        </li>
        {trajectory ? <li className="finding-classification__chip"><span className="sr-only">Trajectory: </span>{trajectory}</li> : null}
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
  const ariaLabel = [
    `Classification: ${presentation.label}`,
    `Classification confidence: ${presentation.classificationConfidence}`,
    `Data confidence: ${presentation.dataConfidence.rating}`,
    `Operating-mode match: ${presentation.operatingMode.match}`,
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
      </div>
      <dl className="finding-classification__facts">
        <div><dt>Confidence</dt><dd>{detailedConfidenceLabel(finding, presentation)}</dd></div>
        <div><dt>Data confidence</dt><dd>{presentation.dataConfidence.rating}</dd></div>
        <div><dt>Mode match</dt><dd>{presentation.operatingMode.match}</dd></div>
        <div><dt>Persistence</dt><dd>{presentation.persistence.label}</dd></div>
        <div><dt>Operational state</dt><dd>{displayLabel(finding?.status)}</dd></div>
        {finding?.trajectory?.state ? <div><dt>Trajectory</dt><dd>{displayLabel(finding.trajectory.state)}</dd></div> : null}
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
