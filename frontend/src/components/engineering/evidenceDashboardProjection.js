const asArray = (value) => Array.isArray(value) ? value : [];
const firstText = (...values) => {
  for (const value of values.flat()) {
    if (typeof value !== "string" && typeof value !== "number") continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return "";
};
const finite = (...values) => {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
};
const label = (value) => String(value ?? "").trim().replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const normalizedState = (value) => String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");

function humanDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(date);
}

function currentEvidenceWindow(sourceRanges) {
  const ranges = asArray(sourceRanges);
  const startFor = (item) => firstText(item?.current_start, item?.currentStart, item?.start, item?.start_time);
  const endFor = (item) => firstText(item?.current_end, item?.currentEnd, item?.end, item?.end_time);
  const range = ranges.find((item) => startFor(item) && endFor(item)) ?? ranges.find(startFor) ?? ranges.find(endFor) ?? null;
  const start = range ? startFor(range) : "";
  const end = range ? endFor(range) : "";
  const startLabel = humanDate(start);
  const endLabel = humanDate(end);
  let windowLabel = "Unavailable";
  if (startLabel && endLabel) {
    const sameYear = new Date(start).getUTCFullYear() === new Date(end).getUTCFullYear();
    windowLabel = sameYear ? `${startLabel.replace(/, \d{4}$/, "")} – ${endLabel}` : `${startLabel} – ${endLabel}`;
  } else if (startLabel || endLabel) windowLabel = startLabel || endLabel;
  return { label: windowLabel, start: start || null, end: end || null };
}

function summaryRelationship(relationship, index) {
  if (!relationship || typeof relationship !== "object" || Array.isArray(relationship)) return null;
  const signedChange = finite(relationship.signedChange);
  return {
    id: firstText(relationship.id) || `relationship-${index + 1}`,
    label: `${firstText(relationship.source, "Source signal")} ↔ ${firstText(relationship.target, "Target signal")}`,
    magnitude: signedChange ?? finite(relationship.absoluteChange, relationship.delta),
    signed: signedChange !== null,
    sparkline: null,
  };
}

function persistenceLabel(value) {
  const state = normalizedState(value);
  if (state === "persistent") return "Persistent";
  if (["not_established", "unavailable", "insufficient"].includes(state)) return "Not established";
  return value ? label(value) : "Not established";
}

function operatingContextLabel(value) {
  const state = normalizedState(value);
  if (["supported", "comparable", "strong"].includes(state)) return "Comparable";
  if (["partially_comparable", "partial", "limited", "weak"].includes(state)) return "Limited";
  if (["unavailable", "not_established", "not_enough_context", "insufficient"].includes(state)) return "Not established";
  return value ? label(value) : "Not established";
}

export function projectEvidenceDashboardSummary(projection) {
  if (projection?.depth === "review" && projection?.dashboardSummary) {
    const dashboard = projection.dashboardSummary;
    const relationships = asArray(dashboard.relationships).slice(0, 3).map((relationship, index) => ({
      id: `review-relationship-${index + 1}`,
      label: firstText(relationship?.label, `Relationship change ${index + 1}`),
      magnitude: finite(relationship?.magnitude),
      signed: relationship?.signed === true,
      sparkline: null,
    }));
    const evidenceWindow = currentEvidenceWindow([dashboard.evidenceWindow]);
    return {
      title: dashboard.title || "Finding title unavailable",
      system: dashboard.system || "System not supplied",
      status: dashboard.status || "Unavailable",
      evidenceWindow,
      metrics: {
        magnitude: { value: finite(dashboard.magnitude), signed: dashboard.magnitudeSigned === true, label: dashboard.magnitude === null ? "Not established" : null, description: dashboard.magnitude === null ? "relationship magnitude unavailable" : "largest supported relationship shift" },
        persistence: { value: firstText(dashboard.assessment?.persistence, "Not established"), description: "persistence evidence" },
        operatingContext: { value: firstText(dashboard.assessment?.operatingContext, "Not established"), description: "operating conditions" },
        confidence: { value: firstText(dashboard.assessment?.changeConfidence, "Not established"), description: "change confidence" },
      },
      relationships,
      relationshipStatus: relationships.length ? "Ranked relationship-change summary" : "Relationship detail available in Investigation",
      cause: { established: dashboard.causeEstablished === true, label: dashboard.causeEstablished === true ? "Yes — established by supplied evidence" : "No — investigation required" },
      insufficient: projection.variant === "insufficient" ? { title: "Insufficient evidence", description: projection.whatChanged } : null,
    };
  }
  if (!projection?.dashboardIdentity) return null;
  const relationships = asArray(projection.exactRelationships).slice(0, 3).map(summaryRelationship).filter(Boolean);
  const relationshipWindows = asArray(projection.exactRelationships).flatMap((relationship) => asArray(relationship?.windows));
  const evidenceWindows = [...asArray(projection.timestamps?.sourceRanges), ...relationshipWindows];
  const contract = projection.classifications?.confidenceContract ?? {};
  const primary = relationships.find((item) => item.magnitude !== null);
  const persistence = firstText(contract?.persistence?.status);
  const operatingContext = firstText(projection.dashboardIdentity.operatingContext, contract?.operating_context?.status);
  const confidence = firstText(contract?.change_detection?.level, contract?.evidence_quality?.level);
  const attribution = normalizedState(contract?.interpretation?.attribution_status);
  const causeEstablished = projection.dashboardIdentity.causeEstablished || ["confirmed", "established"].includes(attribution);
  return {
    title: projection.dashboardIdentity.title || "Finding title unavailable",
    system: projection.dashboardIdentity.system || "System not supplied",
    status: projection.dashboardIdentity.status || "Unavailable",
    evidenceWindow: currentEvidenceWindow(evidenceWindows),
    metrics: {
      magnitude: { value: primary?.magnitude ?? null, signed: primary?.signed ?? false, label: primary ? null : "Not established", description: primary ? "relationship shift" : "relationship magnitude unavailable" },
      persistence: { value: persistenceLabel(persistence), description: persistence ? "persistence evidence" : "persistence evidence unavailable" },
      operatingContext: { value: operatingContextLabel(operatingContext), description: operatingContext ? "operating conditions" : "comparability evidence unavailable" },
      confidence: { value: confidence ? label(confidence) : "Not established", description: confidence ? "supporting evidence" : "confidence evidence unavailable" },
    },
    relationships,
    cause: { established: causeEstablished, label: causeEstablished ? "Yes \u2014 confirmed in evidence" : "No \u2014 investigation required" },
    insufficient: projection.variant === "insufficient" ? { title: "Insufficient evidence", description: firstText(projection.limitations?.material) || "The available evidence does not support a reliable behavioral-change conclusion." } : null,
  };
}
