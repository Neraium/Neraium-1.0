import { sanitizeOperatorText } from "./operatorFinding";

export const CONFIDENCE_TIERS = ["Confirmed", "Qualified", "Narrowed", "Deferred", "Withheld"];
export const OPERATIONAL_STATUSES = ["Normal", "Change detected", "Evidence insufficient"];

const asArray = (value) => Array.isArray(value) ? value : [];
const compact = (values) => values.filter((value) => value !== null && value !== undefined && value !== "");
const firstText = (...values) => {
  for (const value of values.flat()) {
    const text = sanitizeOperatorText(value);
    if (text) return text;
  }
  return "";
};
const firstNumber = (...values) => {
  for (const value of values.flat()) {
    if (value === null || value === undefined || value === "") continue;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
};
const unique = (items) => [...new Set(compact(items).map((item) => String(item).trim()).filter(Boolean))];
const humanize = (value) => String(value ?? "").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const stripPeriod = (value) => String(value ?? "").trim().replace(/[.。]+$/, "");

const UNSUPPORTED_LOCATION = /^(current site|uploaded telemetry|not established|mapped infrastructure|mapped system|unknown|n\/?a|observed subsystem behavior (?:changed|shifted))$/i;
const LOCATION_AS_FINDING = /\b(?:behavior|relationship|performance)\b.*\b(?:changed|shifted|degrading|degraded|detected)\b/i;
const GENERIC_FINDING_TITLE = /^(observed subsystem behavior (?:changed|shifted)|investigation recommended|relationship change detected|structural instability|highest-priority operational finding|operational finding|mapped change|change detected)$/i;
const MALFORMED_FINDING_TITLE = /[;]|\b(?:new operating relationship|operating coupling|correlation|relationship strength)\b|^-?0?\.\d+/i;
const OVERSTATED_FINDING_TITLE = /\b(?:degrading|degraded|deteriorating|underperforming|failure|failing)\b/i;
const DATA_CLEANING_DETAIL = /(dropped rows?|unmapped columns?|constant sensors?|completeness floors?|parsing warnings?|coercion|duplicate rows?)/i;
const MATERIAL_LIMITATION = /(missing|gap|unavailable|incomplete|insufficient|baseline|unreliable|contradict|efficiency|coverage|prevents?|limits?|cannot|could not)/i;
const TIER_RANK = { Withheld: 0, Deferred: 1, Narrowed: 2, Qualified: 3, Confirmed: 4 };

function supportedLocationText(...values) {
  for (const value of values.flat()) {
    const text = sanitizeOperatorText(value);
    if (text && !UNSUPPORTED_LOCATION.test(text) && !LOCATION_AS_FINDING.test(text)) return text;
  }
  return "";
}

function sentence(value, maxLength = 180) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return "";
  const first = clean.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() || clean;
  if (first.length <= maxLength) return first;
  return `${first.slice(0, maxLength - 1).trimEnd()}…`;
}

function strengthLabel(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "not available";
  const magnitude = Math.abs(numeric);
  if (magnitude < 0.3) return "weak";
  if (magnitude < 0.7) return "moderate";
  return "strong";
}

function contextText(values) {
  return values.flat(Infinity).map((value) => sanitizeOperatorText(value)).filter(Boolean).join(" ").toLowerCase().replace(/[_-]+/g, " ");
}

function inferredOperationalArea(values) {
  const combined = contextText(values);
  if (/condenser|approach temperature|chiller|compressor|cooling/.test(combined)) return "Cooling system";
  if (/pump|flow|pressure|valve|hydraulic/.test(combined)) return "Flow and pressure";
  if (/chlor|turbidity|conductivity|water quality|orp|chemical|ph\b/.test(combined)) return "Water quality";
  if (/tower|heat rejection|thermal/.test(combined)) return "Heat rejection";
  return "";
}

function sentenceCaseArea(value) {
  const normalized = String(value || "").replace(/\s*&\s*/g, " and ").replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  const words = normalized.split(" ");
  return words.map((word, index) => index === 0 || /^[A-Z]{2,}$/.test(word) ? word : word.toLowerCase()).join(" ");
}

function operationalTitleFromContext(values, system = "") {
  const combined = contextText([values, system]);
  if (/condenser|approach temperature/.test(combined) || (/temperature/.test(combined) && /compressor|chiller/.test(combined))) return "Condenser-side behavior changed";
  if (/pump/.test(combined) && /flow/.test(combined) && /demand|power|current|amp/.test(combined)) return "Pump demand no longer matches flow";
  if (/chlor|turbidity|conductivity|water quality|orp|chemical|ph\b/.test(combined)) return "Water-quality relationships shifted";
  if (/flow|pressure|hydraulic|pump|valve/.test(combined)) return (sentenceCaseArea(system || "Flow and pressure") || "Flow and pressure") + " behavior changed";
  if (/cooling|chiller|compressor|thermal/.test(combined)) return (sentenceCaseArea(system || "Cooling system") || "Cooling system") + " behavior changed";
  if (system) return sentenceCaseArea(system) + " behavior changed";
  return "Measured behavior changed";
}

function mappedEvidenceSignal(text, contextSignals) {
  if (!/^chiller\s+(?:increased|decreased|changed)\b/i.test(text)) return text;
  const context = contextText(contextSignals);
  let replacement = "Chiller signal";
  if (/compressor/.test(context) && /amp|current/.test(context)) replacement = "Compressor current";
  else if (/chiller/.test(context) && /power|kw/.test(context)) replacement = "Chiller power";
  else if (/chiller|cooling/.test(context) && /load/.test(context)) replacement = "Cooling load";
  return text.replace(/^chiller\b/i, replacement);
}

