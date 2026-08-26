const CONTRACT_VERSION = "results-presentation.v1";

export const RESULTS_KEYS = Object.freeze([
  "contractVersion", "depth", "variant", "outcome", "eyebrow", "headline", "explanation", "systemLabel", "counts", "cards",
]);
export const RESULT_CARD_KEYS = Object.freeze([
  "findingKey", "systemContext", "assetContext", "title", "behavior", "priority", "changeConfidence", "materialLimitation", "reviewState", "assignment", "primaryAction",
]);
export const SYSTEMS_KEYS = Object.freeze([
  "contractVersion", "depth", "variant", "header", "systems",
]);
export const SYSTEM_CARD_KEYS = Object.freeze([
  "systemKey", "name", "locationLabel", "status", "evidenceQuality", "findingsForReview", "primaryAction", "results",
]);
export const REVIEW_KEYS = Object.freeze([
  "contractVersion", "depth", "variant", "identity", "header", "whatChanged", "whyAttention", "assessment", "materialLimitation", "checks", "primaryAction",
]);
export const INVESTIGATION_KEYS = Object.freeze([
  "contractVersion", "depth", "variant", "identity", "header", "primaryComparison", "relationships", "relationshipMap", "systemEvidence", "persistence", "operatingContext", "dataQuality", "timeline", "sourceSignals", "lineageSummary", "projectionQualification", "primaryAction",
]);
export const EVIDENCE_KEYS = Object.freeze([
  "contractVersion", "depth", "variant", "identity", "header", "timestamps", "signals", "exactRelationships", "supportingEvidence", "channels", "classifications", "sufficiency", "limitations", "lineage", "engine", "package", "audit", "projectionQualification", "actions",
]);

