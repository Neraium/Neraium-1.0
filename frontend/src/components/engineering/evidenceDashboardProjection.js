const DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

const CAUSE_ESTABLISHED_STATES = new Set(["confirmed", "established"]);
const PERSISTENCE_LABELS = new Map([
  ["persistent", "Persistent"],
  ["not_established", "Not established"],
  ["unavailable", "Not established"],
  ["insufficient", "Not established"],
]);
const OPERATING_CONTEXT_LABELS = new Map([
  ["supported", "Comparable"],
  ["comparable", "Comparable"],
  ["strong", "Comparable"],
  ["partially_comparable", "Limited"],
  ["partial", "Limited"],
  ["limited", "Limited"],
  ["weak", "Limited"],
  ["unavailable", "Not established"],
  ["not_established", "Not established"],
  ["not_enough_context", "Not established"],
  ["insufficient", "Not established"],
]);

const asArray = (value) => (Array.isArray(value) ? value : []);

function firstText(...values) {
  for (const value of values.flat()) {
    if (typeof value !== "string" && typeof value !== "number") continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return "";
}

function finite(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
}

function displayLabel(value) {
  return String(value ?? "")
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalizedState(value) {
  return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function humanDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return DATE_FORMATTER.format(date);
}

function rangeStart(range) {
  return firstText(range?.current_start, range?.currentStart, range?.start, range?.start_time);
}

function rangeEnd(range) {
  return firstText(range?.current_end, range?.currentEnd, range?.end, range?.end_time);
}

function evidenceWindowLabel(start, end) {
  const startLabel = humanDate(start);
  const endLabel = humanDate(end);

  if (startLabel && endLabel) {
    const sameYear = new Date(start).getUTCFullYear() === new Date(end).getUTCFullYear();
    return sameYear
      ? `${startLabel.replace(/, \d{4}$/, "")} – ${endLabel}`
      : `${startLabel} – ${endLabel}`;
  }
  return startLabel || endLabel || "Unavailable";
}

function currentEvidenceWindow(sourceRanges) {
  const ranges = asArray(sourceRanges);
  const range = ranges.find((item) => rangeStart(item) && rangeEnd(item))
    ?? ranges.find(rangeStart)
    ?? ranges.find(rangeEnd)
    ?? null;
  const start = range ? rangeStart(range) : "";
  const end = range ? rangeEnd(range) : "";

  return {
    label: evidenceWindowLabel(start, end),
    start: start || null,
    end: end || null,
  };
}

function summaryRelationship(relationship, index) {
  if (!relationship || typeof relationship !== "object" || Array.isArray(relationship)) {
    return null;
  }

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
  return PERSISTENCE_LABELS.get(state) ?? (value ? displayLabel(value) : "Not established");
}

function operatingContextLabel(value) {
  const state = normalizedState(value);
  return OPERATING_CONTEXT_LABELS.get(state) ?? (value ? displayLabel(value) : "Not established");
}

function evidenceMetrics({ confidence, operatingContext, persistence, primaryRelationship }) {
  return {
    magnitude: {
      value: primaryRelationship?.magnitude ?? null,
      signed: primaryRelationship?.signed ?? false,
      label: primaryRelationship ? null : "Not established",
      description: primaryRelationship
        ? "relationship shift"
        : "relationship magnitude unavailable",
    },
    persistence: {
      value: persistenceLabel(persistence),
      description: persistence ? "persistence evidence" : "persistence evidence unavailable",
    },
    operatingContext: {
      value: operatingContextLabel(operatingContext),
      description: operatingContext
        ? "operating conditions"
        : "comparability evidence unavailable",
    },
    confidence: {
      value: confidence ? displayLabel(confidence) : "Not established",
      description: confidence ? "supporting evidence" : "confidence evidence unavailable",
    },
  };
}

function insufficientEvidence(projection) {
  if (projection.variant !== "insufficient") return null;
  return {
    title: "Insufficient evidence",
    description: firstText(projection.limitations?.material)
      || "The available evidence does not support a reliable behavioral-change conclusion.",
  };
}

export function projectEvidenceDashboardSummary(projection) {
  if (!projection?.dashboardIdentity) return null;

  const relationships = asArray(projection.exactRelationships)
    .slice(0, 3)
    .map((relationship, index) => summaryRelationship(relationship, index))
    .filter(Boolean);
  const relationshipWindows = asArray(projection.exactRelationships)
    .flatMap((relationship) => asArray(relationship?.windows));
  const evidenceWindows = [
    ...asArray(projection.timestamps?.sourceRanges),
    ...relationshipWindows,
  ];
  const contract = projection.classifications?.confidenceContract ?? {};
  const primaryRelationship = relationships.find((item) => item.magnitude !== null);
  const persistence = firstText(contract?.persistence?.status);
  const operatingContext = firstText(
    projection.dashboardIdentity.operatingContext,
    contract?.operating_context?.status,
  );
  const confidence = firstText(
    contract?.change_detection?.level,
    contract?.evidence_quality?.level,
  );
  const attribution = normalizedState(contract?.interpretation?.attribution_status);
  const causeEstablished = projection.dashboardIdentity.causeEstablished
    || CAUSE_ESTABLISHED_STATES.has(attribution);

  return {
    title: projection.dashboardIdentity.title || "Finding title unavailable",
    system: projection.dashboardIdentity.system || "System not supplied",
    status: projection.dashboardIdentity.status || "Unavailable",
    evidenceWindow: currentEvidenceWindow(evidenceWindows),
    metrics: evidenceMetrics({
      confidence,
      operatingContext,
      persistence,
      primaryRelationship,
    }),
    relationships,
    cause: {
      established: causeEstablished,
      label: causeEstablished
        ? "Yes \u2014 confirmed in evidence"
        : "No \u2014 investigation required",
    },
    insufficient: insufficientEvidence(projection),
  };
}