export function formatPrimaryEvidence(value, contextSignals = []) {
  let text = typeof value === "object" && value !== null
    ? firstText(value?.description, value?.summary, value?.observation, value?.signal, value?.relationship, value?.label, value?.value)
    : firstText(value);
  if (!text) return "";
  const coefficientRange = /(-?0?\.\d{3,})\s*(?:to|→|->)\s*(-?0?\.\d{3,})/gi;
  text = text.replace(coefficientRange, (_, from, to) => strengthLabel(from) + " to " + strengthLabel(to));
  text = text.replace(/\b-?0\.\d{4,}\b/g, (raw) => strengthLabel(raw));
  text = mappedEvidenceSignal(text, contextSignals);
  text = text.replace(/^.*?operating coupling\s+(?:changed|shifted|strengthened|weakened)?\s*from\s+(weak|moderate|strong)\s+to\s+(weak|moderate|strong)\.?$/i, "Their learned relationship changed from $1 to $2.");
  text = text.replace(/^the relationship moved outside its learned range\.?$/i, "Their learned relationship changed.");
  return sentence(text);
}

export function deriveConfidenceTier({ explicit, coverage, evidenceCount, limitations = [], contradictions = [], processing = false, baselineSufficient = null, reliable = true }) {
  const normalized = String(explicit ?? "").trim().toLowerCase();
  const completeness = Number.isFinite(Number(coverage)) ? Number(coverage) : null;
  const explicitTier = CONFIDENCE_TIERS.find((tier) => tier.toLowerCase() === normalized) ?? null;
  if (reliable === false) return "Withheld";
  if (processing) return "Deferred";
  if (baselineSufficient === false) return explicitTier === "Withheld" ? "Withheld" : "Deferred";
  if (!evidenceCount || (completeness !== null && completeness < 0.5) || contradictions.length > evidenceCount) return "Withheld";
  if (explicitTier === "Withheld") return "Withheld";
  if (explicitTier === "Deferred" || /defer|pending|delay|incomplete/.test(normalized)) return "Deferred";
  if (completeness !== null && completeness < 0.75) return "Narrowed";
  if (limitations.length || contradictions.length) return "Narrowed";
  if (explicitTier === "Narrowed" || /low|weak|developing|narrow/.test(normalized)) return "Narrowed";
  if (explicitTier === "Confirmed") return completeness !== null && completeness < 0.95 ? "Qualified" : "Confirmed";
  return "Qualified";
}

export function deriveEvidenceCoverage(result = {}, snapshot = {}) {
  const integrity = result?.sii_intelligence?.telemetry_integrity ?? result?.telemetry_integrity ?? {};
  const signalCoverage = asArray(integrity?.signal_integrity).map((item) => firstNumber(item?.completeness, item?.coverage, item?.coverage_percent)).filter(Number.isFinite).map((value) => value > 1 ? value / 100 : value);
  if (signalCoverage.length) return Math.max(0, Math.min(1, signalCoverage.reduce((sum, value) => sum + value, 0) / signalCoverage.length));
  const quality = result?.data_quality ?? result?.quality ?? {};
  const direct = firstNumber(quality?.coverage, quality?.coverage_percent, quality?.completeness, result?.data_coverage, snapshot?.data_coverage);
  if (direct !== null) return Math.max(0, Math.min(1, direct > 1 ? direct / 100 : direct));
  const received = firstNumber(result?.rows_received, snapshot?.rows_received, result?.row_count, snapshot?.row_count);
  const accepted = firstNumber(result?.rows_accepted, snapshot?.rows_accepted, result?.row_count, snapshot?.row_count);
  if (received && accepted !== null) return Math.max(0, Math.min(1, accepted / received));
  return null;
}

function normalizeGap(item, index) {
  if (typeof item === "string") return { id: `gap-${index}`, source: item, start: null, end: null, duration: "", signals: [], coverageImpact: null, overlapsChange: null };
  return { id: String(item?.id ?? item?.gap_id ?? `gap-${index}`), source: firstText(item?.source, item?.source_name, item?.historian, item?.label, "Telemetry source"), start: item?.start ?? item?.start_at ?? item?.timestamp_start ?? null, end: item?.end ?? item?.end_at ?? item?.timestamp_end ?? null, duration: firstText(item?.duration, item?.missing_duration), signals: unique(asArray(item?.signals ?? item?.affected_signals ?? item?.columns)), coverageImpact: firstNumber(item?.coverage_impact, item?.coverage_percent), overlapsChange: typeof item?.overlaps_change_window === "boolean" ? item.overlaps_change_window : null };
}

export function deriveDataGaps(result = {}, coverage = null) {
  const quality = result?.data_quality ?? {};
  const explicit = [...asArray(result?.data_gaps), ...asArray(quality?.data_gaps), ...asArray(result?.sii_intelligence?.telemetry_integrity?.data_gaps)];
  const missing = unique([...asArray(quality?.missing_recent_values), ...asArray(quality?.missing_columns), ...asArray(result?.data_conditions)]);
  const gaps = explicit.map(normalizeGap);
  if (!gaps.length && missing.length) gaps.push(normalizeGap({ source: firstText(result?.source_name, result?.filename, "Telemetry source"), signals: missing }, 0));
  if (!gaps.length && coverage !== null && coverage < 1) gaps.push(normalizeGap({ source: firstText(result?.source_name, result?.filename, "Telemetry source"), coverage_impact: Math.round(coverage * 100) }, 0));
  return gaps;
}