const asArray = (value) => Array.isArray(value) ? value : [];
const isRecord = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const isPlainObject = (value) => {
  if (!isRecord(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};
const isObject = isPlainObject;
const hasOwn = (value, key) => isPlainObject(value) && Object.prototype.hasOwnProperty.call(value, key);
const own = (value, key) => hasOwn(value, key) ? value[key] : undefined;
const ownPath = (value, path) => path.split(".").reduce((current, key) => own(current, key), value);
const firstText = (...values) => {
  for (const value of values.flat()) {
    if (typeof value !== "string" && typeof value !== "number") continue;
    const text = String(value).replace(/\s+/g, " ").trim();
    if (text) return text;
  }
  return "";
};
const finite = (...values) => {
  for (const value of values.flat()) {
    if (value === null || value === undefined || value === "") continue;
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
};
const uniqueText = (values, limit = Infinity) => [...new Set(asArray(values).map((value) => firstText(value)).filter(Boolean))].slice(0, limit);
const bounded = (value, max = 180) => {
  const clean = firstText(value);
  if (!clean) return "";
  const oneSentence = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() || clean;
  if (oneSentence.length <= max) return oneSentence;
  return `${oneSentence.slice(0, max - 1).trimEnd()}…`;
};
const label = (value) => firstText(value).replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const route = (prefix, key) => `/${prefix}/${encodeURIComponent(key)}`;

function copyJsonSafe(value, seen = new WeakSet()) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (Array.isArray(value)) {
    if (seen.has(value)) return null;
    seen.add(value);
    const copy = value.map((item) => copyJsonSafe(item, seen));
    seen.delete(value);
    return copy;
  }
  if (!isPlainObject(value) || seen.has(value)) return null;
  seen.add(value);
  const copy = {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === "function" || typeof item === "symbol" || typeof item === "undefined") continue;
    copy[key] = copyJsonSafe(item, seen);
  }
  seen.delete(value);
  return copy;
}

function exactFinding(model, requestedFindingId) {
  if (!isObject(model) || !Array.isArray(own(model, "findings"))) return null;
  const requested = typeof requestedFindingId === "string" ? requestedFindingId.trim() : "";
  if (!requested) return null;
  return own(model, "findings").find((finding) => isObject(finding) && String(own(finding, "id") ?? "") === requested) ?? null;
}

function analysisSource(result) {
  return isObject(result?.analysis_explanation)
    ? result.analysis_explanation
    : isObject(result?.analysis_result)
      ? result.analysis_result
      : isObject(result?.analysis)
        ? result.analysis
        : {};
}

function rawFinding(model, finding) {
  const source = analysisSource(model?.result);
  const identities = new Set([finding?.id, finding?.sourceFindingKey, ...asArray(finding?.mergedFindingIds)].map(String));
  return [...asArray(source?.conditions ?? model?.result?.conditions), ...asArray(source?.insights ?? model?.result?.findings)]
    .find((item) => isObject(item) && identities.has(String(item.id ?? item.finding_id ?? item.finding_key ?? ""))) ?? null;
}

function unavailable(depth) {
  const config = {
    results: ["Result unavailable", "The result cannot be presented from the available analysis record.", null],
    review: ["Finding unavailable", "This finding is unavailable in the current analysis record.", { label: "Back to results", route: "/findings" }],
    investigation: ["Investigation unavailable", "Finding-scoped engineering evidence is unavailable.", { label: "Back to results", route: "/findings" }],
    evidence: ["Evidence record unavailable", "A finding-scoped evidence record is unavailable.", { label: "Back to results", route: "/findings" }],
  }[depth];
  return { contractVersion: CONTRACT_VERSION, depth, variant: "unavailable", title: config[0], explanation: config[1], backAction: config[2] };
}

function workflowState(reviewRecord) {
  const value = firstText(own(reviewRecord, "status"), own(reviewRecord, "state"));
  return value ? label(value) : "Not reviewed";
}

function assignmentLabel(reviewRecord) {
  const assignment = own(reviewRecord, "assignment");
  return firstText(own(assignment, "label"), own(assignment, "name"), own(reviewRecord, "assignedTo"), own(reviewRecord, "owner")) || "Unassigned";
}

function systemContext(finding, model) {
  return firstText(ownPath(finding, "location.system"), own(finding, "system"), ownPath(model, "site.name"), "Mapped system");
}

function cardFor(finding, model, reviewRecord = {}) {
  const key = String(own(finding, "id"));
  return {
    findingKey: key,
    systemContext: systemContext(finding, model),
    assetContext: firstText(ownPath(finding, "location.asset"), ownPath(finding, "location.subsystem")) || null,
    title: bounded(own(finding, "title"), 96) || "Behavioral change for review",
    behavior: bounded(own(finding, "observedChange"), 180) || "The available comparison supports a change in learned system behavior.",
    priority: firstText(own(reviewRecord, "priority"), own(reviewRecord, "recommendedPriority"), ownPath(finding, "classificationPresentation.reviewPriority"), "Not assigned"),
    changeConfidence: firstText(ownPath(finding, "confidenceDimensions.changeDetection.level"), ownPath(finding, "confidenceContract.change_detection.level"), own(finding, "tier"), "Unavailable"),
    materialLimitation: bounded(own(finding, "primaryLimitation"), 120) || null,
    reviewState: workflowState(reviewRecord),
    assignment: assignmentLabel(reviewRecord),
    primaryAction: { label: "Review finding", route: route("findings", key) },
  };
}

const normalizedState = (value) => firstText(value).toLowerCase().replace(/[\s-]+/g, "_");

function isInsufficientFinding(finding) {
  const status = normalizedState(own(finding, "status"));
  const tier = normalizedState(own(finding, "tier"));
  return status === "evidence_insufficient" || tier === "deferred" || tier === "withheld";
}

function isResolvedWorkflow(reviewRecord) {
  const state = normalizedState(firstText(own(reviewRecord, "status"), own(reviewRecord, "state")));
  return ["closed", "dismissed", "explained", "not_useful", "resolved"].includes(state);
}

function reviewRecordAt(records, findingKey) {
  return hasOwn(records, findingKey) && isPlainObject(records[findingKey]) ? records[findingKey] : {};
}

function reviewableFindings(findings, records) {
  return findings.filter((finding) => {
    if (!isPlainObject(finding) || !firstText(own(finding, "id")) || isInsufficientFinding(finding)) return false;
    return !isResolvedWorkflow(reviewRecordAt(records, String(own(finding, "id"))));
  });
}

function sourceBackedImprovement(model) {
  const finding = asArray(own(model, "findings"))[0];
  const candidates = [
    own(finding, "primaryLimitation"),
    ...asArray(own(finding, "limitations")),
    ...asArray(ownPath(model, "result.data_quality.warnings")),
    ...asArray(ownPath(model, "result.data_conditions")),
  ];
  const source = firstText(candidates.find((item) => /baseline|histor|comparab|coverage|sample|missing|insufficient/i.test(firstText(item))));
  if (!source) return null;
  if (/baseline|histor|comparab|sample/i.test(source)) return "More comparable operating history would improve the assessment.";
  return "More complete operating history would improve the assessment.";
}

export function projectResults(model, reviewRecords = {}, options = {}) {
  if (!isObject(model)) return unavailable("results");
  if (own(model, "processing") === true) {
    return { contractVersion: CONTRACT_VERSION, depth: "results", variant: "processing", headline: "Analysis in progress", explanation: "Neraium is evaluating the available operating history." };
  }
  if (own(model, "hasAnalysis") !== true) return unavailable("results");
  if (!Array.isArray(own(model, "findings"))) return unavailable("results");
  const sourceFindings = own(model, "findings");
  if (sourceFindings.some((finding) => !isPlainObject(finding) || !firstText(own(finding, "id")))) return unavailable("results");
  const records = isObject(reviewRecords) ? reviewRecords : {};
  const requestedAnalysisResultId = firstText(own(options, "analysisResultId"));
  const analysisResultId = requestedAnalysisResultId && requestedAnalysisResultId === firstText(ownPath(model, "result.result_id"))
    ? requestedAnalysisResultId
    : null;
  const findings = reviewableFindings(sourceFindings, records);
  const cards = findings.map((finding) => cardFor(finding, model, reviewRecordAt(records, String(own(finding, "id")))));
  const systemsRepresented = new Set(cards.map((card) => card.systemContext).filter(Boolean)).size;
  const status = firstText(own(model, "status"));
  if (status === "Normal" && sourceFindings.length > 0) return unavailable("results");
  if (status === "Evidence insufficient" && sourceFindings.some((finding) => !isInsufficientFinding(finding))) return unavailable("results");
  if (status === "Evidence insufficient") {
    const insufficientFindings = sourceFindings.filter(isInsufficientFinding);
    const scoped = insufficientFindings.length === 1 ? insufficientFindings[0] : null;
    const insufficientSystems = new Set(insufficientFindings.map((finding) => systemContext(finding, model)).filter(Boolean)).size;
    return {
      contractVersion: CONTRACT_VERSION,
      depth: "results",
      variant: "insufficient",
      outcome: "insufficient",
      eyebrow: "Operations Brief",
      headline: "Insufficient evidence",
      explanation: bounded(own(insufficientFindings[0], "primaryLimitation"), 180) || "The available evidence does not support a reliable behavioral-change conclusion.",
      systemLabel: firstText(ownPath(model, "site.name"), "Current system"),
      counts: { findingsForReview: 0, systemsRepresented: insufficientSystems },
      improvement: sourceBackedImprovement(model),
      auditAction: scoped
        ? { label: "Open evidence record", route: route("evidence", own(scoped, "id")), findingKey: String(own(scoped, "id")) }
        : analysisResultId
          ? { label: "Open investigation", route: route("investigations", analysisResultId), findingKey: analysisResultId, target: "investigation" }
          : null,
    };
  }
  const stable = status === "Normal";
  return {
    contractVersion: CONTRACT_VERSION,
    depth: "results",
    variant: "ready",
    outcome: stable ? "stable" : "analysis_complete",
    eyebrow: "Operations Brief",
    headline: stable ? "No supported material behavioral change." : "Analysis complete",
    explanation: stable
      ? "The available comparison remains within the learned system-behavior boundary."
      : cards.length
        ? `${cards.length} ${cards.length === 1 ? "finding deserves" : "findings deserve"} review.`
        : "No findings currently deserve review from this completed analysis.",
    systemLabel: firstText(ownPath(model, "site.name"), "Current system"),
    counts: { findingsForReview: cards.length, systemsRepresented },
    cards,
    ...(cards.length || !analysisResultId ? {} : {
      auditAction: { label: "Open investigation", route: route("investigations", analysisResultId), findingKey: analysisResultId, target: "investigation" },
    }),
  };
}

function scopedResultsForSystem(globalResults, system) {
  if (!isPlainObject(globalResults) || !isPlainObject(system)) return unavailable("results");
  if (["unavailable", "processing"].includes(globalResults.variant)) return copyJsonSafe(globalResults);
  const name = firstText(own(system, "name"), "Mapped system");
  const ownedIds = new Set(asArray(own(system, "findings")).filter(isPlainObject).map((finding) => firstText(own(finding, "id"))).filter(Boolean));
  if (globalResults.variant === "insufficient") {
    return {
      contractVersion: CONTRACT_VERSION,
      depth: "results",
      variant: "insufficient",
      outcome: "insufficient",
      eyebrow: "Operations Brief",
      headline: "Insufficient evidence",
      explanation: globalResults.explanation,
      systemLabel: name,
      counts: { findingsForReview: 0, systemsRepresented: asArray(own(system, "findings")).length ? 1 : 0 },
      improvement: globalResults.improvement,
      auditAction: asArray(own(system, "findings")).filter(isInsufficientFinding).length === 1
        ? {
          label: "Open evidence record",
          route: route("evidence", own(asArray(own(system, "findings")).filter(isInsufficientFinding)[0], "id")),
          findingKey: String(own(asArray(own(system, "findings")).filter(isInsufficientFinding)[0], "id")),
        }
        : null,
    };
  }
  const cards = asArray(globalResults.cards)
    .filter((card) => isPlainObject(card) && (ownedIds.has(firstText(card.findingKey)) || card.systemContext === name))
    .map((card) => copyJsonSafe(card));
  const explicitlyNormal = own(system, "status") === "Normal" && Array.isArray(own(system, "findings"));
  return {
    contractVersion: CONTRACT_VERSION,
    depth: "results",
    variant: "ready",
    outcome: explicitlyNormal ? "stable" : "analysis_complete",
    eyebrow: "Operations Brief",
    headline: explicitlyNormal ? "No supported material behavioral change." : "Analysis complete",
    explanation: explicitlyNormal
      ? "The available comparison remains within the learned system-behavior boundary."
      : cards.length
        ? `${cards.length} ${cards.length === 1 ? "finding deserves" : "findings deserve"} review for ${name}.`
        : `No findings currently deserve review for ${name}.`,
    systemLabel: name,
    counts: { findingsForReview: cards.length, systemsRepresented: cards.length ? 1 : 0 },
    cards,
  };
}

export function projectSystems(model, reviewRecords = {}) {
  if (!isPlainObject(model) || !Array.isArray(own(model, "subsystems"))) {
    return { contractVersion: CONTRACT_VERSION, depth: "systems", variant: "unavailable", header: null, systems: [] };
  }
  const globalResults = projectResults(model, reviewRecords);
  if (globalResults.variant === "unavailable") {
    return { contractVersion: CONTRACT_VERSION, depth: "systems", variant: "unavailable", header: null, systems: [] };
  }
  const systems = own(model, "subsystems").filter(isPlainObject).map((system) => {
    const name = firstText(own(system, "name"), "Mapped system");
    const results = scopedResultsForSystem(globalResults, system);
    return {
      systemKey: name,
      name,
      locationLabel: uniqueText(asArray(own(system, "location"))).join(" / "),
      status: firstText(own(system, "status"), "Evidence insufficient"),
      evidenceQuality: firstText(own(system, "evidenceTier"), "Unavailable"),
      findingsForReview: results.counts?.findingsForReview ?? 0,
      primaryAction: { label: "Open system", route: route("systems", name) },
      results,
    };
  });
  return {
    contractVersion: CONTRACT_VERSION,
    depth: "systems",
    variant: "ready",
    header: {
      systemLabel: firstText(ownPath(model, "site.name"), "Current facility"),
      status: firstText(own(model, "status"), "Evidence insufficient"),
      evidenceQuality: firstText(own(model, "evidenceQuality"), "Unavailable"),
      summary: `${systems.length} modeled ${systems.length === 1 ? "system" : "systems"}`,
    },
    systems,
  };
}

function assessmentValue(value, fallback = "Unavailable") {
  const text = firstText(value, fallback);
  const normalized = text.toLowerCase();
  const state = /unavailable|unknown|not established|not enough|insufficient/.test(normalized)
    ? "unknown"
    : /low|limited|partial|narrow|defer|withheld|different/.test(normalized)
      ? "limited"
      : "supported";
  return { value: text, state };
}

function reviewAssessment(finding, insufficient) {
  const presentation = finding?.classificationPresentation ?? {};
  const corroboration = firstText(finding?.corroboration?.corroboration_strength);
  const relationshipCount = finite(finding?.corroboration?.relationship_count);
  return {
    changeConfidence: assessmentValue(firstText(finding?.confidenceDimensions?.changeDetection?.level, finding?.confidenceContract?.change_detection?.level, finding?.tier)),
    evidenceQuality: assessmentValue(firstText(finding?.confidenceDimensions?.evidenceQuality?.level, presentation?.dataConfidence?.rating)),
    causeAttribution: assessmentValue(firstText(finding?.confidenceDimensions?.interpretation?.attribution_status, finding?.confidenceContract?.interpretation?.attribution_status), "Not established"),
    persistence: assessmentValue(firstText(presentation?.persistence?.label, finding?.confidenceContract?.persistence?.status, finding?.persistence?.status)),
    operatingContext: assessmentValue(firstText(finding?.confidenceDimensions?.operatingContext?.status, presentation?.operatingMode?.match, finding?.operatingMode?.match)),
    corroboration: assessmentValue(corroboration ? `${corroboration}${relationshipCount !== null ? ` · ${relationshipCount} relationships` : ""}` : "Unavailable"),
    evidenceSufficiency: assessmentValue(firstText(finding?.confidenceContract?.evidence_sufficiency?.status, insufficient ? "Insufficient" : "Supported for review")),
  };
}

function reviewHeader(finding, model, reviewRecord) {
  return { systemContext: systemContext(finding, model), title: bounded(finding?.title, 120), reviewState: workflowState(reviewRecord) };
}

function reviewReason(item) {
  const text = bounded(typeof item === "string" ? item : item?.description ?? item?.summary ?? item?.reason, 150);
  return /\b(?:0?\.\d{3,}|\d+\s*(?:samples?|rows?)|RAW_|CANONICAL_|UTC)\b/i.test(text) ? "" : text;
}

function reviewChecks(finding) {
  const guidance = [
    ...asArray(finding?.classificationPresentation?.investigationGuidance),
    ...asArray(finding?.investigationGuidance),
    ...asArray(finding?.recommendedInvestigation),
  ].map((item) => firstText(item?.check, item?.label, typeof item === "object" ? "" : item));
  return uniqueText(guidance.map((item) => bounded(item, 140)).filter((item) => item && item !== "[object Object]"), 3).map((item) => ({ label: item }));
}

function canonicalResultContext(result) {
  const canonical = isObject(result?.canonical_result) ? result.canonical_result : {};
  const identity = isObject(canonical.identity) ? canonical.identity : {};
  const resultId = firstText(result?.result_id, identity.result_id);
  if (!resultId) return null;
  return { canonical, identity, resultId };
}

function canonicalRouteIdentity(result) {
  const context = canonicalResultContext(result);
  if (!context) return {};
  return {
    resultId: context.resultId,
    analysisId: firstText(result?.analysis_id, context.identity.analysis_id) || null,
    analysisWindowId: firstText(result?.analysis_window_id, context.identity.analysis_window_id) || null,
    sourceRunId: firstText(result?.source_run_id, context.identity.source_ingestion_run_id) || null,
    connectionId: firstText(result?.connection_id, context.identity.connection_id) || null,
    facilityId: firstText(result?.facility_id, context.identity.facility_id) || null,
    systemId: firstText(result?.system_id, context.identity.system_id) || null,
    assetId: firstText(result?.asset_id, context.identity.asset_id) || null,
    payloadDigest: firstText(result?.payload_digest, context.identity.payload_digest) || null,
    observationCount: finite(result?.observation_count, context.identity.observation_count),
    observationLineageDigest: firstText(result?.observation_lineage_digest, context.identity.observation_lineage_digest) || null,
  };
}

function qualificationBlock(value) {
  if (!isObject(value)) return null;
  return {
    sourcePath: firstText(value.source_path) || null,
    truncated: value.truncated === true,
    omittedValues: finite(value.omitted_values),
    originalItems: finite(value.original_items),
    selectedItems: finite(value.selected_items),
    originalBytes: finite(value.original_bytes),
    selectedBytes: finite(value.selected_bytes),
    transported: value.transported !== false,
  };
}

function canonicalProjectionQualification(result) {
  const context = canonicalResultContext(result);
  const projection = isObject(result?.projection) ? result.projection : null;
  if (!context || !projection) return null;
  const technical = isObject(projection.technical_channels) ? projection.technical_channels : {};
  const technicalChannels = {};
  for (const [key, value] of Object.entries(technical)) {
    const qualified = qualificationBlock(value);
    if (qualified) technicalChannels[key] = qualified;
  }
  const shared = qualificationBlock(projection.shared);
  const evidenceAudit = qualificationBlock(projection.evidence_audit);
  const truncatedSources = uniqueText([
    ...(shared?.truncated ? [shared.sourcePath] : []),
    ...(evidenceAudit?.truncated ? [evidenceAudit.sourcePath] : []),
    ...Object.values(technicalChannels).filter((item) => item.truncated || !item.transported).map((item) => item.sourcePath),
  ]);
  return {
    contractVersion: firstText(projection.contract_version) || null,
    canonicalResultId: firstText(projection.canonical_result_id, context.resultId) || null,
    canonicalPayloadDigest: firstText(projection.canonical_payload_digest, context.identity.payload_digest, result?.payload_digest) || null,
    referenceMetadata: copyJsonSafe(context.canonical.reference_metadata ?? {}),
    shared,
    evidenceAudit,
    technicalChannels,
    truncated: truncatedSources.length > 0,
    truncatedSources,
  };
}

function technicalQualification(result, sourcePath) {
  const projection = canonicalProjectionQualification(result);
  if (!projection) return null;
  const canonicalPath = firstText(sourcePath).replace(/^model\.result\./, "");
  const channelKey = canonicalPath.startsWith("sii_result.") ? canonicalPath.split(".")[1] : "";
  const channel = channelKey ? projection.technicalChannels[channelKey] : null;
  return channel ? { ...channel, canonicalResultId: projection.canonicalResultId, canonicalPayloadDigest: projection.canonicalPayloadDigest } : null;
}

function canonicalIdValues(value) {
  if (Array.isArray(value)) return uniqueText(value);
  if (!isObject(value)) return [];
  for (const key of ["items", "ids", "values"]) {
    if (Array.isArray(value[key])) return uniqueText(value[key]);
  }
  return [];
}

export function projectFindingReview(model, requestedFindingId, reviewRecord = {}) {
  const finding = exactFinding(model, requestedFindingId);
  if (!finding) return unavailable("review");
  const insufficient = finding.status === "Evidence insufficient" || ["Deferred", "Withheld"].includes(finding.tier);
  const reasons = uniqueText([
    reviewReason(finding?.whyItMatters),
    ...asArray(finding?.classificationPresentation?.reasons).map(reviewReason),
    ...asArray(finding?.visibleSupporting).map(reviewReason),
  ], 3);
  const key = String(finding.id);
  return {
    contractVersion: CONTRACT_VERSION,
    depth: "review",
    variant: insufficient ? "insufficient" : "ready",
    identity: { findingKey: key, ...canonicalRouteIdentity(model?.result) },
    header: reviewHeader(finding, model, reviewRecord),
    whatChanged: insufficient
      ? "A supported material behavioral change cannot be shown from the available evidence."
      : bounded(finding?.observedChange, 220) || "A change in learned system behavior is supported for review.",
    whyAttention: reasons.length ? reasons : [insufficient ? "The evidence boundary is not sufficient for a reliable conclusion." : "The learned system behavior differs from the comparison period."],
    assessment: reviewAssessment(finding, insufficient),
    materialLimitation: bounded(finding?.primaryLimitation, 180) || null,
    checks: insufficient ? [] : reviewChecks(finding),
    primaryAction: insufficient && !asArray(finding.relationships).length
      ? null
      : { label: "Open investigation", route: route("investigations", key) },
  };
}

function channelState(payload, reason = "This evidence channel was not supplied for this analysis.") {
  const safePayload = copyChannelPayload(payload);
  const available = safePayload !== null && safePayload !== undefined && (typeof safePayload !== "object" || Object.keys(safePayload).length > 0);
  return available ? { state: "available", reason: "" } : { state: "unavailable", reason };
}

function scopedChannel({ key, label: channelLabel, payload, sourcePath, scope = "run", summary = "", metrics = [], qualification = null }) {
  const scopeLabel = {
    finding: "Finding-scoped evidence",
    relationship: "Relationship-scoped evidence",
    system: "System-scoped evidence; supports context, not finding ownership",
    run: "Analysis-run evidence; not finding-specific",
  }[scope];
  const safePayload = copyChannelPayload(payload);
  return {
    key,
    label: channelLabel,
    state: channelState(safePayload),
    scope,
    scopeLabel,
    sourcePath: qualification?.sourcePath || sourcePath,
    qualification,
    summary: bounded(summary || own(safePayload, "summary") || own(safePayload, "description") || own(safePayload, "status"), 240),
    metrics: copyJsonSafe(asArray(metrics)),
  };
}

function copyChannelPayload(payload) {
  if (Array.isArray(payload) || isPlainObject(payload)) return copyJsonSafe(payload);
  if (payload === null || payload === undefined || typeof payload === "function" || typeof payload === "symbol") return null;
  if (typeof payload === "number") return Number.isFinite(payload) ? payload : null;
  if (["string", "boolean"].includes(typeof payload)) return payload;
  return null;
}

function relationshipProjection(relationship) {
  if (!isObject(relationship)) return null;
  const windows = asArray(relationship.windows).filter(isObject).map((window) => ({
    baselineStart: firstText(window.baseline_start) || null,
    baselineEnd: firstText(window.baseline_end) || null,
    currentStart: firstText(window.current_start) || null,
    currentEnd: firstText(window.current_end) || null,
  }));
  return {
    id: firstText(relationship.id),
    source: { display: firstText(relationship.source, "Source signal"), sourceId: firstText(relationship.rawSource) },
    target: { display: firstText(relationship.target, "Target signal"), sourceId: firstText(relationship.rawTarget) },
    metricChannel: firstText(relationship.metric, "Relationship evidence"),
    baseline: finite(relationship.baseline),
    current: finite(relationship.current),
    signedChange: finite(relationship.signedChange),
    magnitude: finite(relationship.absoluteChange, relationship.delta),
    direction: firstText(relationship.relationshipDirection, relationship.changeType, relationship.state),
    baselineSamples: finite(relationship.baselineSampleCount),
    currentSamples: finite(relationship.currentSampleCount),
    windows,
    persistence: firstText(relationship.persistence?.status, relationship.persistence?.label, relationship.persistence) || null,
    support: firstText(relationship.supportTrend, relationship.confidence) || null,
  };
}

function temporalSource(result) {
  const candidates = [
    [ownPath(result, "sii_result.temporal_analysis"), "model.result.sii_result.temporal_analysis"],
    [own(result, "temporal_math"), "model.result.temporal_math"],
    [ownPath(result, "sii_intelligence.temporal_math"), "model.result.sii_intelligence.temporal_math"],
    [ownPath(result, "engine_result.temporal_math"), "model.result.engine_result.temporal_math"],
  ];
  return candidates.find(([payload]) => isObject(payload)) ?? [null, "model.result.sii_result.temporal_analysis"];
}

function investigationChannels(model) {
  const result = own(model, "result") ?? {};
  const temporal = temporalSource(result);
  const resultEvolution = ownPath(result, "sii_result.behavioral_evolution");
  const resultExpected = ownPath(result, "sii_result.expected_behavior");
  const resultPropagation = ownPath(result, "sii_result.propagation_analysis");
  const resultPhysics = ownPath(result, "sii_result.physics_reasoning");
  const resultPhysicsEvidence = ownPath(result, "sii_result.physics_evidence");
  const paths = [
    ["multivariate", "Multivariate system evidence", ownPath(result, "sii_result.covariance_analysis"), "model.result.sii_result.covariance_analysis"],
    ["temporal", "Temporal evidence", temporal[0], temporal[1]],
    ["lag", "Lag evidence", own(temporal[0], "lagged_relationships"), `${temporal[1]}.lagged_relationships`],
    ["mutual_information", "Mutual-information evidence", own(temporal[0], "mutual_information_drift"), `${temporal[1]}.mutual_information_drift`],
    ["behavioral_evolution", "Behavioral evolution", resultEvolution ?? ownPath(model, "siiEvidence.phase_4.behavioral_evolution"), resultEvolution ? "model.result.sii_result.behavioral_evolution" : "model.siiEvidence.phase_4.behavioral_evolution"],
    ["expected_behavior", "Expected behavior", resultExpected ?? ownPath(model, "siiEvidence.phase_4.expected_behavior"), resultExpected ? "model.result.sii_result.expected_behavior" : "model.siiEvidence.phase_4.expected_behavior"],
    ["propagation", "Propagation evidence", resultPropagation ?? ownPath(model, "siiEvidence.phase_4.propagation"), resultPropagation ? "model.result.sii_result.propagation_analysis" : "model.siiEvidence.phase_4.propagation"],
    ["physics", "Physics-informed evidence", resultPhysics ?? resultPhysicsEvidence ?? ownPath(model, "siiEvidence.phase_4.physics"), resultPhysics ? "model.result.sii_result.physics_reasoning" : resultPhysicsEvidence ? "model.result.sii_result.physics_evidence" : "model.siiEvidence.phase_4.physics"],
  ];
  return paths.map(([key, channelLabel, payload, sourcePath]) => scopedChannel({ key, label: channelLabel, payload, sourcePath, qualification: technicalQualification(result, sourcePath) }));
}

function investigationContext(finding) {
  const presentation = finding?.classificationPresentation ?? {};
  const operating = finding?.operatingMode ?? {};
  const baselineMode = firstText(operating.baseline_mode_label, operating.baselineModeLabel, operating.baseline_mode, operating.baselineMode);
  const currentMode = firstText(operating.recent_mode_label, operating.recentModeLabel, operating.recent_mode, operating.recentMode, operating.current_mode);
  const comparability = firstText(finding?.comparableOperation?.status, operating.match, presentation?.operatingMode?.match);
  return {
    state: channelState(baselineMode || currentMode || comparability),
    baselineMode,
    currentMode,
    comparability,
    reasons: uniqueText(asArray(finding?.comparableOperation?.reasons).concat(asArray(presentation?.operatingMode?.reasons)), 4),
  };
}

function investigationQuality(finding) {
  const quality = finding?.dataConfidence ?? finding?.classificationPresentation?.dataConfidence ?? {};
  const health = asArray(finding?.sensorHealth?.signals ?? finding?.sensorHealth).filter(isObject).map((item) => ({ signal: firstText(item.signal, item.name, item.id), status: firstText(item.status, item.health, item.rating) }));
  const limitations = uniqueText(asArray(finding?.dataLimitations).concat(asArray(finding?.technicalLimitations)), 5);
  const summary = firstText(quality?.summary, quality?.rating, quality?.status);
  return { state: channelState(summary || limitations.length || health.length), summary, limitations, signalHealth: health };
}

export function projectInvestigation(model, requestedFindingId, reviewRecord = {}) {
  const finding = exactFinding(model, requestedFindingId);
  if (!finding) return unavailable("investigation");
  const relationships = asArray(finding.relationships).map(relationshipProjection).filter(Boolean);
  const nodes = relationships.flatMap((item) => [item.source, item.target]);
  const nodeMap = new Map(nodes.filter((item) => item.sourceId || item.display).map((item) => [item.sourceId || item.display, { id: item.sourceId || item.display, label: item.display }]));
  const key = String(finding.id);
  const insufficient = finding.status === "Evidence insufficient" || ["Deferred", "Withheld"].includes(finding.tier);
  const persistenceSummary = firstText(finding?.classificationPresentation?.persistence?.label, finding?.persistence?.summary, finding?.persistence?.status);
  return {
    contractVersion: CONTRACT_VERSION,
    depth: "investigation",
    variant: insufficient ? "insufficient" : "ready",
    identity: { findingKey: key, ...canonicalRouteIdentity(model?.result) },
    header: reviewHeader(finding, model, reviewRecord),
    primaryComparison: relationships[0] ?? null,
    relationships,
    relationshipMap: relationships.length ? {
      nodes: [...nodeMap.values()],
      edges: relationships.map((item) => ({ id: item.id, sourceId: item.source.sourceId || item.source.display, targetId: item.target.sourceId || item.target.display, state: item.direction })),
    } : null,
    systemEvidence: investigationChannels(model),
    persistence: { state: channelState(persistenceSummary), summary: persistenceSummary, supportTrend: firstText(finding?.supportTrend), windowDescription: firstText(finding?.persistence?.window_description, finding?.persistence?.window) || null },
    operatingContext: investigationContext(finding),
    dataQuality: investigationQuality(finding),
    timeline: asArray(finding?.activityTimeline).filter(isObject).map((item) => ({ label: firstText(item.label, item.title, item.event), detail: firstText(item.detail, item.description, item.summary) })),
    sourceSignals: uniqueText(relationships.flatMap((item) => [item.source.sourceId, item.target.sourceId]).concat(asArray(finding.rawVariables))).map((sourceId, index) => ({ display: firstText(asArray(finding.variables)[index], sourceId), sourceId })),
    lineageSummary: { source: firstText(model?.result?.source_name, model?.result?.filename), baselineWindow: firstText(finding?.comparison?.baseline), currentWindow: firstText(finding?.comparison?.current), evidenceRefs: uniqueText(asArray(finding?.relationships).flatMap((item) => asArray(item?.evidenceRefs))) },
    projectionQualification: canonicalProjectionQualification(model?.result),
    primaryAction: { label: "Open evidence record", route: route("evidence", key) },
  };
}

function exactAnalysisResult(model, requestedResultId) {
  if (!isPlainObject(model) || !isPlainObject(model.result)) return null;
  const requested = firstText(requestedResultId);
  const actual = firstText(model.result.result_id);
  return requested && actual && requested === actual ? model.result : null;
}

function analysisHeader(model) {
  const status = firstText(model?.status);
  return {
    systemContext: firstText(model?.result?.system_name, model?.result?.system_id, model?.site?.name, "Mapped system"),
    title: status === "Normal"
      ? "No supported material behavioral change"
      : status === "Evidence insufficient"
        ? "Insufficient evidence"
        : "Completed connector analysis",
    reviewState: "Completed",
  };
}

function analysisLimitations(result) {
  const analysis = analysisSource(result);
  return uniqueText([
    ...asArray(result?.warnings),
    ...asArray(result?.errors),
    ...asArray(result?.data_conditions),
    ...asArray(analysis?.warnings),
    ...asArray(analysis?.errors),
  ], 32);
}

export function projectAnalysisInvestigation(model, requestedResultId) {
  const result = exactAnalysisResult(model, requestedResultId);
  if (!result) return unavailable("investigation");
  const key = String(result.result_id);
  const relationships = asArray(model?.relationships).map(relationshipProjection).filter(Boolean);
  const nodes = relationships.flatMap((item) => [item.source, item.target]);
  const nodeMap = new Map(nodes.filter((item) => item.sourceId || item.display).map((item) => [item.sourceId || item.display, { id: item.sourceId || item.display, label: item.display }]));
  const persistence = ownPath(result, "sii_result.persistence_analysis") ?? ownPath(model, "siiEvidence.persistence");
  const operating = ownPath(result, "sii_result.operating_modes") ?? ownPath(model, "siiEvidence.operating_context");
  const quality = result?.data_quality ?? ownPath(result, "sii_result.data_conditions") ?? ownPath(model, "siiEvidence.data_quality");
  const limitations = analysisLimitations(result);
  const canonicalContext = canonicalResultContext(result);
  const evidenceIndex = analysisSource(result)?.evidence_index;
  const evidenceItems = isObject(evidenceIndex) ? Object.values(evidenceIndex).filter(isObject) : asArray(evidenceIndex).filter(isObject);
  const evidenceRefs = uniqueText(evidenceItems.flatMap((item) => firstText(item?.evidence_id, item?.id)));
  return {
    contractVersion: CONTRACT_VERSION,
    depth: "investigation",
    variant: model?.status === "Evidence insufficient" ? "insufficient" : "ready",
    identity: { findingKey: key, scope: "analysis", ...canonicalRouteIdentity(result), resultId: key },
    header: analysisHeader(model),
    primaryComparison: relationships[0] ?? null,
    relationships,
    relationshipMap: relationships.length ? {
      nodes: [...nodeMap.values()],
      edges: relationships.map((item) => ({ id: item.id, sourceId: item.source.sourceId || item.source.display, targetId: item.target.sourceId || item.target.display, state: item.direction })),
    } : null,
    systemEvidence: investigationChannels(model),
    persistence: {
      state: channelState(persistence),
      summary: firstText(persistence?.summary, persistence?.status),
      supportTrend: firstText(persistence?.support_trend, persistence?.trend),
      windowDescription: firstText(persistence?.window_description, persistence?.window),
    },
    operatingContext: {
      state: channelState(operating),
      baselineMode: firstText(operating?.baseline_mode_label, operating?.baseline_mode),
      currentMode: firstText(operating?.recent_mode_label, operating?.current_mode, operating?.recent_mode),
      comparability: firstText(operating?.match, operating?.status),
      reasons: uniqueText(asArray(operating?.reasons), 4),
    },
    dataQuality: {
      state: channelState(quality),
      summary: firstText(quality?.summary, quality?.status),
      limitations,
      signalHealth: asArray(quality?.signals).filter(isObject).map((item) => ({ signal: firstText(item.signal, item.name, item.id), status: firstText(item.status, item.health, item.rating) })),
    },
    timeline: asArray(analysisSource(result)?.timeline).filter(isObject).map((item) => ({ label: firstText(item.label, item.title, item.event), detail: firstText(item.detail, item.description, item.summary) })),
    sourceSignals: uniqueText(asArray(model?.relationships).flatMap((item) => [item?.rawSource, item?.rawTarget])).map((sourceId) => ({ display: sourceId, sourceId })),
    lineageSummary: {
      source: firstText(result.source_name, result.connection_id),
      baselineWindow: firstText(result.baseline_window, result.window_start),
      currentWindow: firstText(result.current_window, result.window_end),
      evidenceRefs: evidenceRefs.length ? evidenceRefs : canonicalIdValues(canonicalContext?.canonical?.evidence_ids),
    },
    projectionQualification: canonicalProjectionQualification(result),
    primaryAction: { label: "Open evidence record", route: route("evidence", key) },
  };
}

function resultRunId(result) {
  return firstText(result?.comparison_analysis_id, result?.analysis_run_id, result?.run_id, result?.job_id, result?.upload_id);
}

export function resolvePackageAssociation(model, finding) {
  const packagePayload = model?.result?.evidence_package;
  const packageId = firstText(packagePayload?.id, packagePayload?.evidence_package_id, packagePayload?.package_id);
  const directId = firstText(finding?.sourceAssociations?.evidencePackageId);
  const directPath = firstText(finding?.sourceAssociations?.sourcePaths?.evidencePackageId);
  const relationshipId = firstText(packagePayload?.primary_relationship?.source_model_edge_id, packagePayload?.primary_relationship?.relationship_id);
  const ownedIds = new Set(asArray(finding?.relationships).filter((item) => item?.sourceBackedId !== false).map((item) => String(item.id)));
  const relationshipLink = relationshipId
    ? { state: ownedIds.has(relationshipId) ? "matched" : "different", sourcePath: "model.result.evidence_package.primary_relationship.source_model_edge_id", relationshipId }
    : { state: "unavailable", sourcePath: null, relationshipId: null };
  if (!packageId || !isPlainObject(packagePayload)) {
    return { scope: "unavailable", scopeLabel: "No package is explicitly attributable to this finding", sourcePath: null, packageId: null, immutableDetails: null, relationshipLink: { state: "unavailable", sourcePath: null, relationshipId: null } };
  }
  if (directId) {
    if (directId !== packageId) {
      return { scope: "unavailable", scopeLabel: "No package is explicitly attributable to this finding", sourcePath: directPath || null, packageId: null, immutableDetails: null, relationshipLink: { state: "unavailable", sourcePath: null, relationshipId: null } };
    }
    return { scope: "finding", scopeLabel: "Package explicitly linked to this finding", sourcePath: directPath, packageId, immutableDetails: copyJsonSafe(packagePayload), relationshipLink };
  }
  if (asArray(finding?.sourceAssociations?.relatedEvidencePackageIds).map(String).includes(packageId)) {
    return { scope: "related", scopeLabel: "Related package explicitly referenced by this finding; not finding provenance", sourcePath: "finding.related_evidence_package_ids", packageId, immutableDetails: copyJsonSafe(packagePayload), relationshipLink };
  }
  const packageRunId = firstText(packagePayload?.analysis_id, packagePayload?.analysis_run_id, packagePayload?.run_id);
  const runId = resultRunId(model?.result);
  if (packageRunId && runId && packageRunId === runId) {
    return { scope: "run", scopeLabel: "Related package for this analysis run; not finding provenance", sourcePath: "model.result.evidence_package", packageId, immutableDetails: copyJsonSafe(packagePayload), relationshipLink };
  }
  return { scope: "unavailable", scopeLabel: "No package is explicitly attributable to this finding", sourcePath: null, packageId: null, immutableDetails: null, relationshipLink: { state: "unavailable", sourcePath: null, relationshipId: null } };
}

const EVIDENCE_CHANNELS = Object.freeze([
  ["relationship_analysis", "Relationship analysis", "sii_result.relationship_analysis"],
  ["relationship_graph", "Relationship graph", "sii_result.relationship_graph"],
  ["multivariate", "Multivariate evidence", "sii_result.covariance_analysis"],
  ["temporal", "Temporal evidence", "sii_result.temporal_analysis"],
  ["multiscale", "Multiscale evidence", "sii_result.multiscale_analysis"],
  ["persistence", "Persistence evidence", "sii_result.persistence_analysis"],
  ["operating_context", "Operating-mode evidence", "sii_result.operating_modes"],
  ["uncertainty", "Uncertainty", "sii_result.uncertainty"],
  ["data_quality", "Data conditions", "sii_result.data_conditions"],
  ["evidence_fusion", "Evidence fusion", "sii_result.evidence_fusion"],
  ["behavioral_model", "Behavioral model", "sii_result.behavioral_model"],
  ["expected_behavior", "Expected behavior", "sii_result.expected_behavior"],
  ["behavioral_evolution", "Behavioral evolution", "sii_result.behavioral_evolution"],
  ["behavioral_snapshots", "Behavioral snapshots", "sii_result.behavioral_snapshots"],
  ["event_memory", "Event memory", "sii_result.event_memory"],
  ["spectral", "Spectral evidence", "sii_result.spectral_analysis"],
  ["dynamical_stability", "Dynamical stability", "sii_result.dynamical_stability"],
  ["network_stability", "Network stability", "sii_result.network_stability"],
  ["bayesian", "Bayesian evidence", "sii_result.bayesian_evidence"],
  ["propagation", "Propagation evidence", "sii_result.propagation_analysis"],
  ["physics", "Physics-informed evidence", "sii_result.physics_reasoning"],
  ["physics_evidence", "Physics evidence", "sii_result.physics_evidence"],
]);

function pathValue(root, path) {
  return ownPath(root, path);
}

function evidenceChannel(key, channelLabel, payload, sourcePath, scope = "run", qualification = null) {
  const safePayload = copyChannelPayload(payload);
  const base = scopedChannel({ key, label: channelLabel, payload: safePayload, sourcePath, scope, qualification });
  return { key: base.key, label: base.label, state: base.state, scope: base.scope, scopeLabel: base.scopeLabel, sourcePath: base.sourcePath, qualification: base.qualification, payload: safePayload };
}

function evidenceChannels(model, finding) {
  const result = own(model, "result") ?? {};
  const channels = [];
  const exactRelationships = asArray(finding?.relationships);
  channels.push(evidenceChannel("finding_relationships", "Finding-owned relationships", exactRelationships.length ? exactRelationships : undefined, "finding.relationships", "relationship"));
  for (const [key, channelLabel, path] of EVIDENCE_CHANNELS) {
    const sourcePath = `model.result.${path}`;
    channels.push(evidenceChannel(key, channelLabel, pathValue(result, path), sourcePath, "run", technicalQualification(result, sourcePath)));
  }
  const temporal = temporalSource(result);
  channels.push(evidenceChannel("lag", "Lag evidence", own(temporal[0], "lagged_relationships"), `${temporal[1]}.lagged_relationships`, "run", technicalQualification(result, `${temporal[1]}.lagged_relationships`)));
  channels.push(evidenceChannel("mutual_information", "Mutual-information evidence", own(temporal[0], "mutual_information_drift"), `${temporal[1]}.mutual_information_drift`, "run", technicalQualification(result, `${temporal[1]}.mutual_information_drift`)));
  const siiSections = ["relationship_changes", "operating_context", "persistence", "uncertainty", "data_quality", "sensor_health", "configured_prior_observations", "phase_4", "provenance"];
  for (const section of siiSections) channels.push(evidenceChannel(`sii_${section}`, `SII ${label(section)}`, ownPath(model, `siiEvidence.${section}`), `model.siiEvidence.${section}`));
  channels.push(evidenceChannel("traceability", "Traceability", own(result, "traceability"), "model.result.traceability"));
  channels.push(evidenceChannel("processing_trace", "Processing trace", own(result, "processing_trace"), "model.result.processing_trace"));
  channels.push(evidenceChannel("result_data_quality", "Result data quality", own(result, "data_quality"), "model.result.data_quality"));
  channels.push(evidenceChannel("result_data_conditions", "Result data conditions", own(result, "data_conditions"), "model.result.data_conditions"));
  channels.push(evidenceChannel("ingestion", "Ingestion evidence", own(result, "ingestion"), "model.result.ingestion"));
  return channels;
}

function canonicalSignalMap(raw) {
  const rows = asArray(raw?.signals).concat(asArray(raw?.signal_mappings), asArray(raw?.canonical_signals));
  const map = new Map();
  for (const row of rows) {
    if (!isObject(row)) continue;
    const rawId = firstText(row.raw_id, row.raw_tag, row.source_id, row.signal_id);
    const canonicalId = firstText(row.canonical_id, row.canonical_signal_id, row.normalized_name);
    if (rawId && canonicalId) map.set(rawId, canonicalId);
  }
  return map;
}

export function projectEvidenceRecord(model, requestedFindingId, reviewRecord = {}) {
  const finding = exactFinding(model, requestedFindingId);
  if (!finding) return unavailable("evidence");
  const result = model?.result ?? {};
  const raw = rawFinding(model, finding) ?? {};
  const key = String(finding.id);
  const insufficient = finding.status === "Evidence insufficient" || ["Deferred", "Withheld"].includes(finding.tier);
  const exactRelationships = asArray(finding.relationships).map((item) => copyJsonSafe(item));
  const canonical = canonicalSignalMap(raw);
  const rawIds = uniqueText(asArray(finding.rawVariables).concat(asArray(finding.relationships).flatMap((item) => [item?.rawSource, item?.rawTarget])));
  const signals = rawIds.map((rawId, index) => ({ display: firstText(asArray(finding.variables)[index], rawId), rawId, canonicalId: canonical.get(rawId) ?? null }));
  const packageAssociation = resolvePackageAssociation(model, finding);
  const sourceRows = asArray(raw?.source_rows ?? raw?.lineage?.source_rows).map((item) => copyJsonSafe(item));
  const evidenceWindows = asArray(finding?.sourceTimeRanges).map((item) => copyJsonSafe(item));
  const evidenceRefs = uniqueText(asArray(finding?.relationships).flatMap((item) => asArray(item?.evidenceRefs)).concat(asArray(raw?.evidence_refs)));
  const runId = resultRunId(result) || null;
  const canonicalContext = canonicalResultContext(result);
  return {
    contractVersion: CONTRACT_VERSION,
    depth: "evidence",
    variant: insufficient ? "insufficient" : "ready",
    identity: {
      findingKey: key,
      findingId: key,
      workflowFindingId: firstText(finding?.workflowFindingId) || null,
      conditionId: firstText(finding?.conditionId) || null,
      runId,
      uploadId: firstText(result?.upload_id) || null,
      datasetId: firstText(result?.dataset_id) || null,
      baselineId: firstText(result?.baseline_id) || null,
      systemId: firstText(finding?.technicalIdentity?.systemId, raw?.system_id) || null,
      assetId: firstText(finding?.technicalIdentity?.assetId, raw?.asset_id, raw?.equipment_id) || null,
      ...canonicalRouteIdentity(result),
    },
    header: reviewHeader(finding, model, reviewRecord),
    timestamps: { generatedAt: firstText(finding?.generatedAt, result?.completed_at, result?.processed_at) || null, firstDetectedAt: firstText(finding?.firstDetectedAt) || null, sourceRanges: evidenceWindows.map((item) => copyJsonSafe(item)) },
    signals,
    exactRelationships,
    supportingEvidence: {
      statements: uniqueText(asArray(raw?.supporting_evidence).concat(asArray(finding?.supporting))),
      items: asArray(raw?.evidence_items).map((item) => copyJsonSafe(item)),
    },
    channels: evidenceChannels(model, finding),
    classifications: { classification: isObject(finding?.classification) ? copyJsonSafe(finding.classification) : null, confidenceContract: isObject(finding?.confidenceContract) ? copyJsonSafe(finding.confidenceContract) : null, alternatives: uniqueText(asArray(finding?.alternativeExplanations)) },
    sufficiency: { status: firstText(finding?.confidenceContract?.evidence_sufficiency?.status, insufficient ? "Insufficient" : "Supported for review"), reasons: uniqueText(asArray(finding?.confidenceContract?.evidence_sufficiency?.reasons).concat(insufficient ? asArray(finding?.limitations) : [])) },
    limitations: { material: uniqueText(asArray(finding?.limitations).concat(finding?.primaryLimitation ? [finding.primaryLimitation] : [])), technical: uniqueText(asArray(finding?.technicalLimitations).concat(asArray(finding?.dataLimitations))), contradictions: uniqueText(asArray(finding?.contradictions)) },
    lineage: { sourceRows, evidenceWindows, evidenceRefs, traceability: isObject(result?.traceability) ? copyJsonSafe(result.traceability) : null, findingProvenance: isObject(raw?.provenance) || Array.isArray(raw?.provenance) ? copyJsonSafe(raw.provenance) : null, canonical: canonicalContext ? { identity: copyJsonSafe(canonicalContext.identity), referenceMetadata: copyJsonSafe(canonicalContext.canonical.reference_metadata), lineage: copyJsonSafe(result.lineage) } : null },
    engine: { name: firstText(result?.engine_name, result?.engine?.name) || null, version: firstText(result?.engine_version, result?.model_version, result?.engine?.version) || null, schemaVersion: firstText(result?.analysis_schema_version, result?.schema_version) || null, contractVersion: firstText(result?.analysis_contract_version, canonicalContext?.identity?.analysis_contract_version) || null, executionContractVersion: firstText(result?.execution_contract_version, canonicalContext?.identity?.execution_contract_version) || null, artifactSchemaVersion: firstText(result?.artifact_schema_version, canonicalContext?.identity?.artifact_schema_version) || null, buildCommit: firstText(result?.build_commit, result?.engine?.build_commit) || null, configurationHash: firstText(result?.configuration_hash, result?.config_hash) || null, inputHash: firstText(result?.input_hash) || null, resultHash: firstText(result?.payload_digest, result?.result_hash) || null },
    package: packageAssociation,
    audit: { caseState: firstText(finding?.caseState) || null, caseHistory: asArray(finding?.caseHistory).map((item) => copyJsonSafe(item)), outcome: isObject(finding?.outcome) ? copyJsonSafe(finding.outcome) : null, review: isObject(reviewRecord) ? copyJsonSafe(reviewRecord) : null, trace: asArray(model?.trace).map((item) => copyJsonSafe(item)), canonicalResult: canonicalContext ? { resultId: canonicalContext.resultId, payloadDigest: firstText(result?.payload_digest, canonicalContext.identity.payload_digest) || null, projectionContractVersion: firstText(result?.projection?.contract_version) || null } : null },
    projectionQualification: canonicalProjectionQualification(result),
    actions: { exportRunId: runId, exportScopeLabel: runId ? "Analysis-run export; not finding-specific" : null, traceRoute: asArray(model?.trace).length ? "/trace" : null },
  };
}

export function projectAnalysisEvidenceRecord(model, requestedResultId) {
  const result = exactAnalysisResult(model, requestedResultId);
  if (!result) return unavailable("evidence");
  const key = String(result.result_id);
  const analysis = analysisSource(result);
  const limitations = analysisLimitations(result);
  const insufficient = model?.status === "Evidence insufficient";
  const signalCatalog = [
    analysis?.signal_catalog,
    analysis?.telemetry_signals,
    analysis?.normalized_telemetry?.signals,
    result?.signal_catalog,
  ].map((value) => asArray(value).filter(isObject)).find((value) => value.length) ?? [];
  const evidenceIndex = analysis?.evidence_index;
  const evidenceItems = (isObject(evidenceIndex) ? Object.values(evidenceIndex) : asArray(evidenceIndex)).filter(isObject).map((item) => copyJsonSafe(item));
  const exactRelationships = asArray(model?.relationships).map(relationshipProjection).filter(Boolean);
  const canonicalContext = canonicalResultContext(result);
  const canonicalEvidenceIds = canonicalIdValues(canonicalContext?.canonical?.evidence_ids);
  return {
    contractVersion: CONTRACT_VERSION,
    depth: "evidence",
    variant: insufficient ? "insufficient" : "ready",
    identity: {
      findingKey: key,
      scope: "analysis",
      ...canonicalRouteIdentity(result),
      resultId: key,
      runId: firstText(result.source_run_id) || null,
    },
    header: analysisHeader(model),
    timestamps: {
      generatedAt: firstText(result.generated_at, result.completed_at) || null,
      firstDetectedAt: null,
      sourceRanges: result.window_start || result.window_end ? [{ start: result.window_start ?? null, end: result.window_end ?? null }] : [],
    },
    signals: signalCatalog.map((signal) => ({
      display: firstText(signal.display_name, signal.name, signal.tag_name, signal.normalized_name, signal.canonical_signal_id, signal.signal_id),
      rawId: firstText(signal.source_signal_id, signal.external_tag_id, signal.source_column, signal.raw_id, signal.signal_id) || null,
      canonicalId: firstText(signal.canonical_signal_id, signal.canonical_id, signal.normalized_name) || null,
    })),
    exactRelationships,
    supportingEvidence: { statements: [], items: evidenceItems },
    channels: evidenceChannels(model, null),
    classifications: { classification: null, confidenceContract: null, alternatives: [] },
    sufficiency: {
      status: insufficient ? "Insufficient" : firstText(result.evidence_status, model?.status) || "Completed",
      reasons: insufficient ? limitations : [],
    },
    limitations: { material: limitations, technical: [], contradictions: [] },
    lineage: {
      sourceRows: [],
      evidenceWindows: result.window_start || result.window_end ? [{ start: result.window_start ?? null, end: result.window_end ?? null }] : [],
      evidenceRefs: canonicalEvidenceIds.length ? canonicalEvidenceIds : uniqueText(asArray(result.evidence_ids)),
      traceability: isObject(result.traceability) ? copyJsonSafe(result.traceability) : null,
      observationCount: finite(result.observation_count, canonicalContext?.identity?.observation_count),
      observationLineageDigest: firstText(result.observation_lineage_digest, canonicalContext?.identity?.observation_lineage_digest) || null,
      lineageVerified: result.lineage_verified === true,
    },
    engine: {
      name: firstText(result.engine_name, result?.engine?.name) || null,
      version: firstText(result.engine_version, result?.engine?.version) || null,
      schemaVersion: firstText(result.analysis_schema_version, result.schema_version) || null,
      contractVersion: firstText(result.analysis_contract_version) || null,
      executionContractVersion: firstText(result.execution_contract_version) || null,
      artifactSchemaVersion: firstText(result.artifact_schema_version) || null,
      buildCommit: firstText(result.build_commit, result?.engine?.build_commit) || null,
      configurationHash: firstText(result.configuration_hash, result.config_hash) || null,
      inputHash: firstText(result.input_hash) || null,
      resultHash: firstText(result.payload_digest, result.result_hash) || null,
    },
    package: { scope: "unavailable", scopeLabel: "No finding-specific evidence package applies to this analysis result", sourcePath: null, packageId: null, immutableDetails: null, relationshipLink: { state: "unavailable", sourcePath: null, relationshipId: null } },
    audit: {
      resultId: key,
      analysisWindowId: firstText(result.analysis_window_id) || null,
      payloadDigest: firstText(result.payload_digest) || null,
      lineageVerified: result.lineage_verified === true,
      artifactSchemaVersion: firstText(result.artifact_schema_version) || null,
      executionContractVersion: firstText(result.execution_contract_version) || null,
      analysisSchemaVersion: firstText(result.analysis_schema_version, result.schema_version) || null,
      analysisContractVersion: firstText(result.analysis_contract_version) || null,
      referenceMetadata: canonicalContext ? copyJsonSafe(canonicalContext.canonical.reference_metadata) : null,
      evidenceAudit: canonicalContext ? copyJsonSafe(canonicalContext.canonical.evidence_audit) : null,
    },
    projectionQualification: canonicalProjectionQualification(result),
    actions: { exportRunId: null, exportScopeLabel: null, traceRoute: null },
  };
}
