import { sanitizeOperatorText } from "./operatorFinding";

export const CONFIDENCE_TIERS = ["Confirmed", "Qualified", "Narrowed", "Deferred", "Withheld"];

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

export function deriveConfidenceTier({ explicit, coverage, evidenceCount, limitations = [], contradictions = [], processing = false }) {
  const normalized = String(explicit ?? "").trim().toLowerCase();
  const completeness = Number.isFinite(Number(coverage)) ? Number(coverage) : null;
  if (CONFIDENCE_TIERS.some((tier) => tier.toLowerCase() === normalized)) {
    const tier = CONFIDENCE_TIERS.find((item) => item.toLowerCase() === normalized);
    if (tier === "Confirmed" && ((completeness !== null && completeness < 0.95) || limitations.length || contradictions.length)) return "Qualified";
    return tier;
  }
  if (processing) return "Deferred";
  if (!evidenceCount || (completeness !== null && completeness < 0.5) || contradictions.length > evidenceCount) return "Withheld";
  if (completeness !== null && completeness < 0.75) return "Narrowed";
  if (/defer|pending|delay|incomplete/.test(normalized)) return "Deferred";
  if (/low|weak|developing|narrow/.test(normalized)) return "Narrowed";
  // Legacy high/100% scores do not establish the complete context required for Confirmed.
  return "Qualified";
}

export function deriveEvidenceCoverage(result = {}, snapshot = {}) {
  const integrity = result?.sii_intelligence?.telemetry_integrity ?? result?.telemetry_integrity ?? {};
  const signalIntegrity = asArray(integrity?.signal_integrity);
  const signalCoverage = signalIntegrity
    .map((item) => firstNumber(item?.completeness, item?.coverage, item?.coverage_percent))
    .filter(Number.isFinite)
    .map((value) => value > 1 ? value / 100 : value);
  if (signalCoverage.length) return Math.max(0, Math.min(1, signalCoverage.reduce((sum, value) => sum + value, 0) / signalCoverage.length));

  const quality = result?.data_quality ?? result?.quality ?? {};
  const direct = firstNumber(
    quality?.coverage,
    quality?.coverage_percent,
    quality?.completeness,
    result?.data_coverage,
    snapshot?.data_coverage,
  );
  if (direct !== null) return Math.max(0, Math.min(1, direct > 1 ? direct / 100 : direct));

  const received = firstNumber(result?.rows_received, snapshot?.rows_received, result?.row_count, snapshot?.row_count);
  const accepted = firstNumber(result?.rows_accepted, snapshot?.rows_accepted, result?.row_count, snapshot?.row_count);
  if (received && accepted !== null) return Math.max(0, Math.min(1, accepted / received));
  return null;
}

function normalizeGap(item, index) {
  if (typeof item === "string") {
    return { id: `gap-${index}`, source: item, start: null, end: null, duration: "Duration not supplied", signals: [], coverageImpact: null, overlapsChange: null };
  }
  return {
    id: String(item?.id ?? item?.gap_id ?? `gap-${index}`),
    source: firstText(item?.source, item?.source_name, item?.historian, item?.label, "Telemetry source"),
    start: item?.start ?? item?.start_at ?? item?.timestamp_start ?? null,
    end: item?.end ?? item?.end_at ?? item?.timestamp_end ?? null,
    duration: firstText(item?.duration, item?.missing_duration, "Duration not supplied"),
    signals: unique(asArray(item?.signals ?? item?.affected_signals ?? item?.columns)),
    coverageImpact: firstNumber(item?.coverage_impact, item?.coverage_percent),
    overlapsChange: typeof item?.overlaps_change_window === "boolean" ? item.overlaps_change_window : null,
  };
}