function relationshipLabel(row, index) {
  const columns = unique([...asArray(row?.columns), ...asArray(row?.display_columns), row?.source_label, row?.target_label, row?.source, row?.target]);
  return firstText(row?.label, row?.name, row?.relationship, row?.description, columns.length >= 2 ? `${columns[0]} and ${columns[1]}` : "", `Relationship ${index + 1}`);
}

function edgeState(row) {
  const state = firstText(row?.change_type, row?.state, row?.status, row?.relationship_state).toLowerCase();
  if (/emerg|new|unusual/.test(state)) return "emerging";
  if (/weaken|drift|change|degrad|shift|diverg/.test(state)) return "changed";
  if (/histor|inactive/.test(state)) return "historical";
  if (/insufficient|unknown|missing/.test(state)) return "insufficient";
  return "normal";
}

function normalizeRelationship(row, index, evidenceIndex = {}) {
  const columns = unique([...asArray(row?.columns), ...asArray(row?.display_columns), row?.source_label, row?.target_label, row?.source, row?.target]);
  const source = columns[0] || "";
  const target = columns[1] || "";
  const evidenceRefs = unique(asArray(row?.evidence_refs ?? row?.evidenceRefs));
  const evidence = compact([row?.evidence, ...evidenceRefs.map((ref) => evidenceIndex?.[ref])]).filter((item) => typeof item === "object");
  return { id: String(row?.id ?? row?.relationship_id ?? `relationship-${index}`), label: relationshipLabel(row, index), source, target, state: edgeState(row), changeType: firstText(row?.change_type, row?.state, row?.status, row?.relationship_state).toLowerCase(), baseline: firstNumber(row?.baseline_strength, row?.baseline, row?.statistics?.baseline_strength), current: firstNumber(row?.current_strength, row?.current, row?.statistics?.current_strength), delta: firstNumber(row?.calculated_delta, row?.correlation_delta, row?.delta, row?.statistics?.correlation_delta), evidence, confidence: firstText(row?.confidence, evidence[0]?.confidence), windows: asArray(row?.source_time_ranges ?? evidence[0]?.source_time_ranges) };
}

function collectRelationships(result, analysis) {
  const graphEdges = asArray(analysis?.relationship_graph?.edges ?? result?.relationship_model?.relationship_graph?.edges);
  const rows = [...asArray(analysis?.relationships), ...asArray(result?.baseline_analysis?.relationship_drift), ...graphEdges];
  const evidenceIndex = analysis?.evidence_index ?? {};
  const seen = new Set();
  return rows.map((row, index) => normalizeRelationship(row, index, evidenceIndex)).filter((row) => { const key = row.id || row.label; if (seen.has(key)) return false; seen.add(key); return true; });
}

function evidenceText(item) {
  if (typeof item === "string") return sanitizeOperatorText(item);
  const direct = firstText(item?.description, item?.summary, item?.observation, item?.value);
  if (direct) return direct;
  const signal = firstText(item?.signal, item?.metric, item?.relationship, item?.label);
  const direction = firstText(item?.direction, item?.change_direction, item?.change);
  const magnitude = firstNumber(item?.percent_change, item?.change_percent, item?.magnitude_percent);
  if (!signal) return "";
  return compact([signal, direction, magnitude === null ? "" : `${Math.abs(magnitude).toFixed(1)}%`]).join(" ");
}

