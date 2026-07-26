import { normalizeFindingPresentation } from "./operatorFinding";
import { isResolvedReviewState, isSuppressedReviewState, reviewRecordFor } from "./findingReviewState";

function asArray(value) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

function firstText(...values) {
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) return text;
  }
  return "";
}

function analysisSource(result = {}) {
  return result.analysis_explanation ?? result.analysis_result ?? result.analysis ?? {};
}

function rawFindingFor(finding, result = {}) {
  const source = analysisSource(result);
  const candidates = [
    ...asArray(source.conditions ?? result.conditions),
    ...asArray(source.insights ?? result.findings),
  ];
  const identities = new Set([finding?.id, ...asArray(finding?.mergedFindingIds)].map((value) => String(value ?? "")));
  return candidates.find((item) => identities.has(String(item?.id ?? item?.finding_id ?? ""))) ?? {};
}

function coverageRatio(result = {}) {
  const raw = result?.data_quality?.coverage_percent
    ?? result?.data_quality?.coverage
    ?? result?.evidence_coverage
    ?? result?.coverage;
  const numeric = Number(raw);
  if (!Number.isFinite(numeric)) return null;
  return numeric > 1 ? Math.min(1, numeric / 100) : Math.max(0, Math.min(1, numeric));
}

function explicitPositive(value, words) {
  if (value === true) return true;
  const normalized = String(value ?? "").trim().toLowerCase();
  if (/^(false|no|not|unmatched|weak|low)\b/.test(normalized)) return false;
  return words.some((word) => normalized === word || normalized.includes(word));
}

function strengtheningEvidence(raw = {}) {
  return explicitPositive(
    raw.strengthening
      ?? raw.is_strengthening
      ?? raw.severity_trajectory
      ?? raw.magnitude_trajectory
      ?? raw.spread_trajectory
      ?? raw.evidence_trajectory
      ?? raw.trajectory?.state,
    ["strengthening", "escalating", "increasing", "growing", "spreading"],
  );
}

function confidenceRank(finding, presentation) {
  const label = [presentation.classificationConfidence, presentation.dataConfidence.rating, finding?.tier]
    .map((value) => String(value ?? "").toLowerCase())
    .filter((value) => value && value !== "unavailable")
    .join(" ");
  if (/high|confirmed|qualified|strong/.test(label)) return 0;
  if (/moderate|narrowed|partial/.test(label)) return 1;
  if (/low|deferred|withheld|weak/.test(label)) return 3;
  return 2;
}

function classificationRank(presentation) {
  if (presentation.legacy) return 4;
  return {
    unexplained_systemic_change: 0,
    possible_instrumentation_issue: 1,
    known_operational_change: 2,
    insufficient_evidence: 3,
  }[presentation.type] ?? 4;
}

function findingTimestamp(finding, model) {
  return firstText(
    finding?.firstDetectedAt,
    finding?.generatedAt,
    model?.result?.completed_at,
    model?.result?.processed_at,
    model?.result?.generated_at,
    analysisSource(model?.result).generated_at,
  );
}

function recentlyResolved(value, now, days = 7) {
  if (!value) return true;
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return true;
  return now.getTime() - timestamp.getTime() <= days * 24 * 60 * 60 * 1000;
}

function happenedToday(value, now) {
  if (!value) return false;
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return false;
  return timestamp.getUTCFullYear() === now.getUTCFullYear()
    && timestamp.getUTCMonth() === now.getUTCMonth()
    && timestamp.getUTCDate() === now.getUTCDate();
}

function priorityMetadata(finding, model, records, now) {
  const raw = rawFindingFor(finding, model.result);
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const review = reviewRecordFor(finding, records);
  const isNew = review.state === "new" && happenedToday(findingTimestamp(finding, model), now);
  const persistent = presentation.persistence.persistent;
  const strengthening = strengtheningEvidence(raw);
  const critical = explicitPositive(raw.critical_asset ?? raw.asset_criticality ?? raw.criticality, ["critical", "high"]);
  const corroborated = asArray(finding.relationships).length >= 2
    || Number(raw.relationship_count ?? raw.corroboration?.relationship_count ?? raw.supporting_relationship_count ?? 0) >= 2;
  return {
    raw,
    presentation,
    review,
    isNew,
    persistent,
    strengthening,
    critical,
    corroborated,
    order: [
      isNew ? 0 : 1,
      classificationRank(presentation),
      strengthening ? 0 : 1,
      persistent ? 0 : 1,
      confidenceRank(finding, presentation),
      critical ? 0 : 1,
      corroborated ? 0 : 1,
    ],
  };
}

