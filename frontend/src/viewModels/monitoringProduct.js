const CHANGE_WORDS = /\b(change(?:d)?|drift(?:ing)?|diverg(?:ed|ence)|weaken(?:ed)?|decoupl(?:ed|ing)|disrupt(?:ed)?|unstable|alert|watch|elevated|outside (?:its|the) (?:learned|usual)|no longer)\b/i;
const QUIET_WORDS = /\b(normal|stable|resolved|closed|unchanged|no[_ -]?change|not detected|nominal)\b/i;
const WITHHELD_WORDS = /\b(withheld|insufficient|deferred|unreliable|invalid|failed|error|cancelled)\b/i;
const DIAGNOSTIC_WORDS = /\b(failure|fault|bearing|inspect|repair|replace|root cause|possible cause|recommend|check\b|maintenance|investigat)\b/i;

const asArray = (value) => Array.isArray(value) ? value : [];
const compact = (values) => values.filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
const unique = (values) => [...new Set(compact(values).map((value) => String(value).trim()).filter(Boolean))];

function firstText(...values) {
  for (const value of values.flat(Infinity)) {
    if (value === null || value === undefined || typeof value === "object") continue;
    const normalized = String(value).trim();
    if (normalized) return normalized;
  }
  return "";
}

function firstNumber(...values) {
  for (const value of values.flat(Infinity)) {
    if (value === null || value === undefined || value === "") continue;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function sentence(value) {
  const normalized = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  const first = normalized.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() || normalized;
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

export function signalLabel(value) {
  return String(value ?? "")
    .replace(/^tag:/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\bkw\b/gi, "kW")
    .replace(/\bpct\b/gi, "percent")
    .replace(/\bdp\b/gi, "differential pressure")
    .replace(/\bvfd\b/gi, "VFD")
    .replace(/\b[a-z]/g, (letter) => letter.toUpperCase())
    .replace(/\s+/g, " ")
    .trim();
}

function relationshipColumns(value) {
  if (!value || typeof value !== "object") return [];
  return unique([
    ...asArray(value.columns),
    ...asArray(value.source_columns),
    ...asArray(value.source_tags),
    value.source,
    value.target,
    value.left,
    value.right,
  ]).map(signalLabel).filter(Boolean).slice(0, 4);
}

function collectRelationships(value) {
  const candidates = [
    ...asArray(value?.relationships),
    ...asArray(value?.contributing_relationships),
    ...asArray(value?.relationship_changes),
    ...asArray(value?.drift_metrics?.relationships),
  ];
  return candidates.filter((item) => item && typeof item === "object").map((item, index) => {
    const endpoints = relationshipColumns(item);
    return {
      id: firstText(item.id, item.relationship_id, `relationship-${index}`),
      endpoints,
      label: endpoints.length >= 2 ? `${endpoints[0]} and ${endpoints[1]}` : firstText(item.label, item.name, `Relationship ${index + 1}`),
      baseline: firstNumber(item.baseline_strength, item.baseline_correlation, item.baseline, item.statistics?.baseline_strength),
      current: firstNumber(item.current_strength, item.current_correlation, item.recent_correlation, item.current, item.strength, item.statistics?.current_strength),
      delta: firstNumber(item.correlation_delta, item.coupling_delta, item.delta, item.statistics?.correlation_delta),
      changeType: firstText(item.change_type, item.state, item.status),
      windows: asArray(item.source_time_ranges ?? item.windows),
      raw: item,
    };
  });
}

function collectVariables(value, relationships = []) {
  return unique(unique([
    ...asArray(value?.variables),
    ...asArray(value?.affected_variables),
    ...asArray(value?.supporting_signals),
    ...asArray(value?.corroborating_signals),
    ...relationships.flatMap((relationship) => relationship.endpoints),
  ]).map(signalLabel)).filter(Boolean).slice(0, 12);
}

function observedTitle(variables, system, supplied = "") {
  const context = `${variables.join(" ")} ${system} ${supplied}`.toLowerCase();
  if (/pump/.test(context) && /(flow|power|demand|speed|current)/.test(context)) return "Pump response changed";
  if (/pressure/.test(context) && /flow/.test(context)) return "Pressure and flow no longer move together normally";
  if (/valve/.test(context)) return "Valve response changed";
  if (/cooling|chiller|compressor/.test(context) && /power|demand|load|current/.test(context)) return "Cooling demand and power usage have diverged";
  if (/filter/.test(context) && /pressure/.test(context)) return "Filter pressure behavior changed";
  if (variables.length >= 2) return `${variables[0]} and ${variables[1]} relationship changed`;
  const safeSupplied = sentence(supplied).replace(/[.!?]$/, "");
  if (safeSupplied && CHANGE_WORDS.test(safeSupplied) && !DIAGNOSTIC_WORDS.test(safeSupplied) && safeSupplied.length <= 80) return safeSupplied;
  if (system) return `${signalLabel(system)} behavior changed`;
  return "A previously stable relationship has weakened";
}

function observedDescription(variables, system = "") {
  const context = `${variables.join(" ")} ${system}`.toLowerCase();
  const find = (pattern) => variables.find((value) => pattern.test(value.toLowerCase()));
  if (/pump/.test(context)) {
    const flow = find(/flow/);
    const power = find(/power|demand|current|speed/);
    if (flow && power) return `${flow} is no longer responding to ${power} the way it normally does.`;
  }
  if (variables.length >= 2) return `${variables[0]} and ${variables[1]} are no longer moving together the way they normally do.`;
  if (variables.length === 1) return `${variables[0]} no longer follows its learned relationship pattern.`;
  return "A learned relationship no longer follows its usual pattern.";
}

function findingState(value) {
  const raw = [value?.observation_status, value?.finding_state, value?.state, value?.validation_status].filter(Boolean).join(" " ).toLowerCase();
  if (/resolved|closed|normal|dismissed|explained/.test(raw)) return "resolved";
  return "active";
}

function isMeaningfulEvidenceRun(run) {
  if (!run || typeof run !== "object") return false;
  if (run.meaningful_change === false || run.relationship_change_detected === false) return false;
  if (run.reliable === false || run.finding_reliable === false) return false;
  const observationStatus = String(run.observation_status ?? "").replace(/[_-]+/g, " ");
  if (run.meaningful_change !== true && /^(normal|stable|no change|not detected|nominal)$/i.test(observationStatus)) return false;
  const status = [run.status, run.observation_status, run.observation_type, run.structural_state, run.operating_state, run.drift_status, run.confidence_tier].filter(Boolean).join(" ").replace(/[_-]+/g, " ");
  if (WITHHELD_WORDS.test(status)) return false;
  if (run.meaningful_change === true || run.relationship_change_detected === true) return true;
  if (QUIET_WORDS.test(status) && !CHANGE_WORDS.test(status)) return false;
  return CHANGE_WORDS.test(status);
}

function evidenceWindow(value) {
  const windows = asArray(value?.evidence_windows);
  const sourceRanges = [
    ...asArray(value?.source_time_ranges),
    ...collectRelationships(value).flatMap((relationship) => relationship.windows),
  ];
  const first = windows[0] ?? sourceRanges[0] ?? {};
  return {
    baselineStart: firstText(first.baseline_start, first.reference_start, first.before_start),
    baselineEnd: firstText(first.baseline_end, first.reference_end, first.before_end),
    currentStart: firstText(first.current_start, first.recent_start, first.after_start, first.start),
    currentEnd: firstText(first.current_end, first.recent_end, first.after_end, first.end),
    comparableContext: firstText(first.operating_mode, first.context, first.condition_group, value?.operating_mode, value?.regime_label),
  };
}

function collectLimitations(value) {
  const raw = unique([
    ...asArray(value?.limitations),
    ...asArray(value?.warnings),
    ...asArray(value?.data_conditions),
    ...asArray(value?.quality_warnings),
    value?.quality_warning,
    value?.baseline_error_message,
  ]);
  return raw.map((item) => {
    const normalized = String(item).trim();
    if (/comparable|context|operating mode|condition group/i.test(normalized) && /limit|insufficient|sparse|few|missing/i.test(normalized)) return "Comparable operating data was limited.";
    if (/abrupt step|step change/i.test(normalized)) return "One sensor showed an abrupt step.";
    if (/stale/i.test(normalized)) return "Some source data was stale during this comparison.";
    if (/missing|gap|coverage|incomplete|sparse/i.test(normalized)) return "Some telemetry was unavailable during this comparison.";
    return sentence(normalized);
  }).filter(Boolean);
}

function firstDetected(value, window = evidenceWindow(value)) {
  return firstText(
    value?.first_detected_at,
    value?.deformation_started_at,
    value?.change_started_at,
    value?.timestamps?.first_detected_at,
    window.currentStart,
    value?.created_at,
  );
}

function lastObserved(value) {
  return firstText(value?.last_observed_at, value?.completed_at, value?.updated_at, value?.created_at);
}

function evidenceSummary(value) {
  return unique([
    ...asArray(value?.evidence_summary),
    ...asArray(value?.supporting_evidence),
    ...asArray(value?.observed_facts),
  ]).filter((item) => !DIAGNOSTIC_WORDS.test(item)).slice(0, 8);
}

export function normalizePersistedFinding(run, index = 0) {
  if (!isMeaningfulEvidenceRun(run)) return null;
  const relationships = collectRelationships(run);
  const variables = collectVariables(run, relationships);
  const system = firstText(run.system_name, run.subsystem_name, run.system_id, run.room);
  const window = evidenceWindow(run);
  const detectedAt = firstDetected(run, window);
  const observedAt = lastObserved(run);
  const evidence = evidenceSummary(run);
  return {
    id: firstText(run.finding_id, run.run_id, run.job_id, `stored-finding-${index}`),
    runId: firstText(run.run_id, run.job_id, run.upload_id),
    title: observedTitle(variables, system, firstText(run.finding_title, run.title, run.historical_fact)),
    description: observedDescription(variables, system),
    state: findingState(run),
    system: signalLabel(system) || "Unassigned system",
    variables,
    corroborationCount: firstNumber(run.corroboration_count, run.supporting_signal_count) ?? variables.length,
    relationships,
    evidence,
    limitations: collectLimitations(run),
    firstDetectedAt: detectedAt,
    lastObservedAt: observedAt,
    window,
    sourceName: firstText(run.source_name, run.filename, run.source_type),
    dataQuality: firstText(run.data_quality?.status, run.quality_status),
    raw: run,
  };
}

export function normalizeCurrentFindings(model) {
  const result = model?.result ?? {};
  return asArray(model?.findings).filter((finding) => finding?.status === "Change detected").map((finding, index) => {
    const relationships = asArray(finding.relationships).map((relationship, relationshipIndex) => ({
      id: firstText(relationship.id, `current-relationship-${relationshipIndex}`),
      endpoints: asArray(relationship.endpoints).length ? relationship.endpoints.map(signalLabel) : unique([relationship.source, relationship.target]).map(signalLabel),
      label: firstText(relationship.label),
      baseline: firstNumber(relationship.baseline),
      current: firstNumber(relationship.current),
      delta: firstNumber(relationship.delta),
      changeType: firstText(relationship.changeType),
      windows: asArray(relationship.windows),
      raw: relationship.raw ?? relationship,
    }));
    const variables = collectVariables(finding, relationships);
    const system = firstText(finding.location?.subsystem, finding.location?.system, finding.system);
    const runId = firstText(result.job_id, result.run_id, result.upload_id);
    const raw = { ...result, ...finding, relationships, variables };
    const window = evidenceWindow(raw);
    return {
      id: firstText(finding.id, runId && `current-${runId}`, `current-finding-${index}`),
      runId,
      title: observedTitle(variables, system, finding.title),
      description: observedDescription(variables, system),
      state: "active",
      system: signalLabel(system) || "Unassigned system",
      variables,
      corroborationCount: variables.length,
      relationships,
      evidence: unique([...asArray(finding.supporting), ...asArray(finding.visibleSupporting)]).slice(0, 8),
      limitations: unique([...asArray(finding.limitations), ...asArray(finding.technicalLimitations), ...collectLimitations(result)]),
      firstDetectedAt: firstDetected(raw, window),
      lastObservedAt: lastObserved(raw),
      window,
      sourceName: firstText(result.source_name, result.filename),
      dataQuality: firstText(result.data_quality?.status),
      raw,
    };
  });
}

export function mergeFindings(current = [], persisted = []) {
  const merged = [];
  const identities = new Set();
  [...current, ...persisted].forEach((finding) => {
    if (!finding) return;
    const identity = String(finding.runId || finding.id);
    if (identities.has(identity)) return;
    identities.add(identity);
    merged.push(finding);
  });
  return merged.sort((left, right) => {
    if (left.state !== right.state) return left.state === "active" ? -1 : 1;
    return timestamp(right.firstDetectedAt) - timestamp(left.firstDetectedAt);
  });
}

function timestamp(value) {
  const parsed = new Date(value ?? 0).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatDateTime(value) {
  const parsed = new Date(value ?? "");
  if (Number.isNaN(parsed.getTime())) return "Not available";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(parsed);
}

export function formatDuration(start, end = Date.now()) {
  const startTime = timestamp(start);
  const endTime = typeof end === "number" ? end : timestamp(end);
  if (!startTime || !endTime || endTime < startTime) return "Not available";
  const hours = Math.max(1, Math.floor((endTime - startTime) / 3_600_000));
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"}`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"}`;
  const months = Math.floor(days / 30);
  return `${months} month${months === 1 ? "" : "s"}`;
}

export function persistenceLabel(finding) {
  const explicit = firstText(finding?.raw?.persistence_duration, finding?.raw?.persistence, finding?.raw?.duration);
  if (explicit && !/\[object object\]/i.test(explicit)) return explicit;
  return formatDuration(finding?.firstDetectedAt, finding?.lastObservedAt || Date.now());
}

export function buildSystemRows({ systems = [], findings = [], relationships = [], coverage = null, freshness = null } = {}) {
  const names = unique([
    ...asArray(systems).map((system) => firstText(system?.name, system?.label, system?.system_name, system?.id)),
    ...findings.map((finding) => finding.system),
  ]).filter((name) => name && name !== "Unassigned system");
  return names.map((name, index) => {
    const normalizedName = signalLabel(name);
    const sourceSystem = asArray(systems).find((system) => signalLabel(firstText(system?.name, system?.label, system?.system_name, system?.id)) === normalizedName) ?? {};
    const activeFindings = findings.filter((finding) => finding.state === "active" && finding.system === normalizedName);
    const globallyAssignedSignals = names.length === 1 ? relationships.flatMap((relationship) => [...asArray(relationship.endpoints), relationship.source, relationship.target]) : [];
    const signals = unique([
      ...activeFindings.flatMap((finding) => finding.variables),
      ...asArray(sourceSystem.mapped_signals),
      ...asArray(sourceSystem.signals),
      ...asArray(sourceSystem.tags),
      ...globallyAssignedSignals,
    ].map(signalLabel));
    const ownedRelationships = relationships.filter((relationship) => {
      const haystack = `${relationship.label ?? ""} ${asArray(relationship.endpoints).join(" ")} ${relationship.system ?? ""}`.toLowerCase();
      return haystack.includes(String(name).toLowerCase());
    });
    const explicitRelationshipCount = firstNumber(sourceSystem.relationship_count, sourceSystem.learned_relationship_count, asArray(sourceSystem.learned_relationships).length || null);
    const explicitSignalCount = firstNumber(sourceSystem.mapped_signal_count, sourceSystem.signal_count, sourceSystem.sensors_detected);
    return {
      id: firstText(sourceSystem.id, `system-${index}`),
      name: normalizedName,
      signalCount: explicitSignalCount ?? signals.length,
      relationshipCount: explicitRelationshipCount ?? (ownedRelationships.length || activeFindings.reduce((count, finding) => count + finding.relationships.length, 0) || (names.length === 1 ? relationships.length : 0)),
      coverage: firstNumber(sourceSystem.coverage, sourceSystem.data_coverage) ?? coverage,
      freshness,
      activeFindingCount: activeFindings.length,
      health: activeFindings.length ? "Relationship changed" : relationships.length ? "Within learned pattern" : "Learning baseline",
    };
  });
}

export function buildFindingNotification(finding) {
  if (!finding) return null;
  return {
    title: `${finding.title}.`,
    body: finding.description,
    firstDetected: finding.firstDetectedAt ? `First detected: ${formatDateTime(finding.firstDetectedAt)}` : "",
    actionLabel: "View evidence",
    findingId: finding.id,
  };
}

export function filterFindings(findings, { state = "all", system = "all", date = "" } = {}) {
  return findings.filter((finding) => {
    if (state !== "all" && finding.state !== state) return false;
    if (system !== "all" && finding.system !== system) return false;
    if (date) {
      const findingDate = new Date(finding.firstDetectedAt ?? "");
      if (Number.isNaN(findingDate.getTime()) || findingDate.toISOString().slice(0, 10) !== date) return false;
    }
    return true;
  });
}