function collectTechnicalLimitations(raw, result, gaps) {
  return unique([...asArray(raw?.limitations), ...asArray(raw?.confidence_decrease_factors), ...asArray(result?.data_quality?.warnings), ...asArray(result?.warnings), ...asArray(result?.data_conditions), ...gaps.map((gap) => `Evidence gap in ${gap.signals.join(", ") || gap.source}${gap.duration ? ` (${gap.duration})` : ""}.`)].map(evidenceText));
}
function collectContradictions(raw) { return unique([...asArray(raw?.contradicting_evidence), ...asArray(raw?.contradictions), ...asArray(raw?.counter_evidence), ...asArray(raw?.confounders)].map(evidenceText)); }
function plainLimitation(value) {
  const text = sentence(value, 120);
  const lower = text.toLowerCase();
  if (/efficiency/.test(lower) && /missing|gap|unavailable/.test(lower)) return "Missing efficiency telemetry limits the conclusion.";
  if (/missing numeric|missing values?|rows? contain missing|gap|unavailable|historian/.test(lower)) return "Missing telemetry limits the conclusion.";
  if (/baseline/.test(lower) && /insufficient|incomplete|missing|unavailable/.test(lower)) return "The baseline is insufficient for a reliable conclusion.";
  if (/coverage|completeness/.test(lower)) return "Limited telemetry coverage narrows the conclusion.";
  return text;
}
function materialLimitations(raw, technicalLimitations, gaps) {
  const explicit = unique([...asArray(raw?.limitations), ...asArray(raw?.confidence_decrease_factors)].map(evidenceText));
  const relevantTechnical = technicalLimitations.filter((item) => !DATA_CLEANING_DETAIL.test(item) && MATERIAL_LIMITATION.test(item));
  const gapSentences = gaps.map((gap) => gap.signals.length ? "Missing " + gap.signals.join(", ") + " telemetry limits the conclusion." : "Missing telemetry limits the conclusion.");
  return unique([...explicit, ...relevantTechnical, ...gapSentences].map(plainLimitation).filter(Boolean));
}
function deriveBaselineSufficiency(result, analysis, relationships) {
  const explicit = result?.baseline_sufficient ?? result?.baseline_established ?? analysis?.baseline_sufficient ?? analysis?.fingerprint?.baseline_sufficient;
  if (typeof explicit === "boolean") return explicit;
  const status = firstText(result?.baseline_status, analysis?.fingerprint?.status, result?.fingerprint?.status).toLowerCase();
  if (/insufficient|missing|unavailable|failed/.test(status)) return false;
  if (/established|ready|complete|stable|changed|drift/.test(status)) return true;
  if (relationships.length) return true;
  return null;
}
function isReliable(raw, result) {
  const explicit = raw?.reliable ?? raw?.finding_reliable ?? result?.reliable ?? result?.data_quality?.reliable;
  if (explicit === false) return false;
  return !/unreliable|invalid/.test(firstText(raw?.confidence_state, result?.data_quality?.status).toLowerCase());
}
function isActiveRawFinding(raw) {
  const id = firstText(raw?.id, raw?.finding_id).toLowerCase();
  const status = firstText(raw?.status, raw?.state, raw?.observation_status).toLowerCase();
  const title = firstText(raw?.title, raw?.summary).toLowerCase();
  if (id === "baseline-stable") return false;
  if (/^(resolved|closed|normal|stable|no[_ -]?change)$/.test(status)) return false;
  if (/^(no (?:material )?change|normal operation|relationships? (?:remain )?(?:normal|stable))/.test(title)) return false;
  return true;
}
function specificFindingTitle(raw, observedChange, relationship, tier, system, contextValues = []) {
  if (["Deferred", "Withheld"].includes(tier)) return "Evidence insufficient to isolate cause";
  const supplied = stripPeriod(firstText(raw?.title, raw?.finding_title));
  const observed = stripPeriod(sentence(observedChange, 90));
  const fullContext = [contextValues, supplied, observed, relationship?.source, relationship?.target];
  const inferred = operationalTitleFromContext(fullContext, system);
  const directionalSupport = /weakened|decreased|fell|reduced|no longer matches/.test(contextText(contextValues));
  const suppliedIsUsable = supplied && supplied.length <= 72 && !GENERIC_FINDING_TITLE.test(supplied) && !MALFORMED_FINDING_TITLE.test(supplied) && !OVERSTATED_FINDING_TITLE.test(supplied);
  if (inferred === "Condenser-side behavior changed" || inferred === "Pump demand no longer matches flow") return inferred;
  if (suppliedIsUsable) {
    if (/\bweakened\b/i.test(supplied) && !directionalSupport) return inferred;
    if (/\bperformance changed\b/i.test(supplied) && inferred !== "Measured behavior changed") return inferred;
    return supplied.replace(/\s*&\s*/g, " and ");
  }
  const observedIsUsable = observed && observed.length <= 72 && !GENERIC_FINDING_TITLE.test(observed) && !MALFORMED_FINDING_TITLE.test(observed) && !OVERSTATED_FINDING_TITLE.test(observed);
  return observedIsUsable && inferred === "Measured behavior changed" ? observed : inferred;
}
function deriveLocation(raw, context) {
  const rawRelationships = asArray(raw?.contributing_relationships ?? raw?.relationships);
  const signalContext = [
    ...asArray(raw?.variables), ...asArray(raw?.affected_variables), ...asArray(raw?.supporting_signals),
    raw?.title, raw?.what_changed, raw?.observed_change,
    ...rawRelationships.flatMap((item) => [...asArray(item?.columns), ...asArray(item?.display_columns), item?.source, item?.target]),
  ];
  const inferredSystem = inferredOperationalArea(signalContext);
  const system = supportedLocationText(raw?.system, raw?.system_name, raw?.location?.system, context.primarySystem) || inferredSystem;
  const subsystem = supportedLocationText(raw?.subsystem, raw?.subsystem_name, raw?.location?.subsystem);
  const asset = supportedLocationText(raw?.asset, raw?.asset_name, raw?.equipment, raw?.equipment_name, raw?.mapped_asset, raw?.location?.asset);
  const normalizedSubsystem = subsystem && subsystem !== system ? subsystem : "";
  const normalizedAsset = asset && asset !== normalizedSubsystem && asset !== system ? asset : "";
  const supportedHierarchy = unique([context.siteLocation, system, normalizedSubsystem, normalizedAsset]);
  const hierarchy = supportedHierarchy.length > 1 ? supportedHierarchy : [...supportedHierarchy, "Asset not identified"];
  return { site: context.siteLocation, system, subsystem: normalizedSubsystem, asset: normalizedAsset, hierarchy, label: hierarchy.join(" · ") };
}
function comparisonSummary(relationship) {
  if (!relationship) return "A readable baseline comparison is not available.";
  if (relationship.baseline !== null && relationship.current !== null) return `Relationship was ${strengthLabel(relationship.baseline)} at baseline and is ${strengthLabel(relationship.current)} now.`;
  if (relationship.state === "emerging") return "This relationship was not present in the learned baseline and is present now.";
  if (relationship.state === "changed") return "This relationship moved outside its learned behavior during the current comparison.";
  if (relationship.state === "normal") return "This relationship remains within its learned behavior.";
  return "The available baseline is not sufficient for a reliable comparison.";
}
function confidenceReason(tier, primaryLimitation) {
  if (primaryLimitation) return sentence(primaryLimitation);
  if (tier === "Narrowed") return "Evidence supports a broad change, but not a more specific conclusion.";
  if (tier === "Deferred") return "More baseline evidence is required before this conclusion can be assessed.";
  if (tier === "Withheld") return "The available evidence is not reliable enough to support a conclusion.";
  return "";
}

