import { Panel } from "../workspacePrimitives";

function asEpoch(value) {
  if (!value) return null;
  const epoch = Date.parse(value);
  return Number.isFinite(epoch) ? epoch : null;
}

export default function PilotReadinessPanel({
  apiStatus,
  latestUploadSnapshot,
  hasRealSiiOutput,
  formatClockTime,
}) {
  const baselineStatus = String(latestUploadSnapshot?.baseline_status ?? "none").toLowerCase();
  const latestStatus = String(latestUploadSnapshot?.status ?? "empty").toLowerCase();
  const lastProcessedAt = latestUploadSnapshot?.last_processed_at ?? null;
  const lastProcessedEpoch = asEpoch(lastProcessedAt);
  const freshnessMs = lastProcessedEpoch == null ? null : Date.now() - lastProcessedEpoch;
  const isFresh = freshnessMs != null && freshnessMs <= 1000 * 60 * 60 * 24;

  const checks = [
    { label: "Control plane connectivity", ok: String(apiStatus?.label ?? "").toLowerCase() === "online", detail: apiStatus?.label ?? "Unknown" },
    { label: "Latest upload validity", ok: latestStatus === "active" || latestStatus === "complete", detail: latestUploadSnapshot?.last_filename ?? "No recent upload" },
    { label: "Baseline status", ok: baselineStatus === "active", detail: baselineStatus === "active" ? "Baseline active" : "Baseline pending" },
    { label: "Analysis freshness", ok: isFresh, detail: lastProcessedAt ? formatClockTime(lastProcessedAt) : "No analysis timestamp" },
    { label: "Read-only boundary", ok: true, detail: "Read-only. No control or actuation paths enabled." },
    { label: "SII result availability", ok: Boolean(hasRealSiiOutput), detail: hasRealSiiOutput ? "SII output available" : "No completed SII output yet" },
  ];
  const passed = checks.filter((item) => item.ok).length;
  const total = checks.length;

  return (
    <Panel title="Pilot Readiness Check" className="span-12 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
      <p className="narrative-text">{`Readiness ${passed}/${total} checks passing.`}</p>
      <ul className="pilot-readiness-list">
        {checks.map((check) => (
          <li key={check.label} className={check.ok ? "is-ok" : "is-warn"}>
            <strong>{check.ok ? "PASS" : "WARN"}</strong>
            <span>{`${check.label}: ${check.detail}`}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