function comparePriority(left, right) {
  for (let index = 0; index < left.meta.order.length; index += 1) {
    const difference = left.meta.order[index] - right.meta.order[index];
    if (difference) return difference;
  }
  return left.index - right.index;
}

function rankingExplanation(meta) {
  const descriptors = [];
  if (meta.isNew) descriptors.push("new and unreviewed");
  if (meta.persistent) descriptors.push("persistent");
  if (meta.strengthening) descriptors.push("strengthening");
  if (meta.presentation.classificationConfidence === "High" || meta.presentation.dataConfidence.rating === "High" || ["Confirmed", "Qualified"].includes(meta.findingTier)) descriptors.push("high-confidence");
  if (!descriptors.length && meta.presentation.legacy) return "Historical finding without contextual classification; ordered conservatively.";
  if (!descriptors.length) return "Unresolved finding with available supporting evidence.";
  let explanation = `${descriptors.slice(0, 3).join(", ")} change`;
  if (meta.critical) explanation += " affecting a critical system";
  else if (meta.corroborated) explanation += " supported by related relationships";
  return `${explanation}.`.replace(/^./, (letter) => letter.toUpperCase());
}

export function deriveEscalationReadiness(finding, result = {}) {
  const raw = rawFindingFor(finding, result);
  const governedEscalation = raw?.escalation ?? finding?.escalation;
  const governedRelationshipCount = Number(
    raw?.relationship_count
      ?? raw?.corroboration?.relationship_count
      ?? finding?.corroboration?.relationship_count
      ?? asArray(finding?.relationships).length,
  );
  if (governedEscalation?.rule_version) {
    const inputs = governedEscalation.inputs ?? {};
    return {
      unexplainedSystemicChange: inputs.classification === "unexplained_systemic_change",
      modeMatchStrong: inputs.operating_mode_match === "strong",
      dataConfidenceGood: ["high", "moderate"].includes(inputs.data_quality),
      persistentChange: Number(finding?.trajectory?.persistence ?? raw?.trajectory?.persistence ?? 0) >= 0.6,
      multipleSupportingRelationships: governedRelationshipCount >= 2,
      criticalAsset: ["critical", "high"].includes(inputs.criticality),
      noKnownOperationalExplanation: inputs.classification === "unexplained_systemic_change",
      strengthening: ["Strengthening", "Sudden", "Recurring"].includes(inputs.trajectory),
      serious: governedEscalation.prompt_engineering_review === true,
      eligible: governedEscalation.eligible === true,
      level: governedEscalation.level,
    };
  }
  const presentation = finding?.classificationPresentation ?? normalizeFindingPresentation(finding);
  const unexplainedSystemicChange = !presentation.legacy && presentation.type === "unexplained_systemic_change";
  const modeMatchStrong = explicitPositive(
    raw.strong_mode_match ?? raw.mode_match_strength ?? raw.mode_match ?? raw.operating_mode_match ?? finding?.operatingMode?.match,
    ["strong", "confirmed", "matched"],
  );
  const coverage = coverageRatio(result);
  const dataConfidenceGood = ["Confirmed", "Qualified"].includes(String(finding?.tier ?? ""))
    && coverage !== null
    && coverage >= 0.8;
  const persistentChange = explicitPositive(
    raw.persistent_change ?? raw.persistence_confirmed ?? raw.is_persistent ?? raw.persistence ?? finding?.persistence?.persistent,
    ["persistent", "confirmed", "sustained"],
  ) || Number(raw.persistence_windows ?? raw.changed_windows ?? 0) >= 2;
  const multipleSupportingRelationships = asArray(finding?.relationships).length >= 2
    || Number(raw.relationship_count ?? raw.corroboration?.relationship_count ?? raw.supporting_relationship_count ?? 0) >= 2;
  const criticalAsset = explicitPositive(
    raw.critical_asset ?? raw.asset_criticality ?? raw.criticality,
    ["critical", "high"],
  );
  const explanationValue = raw.known_operational_explanation
    ?? raw.operational_explanation_known
    ?? raw.explained_by_operations;
  const noKnownOperationalExplanation = explanationValue === false
    || String(explanationValue ?? "").trim().toLowerCase() === "none";
  const criteria = {
    unexplainedSystemicChange,
    modeMatchStrong,
    dataConfidenceGood,
    persistentChange,
    multipleSupportingRelationships,
    criticalAsset,
    noKnownOperationalExplanation,
  };
  return { ...criteria, strengthening: strengtheningEvidence(raw), serious: Object.values(criteria).every(Boolean) };
}