function buildFinding(raw, index, context) {
  const relatedRows = asArray(raw?.contributing_relationships ?? raw?.relationships).map((row, rowIndex) => normalizeRelationship(row, rowIndex, context.evidenceIndex));
  const relationship = relatedRows[0] ?? context.relationships[0] ?? null;
  const evidenceRefs = unique(asArray(raw?.evidence_refs ?? raw?.evidenceRefs));
  const evidenceObjects = compact([...asArray(raw?.evidence ?? raw?.evidence_items), ...evidenceRefs.map((ref) => context.evidenceIndex?.[ref]), ...relatedRows.flatMap((row) => row.evidence)]);
  const rawSupporting = unique([...asArray(raw?.supporting_evidence), ...asArray(raw?.observed_facts), ...evidenceObjects.map(evidenceText)].map(evidenceText));
  if (!rawSupporting.length && relationship && ["changed", "emerging"].includes(relationship.state)) rawSupporting.push(relationship.label + " moved outside its learned range.");
  const technicalLimitations = collectTechnicalLimitations(raw, context.result, context.gaps);
  const limitations = materialLimitations(raw, technicalLimitations, context.gaps);
  const contradictions = collectContradictions(raw);
  const variables = unique([...asArray(raw?.variables), ...asArray(raw?.affected_variables), ...asArray(raw?.supporting_signals), relationship?.source, relationship?.target]);
  const tier = deriveConfidenceTier({ explicit: raw?.confidence_tier ?? raw?.confidence ?? raw?.confidence_state, coverage: context.coverage, evidenceCount: rawSupporting.length + evidenceObjects.length, limitations, contradictions, processing: context.processing, baselineSufficient: raw?.baseline_sufficient === false ? false : context.baselineSufficient, reliable: isReliable(raw, context.result) });
  const observedChange = firstText(raw?.what_changed, raw?.observed_change, raw?.whatHappened, raw?.summary, raw?.title) || (relationship ? relationship.label + " moved outside its learned behavior." : "The available comparison indicates a change in measured behavior.");
  const location = deriveLocation(raw, context);
  const titleContext = [variables, rawSupporting, relatedRows.map((item) => [item.label, item.source, item.target])];
  const title = specificFindingTitle(raw, observedChange, relationship, tier, location.subsystem || location.system, titleContext);
  const supporting = unique(rawSupporting.map((item) => formatPrimaryEvidence(item, titleContext)).filter(Boolean));
  const specificRecommendation = firstText(raw?.first_place_to_look, raw?.recommended_first_action, raw?.recommended_check, raw?.operator_check, raw?.recommended_action);
  const hasMappedContext = Boolean(location.system || location.subsystem || location.asset) && variables.length > 0;
  const prior = raw?.engineering_prior ?? raw?.relationship_prior ?? raw?.prior_contribution ?? null;
  const interpretationLevel = prior && hasMappedContext ? 1 : specificRecommendation && hasMappedContext ? 2 : relationship ? 3 : 4;
  const recommendationAllowed = !["Deferred", "Withheld"].includes(tier) && interpretationLevel <= 2;
  const whyItMatters = sentence(firstText(raw?.why_it_matters, raw?.potential_impact, raw?.behavior_interpretation, raw?.interpretation)) || "Neraium flagged a repeatable difference between the learned baseline and the current comparison.";
  const primaryLimitation = limitations[0] || plainLimitation(contradictions[0]) || "";
  const status = ["Deferred", "Withheld"].includes(tier) ? "Evidence insufficient" : "Change detected";
  return { id: String(raw?.id ?? raw?.finding_id ?? "finding-" + index), title, status, system: location.subsystem || location.system || context.siteLocation, location, relatedAreas: [], observedChange: sentence(observedChange), whyItMatters, tier, confidenceReason: confidenceReason(tier, primaryLimitation), supporting, visibleSupporting: supporting.slice(0, 3), rawSupporting, contradictions, limitations, primaryLimitation, technicalLimitations, firstPlaceToLook: recommendationAllowed ? specificRecommendation : "", confirmationCriteria: firstText(raw?.confirmation_criteria, raw?.confirm_or_rule_out, raw?.expected_confirmation), comparison: deriveComparison(raw, relationship, context.result), comparisonSummary: comparisonSummary(relationship), relationships: relatedRows.length ? relatedRows : (relationship ? [relationship] : []), variables, engineeringPrior: prior, interpretationLevel, recommendationAllowed, evidenceObjects, outcome: asArray(raw?.operator_feedback_history)[0] ?? null };
}