export function deriveDataGaps(result = {}, coverage = null) {
  const quality = result?.data_quality ?? {};
  const explicit = [
    ...asArray(result?.data_gaps),
    ...asArray(quality?.data_gaps),
    ...asArray(result?.sii_intelligence?.telemetry_integrity?.data_gaps),
  ];
  const missing = unique([
    ...asArray(quality?.missing_recent_values),
    ...asArray(quality?.missing_columns),
    ...asArray(result?.data_conditions),
  ]);
  const gaps = explicit.map(normalizeGap);
  if (!gaps.length && missing.length) {
    gaps.push(normalizeGap({ source: firstText(result?.source_name, result?.filename, "Telemetry source"), signals: missing }, 0));
  }
  if (!gaps.length && coverage !== null && coverage < 1) {
    gaps.push(normalizeGap({ source: firstText(result?.source_name, result?.filename, "Telemetry source"), coverage_impact: Math.round(coverage * 100) }, 0));
  }
  return gaps;
}

function relationshipLabel(row, index) {
  const columns = unique([
    ...asArray(row?.columns),
    ...asArray(row?.display_columns),
    row?.source_label,
    row?.target_label,
    row?.source,
    row?.target,
  ]);
  return firstText(row?.label, row?.name, row?.relationship, row?.description, columns.length >= 2 ? `${columns[0]} ↔ ${columns[1]}` : "", `Relationship ${index + 1}`);
}

function edgeState(row) {
  const state = firstText(row?.change_type, row?.state, row?.status, row?.relationship_state).toLowerCase();
  if (/emerg|new|unusual/.test(state)) return "emerging";
  if (/weaken|drift|change|degrad|shift|diverg/.test(state)) return "weakening";
  if (/histor|inactive/.test(state)) return "historical";
  if (/insufficient|unknown|missing/.test(state)) return "insufficient";
  return "stable";
}

function normalizeRelationship(row, index, evidenceIndex = {}) {
  const columns = unique([
    ...asArray(row?.columns),
    ...asArray(row?.display_columns),
    row?.source_label,
    row?.target_label,
    row?.source,
    row?.target,
  ]);
  const source = columns[0] || `signal-${index + 1}-a`;
  const target = columns[1] || `signal-${index + 1}-b`;
  const evidenceRefs = unique(asArray(row?.evidence_refs ?? row?.evidenceRefs));
  const evidence = compact([
    row?.evidence,
    ...evidenceRefs.map((ref) => evidenceIndex?.[ref]),
  ]).filter((item) => typeof item === "object");
  return {
    id: String(row?.id ?? row?.relationship_id ?? `relationship-${index}`),
    label: relationshipLabel(row, index),
    source,
    target,
    state: edgeState(row),
    baseline: firstNumber(row?.baseline_strength, row?.baseline, row?.statistics?.baseline_strength),
    current: firstNumber(row?.current_strength, row?.current, row?.statistics?.current_strength),
    delta: firstNumber(row?.calculated_delta, row?.correlation_delta, row?.delta, row?.statistics?.correlation_delta),
    evidence,
    confidence: firstText(row?.confidence, evidence[0]?.confidence),
    windows: asArray(row?.source_time_ranges ?? evidence[0]?.source_time_ranges),
  };
}

