import { MetricGrid, Panel, EmptyState } from "./workspacePrimitives";

function toneRank(tone) {
  if (tone === "unstable" || tone === "elevated") return 2;
  if (tone === "review") return 1;
  return 0;
}

function toneLabel(tone) {
  if (tone === "unstable" || tone === "elevated") return "Separation";
  if (tone === "review") return "Drift";
  return "Stable";
}

function inferToneFromHistoryEntry(entry) {
  const drift = String(entry?.drift_status ?? "").toLowerCase();
  const state = String(entry?.operating_state ?? "").toLowerCase();
  if (drift.includes("elevated") || state.includes("separation")) return "elevated";
  if (drift.includes("watch") || drift.includes("review") || state.includes("drift")) return "review";
  return "nominal";
}

function buildFleetFromUploads(snapshot, fallbackTone) {
  const history = Array.isArray(snapshot?.history) ? snapshot.history : [];
  if (history.length === 0) {
    return [{
      id: "primary-facility",
      name: "Primary Facility",
      tone: fallbackTone,
      score: "n/a",
      source: "Awaiting CSV upload",
      lastUpdate: "No completed run",
    }];
  }

  return history.slice(0, 6).map((entry, index) => ({
    id: entry.run_id ?? `run-${index}`,
    runId: entry.run_id ?? null,
    name: entry.filename ?? entry.source_name ?? `Facility Run ${index + 1}`,
    tone: inferToneFromHistoryEntry(entry),
    score: entry.neraium_score ?? "n/a",
    source: entry.source_name ?? "CSV upload",
    lastUpdate: entry.completed_at ?? entry.timestamp ?? "Unknown",
  }));
}

function buildFleetForDemo(demoScenario, telemetryTick) {
  const base = demoScenario === "separation" ? "elevated" : demoScenario === "drift" ? "review" : "nominal";
  const peers = ["North Campus", "South Campus", "East Campus", "West Campus"];
  return peers.map((name, idx) => {
    const rotate = (telemetryTick + idx) % 3;
    const tone = base === "nominal"
      ? (rotate === 0 ? "nominal" : "review")
      : base === "review"
        ? (rotate === 2 ? "elevated" : "review")
        : (rotate === 0 ? "review" : "elevated");
    return {
      id: `demo-${idx}`,
      runId: `demo-run-${telemetryTick}-${idx + 1}`,
      name,
      tone,
      score: tone === "nominal" ? 91 - idx : tone === "review" ? 74 - idx : 52 - idx,
      source: "Demo telemetry",
      lastUpdate: `tick ${telemetryTick}`,
    };
  });
}

function buildTransitionAlerts(driftHistory) {
  const rows = Array.isArray(driftHistory) ? driftHistory : [];
  const alerts = [];
  for (let idx = 1; idx < rows.length; idx += 1) {
    const prev = rows[idx - 1];
    const next = rows[idx];
    if (toneRank(next?.tone) > toneRank(prev?.tone)) {
      alerts.push(`${prev?.stamp ?? "prev"}: ${toneLabel(prev?.tone)} -> ${toneLabel(next?.tone)}`);
    }
  }
  return alerts.slice(-6).reverse();
}

export default function FleetWorkspace({
  liveOps,
  latestUploadSnapshot,
  driftHistory,
  isDemoMode = false,
  demoScenario = "drift",
  telemetryTick = 0,
  onOpenFacility,
}) {
  const facilities = isDemoMode
    ? buildFleetForDemo(demoScenario, telemetryTick)
    : buildFleetFromUploads(latestUploadSnapshot, liveOps.facilityTone);

  const total = facilities.length;
  const stableCount = facilities.filter((f) => f.tone === "nominal").length;
  const driftCount = facilities.filter((f) => f.tone === "review").length;
  const separationCount = facilities.filter((f) => f.tone === "elevated" || f.tone === "unstable").length;
  const priority = [...facilities].sort((a, b) => toneRank(b.tone) - toneRank(a.tone))[0];
  const transitions = buildTransitionAlerts(driftHistory);

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Fleet View" className="span-12 workspace-hero-panel">
        <MetricGrid
          metrics={[
            { label: "Sites in view", value: total },
            { label: "Stable", value: stableCount },
            { label: "Drift", value: driftCount },
            { label: "Separation", value: separationCount },
            { label: "Priority site", value: priority?.name ?? "n/a" },
            { label: "Priority state", value: toneLabel(priority?.tone) },
          ]}
        />
      </Panel>

      <Panel title="Fleet Status Board" className="span-7">
        <div className="fleet-board">
          {facilities.map((facility) => (
            <button
              className={`fleet-card fleet-card--${facility.tone}`}
              key={facility.id}
              type="button"
              onClick={() => onOpenFacility?.(facility)}
            >
              <div className="fleet-card__top">
                <strong>{facility.name}</strong>
                <span>{toneLabel(facility.tone)}</span>
              </div>
              <p>{`Score ${facility.score}`}</p>
              <p className="fleet-card__meta">{`${facility.source} • ${facility.lastUpdate}`}</p>
            </button>
          ))}
        </div>
      </Panel>

      <Panel title="Replay Escalation Log" className="span-5">
        {transitions.length === 0 ? (
          <EmptyState
            title="No escalation transitions yet"
            body="After CSV replay runs, severity transitions will be listed here."
            compact
          />
        ) : (
          <div className="fleet-log">
            {transitions.map((line, index) => (
              <p key={`${line}-${index}`}>{line}</p>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