function evidenceKey(value) {
  const text = String(value || "").toLowerCase().replace(/[^a-z0-9.%]+/g, " ").trim();
  if (/relationship|coupling|learned range|learned behavior/.test(text)) return "relationship-change";
  return text;
}
function findingsOverlap(left, right) {
  const leftKeys = new Set(left.supporting.map(evidenceKey));
  const rightKeys = new Set(right.supporting.map(evidenceKey));
  if (Math.min(leftKeys.size, rightKeys.size) < 2) return false;
  let shared = 0;
  for (const key of leftKeys) if (rightKeys.has(key)) shared += 1;
  return shared >= 2;
}
function uniqueObjects(items, identity) {
  const seen = new Set();
  return items.filter((item) => {
    const key = identity(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
function prioritizeEvidence(items) {
  const all = unique(items);
  const relationship = all.filter((item) => /relationship|coupling|learned range|learned behavior/i.test(item));
  const metrics = all.filter((item) => !relationship.includes(item) && /%|increased|decreased|rose|fell/i.test(item));
  const other = all.filter((item) => !relationship.includes(item) && !metrics.includes(item));
  const visible = unique([...metrics.slice(0, 2), ...relationship.slice(0, 1), ...other]).slice(0, 3);
  return { all: unique([...visible, ...all]), visible };
}
function mergeFindingGroup(group) {
  if (group.length === 1) return group[0];
  const primary = group[0];
  const variables = unique(group.flatMap((finding) => finding.variables));
  const allSupporting = group.flatMap((finding) => finding.supporting);
  const areas = unique(group.flatMap((finding) => [finding.location.system, finding.location.subsystem])).filter(Boolean);
  const inferredSystem = inferredOperationalArea([variables, allSupporting, areas]) || primary.location.system;
  const assets = unique(group.map((finding) => finding.location.asset).filter(Boolean));
  const site = primary.location.site;
  const hierarchyBase = unique([site, inferredSystem, assets.length === 1 ? assets[0] : ""]);
  const hierarchy = hierarchyBase.length > 1 ? hierarchyBase : [...hierarchyBase, "Asset not identified"];
  const location = { site, system: inferredSystem, subsystem: "", asset: assets.length === 1 ? assets[0] : "", hierarchy, label: hierarchy.join(" · ") };
  const tier = group.reduce((lowest, finding) => TIER_RANK[finding.tier] < TIER_RANK[lowest] ? finding.tier : lowest, primary.tier);
  const limitations = unique(group.flatMap((finding) => finding.limitations));
  const contradictions = unique(group.flatMap((finding) => finding.contradictions));
  const primaryLimitation = limitations[0] || plainLimitation(contradictions[0]) || "";
  const evidence = prioritizeEvidence(allSupporting);
  const title = operationalTitleFromContext([variables, evidence.all, areas], inferredSystem);
  const relationships = uniqueObjects(group.flatMap((finding) => finding.relationships), (item) => item.id + "|" + item.label);
  const evidenceObjects = uniqueObjects(group.flatMap((finding) => finding.evidenceObjects), (item) => String(item?.id ?? item?.evidence_id ?? evidenceText(item)));
  const status = ["Deferred", "Withheld"].includes(tier) ? "Evidence insufficient" : "Change detected";
  return {
    ...primary,
    title: title === "Measured behavior changed" ? primary.title : title,
    status,
    location,
    system: inferredSystem || primary.system,
    relatedAreas: areas.length > 1 ? areas : [],
    observedChange: (title === "Measured behavior changed" ? primary.title : title) + ".",
    tier,
    confidenceReason: confidenceReason(tier, primaryLimitation),
    supporting: evidence.all,
    visibleSupporting: evidence.visible,
    rawSupporting: unique(group.flatMap((finding) => finding.rawSupporting)),
    contradictions,
    limitations,
    primaryLimitation,
    technicalLimitations: unique(group.flatMap((finding) => finding.technicalLimitations)),
    relationships,
    variables,
    evidenceObjects,
    recommendationAllowed: !["Deferred", "Withheld"].includes(tier) && group.some((finding) => finding.recommendationAllowed),
    mergedFindingIds: group.map((finding) => finding.id),
  };
}
function consolidateFindings(findings) {
  const groups = [];
  for (const finding of findings) {
    const match = groups.find((group) => group.some((candidate) => findingsOverlap(candidate, finding)));
    if (match) match.push(finding);
    else groups.push([finding]);
  }
  return groups.map(mergeFindingGroup);
}

function deriveComparison(raw, relationship, result) {
  const window = asArray(raw?.source_time_ranges)[0] ?? relationship?.windows?.[0] ?? {};
  return { baseline: firstText(window?.baseline_label, joinWindow(window?.baseline_start, window?.baseline_end), result?.baseline_window, "Learned baseline"), current: firstText(window?.current_label, joinWindow(window?.current_start, window?.current_end), result?.comparison_window, "Current comparison"), baselineValue: relationship?.baseline ?? null, currentValue: relationship?.current ?? null, delta: relationship?.delta ?? null };
}
function joinWindow(start, end) { if (!start && !end) return ""; return [start, end].filter(Boolean).join(" to "); }
function canonicalAsRaw(canonicalFinding) {
  if (!canonicalFinding?.exists) return null;
  return { id: canonicalFinding.id, title: canonicalFinding.summary, summary: canonicalFinding.summary, why_it_matters: canonicalFinding.whyItMatters, confidence: canonicalFinding.confidence, recommended_check: canonicalFinding.reviewNext, supporting_evidence: canonicalFinding.supportingEvidence, variables: canonicalFinding.affectedVariables };
}
function deriveSubsystems(systems, findings, relationships, siteLocation) {
  const names = unique([...asArray(systems).map((item) => supportedLocationText(item?.name, item?.label)), ...findings.flatMap((finding) => [finding.location.system, finding.location.subsystem, ...finding.relatedAreas])]);
  return names.map((name, index) => {
    const owned = findings.filter((finding) => finding.location.system === name || finding.location.subsystem === name || finding.relatedAreas.includes(name));
    const status = owned.some((finding) => finding.status === "Change detected") ? "Change detected" : owned.length ? "Evidence insufficient" : relationships.length ? "Normal" : "Evidence insufficient";
    return { id: `system-${index}`, name, status, findingCount: owned.length, findings: owned, location: unique([siteLocation, name]), evidenceTier: owned[0]?.tier ?? (relationships.length ? "Qualified" : "Deferred") };
  });
}
function buildTrace(finding, result) {
  if (!finding) return [];
  const timestamp = result?.completed_at ?? result?.processed_at ?? result?.timestamp_profile?.last_timestamp ?? null;
  const source = firstText(result?.source_name, result?.filename, "Persisted evidence record");
  const relationship = finding.relationships[0];
  return [
    { type: "Observation", source, transformation: "Telemetry observation selected", input: finding.variables.join(", ") || "Mapped signals", output: finding.observedChange, timestamp, classification: "Measured / derived", version: result?.schema_version ?? "Not supplied" },
    { type: "Normalization", source, transformation: firstText(result?.normalization?.method, "Configured signal normalization"), input: finding.variables.join(", ") || "Mapped signals", output: firstText(result?.normalization?.summary, "Normalized evidence window"), timestamp, classification: "Configured / derived", version: result?.normalization?.version ?? "Not supplied" },
    { type: "Relationship", source: "Learned baseline", transformation: "Baseline/current comparison", input: relationship?.label ?? "Available evidence", output: finding.comparisonSummary, timestamp, classification: "Inferred", version: result?.baseline_version ?? "Not supplied" },
    { type: "Change detection", source: "Neraium engine", transformation: "Relationship comparison", input: relationship?.label ?? finding.observedChange, output: finding.observedChange, timestamp, classification: "Derived", version: result?.model_version ?? "Not supplied" },
    { type: "Finding", source: "Neraium reasoning layer", transformation: "Confidence and limitations gating", input: finding.whyItMatters, output: `${finding.tier}: ${finding.title}`, timestamp, classification: "Conclusion", version: result?.schema_version ?? "Not supplied" },
  ].map((step, index) => ({ ...step, id: `trace-${index}`, governance: firstText(result?.governance_statement, result?.governance_boundary?.statement, "Stored within the configured evidence boundary"), confidenceContribution: index >= 3 ? finding.tier : "Contributing evidence" }));
}
function assignedSite(result, snapshot, currentSession, liveOps) {
  const candidates = [result?.facility_name, result?.site_name, snapshot?.facility_name, currentSession?.facilityName, liveOps?.facilityName];
  for (const candidate of candidates) { const text = supportedLocationText(candidate); if (text) return { assigned: true, name: text, location: text }; }
  return { assigned: false, name: "Unassigned Analysis", location: "Unassigned dataset" };
}
function deriveSiteStatus(findings, hasAnalysis, baselineSufficient, coverage) {
  if (findings.some((finding) => finding.status === "Change detected")) return "Change detected";
  if (findings.length || !hasAnalysis || baselineSufficient === false || (coverage !== null && coverage < 0.5)) return "Evidence insufficient";
  return "Normal";
}

export function buildEngineeringReasoningModel({ liveOps = {}, canonicalFinding = null, currentSession = null, result: explicitResult = null, snapshot = null, domainDetection = null } = {}) {
  const result = explicitResult ?? liveOps?.latestUploadResult ?? currentSession?.latestUploadResult ?? {};
  const resolvedSnapshot = snapshot ?? liveOps?.latestUploadSnapshot ?? {};
  const analysis = result?.analysis_explanation ?? result?.analysis_result ?? result?.analysis ?? {};
  const coverage = deriveEvidenceCoverage(result, resolvedSnapshot);
  const gaps = deriveDataGaps(result, coverage);
  const relationships = collectRelationships(result, analysis);
  const baselineSufficient = deriveBaselineSufficiency(result, analysis, relationships);
  const siteIdentity = assignedSite(result, resolvedSnapshot, currentSession, liveOps);
  const rawFindings = asArray(analysis?.insights ?? result?.findings).filter(isActiveRawFinding);
  const canonicalRaw = canonicalAsRaw(canonicalFinding);
  const findingsSource = rawFindings.length ? rawFindings : (canonicalRaw ? [canonicalRaw] : []);
  const processing = /process|pending|queue|analyz/.test(firstText(resolvedSnapshot?.status, currentSession?.status).toLowerCase());
  const primarySystem = supportedLocationText(result?.system_name, analysis?.systems?.[0]?.name, liveOps?.primaryWindow?.label);
  const context = { result, evidenceIndex: analysis?.evidence_index ?? {}, relationships, coverage, gaps, processing, primarySystem, baselineSufficient, siteLocation: siteIdentity.location };
  const findings = consolidateFindings(findingsSource.map((raw, index) => buildFinding(raw, index, context)));
  const systems = asArray(analysis?.systems).length ? analysis.systems : asArray(liveOps?.systems);
  const subsystems = deriveSubsystems(systems, findings, relationships, siteIdentity.location);
  const hasAnalysis = Boolean(result && Object.keys(result).length);
  const evidenceQuality = findings[0]?.tier ?? deriveConfidenceTier({ explicit: result?.evidence_quality ?? result?.confidence_tier, coverage, evidenceCount: relationships.length || (hasAnalysis && baselineSufficient !== false ? 1 : 0), processing, baselineSufficient, reliable: result?.reliable !== false && result?.data_quality?.reliable !== false });
  const selectedFinding = findings[0] ?? null;
  const status = deriveSiteStatus(findings, hasAnalysis, baselineSufficient, coverage);
  const site = { id: String(result?.site_id ?? result?.adaptive_site_key ?? (siteIdentity.assigned ? siteIdentity.name.toLowerCase().replace(/[^a-z0-9]+/g, "-") : "unassigned-dataset")), name: siteIdentity.name, locationLabel: siteIdentity.location, assigned: siteIdentity.assigned, status, activeInvestigations: findings.length, evidenceQuality, coverage, lastMeaningfulChange: selectedFinding?.title ?? (status === "Normal" ? "No active findings" : "Evidence requirements not met") };
  const nodes = unique(relationships.flatMap((row) => [row.source, row.target])).map((label, index) => ({ id: label, label, kind: "signal", x: 16 + ((index * 31) % 70), y: 22 + ((index * 23) % 58) }));
  const timelineFrames = asArray(result?.replay_timeline?.timeline ?? result?.sii_intelligence?.replay_timeline?.timeline);
  return { result, site, sites: [site], status, findings, selectedFinding, subsystems, relationships, nodes, gaps, coverage, baselineSufficient, timelineFrames, evidenceQuality, domainLabel: humanize(domainDetection?.mode ?? result?.domain_detection?.mode ?? result?.detected_schema?.mode ?? "Infrastructure"), trace: buildTrace(selectedFinding, result), searchItems: buildSearchItems(site, subsystems, findings, nodes, analysis?.evidence_index), hasAnalysis, processing };
}
function buildSearchItems(site, subsystems, findings, nodes, evidenceIndex = {}) {
  return [
    { id: site.id, type: "Site", label: site.name, target: "site" },
    ...subsystems.map((item) => ({ id: item.id, type: "System", label: item.name, target: "system", systemName: item.name })),
    ...nodes.map((item) => ({ id: item.id, type: "Asset / signal", label: item.label, target: "evidence", nodeId: item.id, findingId: findings.find((finding) => finding.variables.includes(item.id))?.id })),
    ...findings.map((item) => ({ id: item.id, type: "Finding", label: item.title, target: "evidence", findingId: item.id })),
    ...Object.values(evidenceIndex ?? {}).map((item, index) => ({ id: item?.evidence_id ?? `evidence-${index}`, type: "Evidence", label: firstText(item?.description, item?.evidence_id, `Evidence ${index + 1}`), target: "evidence" })),
  ];
}

export function buildEngineeringReasoningModelsFromEvidenceRuns(runs = []) {
  const latestBySite = new Map();
  for (const run of asArray(runs)) {
    if (!run || typeof run !== "object") continue;
    const siteKey = String(run?.adaptive_site_key ?? run?.site_id ?? run?.site_name ?? run?.room ?? "unassigned-dataset").trim() || "unassigned-dataset";
    const prior = latestBySite.get(siteKey);
    const timestamp = new Date(run?.completed_at ?? run?.created_at ?? 0).getTime() || 0;
    const priorTimestamp = new Date(prior?.completed_at ?? prior?.created_at ?? 0).getTime() || 0;
    if (!prior || timestamp >= priorTimestamp) latestBySite.set(siteKey, run);
  }
  return [...latestBySite.entries()].map(([siteKey, run]) => {
    const active = !["resolved", "closed", "normal"].includes(String(run?.observation_status ?? "").toLowerCase());
    const evidence = asArray(run?.evidence_summary);
    const coverage = run?.rows_received ? Math.max(0, Math.min(1, Number(run?.rows_accepted ?? 0) / Number(run.rows_received))) : null;
    const result = { ...run, job_id: run?.run_id, facility_name: firstText(run?.site_name, run?.room), site_id: siteKey === "unassigned-dataset" ? undefined : siteKey, data_quality: { coverage, warnings: [...asArray(run?.warnings), ...asArray(run?.data_conditions)] }, analysis_explanation: { fingerprint: { status: run?.baseline_status }, systems: compact([{ id: run?.system_id, name: firstText(run?.system_name, run?.system_id) }]), insights: active && evidence.length ? [{ id: `evidence-${run.run_id}`, title: firstText(run?.finding_title, run?.historical_fact, evidence[0]), what_changed: evidence[0], why_it_matters: firstText(run?.potential_impact, run?.historical_fact), confidence_tier: run?.confidence_tier, system: firstText(run?.system_name, run?.system_id), subsystem: run?.subsystem_name, asset: run?.asset_name, variables: asArray(run?.variables), supporting_evidence: evidence, limitations: [...asArray(run?.warnings), ...asArray(run?.data_conditions)], operator_feedback_history: asArray(run?.operator_feedback_history) }] : [] } };
    return buildEngineeringReasoningModel({ result });
  });
}