function collectRelationships(result, analysis) {
  const graphEdges = asArray(analysis?.relationship_graph?.edges ?? result?.relationship_model?.relationship_graph?.edges);
  const rows = [
    ...asArray(analysis?.relationships),
    ...asArray(result?.baseline_analysis?.relationship_drift),
    ...graphEdges,
  ];
  const evidenceIndex = analysis?.evidence_index ?? {};
  const seen = new Set();
  return rows.map((row, index) => normalizeRelationship(row, index, evidenceIndex)).filter((row) => {
    const key = row.id || row.label;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function evidenceText(item) {
  if (typeof item === "string") return sanitizeOperatorText(item);
  return firstText(item?.description, item?.summary, item?.observation, item?.value);
}

function collectLimitations(raw, result, gaps) {
  return unique([
    ...asArray(raw?.limitations),
    ...asArray(raw?.confidence_decrease_factors),
    ...asArray(result?.data_quality?.warnings),
    ...asArray(result?.warnings),
    ...gaps.map((gap) => `Evidence is incomplete for ${gap.source}${gap.duration ? ` (${gap.duration})` : ""}.`),
  ].map(evidenceText));
}

function collectContradictions(raw) {
  return unique([
    ...asArray(raw?.contradicting_evidence),
    ...asArray(raw?.contradictions),
    ...asArray(raw?.counter_evidence),
    ...asArray(raw?.confounders),
  ].map(evidenceText));
}

function buildFinding(raw, index, context) {
  const relatedRows = asArray(raw?.contributing_relationships ?? raw?.relationships).map((row, rowIndex) => normalizeRelationship(row, rowIndex, context.evidenceIndex));
  const evidenceRefs = unique(asArray(raw?.evidence_refs ?? raw?.evidenceRefs));
  const evidenceObjects = compact([
    ...asArray(raw?.evidence ?? raw?.evidence_items),
    ...evidenceRefs.map((ref) => context.evidenceIndex?.[ref]),
    ...relatedRows.flatMap((row) => row.evidence),
  ]);
  const supporting = unique([
    ...asArray(raw?.supporting_evidence),
    ...asArray(raw?.observed_facts),
    ...evidenceObjects.map(evidenceText),
  ].map(evidenceText)).slice(0, 4);
  const limitations = collectLimitations(raw, context.result, context.gaps);
  const contradictions = collectContradictions(raw);
  const tier = deriveConfidenceTier({
    explicit: raw?.confidence_tier ?? raw?.confidence ?? raw?.confidence_state,
    coverage: context.coverage,
    evidenceCount: supporting.length + evidenceObjects.length,
    limitations,
    contradictions,
    processing: context.processing,
  });
  const relationship = relatedRows[0] ?? context.relationships[0] ?? null;
  const variables = unique([
    ...asArray(raw?.variables),
    ...asArray(raw?.affected_variables),
    ...asArray(raw?.supporting_signals),
    relationship?.source,
    relationship?.target,
  ]);
  const specificRecommendation = firstText(
    raw?.first_place_to_look,
    raw?.recommended_first_action,
    raw?.recommended_check,
    raw?.operator_check,
    raw?.recommended_action,
  );
  const hasMappedContext = Boolean(raw?.system || raw?.subsystem) && variables.length > 0;
  const prior = raw?.engineering_prior ?? raw?.relationship_prior ?? raw?.prior_contribution ?? null;
  const interpretationLevel = prior && hasMappedContext ? 1 : specificRecommendation && hasMappedContext ? 2 : relationship ? 3 : 4;
  const recommendationAllowed = tier !== "Withheld" && interpretationLevel <= 2;
  const observedChange = firstText(raw?.what_changed, raw?.observed_change, raw?.whatHappened, raw?.summary, raw?.title);
  const whyItMatters = firstText(raw?.why_it_matters, raw?.potential_impact, raw?.behavior_interpretation, raw?.interpretation);
  const confirmation = firstText(raw?.confirmation_criteria, raw?.confirm_or_rule_out, raw?.expected_confirmation);
  return {
    id: String(raw?.id ?? raw?.finding_id ?? `finding-${index}`),
    title: firstText(raw?.title, raw?.summary, observedChange, "Operational finding"),
    system: firstText(raw?.subsystem, raw?.system, context.primarySystem, "Mapped system"),
    observedChange: observedChange || "A measured relationship changed from the available learned baseline.",
    whyItMatters: whyItMatters || (relationship ? "The changed relationship may alter how this subsystem responds under comparable operating conditions." : "Available evidence does not support a more specific engineering interpretation."),
    tier,
    supporting,
    contradictions,
    limitations,
    firstPlaceToLook: recommendationAllowed ? specificRecommendation : "",
    confirmationCriteria: confirmation || (relationship ? `Compare ${relationship.label} under a comparable operating mode. A return to its learned range would weaken this interpretation.` : "Additional mapped relationship evidence is required before a confirmation test can be stated."),
    comparison: deriveComparison(raw, relationship, context.result),
    relationships: relatedRows.length ? relatedRows : (relationship ? [relationship] : []),
    variables,
    engineeringPrior: prior,
    interpretationLevel,
    recommendationAllowed,
    evidenceObjects,
    outcome: asArray(raw?.operator_feedback_history)[0] ?? null,
  };
}

function deriveComparison(raw, relationship, result) {
  const window = asArray(raw?.source_time_ranges)[0] ?? relationship?.windows?.[0] ?? {};
  return {
    baseline: firstText(window?.baseline_label, joinWindow(window?.baseline_start, window?.baseline_end), result?.baseline_window, "Learned baseline"),
    current: firstText(window?.current_label, joinWindow(window?.current_start, window?.current_end), result?.comparison_window, "Current evidence window"),
  };
}

function joinWindow(start, end) {
  if (!start && !end) return "";
  return [start, end].filter(Boolean).join(" to ");
}

function canonicalAsRaw(canonicalFinding) {
  if (!canonicalFinding?.exists) return null;
  return {
    id: canonicalFinding.id,
    title: canonicalFinding.summary,
    summary: canonicalFinding.summary,
    why_it_matters: canonicalFinding.whyItMatters,
    confidence: canonicalFinding.confidence,
    recommended_check: canonicalFinding.reviewNext,
    supporting_evidence: canonicalFinding.supportingEvidence,
    variables: canonicalFinding.affectedVariables,
  };
}

function deriveSubsystems(systems, findings, relationships) {
  const names = unique([
    ...asArray(systems).map((item) => firstText(item?.name, item?.label)),
    ...findings.map((finding) => finding.system),
  ]);
  return names.map((name, index) => {
    const owned = findings.filter((finding) => finding.system === name);
    const active = owned.filter((finding) => finding.tier !== "Withheld");
    const withheld = owned.filter((finding) => finding.tier === "Withheld");
    const state = active.length ? "Investigate" : withheld.length ? "Evidence insufficient" : relationships.length ? "Stable" : "Monitor";
    return {
      id: `subsystem-${index}`,
      name,
      state,
      findingCount: owned.length,
      explanation: owned[0]?.observedChange || (relationships.length ? "Mapped relationships remain within the available comparison context." : "A learned relationship baseline has not been established."),
      evidenceTier: owned[0]?.tier ?? (relationships.length ? "Qualified" : "Deferred"),
    };
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
    { type: "Derived feature", source: "SII Engine", transformation: "Relationship feature derivation", input: finding.variables.join(", ") || "Normalized signals", output: relationship?.label ?? "No supported relationship feature", timestamp, classification: "Derived", version: result?.engine_version ?? "Not supplied" },
    { type: "Relationship", source: "Learned baseline", transformation: "Baseline/current comparison", input: relationship?.label ?? "Available evidence", output: relationship ? `${humanize(relationship.state)} relationship state` : "Relationship evidence insufficient", timestamp, classification: "Inferred", version: result?.baseline_version ?? "Not supplied" },
    { type: "Drift detection", source: "SII Engine", transformation: "Structural change evaluation", input: relationship?.label ?? finding.observedChange, output: finding.observedChange, timestamp, classification: "Derived", version: result?.model_version ?? "Not supplied" },
    { type: "Engineering interpretation", source: finding.engineeringPrior ? "Approved engineering prior" : "Bounded SII interpretation", transformation: finding.engineeringPrior ? "Conditional prior application" : "Evidence-bounded interpretation", input: finding.observedChange, output: finding.whyItMatters, timestamp, classification: finding.engineeringPrior ? "Configured / inferred" : "Inferred", version: result?.prior_version ?? "Not applicable" },
    { type: "Finding", source: "Neraium reasoning layer", transformation: "Confidence and limitations bounding", input: finding.whyItMatters, output: `${finding.tier}: ${finding.title}`, timestamp, classification: "Conclusion", version: result?.schema_version ?? "Not supplied" },
    { type: "Recommendation", source: "Investigation guidance", transformation: "Supported next-inspection selection", input: finding.title, output: finding.recommendationAllowed ? finding.firstPlaceToLook : "No specific operational recommendation presented", timestamp, classification: finding.recommendationAllowed ? "Inferred" : "Withheld", version: "Read-only" },
  ].map((step, index) => ({ ...step, id: `trace-${index}`, governance: firstText(result?.governance_statement, result?.governance_boundary?.statement, "Persisted within the configured evidence boundary"), confidenceContribution: index >= 5 ? finding.tier : "Contributing evidence" }));
}

export function buildEngineeringReasoningModel({ liveOps = {}, canonicalFinding = null, currentSession = null, result: explicitResult = null, snapshot = null, domainDetection = null } = {}) {
  const result = explicitResult ?? liveOps?.latestUploadResult ?? currentSession?.latestUploadResult ?? {};
  const analysis = result?.analysis_explanation ?? result?.analysis_result ?? result?.analysis ?? {};
  const coverage = deriveEvidenceCoverage(result, snapshot ?? liveOps?.latestUploadSnapshot ?? {});
  const gaps = deriveDataGaps(result, coverage);
  const relationships = collectRelationships(result, analysis);
  const rawFindings = asArray(analysis?.insights ?? result?.findings);
  const canonicalRaw = canonicalAsRaw(canonicalFinding);
  const findingsSource = rawFindings.length ? rawFindings : (canonicalRaw ? [canonicalRaw] : []);
  const processing = /process|pending|queue|analyz/.test(firstText(snapshot?.status, currentSession?.status).toLowerCase());
  const primarySystem = firstText(result?.system_name, liveOps?.primaryWindow?.label, analysis?.systems?.[0]?.name, "Mapped infrastructure");
  const context = { result, evidenceIndex: analysis?.evidence_index ?? {}, relationships, coverage, gaps, processing, primarySystem };
  const findings = findingsSource.map((raw, index) => buildFinding(raw, index, context));
  const systems = asArray(analysis?.systems).length ? analysis.systems : asArray(liveOps?.systems);
  const subsystems = deriveSubsystems(systems, findings, relationships);
  const siteName = firstText(result?.facility_name, snapshot?.facility_name, currentSession?.facilityName, liveOps?.facilityName, "Current site");
  const drift = firstNumber(result?.drift_metrics?.baseline_distance, result?.drift_metrics?.drift_index, result?.sii_intelligence?.instability_index);
  const stability = firstNumber(result?.structural_stability, result?.sii_intelligence?.structural_stability, drift !== null ? Math.max(0, 1 - Math.min(1, Math.abs(drift))) : null);
  const stabilityPercent = stability === null ? null : Math.round((stability > 1 ? stability / 100 : stability) * 100);
  const evidenceQuality = findings[0]?.tier ?? (coverage === null ? "Deferred" : coverage < 0.5 ? "Withheld" : "Qualified");
  const governance = result?.governance_boundary ?? result?.distributed_cognition_governance ?? result?.sii_intelligence?.distributed_cognition_governance ?? {};
  const governanceStatement = [governance?.data_residency_statement, governance?.statement, governance?.policy_statement].find((value) => typeof value === "string" && value.trim())?.trim() || "Evidence handling follows the configured site governance policy.";
  const selectedFinding = findings[0] ?? null;
  const nodes = unique(relationships.flatMap((row) => [row.source, row.target])).map((label, index) => ({ id: label, label, kind: "signal", x: 16 + ((index * 31) % 70), y: 22 + ((index * 23) % 58) }));
  const timelineFrames = asArray(result?.replay_timeline?.timeline ?? result?.sii_intelligence?.replay_timeline?.timeline);
  const comparisonWindow = selectedFinding?.comparison ?? { baseline: "Learned baseline", current: firstText(result?.comparison_window, "Current evidence window") };
  const lastMeaningfulChange = firstText(selectedFinding?.observedChange, result?.completed_at, result?.processed_at, "No supported change in the available window");
  const site = {
    id: String(result?.site_id ?? result?.adaptive_site_key ?? "current-site"),
    name: siteName,
    stabilityPercent,
    activeInvestigations: findings.filter((finding) => finding.tier !== "Withheld").length,
    evidenceQuality,
    coverage,
    highestConfidence: evidenceQuality,
    lastMeaningfulChange,
    governanceStatus: firstText(governance?.status, governance?.policy_status, "Policy applied"),
    governanceStatement,
  };
  return {
    result,
    site,
    sites: [site],
    findings,
    selectedFinding,
    subsystems,
    relationships,
    nodes,
    gaps,
    coverage,
    timelineFrames,
    comparisonWindow,
    evidenceQuality,
    domainLabel: humanize(domainDetection?.mode ?? result?.domain_detection?.mode ?? result?.detected_schema?.mode ?? "Infrastructure"),
    trace: buildTrace(selectedFinding, result),
    searchItems: buildSearchItems(site, subsystems, findings, nodes, analysis?.evidence_index),
    hasAnalysis: Boolean(result && Object.keys(result).length),
    processing,
  };
}

function buildSearchItems(site, subsystems, findings, nodes, evidenceIndex = {}) {
  return [
    { id: site.id, type: "Site", label: site.name, target: "site" },
    ...subsystems.map((item) => ({ id: item.id, type: "Subsystem", label: item.name, target: "site" })),
    ...nodes.map((item) => ({ id: item.id, type: "Asset / signal", label: item.label, target: "investigation", nodeId: item.id })),
    ...findings.map((item) => ({ id: item.id, type: "Finding", label: item.title, target: "investigation", findingId: item.id })),
    ...Object.values(evidenceIndex ?? {}).map((item, index) => ({ id: item?.evidence_id ?? `evidence-${index}`, type: "Evidence package", label: firstText(item?.description, item?.evidence_id, `Evidence ${index + 1}`), target: "evidence" })),
  ];
}

export function buildEngineeringReasoningModelsFromEvidenceRuns(runs = []) {
  const latestBySite = new Map();
  for (const run of asArray(runs)) {
    if (!run || typeof run !== "object") continue;
    const siteKey = String(run?.adaptive_site_key ?? run?.site_id ?? run?.room ?? run?.source_name ?? run?.run_id ?? "").trim();
    if (!siteKey) continue;
    const prior = latestBySite.get(siteKey);
    const timestamp = new Date(run?.completed_at ?? run?.created_at ?? 0).getTime() || 0;
    const priorTimestamp = new Date(prior?.completed_at ?? prior?.created_at ?? 0).getTime() || 0;
    if (!prior || timestamp >= priorTimestamp) latestBySite.set(siteKey, run);
  }
  return [...latestBySite.entries()].map(([siteKey, run]) => {
    const active = !["resolved", "closed", "normal"].includes(String(run?.observation_status ?? "").toLowerCase());
    const evidence = asArray(run?.evidence_summary);
    const coverage = run?.rows_received ? Math.max(0, Math.min(1, Number(run?.rows_accepted ?? 0) / Number(run.rows_received))) : null;
    const result = {
      ...run,
      job_id: run?.run_id,
      facility_name: firstText(run?.site_name, run?.room, siteKey),
      data_quality: { coverage, warnings: [...asArray(run?.warnings), ...asArray(run?.data_conditions)] },
      governance_boundary: run?.governance_boundary,
      analysis_explanation: {
        systems: compact([{ id: run?.system_id, name: firstText(run?.system_name, run?.room, run?.system_id) }]),
        insights: active && evidence.length ? [{
          id: `evidence-${run.run_id}`,
          title: firstText(run?.finding_title, run?.historical_fact, evidence[0]),
          what_changed: evidence[0],
          why_it_matters: firstText(run?.potential_impact, run?.historical_fact),
          confidence_tier: run?.confidence_tier,
          system: firstText(run?.system_name, run?.room, run?.system_id),
          variables: asArray(run?.variables),
          supporting_evidence: evidence,
          limitations: [...asArray(run?.warnings), ...asArray(run?.data_conditions)],
          operator_feedback_history: asArray(run?.operator_feedback_history),
        }] : [],
      },
    };
    const model = buildEngineeringReasoningModel({ result });
    return {
      ...model,
      site: {
        ...model.site,
        id: siteKey,
        activeInvestigations: active && evidence.length ? 1 : 0,
        lastMeaningfulChange: firstText(evidence[0], run?.historical_fact, run?.completed_at),
      },
    };
  });
}
