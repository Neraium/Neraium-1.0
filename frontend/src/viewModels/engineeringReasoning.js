import { normalizeFindingPresentation, sanitizeOperatorText } from "./operatorFinding";

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
const rawText = (value) => String(value ?? "").trim();

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

function sentences(value, maxSentences = 2, maxLength = 260) {
  const clean = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return "";
  const selected = clean.match(/[^.!?]+[.!?]?/g)?.map((item) => item.trim()).filter(Boolean).slice(0, maxSentences) ?? [clean];
  const text = selected.join(" ");
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
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

function displaySignalName(value) {
  let tokens = String(value || "").trim().toLowerCase().split(/[_\-\s]+/).filter(Boolean);
  if (["chw", "chilledwater"].includes(tokens[0]) && tokens.some((token) => ["return", "supply"].includes(token))) tokens = tokens.slice(1);
  else if (tokens[0] === "chw") tokens = ["chilled", "water", ...tokens.slice(1)];
  if (["a", "c", "f", "gpm", "hz", "kpa", "kw", "pct", "percent", "psi", "rpm", "v"].includes(tokens.at(-1))) tokens = tokens.slice(0, -1);
  const aliases = { temp: "temperature", amp: "current", amps: "current" };
  const label = tokens.map((token) => aliases[token] || token).join(" ");
  return label ? label[0].toUpperCase() + label.slice(1) : "";
}

function isOpaqueIdentity(value) {
  const text = rawText(value);
  return Boolean(text) && (/[_-]/.test(text) || /\d/.test(text)) && !/\s/.test(text);
}

function roleSignalLabel(value, index = 0) {
  const text = rawText(value).toLowerCase().replace(/[_-]+/g, " ");
  const roles = [
    [/approach.*temp|temp.*approach/, "Approach temperature signal"],
    [/return.*temp|temp.*return/, "Return temperature signal"],
    [/supply.*temp|temp.*supply/, "Supply temperature signal"],
    [/temperature|\btemp\b/, "Temperature signal"],
    [/pressure|\bpsi\b|\bkpa\b/, "Pressure signal"],
    [/flow|\bgpm\b/, "Flow signal"],
    [/current|\bamp|amper/, "Current signal"],
    [/power|\bkw\b/, "Power signal"],
    [/speed|\brpm\b|frequency|\bhz\b/, "Speed signal"],
    [/valve|position|command/, "Control signal"],
    [/turbidity|chlor|conductivity|\borp\b|\bph\b/, "Water-quality signal"],
  ];
  return roles.find(([pattern]) => pattern.test(text))?.[1] ?? `Signal ${String.fromCharCode(65 + Math.min(index, 25))}`;
}

export function buildFacilityLabelContext(payload = {}) {
  const signalLabels = {};
  const systemLabels = {};
  const equipmentLabels = {};
  for (const system of asArray(payload?.systems)) {
    const id = rawText(system?.system_id);
    const name = rawText(system?.display_name ?? system?.name ?? system?.label);
    if (id && name) systemLabels[id] = name;
  }
  for (const equipment of asArray(payload?.equipment)) {
    const id = rawText(equipment?.equipment_id);
    const name = rawText(equipment?.display_name ?? equipment?.name ?? equipment?.alias ?? equipment?.label);
    if (id && name) equipmentLabels[id] = name;
  }
  for (const mapping of asArray(payload?.signal_mappings)) {
    const alias = rawText(mapping?.alias);
    const rawTag = rawText(mapping?.raw_tag);
    const normalizedName = rawText(mapping?.normalized_name);
    if (alias) {
      if (rawTag) signalLabels[rawTag] = alias;
      if (normalizedName) signalLabels[normalizedName] = alias;
    }
    const equipmentId = rawText(mapping?.equipment_id);
    const subsystem = rawText(mapping?.subsystem);
    if (equipmentId && subsystem && !equipmentLabels[equipmentId]) equipmentLabels[equipmentId] = subsystem;
  }
  return { signalLabels, systemLabels, equipmentLabels, timeZone: rawText(payload?.timezone) };
}

function signalDisplayLabel(raw, explicit, labelContext, index) {
  const rawValue = rawText(raw);
  const mapped = rawText(explicit) || rawText(labelContext?.signalLabels?.[rawValue]);
  if (mapped && mapped !== rawValue) return mapped;
  if (rawValue && !isOpaqueIdentity(rawValue)) return rawValue;
  return roleSignalLabel(rawValue, index);
}

function mappedLocationLabel(value, labels = {}) {
  const rawValue = rawText(value);
  if (!rawValue) return "";
  return rawText(labels?.[rawValue]) || (!isOpaqueIdentity(rawValue) ? rawValue : "");
}

function readableRelationshipCopy(value, relationships = []) {
  let text = String(value || "");
  const byRawSignal = new Map(relationships.flatMap((item) => [[item?.rawSource, item?.source], [item?.rawTarget, item?.target]])
    .filter(([signal, label]) => signal && label && signal !== label));
  const signals = [...byRawSignal.entries()].sort(([left], [right]) => right.length - left.length);
  for (const [signal, label] of signals) {
    const escaped = signal.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    text = text.replace(new RegExp(`\\b${escaped}\\b`, "g"), label);
  }
  return maintenanceRelationshipLanguage(text);
}

function maintenanceRelationshipLanguage(value) {
  let text = String(value || "");
  text = text.replace(/\bevidence(?: support)? is strengthening\b/gi, "Evidence support is increasing");
  text = text.replace(/\bevidence(?: support)? is weakening\b/gi, "Evidence support is decreasing");
  const replacements = {
    strengthened: "increased",
    strengthening: "increasing",
    weakened: "decreased",
    weakening: "decreasing",
  };
  return text.replace(/\b(strengthened|strengthening|weakened|weakening)\b/gi, (match) => {
    const replacement = replacements[match.toLowerCase()];
    return /^[A-Z]/.test(match) ? replacement[0].toUpperCase() + replacement.slice(1) : replacement;
  });
}

function evidenceBoundedRelationshipTitle(raw, relationship, system) {
  if (!relationship) return "";
  const count = Number(raw?.relationship_count ?? raw?.corroboration?.relationship_count ?? 1);
  const direction = relationship.relationshipDirection || "shifted";
  if (count > 1 && system) return `${String(system).replace(/\s*&\s*/g, " and ").trim()} relationship ${direction}`;
  const pair = [displaySignalName(relationship.source), displaySignalName(relationship.target)].filter(Boolean).join(" / ");
  if (!pair) return "";
  return `${pair} relationship ${direction}`;
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
  return sentence(maintenanceRelationshipLanguage(text));
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

function relationshipLabel(row, index, source, target) {
  return firstText(row?.label, row?.name, row?.relationship, row?.description, source && target ? `${source} and ${target}` : "", `Relationship ${index + 1}`);
}

function edgeState(row) {
  const state = firstText(row?.change_type, row?.state, row?.status, row?.relationship_state).toLowerCase();
  if (/emerg|new|unusual/.test(state)) return "emerging";
  if (/weaken|drift|change|degrad|shift|diverg/.test(state)) return "changed";
  if (/histor|inactive/.test(state)) return "historical";
  if (/insufficient|unknown|missing/.test(state)) return "insufficient";
  return "normal";
}

function supportTrend(value, trajectory = {}) {
  const explicit = firstText(value).toLowerCase();
  if (["increasing", "stable", "decreasing"].includes(explicit)) return explicit;
  if (firstText(trajectory?.scope).toLowerCase() !== "evidence_support") return "";
  return ({ strengthening: "increasing", increasing: "increasing", stable: "stable", steady: "stable", weakening: "decreasing", decreasing: "decreasing" })[firstText(trajectory?.support_trend, trajectory?.state).toLowerCase()] ?? "";
}

function relationshipDirection(signedChange, absoluteChange, explicit) {
  const normalized = firstText(explicit).toLowerCase();
  if (["increased", "decreased", "shifted"].includes(normalized)) return normalized;
  if (signedChange !== null) return signedChange > 0 ? "increased" : signedChange < 0 ? "decreased" : "";
  return absoluteChange !== null && absoluteChange > 0 ? "shifted" : "";
}

function normalizeRelationship(row, index, evidenceIndex = {}, labelContext = {}) {
  const rawColumns = asArray(row?.columns);
  const displayColumns = asArray(row?.display_columns);
  const rawSource = rawText(row?.source ?? row?.source_tag ?? row?.source_id ?? rawColumns[0]);
  const rawTarget = rawText(row?.target ?? row?.target_tag ?? row?.target_id ?? rawColumns[1]);
  const source = signalDisplayLabel(rawSource, row?.source_display_name ?? row?.source_alias ?? row?.source_label ?? displayColumns[0], labelContext, 0);
  const target = signalDisplayLabel(rawTarget, row?.target_display_name ?? row?.target_alias ?? row?.target_label ?? displayColumns[1], labelContext, 1);
  const evidenceRefs = unique(asArray(row?.evidence_refs ?? row?.evidenceRefs));
  const evidence = compact([row?.evidence, ...evidenceRefs.map((ref) => evidenceIndex?.[ref])]).filter((item) => typeof item === "object");
  const comparison = row?.relationship_comparison ?? row?.relationshipComparison ?? {};
  const baseline = firstNumber(comparison?.baseline_value, row?.baseline_value, row?.baseline_strength, row?.baseline_correlation, row?.baseline, row?.statistics?.baseline_strength);
  const current = firstNumber(comparison?.current_value, row?.current_value, row?.current_strength, row?.current_correlation, row?.recent_correlation, row?.current, row?.statistics?.current_strength);
  let signedChange = firstNumber(comparison?.signed_change, row?.signed_change, row?.signed_correlation_delta, row?.statistics?.signed_change);
  if (signedChange === null && baseline !== null && current !== null) signedChange = current - baseline;
  let absoluteChange = firstNumber(comparison?.absolute_change, row?.absolute_change, row?.absolute_correlation_delta, row?.absolute_correlation_change, row?.calculated_delta, row?.correlation_delta, row?.delta, row?.statistics?.correlation_delta);
  if (signedChange !== null) absoluteChange = Math.abs(signedChange);
  else if (absoluteChange !== null) absoluteChange = Math.abs(absoluteChange);
  const direction = relationshipDirection(signedChange, absoluteChange, comparison?.direction ?? row?.relationship_direction);
  return { id: String(row?.id ?? row?.relationship_id ?? `relationship-${index}`), label: relationshipLabel(row, index, source, target), source, target, rawSource, rawTarget, metric: firstText(comparison?.metric, comparison?.metric_name, row?.metric_name, row?.metric, row?.statistic, "Relationship coefficient"), state: edgeState(row), changeType: firstText(row?.change_type, row?.state, row?.status, row?.relationship_state).toLowerCase(), baseline, current, signedChange, absoluteChange, relationshipDirection: direction, delta: absoluteChange, baselineSampleCount: firstNumber(comparison?.baseline_sample_size, row?.baseline_sample_size, row?.baseline_samples), currentSampleCount: firstNumber(comparison?.recent_sample_size, comparison?.current_sample_size, row?.recent_sample_size, row?.current_sample_size, row?.recent_samples), evidence, evidenceRefs, confidence: firstText(row?.confidence, row?.confidence_level, evidence[0]?.confidence), persistence: row?.persistence ?? null, supportTrend: supportTrend(row?.support_trend, row?.trajectory), windows: asArray(row?.source_time_ranges ?? row?.time_window ?? evidence[0]?.source_time_ranges) };
}

function siiProjection(result, analysis) {
  const projection = analysis?.sii_evidence ?? result?.analysis_result?.sii_evidence ?? result?.analysis_explanation?.sii_evidence;
  return projection && typeof projection === "object" && !Array.isArray(projection) ? projection : null;
}

function collectRelationships(result, analysis, labelContext) {
  const graphEdges = asArray(analysis?.relationship_graph?.edges ?? result?.relationship_model?.relationship_graph?.edges);
  const rows = [...asArray(analysis?.relationships), ...asArray(result?.baseline_analysis?.relationship_drift), ...graphEdges];
  const evidenceIndex = analysis?.evidence_index ?? {};
  const seen = new Set();
  return rows.map((row, index) => normalizeRelationship(row, index, evidenceIndex, labelContext)).filter((row) => { const key = row.id || row.label; if (seen.has(key)) return false; seen.add(key); return true; });
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
function hasSupportedClaimTransport(result) {
  const persistence = result?.evidence_persisted ?? result?.evidence_persistence?.persisted;
  const governed = result?.sii_reliable_enough_to_show !== undefined || persistence !== undefined;
  if (!governed) return true;
  return result?.sii_reliable_enough_to_show === true && persistence === true;
}
function isReliable(raw, result) {
  const explicit = raw?.reliable ?? raw?.finding_reliable ?? result?.reliable ?? result?.data_quality?.reliable;
  if (!hasSupportedClaimTransport(result)) return false;
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
  if (["Deferred", "Withheld"].includes(tier)) return "Evidence insufficient for reliable interpretation";
  const supplied = stripPeriod(firstText(raw?.headline, raw?.title, raw?.finding_title));
  const relationshipTitle = evidenceBoundedRelationshipTitle(raw, relationship, system);
  if (raw?.object_type === "condition" && relationshipTitle && /\bresponse\b|^connected relationships?|connected behavior/i.test(supplied)) return relationshipTitle;
  if (raw?.object_type === "condition" && supplied && supplied.length <= 96 && !MALFORMED_FINDING_TITLE.test(supplied) && !OVERSTATED_FINDING_TITLE.test(supplied)) return supplied;
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
  const rawRelationships = asArray(raw?.supporting_relationships ?? raw?.contributing_relationships ?? raw?.relationships);
  const localization = raw?.localization ?? {};
  const signalContext = [
    ...asArray(raw?.variables), ...asArray(raw?.affected_variables), ...asArray(raw?.affected_signals), ...asArray(raw?.supporting_signals),
    raw?.title, raw?.what_changed, raw?.observed_change,
    ...rawRelationships.flatMap((item) => [...asArray(item?.columns), ...asArray(item?.display_columns), item?.source, item?.target]),
  ];
  const inferredSystem = inferredOperationalArea(signalContext);
  const rawSystem = rawText(localization?.system ?? raw?.system ?? raw?.system_id ?? raw?.system_name ?? raw?.location?.system ?? asArray(raw?.affected_systems)[0] ?? context.primarySystem);
  const system = supportedLocationText(mappedLocationLabel(rawSystem, context.labelContext?.systemLabels), raw?.system_display_name, raw?.system_name) || inferredSystem || "Mapped system";
  const boundary = supportedLocationText(localization?.monitored_boundary, asArray(raw?.affected_boundaries)[0]);
  const subsystem = supportedLocationText(localization?.subsystem, raw?.subsystem, raw?.subsystem_name, raw?.location?.subsystem, boundary);
  const rawAsset = rawText(raw?.asset_id ?? raw?.equipment_id ?? raw?.asset ?? raw?.equipment ?? raw?.mapped_asset ?? raw?.location?.asset);
  const asset = raw?.object_type === "condition" ? "" : supportedLocationText(raw?.asset_name, raw?.equipment_name, mappedLocationLabel(rawAsset, context.labelContext?.equipmentLabels));
  const normalizedSubsystem = subsystem && subsystem !== system ? subsystem : "";
  const normalizedAsset = asset && asset !== normalizedSubsystem && asset !== system ? asset : "";
  const supportedHierarchy = unique([
    context.siteLocation,
    ...asArray(localization?.hierarchy).filter((item) => item?.supported && item?.level !== "site" && item?.level !== "signals").map((item) => item?.label),
    system,
    normalizedSubsystem,
    normalizedAsset,
  ]);
  const hierarchy = supportedHierarchy.length > 1 ? supportedHierarchy : [...supportedHierarchy, "Asset not identified"];
  return { site: context.siteLocation, system, subsystem: normalizedSubsystem, boundary, asset: normalizedAsset, likelyInvestigationArea: localization?.likely_investigation_area ?? boundary ?? normalizedSubsystem ?? system, hierarchy, label: hierarchy.join(" · "), rawSystem, rawAsset };
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
  const relatedRows = asArray(raw?.supporting_relationships ?? raw?.contributing_relationships ?? raw?.relationships).map((row, rowIndex) => normalizeRelationship(row, rowIndex, context.evidenceIndex, context.labelContext));
  const relationship = relatedRows[0] ?? context.relationships[0] ?? null;
  const evidenceRefs = unique(asArray(raw?.evidence_refs ?? raw?.evidenceRefs));
  const evidenceObjects = compact([...asArray(raw?.evidence ?? raw?.evidence_items), ...evidenceRefs.map((ref) => context.evidenceIndex?.[ref]), ...relatedRows.flatMap((row) => row.evidence)]);
  const rawSupporting = unique([...asArray(raw?.supporting_evidence), ...asArray(raw?.observed_facts), ...evidenceObjects.map(evidenceText)]
    .map(evidenceText)
    .map((item) => raw?.object_type === "condition" ? readableRelationshipCopy(item, relatedRows) : item));
  if (!rawSupporting.length && relationship && ["changed", "emerging"].includes(relationship.state)) rawSupporting.push(relationship.label + " moved outside its learned range.");
  const technicalLimitations = collectTechnicalLimitations(raw, context.result, context.gaps);
  const limitations = materialLimitations(raw, technicalLimitations, context.gaps);
  const contradictions = collectContradictions(raw);
  const rawVariables = unique([...asArray(raw?.variables), ...asArray(raw?.affected_variables), ...asArray(raw?.affected_signals), ...asArray(raw?.source_tags), ...asArray(raw?.supporting_signals), relationship?.rawSource, relationship?.rawTarget]);
  const variables = rawVariables.map((value, variableIndex) => signalDisplayLabel(value, "", context.labelContext, variableIndex));
  const tier = deriveConfidenceTier({ explicit: raw?.confidence_tier ?? raw?.confidence ?? raw?.confidence_state, coverage: context.coverage, evidenceCount: rawSupporting.length + evidenceObjects.length, limitations, contradictions, processing: context.processing, baselineSufficient: raw?.baseline_sufficient === false ? false : context.baselineSufficient, reliable: isReliable(raw, context.result) });
  const rawObservedChange = firstText(raw?.what_changed, raw?.observed_change, raw?.whatHappened, raw?.summary, raw?.title) || (relationship ? relationship.label + " moved outside its learned behavior." : "The available comparison indicates a change in measured behavior.");
  const observedChange = maintenanceRelationshipLanguage(raw?.object_type === "condition" ? readableRelationshipCopy(rawObservedChange, relatedRows) : rawObservedChange);
  const location = deriveLocation(raw, context);
  const titleContext = [variables, rawSupporting, relatedRows.map((item) => [item.label, item.source, item.target])];
  const title = specificFindingTitle(raw, observedChange, relationship, tier, location.system || location.subsystem, titleContext);
  const supporting = unique(rawSupporting.map((item) => formatPrimaryEvidence(item, titleContext)).filter(Boolean));
  const specificRecommendation = firstText(raw?.first_place_to_look, raw?.recommended_first_action, raw?.recommended_check, asArray(raw?.next_checks)[0], raw?.operator_check, raw?.recommended_action);
  const hasMappedContext = Boolean(location.system || location.subsystem || location.asset) && variables.length > 0;
  const prior = raw?.engineering_prior ?? raw?.relationship_prior ?? raw?.prior_contribution ?? null;
  const interpretationLevel = prior && hasMappedContext ? 1 : specificRecommendation && hasMappedContext ? 2 : relationship ? 3 : 4;
  const recommendationAllowed = !["Deferred", "Withheld"].includes(tier) && interpretationLevel <= 2;
  const whyItMatters = sentences(maintenanceRelationshipLanguage(firstText(raw?.why_it_matters, raw?.potential_impact, raw?.behavior_interpretation, raw?.interpretation))) || "Neraium flagged a difference between the learned baseline and the current comparison.";
  const primaryLimitation = limitations[0] || plainLimitation(contradictions[0]) || "";
  const status = ["Deferred", "Withheld"].includes(tier) ? "Evidence insufficient" : "Change detected";
  const confidenceContract = raw?.finding_confidence_v1 ?? raw?.classification?.finding_confidence_v1 ?? {};
  const legacyOperatingContext = confidenceContract?.operating_context ?? null;
  const operatingContextStatus = legacyOperatingContext?.status ?? ({
    high: "comparable",
    medium: "partially_comparable",
    low: "different_from_baseline",
    unknown: "not_enough_context",
  }[String(legacyOperatingContext?.level ?? "").toLowerCase()] || null);
  const evidenceSupportTrend = supportTrend(confidenceContract?.support_trend ?? raw?.support_trend, raw?.trajectory);
  const analyticalId = rawText(raw?.id ?? raw?.finding_id ?? "finding-" + index);
  const finding = {
    id: analyticalId,
    workflowFindingId: rawText(raw?.workflow_finding_id ?? raw?.canonical_finding_id),
    sourceFindingKey: rawText(raw?.source_finding_key ?? raw?.finding_key ?? analyticalId),
    title,
    status,
    system: location.subsystem || location.system || context.siteLocation,
    location,
    relatedAreas: [],
    observedChange: sentences(observedChange),
    whyItMatters,
    tier,
    confidenceReason: confidenceReason(tier, primaryLimitation),
    supporting,
    visibleSupporting: supporting.slice(0, 3),
    rawSupporting,
    contradictions,
    limitations,
    primaryLimitation,
    technicalLimitations,
    firstPlaceToLook: recommendationAllowed ? specificRecommendation : "",
    confirmationCriteria: firstText(raw?.confirmation_criteria, raw?.confirm_or_rule_out, raw?.expected_confirmation),
    comparison: deriveComparison(raw, relationship, context.result),
    comparisonSummary: comparisonSummary(relationship),
    relationships: relatedRows.length ? relatedRows : (relationship ? [relationship] : []),
    variables,
    rawVariables,
    technicalIdentity: {
      findingId: analyticalId,
      workflowFindingId: rawText(raw?.workflow_finding_id ?? raw?.canonical_finding_id),
      systemId: location.rawSystem,
      assetId: location.rawAsset,
    },
    engineeringPrior: prior,
    interpretationLevel,
    recommendationAllowed,
    evidenceObjects,
    outcome: asArray(raw?.operator_feedback_history)[0] ?? null,
    caseState: firstText(raw?.observation_status, raw?.case_state),
    caseHistory: asArray(raw?.finding_status_history),
    classification: raw?.classification,
    objectType: raw?.object_type ?? (raw?.condition_id ? "condition" : "finding"),
    conditionId: firstText(raw?.condition_id, raw?.id),
    titleScope: firstText(raw?.title_scope),
    titleEvidenceRelationshipId: firstText(raw?.title_evidence_relationship_id),
    confidence: raw?.confidence,
    confidenceScore: firstNumber(raw?.confidence_score),
    confidenceContract,
    confidenceDimensions: {
      changeDetection: confidenceContract?.change_detection ?? null,
      interpretation: confidenceContract?.interpretation ?? null,
      operatingContext: legacyOperatingContext ? { ...legacyOperatingContext, status: operatingContextStatus } : null,
      evidenceQuality: confidenceContract?.evidence_quality ?? null,
    },
    supportTrend: evidenceSupportTrend,
    relationshipDirection: relationship?.relationshipDirection ?? "",
    trajectory: raw?.trajectory ?? {},
    corroboration: raw?.corroboration ?? {
      corroboration_strength: raw?.corroboration_strength,
      relationship_count: raw?.relationship_count,
    },
    comparableOperation: raw?.comparable_operation ?? {},
    affectedBoundaries: asArray(raw?.affected_boundaries),
    conflictingRelationships: asArray(raw?.conflicting_relationships),
    uncertainRelationships: asArray(raw?.uncertain_relationships),
    escalation: raw?.escalation ?? {},
    dataConfidence: raw?.data_confidence ?? raw?.dataConfidence,
    operatingMode: raw?.operating_mode ?? raw?.operatingMode,
    sensorHealth: raw?.sensor_health ?? raw?.sensorHealth,
    certaintyLimit: firstText(raw?.certainty_limit, raw?.certaintyLimit),
    alternativeExplanations: raw?.alternative_explanations ?? raw?.alternativeExplanations ?? [],
    dataLimitations: raw?.data_limitations ?? raw?.dataLimitations ?? [],
    persistence: raw?.persistence ?? confidenceContract?.persistence,
    relationshipEvidence: raw?.relationship_evidence ?? raw?.relationshipEvidence,
    investigationGuidance: raw?.investigation_guidance ?? raw?.investigationGuidance ?? [],
    recommendedInvestigation: (Array.isArray(raw?.recommended_investigation ?? raw?.recommendedInvestigation ?? raw?.next_checks)
      ? (raw?.recommended_investigation ?? raw?.recommendedInvestigation ?? raw?.next_checks)
      : compact([raw?.recommended_investigation ?? raw?.recommendedInvestigation ?? raw?.next_checks]))
      .map((item) => sentence(item, 140)).filter(Boolean).slice(0, 3),
    recommendedFirstAction: recommendationAllowed ? specificRecommendation : "",
    activityTimeline: asArray(raw?.timeline ?? raw?.activity_timeline ?? raw?.activityTimeline),
    sourceTimeRanges: asArray(raw?.source_time_ranges ?? raw?.sourceTimeRanges),
    firstDetectedAt: firstText(raw?.first_detected_at, raw?.firstDetectedAt),
    generatedAt: firstText(raw?.generated_at, raw?.generatedAt, context.result?.completed_at, context.result?.processed_at),
    siiEvidence: context.siiEvidence,
  };
  finding.classificationPresentation = normalizeFindingPresentation(finding);
  return finding;
}

function evidenceKey(value) {
  const text = String(value || "").toLowerCase().replace(/[^a-z0-9.%]+/g, " ").trim();
  if (/relationship|coupling|learned range|learned behavior/.test(text)) return "relationship-change";
  return text;
}
function findingsOverlap(left, right) {
  if (left.classificationPresentation.type !== right.classificationPresentation.type) return false;
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
  const title = primary.objectType === "condition"
    ? primary.title
    : operationalTitleFromContext([variables, evidence.all, areas], inferredSystem);
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
  const named = raw?.relationship_comparison ?? raw?.finding_confidence_v1?.relationship_comparison ?? raw?.classification?.finding_confidence_v1?.relationship_comparison ?? {};
  const baselineValue = firstNumber(named?.baseline_value, relationship?.baseline);
  const currentValue = firstNumber(named?.current_value, relationship?.current);
  let signedChange = firstNumber(named?.signed_change, relationship?.signedChange);
  if (signedChange === null && baselineValue !== null && currentValue !== null) signedChange = currentValue - baselineValue;
  let absoluteChange = firstNumber(named?.absolute_change, relationship?.absoluteChange, relationship?.delta);
  if (signedChange !== null) absoluteChange = Math.abs(signedChange);
  const direction = relationshipDirection(signedChange, absoluteChange, named?.direction ?? relationship?.relationshipDirection);
  return { baseline: firstText(window?.baseline_label, joinWindow(window?.baseline_start, window?.baseline_end), result?.baseline_window, "Learned baseline"), current: firstText(window?.current_label, joinWindow(window?.current_start, window?.current_end), result?.comparison_window, "Current comparison"), metric: firstText(named?.metric), baselineValue, currentValue, signedChange, absoluteChange, direction, formula: firstText(named?.formula), delta: absoluteChange };
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
  return { assigned: false, name: "Current facility", location: "Facility context not assigned" };
}
function deriveSiteStatus(findings, hasAnalysis, baselineSufficient, coverage) {
  if (findings.some((finding) => finding.status === "Change detected")) return "Change detected";
  if (findings.length || !hasAnalysis || baselineSufficient === false || (coverage !== null && coverage < 0.5)) return "Evidence insufficient";
  return "Normal";
}

export function buildEngineeringReasoningModel({ liveOps = {}, canonicalFinding = null, currentSession = null, result: explicitResult = null, snapshot = null, domainDetection = null, labelContext = {} } = {}) {
  const result = explicitResult ?? liveOps?.latestUploadResult ?? currentSession?.latestUploadResult ?? {};
  const resolvedSnapshot = snapshot ?? liveOps?.latestUploadSnapshot ?? {};
  const analysis = result?.analysis_explanation ?? result?.analysis_result ?? result?.analysis ?? {};
  const siiEvidence = siiProjection(result, analysis);
  const coverage = deriveEvidenceCoverage(result, resolvedSnapshot);
  const gaps = deriveDataGaps(result, coverage);
  const relationships = collectRelationships(result, analysis, labelContext);
  const baselineSufficient = deriveBaselineSufficiency(result, analysis, relationships);
  const siteIdentity = assignedSite(result, resolvedSnapshot, currentSession, liveOps);
  const analysisConditions = asArray(analysis?.conditions);
  const rawConditions = (analysisConditions.length ? analysisConditions : asArray(result?.conditions)).filter(isActiveRawFinding);
  const rawFindings = asArray(analysis?.insights ?? result?.findings).filter(isActiveRawFinding);
  const canonicalRaw = canonicalAsRaw(canonicalFinding);
  const findingsSource = rawConditions.length ? rawConditions : rawFindings.length ? rawFindings : (canonicalRaw ? [canonicalRaw] : []);
  const processing = /process|pending|queue|analyz/.test(firstText(resolvedSnapshot?.status, currentSession?.status).toLowerCase());
  const rawPrimarySystem = rawText(result?.system_id ?? analysis?.systems?.[0]?.id);
  const primarySystem = supportedLocationText(result?.system_name, analysis?.systems?.[0]?.name, mappedLocationLabel(rawPrimarySystem, labelContext?.systemLabels), liveOps?.primaryWindow?.label);
  const context = { result, siiEvidence, evidenceIndex: analysis?.evidence_index ?? {}, relationships, coverage, gaps, processing, primarySystem, baselineSufficient, siteLocation: siteIdentity.location, labelContext };
  const findings = rawConditions.length
    ? findingsSource.map((raw, index) => buildFinding(raw, index, context))
    : consolidateFindings(findingsSource.map((raw, index) => buildFinding(raw, index, context)));
  const systems = asArray(analysis?.systems).length ? analysis.systems : asArray(liveOps?.systems);
  const subsystems = deriveSubsystems(systems, findings, relationships, siteIdentity.location);
  const hasAnalysis = Boolean(result && Object.keys(result).length);
  const reliableEnoughToShow = hasSupportedClaimTransport(result);
  const evidenceQuality = findings[0]?.tier ?? deriveConfidenceTier({ explicit: result?.evidence_quality ?? result?.confidence_tier, coverage, evidenceCount: relationships.length || (hasAnalysis && baselineSufficient !== false ? 1 : 0), processing, baselineSufficient, reliable: reliableEnoughToShow && result?.reliable !== false && result?.data_quality?.reliable !== false });
  const selectedFinding = findings[0] ?? null;
  const status = reliableEnoughToShow ? deriveSiteStatus(findings, hasAnalysis, baselineSufficient, coverage) : "Evidence insufficient";
  const site = { id: String(result?.site_id ?? result?.adaptive_site_key ?? (siteIdentity.assigned ? siteIdentity.name.toLowerCase().replace(/[^a-z0-9]+/g, "-") : "unassigned-dataset")), name: siteIdentity.name, locationLabel: siteIdentity.location, assigned: siteIdentity.assigned, status, activeInvestigations: findings.length, evidenceQuality, coverage, lastMeaningfulChange: selectedFinding?.title ?? (status === "Normal" ? "No active findings" : "Evidence requirements not met") };
  const nodes = unique(relationships.flatMap((row) => [row.source, row.target])).map((label, index) => ({ id: label, label, kind: "signal", x: 16 + ((index * 31) % 70), y: 22 + ((index * 23) % 58) }));
  const timelineFrames = asArray(result?.replay_timeline?.timeline ?? result?.sii_intelligence?.replay_timeline?.timeline);
  return { result, siiEvidence, site, sites: [site], status, findings, selectedFinding, subsystems, relationships, nodes, gaps, coverage, baselineSufficient, reliableEnoughToShow, timelineFrames, evidenceQuality, facilityTimeZone: labelContext?.timeZone || "", domainLabel: humanize(domainDetection?.mode ?? result?.domain_detection?.mode ?? result?.detected_schema?.mode ?? "Infrastructure"), trace: buildTrace(selectedFinding, result), searchItems: buildSearchItems(site, subsystems, findings, nodes, analysis?.evidence_index), hasAnalysis, processing };
}
function buildSearchItems(site, subsystems, findings, nodes, evidenceIndex = {}) {
  return [
    { id: site.id, type: "Site", label: site.name, target: "site" },
    ...subsystems.map((item) => ({ id: item.id, type: "System", label: item.name, target: "system", systemName: item.name })),
    ...nodes.map((item) => ({ id: item.id, type: "Asset / signal", label: item.label, target: "evidence", nodeId: item.id, findingId: findings.find((finding) => finding.variables.includes(item.id))?.id })),
    ...findings.map((item) => ({ id: item.id, type: item.objectType === "condition" ? "Condition" : "Finding", label: item.title, target: "evidence", findingId: item.id })),
    ...Object.values(evidenceIndex ?? {}).map((item, index) => ({ id: item?.evidence_id ?? `evidence-${index}`, type: "Evidence", label: firstText(item?.description, item?.evidence_id, `Evidence ${index + 1}`), target: "evidence" })),
  ];
}

export function buildEngineeringReasoningModelsFromEvidenceRuns(runs = [], labelContext = {}) {
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
    const active = !["resolved", "dismissed", "closed", "normal"].includes(String(run?.observation_status ?? "").toLowerCase());
    const evidence = asArray(run?.evidence_summary);
    const coverage = run?.rows_received ? Math.max(0, Math.min(1, Number(run?.rows_accepted ?? 0) / Number(run.rows_received))) : null;
    const persistedCondition = run?.condition && typeof run.condition === "object"
      ? { ...run.condition, observation_status: run?.observation_status, finding_status_history: asArray(run?.finding_status_history), supporting_evidence: asArray(run.condition.supporting_evidence).length ? run.condition.supporting_evidence : evidence, operator_feedback_history: asArray(run?.operator_feedback_history) }
      : null;
    const result = { ...run, job_id: run?.run_id, facility_name: firstText(run?.site_name, run?.room), site_id: siteKey === "unassigned-dataset" ? undefined : siteKey, data_quality: { coverage, warnings: [...asArray(run?.warnings), ...asArray(run?.data_conditions)] }, analysis_explanation: { fingerprint: { status: run?.baseline_status }, systems: compact([{ id: run?.system_id, name: firstText(run?.system_name, run?.system_id) }]), conditions: active && persistedCondition ? [persistedCondition] : [], insights: active && !persistedCondition && evidence.length ? [{ id: `evidence-${run.run_id}`, title: firstText(run?.finding_title, run?.historical_fact, evidence[0]), what_changed: evidence[0], why_it_matters: firstText(run?.potential_impact, run?.historical_fact), confidence_tier: run?.confidence_tier, system: firstText(run?.system_name, run?.system_id), subsystem: run?.subsystem_name, asset: run?.asset_name, variables: asArray(run?.variables), supporting_evidence: evidence, limitations: [...asArray(run?.warnings), ...asArray(run?.data_conditions)], operator_feedback_history: asArray(run?.operator_feedback_history) }] : [] } };
    return buildEngineeringReasoningModel({ result, labelContext });
  });
}
