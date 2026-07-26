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
  const candidates = asArray(analysisSource(result).insights ?? result.findings);
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

export function deriveEscalationReadiness(finding, result = {}) {
  const raw = rawFindingFor(finding, result);
  const modeMatchStrong = explicitPositive(
    raw.strong_mode_match ?? raw.mode_match_strength ?? raw.mode_match ?? raw.operating_mode_match,
    ["strong", "confirmed", "matched"],
  );
  const coverage = coverageRatio(result);
  const dataConfidenceGood = ["Confirmed", "Qualified"].includes(String(finding?.tier ?? ""))
    && coverage !== null
    && coverage >= 0.8;
  const persistentChange = explicitPositive(
    raw.persistent_change ?? raw.persistence_confirmed ?? raw.is_persistent ?? raw.persistence,
    ["persistent", "confirmed", "sustained"],
  ) || Number(raw.persistence_windows ?? raw.changed_windows ?? 0) >= 2;
  const multipleSupportingRelationships = asArray(finding?.relationships).length >= 2
    || Number(raw.supporting_relationship_count ?? 0) >= 2;
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
    modeMatchStrong,
    dataConfidenceGood,
    persistentChange,
    multipleSupportingRelationships,
    criticalAsset,
    noKnownOperationalExplanation,
  };
  return { ...criteria, serious: Object.values(criteria).every(Boolean) };
}

export function deriveWorkspacePresentationState(model = {}) {
  const result = model.result ?? {};
  if (model.processing) {
    return {
      key: "analysisRunning",
      status: "Analysis Running",
      headline: "Learning normal behavior",
      body: "Neraium is building the baseline and comparing relationships.",
      action: "View Analysis Progress",
    };
  }
  if (!model.hasAnalysis) {
    return {
      key: "noDataset",
      status: "Baseline Needed",
      headline: "No baseline available",
      body: "Import a historical dataset so Neraium can learn how your system normally behaves.",
      action: "Import Historical Dataset",
    };
  }
  const source = analysisSource(result);
  const hasAnalysisOutput = Boolean(
    result.sii_completed === true
    || asArray(source.insights).length
    || asArray(source.relationships).length
    || asArray(source.systems).length
    || result.baseline_analysis
  );
  const legacy = result.legacy_analysis === true
    || result.is_legacy === true
    || /legacy/i.test(firstText(result.analysis_version, result.schema_version));
  if (legacy) {
    return {
      key: "legacyAnalysis",
      status: "Legacy Analysis",
      headline: "Earlier analysis available",
      body: "Review the saved evidence or import current data for a new comparison.",
      action: "Review Saved Evidence",
    };
  }
  if (!hasAnalysisOutput) {
    return {
      key: "datasetReady",
      status: "Dataset Ready",
      headline: "Ready to learn normal behavior",
      body: "The historical dataset is ready for baseline analysis.",
      action: "Start Baseline Analysis",
    };
  }
  if (model.status === "Evidence insufficient") {
    return {
      key: "insufficientEvidence",
      status: "Insufficient Evidence",
      headline: "More evidence is needed",
      body: "Analysis completed, but the available data does not support a reliable finding.",
      action: "Review Evidence",
    };
  }
  if (model.status === "Normal") {
    return {
      key: "noMeaningfulChanges",
      status: "Monitoring",
      headline: "No meaningful changes",
      body: "Measured relationships remain within the learned baseline.",
      action: "View Monitoring",
    };
  }
  return {
    key: "analysisComplete",
    status: "Analysis Complete",
    headline: "Findings ready for review",
    body: "Review the highest-priority unexplained change first.",
    action: "Review Findings",
  };
}

function timestampFor(model = {}) {
  return firstText(
    model.result?.completed_at,
    model.result?.processed_at,
    model.result?.generated_at,
    analysisSource(model.result).generated_at,
  );
}

function happenedToday(value, now) {
  if (!value) return true;
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return true;
  return timestamp.getFullYear() === now.getFullYear()
    && timestamp.getMonth() === now.getMonth()
    && timestamp.getDate() === now.getDate();
}

export function buildShiftBrief(model = {}, acknowledgedIds = [], now = new Date()) {
  const acknowledged = new Set(asArray(acknowledgedIds).map(String));
  const findings = asArray(model.findings);
  const detectedAt = timestampFor(model);
  const newFindings = findings.filter((finding) => !acknowledged.has(String(finding.id)) && happenedToday(detectedAt, now));
  const needsAttention = findings.filter((finding) => !newFindings.includes(finding));
  const escalations = findings.filter((finding) => deriveEscalationReadiness(finding, model.result).serious);
  const monitoringIssues = asArray(model.gaps);
  const quietSystems = asArray(model.subsystems).filter((system) => system.status === "Normal");
  const resolvedItems = asArray(model.result?.resolved_items ?? model.result?.resolved_findings);
  return {
    newFindings,
    needsAttention,
    escalations,
    monitoringIssues,
    quietSystems,
    resolvedItems,
    counts: {
      newFindings: newFindings.length,
      escalations: escalations.length,
      resolved: resolvedItems.length,
      monitoring: monitoringIssues.length,
    },
  };
}
