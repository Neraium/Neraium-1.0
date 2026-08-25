function validTimeZone(value) {
  const candidate = String(value ?? "").trim();
  if (!candidate) return "";
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: candidate }).format(new Date(0));
    return candidate;
  } catch {
    return "";
  }
}

export function resolveDisplayTimeZone(preferredTimeZone = "") {
  const preferred = validTimeZone(preferredTimeZone);
  if (preferred) return preferred;
  const local = validTimeZone(Intl.DateTimeFormat().resolvedOptions().timeZone);
  return local || "UTC";
}

export function formatLocalTimestamp(value, preferredTimeZone = "", fallback = "Not supplied") {
  if (!value) return fallback;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  const timeZone = resolveDisplayTimeZone(preferredTimeZone);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZoneName: "short",
  }).formatToParts(date);
  const part = (type) => parts.find((item) => item.type === type)?.value ?? "";
  const datePart = `${part("month")} ${part("day")}, ${part("year")}`;
  const timePart = `${part("hour")}:${part("minute")} ${part("dayPeriod")} ${part("timeZoneName")}`.replace(/\s+/g, " ").trim();
  return `${datePart} · ${timePart}`;
}

export function formatLocalTimestampRange(start, end, preferredTimeZone = "", fallback = "Recorded period") {
  if (start && end) return `${formatLocalTimestamp(start, preferredTimeZone, fallback)} → ${formatLocalTimestamp(end, preferredTimeZone, fallback)}`;
  if (start) return `From ${formatLocalTimestamp(start, preferredTimeZone, fallback)}`;
  if (end) return `Through ${formatLocalTimestamp(end, preferredTimeZone, fallback)}`;
  return fallback;
}

export function timestampTechnicalTitle(value, preferredTimeZone = "") {
  if (!value) return "";
  return `Source timestamp: ${String(value)} · Displayed in ${resolveDisplayTimeZone(preferredTimeZone)}`;
}
