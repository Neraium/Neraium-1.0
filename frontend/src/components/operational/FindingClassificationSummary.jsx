import "../../styles/finding-classification.css";
import { normalizeFindingPresentation } from "../../viewModels/operatorFinding";

export default function FindingClassificationSummary({ finding, compact = false }) {
  const presentation = normalizeFindingPresentation(finding);
  const ariaLabel = [
    `Classification: ${presentation.label}`,
    `Classification confidence: ${presentation.classificationConfidence}`,
    `Data confidence: ${presentation.dataConfidence.rating}`,
    `Operating-mode match: ${presentation.operatingMode.match}`,
    `Persistence: ${presentation.persistence.label}`,
    `Review priority: ${presentation.reviewPriority}`,
  ].join(". ");

  return (
    <section
      className={`finding-classification finding-classification--${presentation.tone}${compact ? " finding-classification--compact" : ""}`}
      aria-label={ariaLabel}
      data-classification={presentation.type}
      data-testid="finding-classification-summary"
    >
      <div className="finding-classification__identity">
        <span>Classification</span>
        <strong>{presentation.label}</strong>
        <small aria-label={`Classification confidence: ${presentation.classificationConfidence}`}>Classification confidence: {presentation.classificationConfidence}</small>
      </div>
      <dl className="finding-classification__facts">
        <div aria-label={`Data confidence: ${presentation.dataConfidence.rating}`}><dt>Data confidence</dt><dd>{presentation.dataConfidence.rating}</dd></div>
        <div><dt>Operating-mode match</dt><dd>{presentation.operatingMode.match}</dd></div>
        <div><dt>Persistence</dt><dd>{presentation.persistence.label}</dd></div>
        <div><dt>Review priority</dt><dd>{presentation.reviewPriority}</dd></div>
      </dl>
    </section>
  );
}