export function deriveWorkspacePresentationState(model = {}) {
  const result = model.result ?? {};
  if (model.processing) return { key: "analysisRunning", status: "Analysis Running", headline: "Learning normal behavior", body: "Neraium is building the baseline and comparing relationships.", action: "View Analysis Progress" };
  if (!model.hasAnalysis) return { key: "noDataset", status: "Baseline Needed", headline: "No baseline available", body: "Import a historical dataset so Neraium can learn how your system normally behaves.", action: "Import Historical Dataset" };
  const source = analysisSource(result);
  const hasAnalysisOutput = Boolean(result.sii_completed === true || asArray(source.conditions).length || asArray(source.insights).length || asArray(source.relationships).length || asArray(source.systems).length || result.baseline_analysis);
  const legacy = result.legacy_analysis === true || result.is_legacy === true || /legacy/i.test(firstText(result.analysis_version, result.schema_version));
  if (legacy) return { key: "legacyAnalysis", status: "Legacy Analysis", headline: "Earlier analysis available", body: "Review the saved evidence or import current data for a new comparison.", action: "Review Saved Evidence" };
  if (!hasAnalysisOutput) return { key: "datasetReady", status: "Dataset Ready", headline: "Ready to learn normal behavior", body: "The historical dataset is ready for baseline analysis.", action: "Start Baseline Analysis" };
  if (model.status === "Evidence insufficient") return { key: "insufficientEvidence", status: "Insufficient Evidence", headline: "More evidence is needed", body: "Analysis completed, but the available data does not support a reliable finding.", action: "Review Evidence" };
  if (model.status === "Normal") return { key: "noMeaningfulChanges", status: "Monitoring", headline: "No meaningful changes", body: "Measured relationships remain within the learned baseline.", action: "View Monitoring" };
  return { key: "analysisComplete", status: "Analysis Complete", headline: "Findings ready for review", body: "Review the highest-priority unexplained change first.", action: "Review Findings" };
}

export function buildOperationsBrief(model = {}, reviewRecords = {}, now = new Date()) {
  const ranked = asArray(model.findings).map((finding, index) => {
    const meta = priorityMetadata(finding, model, reviewRecords, now);
    return { finding, index, meta: { ...meta, findingTier: finding.tier } };
  }).sort(comparePriority);
  const active = ranked.filter(({ meta }) => !isResolvedReviewState(meta.review) && !isSuppressedReviewState(meta.review));
  const newFindings = active.filter(({ meta }) => meta.isNew && meta.presentation.type !== "known_operational_change").map(({ finding }) => finding);
  const newIds = new Set(newFindings.map((finding) => finding.id));
  const monitoringFindings = active.filter(({ meta }) => !meta.strengthening && (meta.review.state === "investigating" || meta.review.state === "monitoring" || meta.presentation.type === "known_operational_change")).map(({ finding }) => finding);
  const monitoringIds = new Set(monitoringFindings.map((finding) => finding.id));
  const needsAttention = active.filter(({ finding, meta }) => !newIds.has(finding.id) && !monitoringIds.has(finding.id) && meta.review.state !== "closed").map(({ finding }) => finding);
  const resolvedFromReview = ranked.filter(({ meta }) => isResolvedReviewState(meta.review) && recentlyResolved(meta.review.reviewedAt, now)).map(({ finding, meta }) => ({ id: finding.id, title: finding.title, system: finding.system, status: "Explained", reviewedAt: meta.review.reviewedAt }));
  const resolvedFromPayload = asArray(model.result?.resolved_items ?? model.result?.resolved_findings).map((item, index) => typeof item === "string"
    ? { id: `resolved-${index}`, title: item, system: "", status: "Resolved", reviewedAt: "" }
    : { id: item.id ?? `resolved-${index}`, title: firstText(item.title, item.summary, "Resolved finding"), system: firstText(item.system, item.asset), status: "Resolved", reviewedAt: firstText(item.resolved_at, item.updated_at) }).filter((item) => recentlyResolved(item.reviewedAt, now));
  const escalations = active.filter(({ finding }) => deriveEscalationReadiness(finding, model.result).serious).map(({ finding }) => finding);
  const priorityFinding = newFindings[0] ?? needsAttention[0] ?? monitoringFindings[0] ?? null;
  const priorityMeta = priorityFinding ? ranked.find(({ finding }) => finding.id === priorityFinding.id)?.meta : null;
  return {
    newFindings,
    needsAttention,
    monitoringFindings,
    monitoringIssues: asArray(model.gaps),
    recentlyResolved: [...resolvedFromReview, ...resolvedFromPayload].slice(0, 5),
    escalations,
    priorityFinding,
    priorityExplanation: priorityMeta ? rankingExplanation(priorityMeta) : "",
  };
}
