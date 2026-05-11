import { useMemo, useState } from "react";
import { StatusDot } from "./workspacePrimitives";
import KftHealthOrb from "./KftHealthOrb";
import StructuralIntegrityField from "./StructuralIntegrityField";

const ZONES = [
  { id: "hvac", label: "HVAC", x: 18, y: 22 },
  { id: "lighting", label: "Lighting", x: 52, y: 14 },
  { id: "irrigation", label: "Irrigation", x: 82, y: 28 },
  { id: "humidity", label: "Humidity", x: 30, y: 62 },
  { id: "airflow", label: "Airflow", x: 62, y: 66 },
  { id: "power", label: "Power", x: 86, y: 64 },
];

const FALLBACK_LINKS = [
  ["hvac", "lighting"],
  ["hvac", "humidity"],
  ["lighting", "irrigation"],
  ["lighting", "airflow"],
  ["humidity", "airflow"],
  ["airflow", "power"],
  ["irrigation", "power"],
];

const ZONE_ALIAS = {
  temperature: "hvac",
  hvac: "hvac",
  lighting: "lighting",
  irrigation: "irrigation",
  humidity: "humidity",
  airflow: "airflow",
  co2: "airflow",
  "sensor network": "power",
  power: "power",
};

const STATE = {
  nominal: { label: "Coherence High", nodeClass: "node--stable" },
  review: { label: "Coherence Degrading", nodeClass: "node--drift" },
  elevated: { label: "Coherence Fragmenting", nodeClass: "node--separation" },
  unstable: { label: "Coherence Fragmenting", nodeClass: "node--separation" },
  info: { label: "Baseline Pending", nodeClass: "node--pending" },
};

function toXY(zone) {
  return { x: (zone.x / 100) * 1000, y: (zone.y / 100) * 600 };
}

function zoneByCategory(category) {
  const normalized = String(category ?? "").toLowerCase();
  return ZONE_ALIAS[normalized] ?? null;
}

function buildCanonicalEdges(rows, fallbackTone) {
  const grouped = new Map();

  (rows ?? []).forEach((row) => {
    const categories = Array.isArray(row.pair_categories) ? row.pair_categories : [];
    if (categories.length < 2) {
      return;
    }
    const first = zoneByCategory(categories[0]);
    const second = zoneByCategory(categories[1]);
    if (!first || !second || first === second) {
      return;
    }
    const key = [first, second].sort().join("::");
    const bucket = grouped.get(key) ?? {
      id: key,
      from: [first, second].sort()[0],
      to: [first, second].sort()[1],
      pairKeys: [],
      evidence: [],
      strength: 0,
      tone: fallbackTone,
      directionBias: 0,
    };
    bucket.pairKeys.push(row.pair_key);
    bucket.evidence.push(row.detail);
    bucket.strength += Number(row.pair_weight ?? 0);
    bucket.directionBias += Number(row.change ?? 0);
    bucket.tone = row.tone ?? bucket.tone;
    grouped.set(key, bucket);
  });

  return Array.from(grouped.values()).map((edge) => ({
    ...edge,
    strength: Math.max(0.15, Math.min(1, edge.strength)),
    marker: edge.directionBias >= 0 ? "url(#arrow-forward)" : "url(#arrow-backward)",
  }));
}

export default function SystemTopologyWorkspace({ liveOps, selectedTarget, onSelectTarget }) {
  const state = STATE[liveOps.facilityTone] ?? STATE.info;
  const findings = liveOps.findings?.slice(0, 3) ?? [];
  const [hoveredEdgeId, setHoveredEdgeId] = useState(null);
  const edges = buildCanonicalEdges(liveOps.relationshipRows, liveOps.facilityTone);
  const displayEdges = edges.length > 0
    ? edges
    : FALLBACK_LINKS.map(([from, to]) => ({
        id: `${from}::${to}`,
        from,
        to,
        pairKeys: [],
        evidence: [],
        strength: 0.2,
        tone: "info",
        marker: "url(#arrow-forward)",
      }));
  const hoveredEdge = useMemo(() => edges.find((edge) => edge.id === hoveredEdgeId) ?? null, [edges, hoveredEdgeId]);
  const coherence = useMemo(() => {
    const total = (liveOps.relationshipRows ?? []).reduce((sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)), 0);
    return Math.max(0, Math.min(1, 1 - total));
  }, [liveOps.relationshipRows]);
  const systemState = liveOps.facilityTone === "nominal"
    ? "stable"
    : liveOps.facilityTone === "review"
      ? "drift"
      : "separation";
  const fieldToneClass = coherence > 0.72 ? "field--coherent" : coherence > 0.46 ? "field--strained" : "field--collapsing";
  const hoveredRows = useMemo(() => {
    if (!hoveredEdge) {
      return [];
    }
    const keySet = new Set(hoveredEdge.pairKeys ?? []);
    return (liveOps.relationshipRows ?? []).filter((row) => keySet.has(row.pair_key));
  }, [hoveredEdge, liveOps.relationshipRows]);

  return (
    <section className="system-body">
      <div className="system-body__header">
        <p className="system-body__kicker">System Body</p>
        <h2>Structural Integrity Field</h2>
        <p>{liveOps.heroSubline}</p>
      </div>

      <div className="integrity-hero">
        <div className="integrity-hero__lead">
          <p className="integrity-hero__kicker">KFT Primary System Condition Indicator</p>
          <h3>Systems fail in relationships before they fail in signals.</h3>
          <p>
            This field is the operational heartbeat of Neraium. It exposes hidden structural deterioration before endpoint telemetry crosses hard thresholds.
          </p>
        </div>
        <div className="integrity-hero__score">
          <div className="integrity-hero__score-orb">
            <KftHealthOrb systemState={systemState} intensity={1 - coherence} />
          </div>
          <span>KFT Coherence Index</span>
          <strong>{Math.round(coherence * 100)}</strong>
          <p>{state.label}</p>
        </div>
      </div>

      <div className="topology-card topology-card--heartbeat">
        <div className="topology-card__status">
          <StatusDot tone={liveOps.facilityTone} />
          <strong>Platform Heartbeat | {state.label}</strong>
          <span>{liveOps.connectionSummary}</span>
        </div>

        <StructuralIntegrityField
          systemState={systemState}
          intensity={Math.round((1 - coherence) * 100)}
          animated
        />
        <svg className={`topology-map ${fieldToneClass}`} viewBox="0 0 1000 600" role="img" aria-label="Structural integrity field">
          <defs>
            <marker id="arrow-forward" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#d0ab33" />
            </marker>
            <marker id="arrow-backward" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#39ff88" />
            </marker>
          </defs>
          <rect x="0" y="0" width="1000" height="600" className="integrity-field-bg" />
          <g className="integrity-isolines">
            <ellipse cx="500" cy="300" rx={420 + (1 - coherence) * 120} ry={220 + (1 - coherence) * 90} />
            <ellipse cx="500" cy="300" rx={330 + (1 - coherence) * 95} ry={170 + (1 - coherence) * 70} />
            <ellipse cx="500" cy="300" rx={240 + (1 - coherence) * 70} ry={120 + (1 - coherence) * 52} />
          </g>
          <g className="integrity-collapse-front">
            <line x1={220 + (1 - coherence) * 120} y1="90" x2={760 + (1 - coherence) * 60} y2="520" />
            <line x1={760 - (1 - coherence) * 110} y1="80" x2={250 - (1 - coherence) * 50} y2="500" />
          </g>

          {displayEdges.map((edge) => {
            const a = toXY(ZONES.find((zone) => zone.id === edge.from));
            const b = toXY(ZONES.find((zone) => zone.id === edge.to));
            const active = selectedTarget?.type === "edge" && selectedTarget.id === edge.id;
            return (
              <line
                key={edge.id}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                markerEnd={edge.marker}
                className={`topology-edge edge--${edge.tone ?? "pending"} ${active ? "topology-edge--active" : ""}`}
                style={{ strokeWidth: 1.8 + edge.strength * 6 }}
                onMouseEnter={() => setHoveredEdgeId(edge.id)}
                onMouseLeave={() => setHoveredEdgeId(null)}
                onClick={() => onSelectTarget({
                  type: "edge",
                  id: edge.id,
                  from: edge.from,
                  to: edge.to,
                  pairKeys: Array.from(new Set(edge.pairKeys)).filter(Boolean),
                  evidence: edge.evidence[0] ?? "Relationship movement detected.",
                })}
              />
            );
          })}

          {ZONES.map((zone) => {
            const point = toXY(zone);
            const active = selectedTarget?.type === "node" && selectedTarget.id === zone.id;
            return (
              <g key={zone.id} transform={`translate(${point.x}, ${point.y})`} onClick={() => onSelectTarget({ type: "node", id: zone.id, label: zone.label })}>
                <circle r="34" className={`topology-node ${state.nodeClass} ${active ? "topology-node--active" : ""}`} />
                <text className="topology-node__label" y="5">{zone.label}</text>
              </g>
            );
          })}
        </svg>
        <div className="integrity-footer">
          <span>Coherence Index</span>
          <strong>{Math.round(coherence * 100)}</strong>
          <p>Field coherence is continuous and decays as relationship structure separates.</p>
        </div>
        {edges.length === 0 && (
          <p className="topology-empty-hint">
            Waiting for relationship evidence. Showing baseline facility mesh.
          </p>
        )}
        {hoveredEdge && (
          <div className="topology-debug-panel" aria-live="polite">
            <p className="topology-debug-panel__title">
              {hoveredEdge.from.toUpperCase()} {"->"} {hoveredEdge.to.toUpperCase()}
            </p>
            <ul>
              {hoveredRows.slice(0, 4).map((row) => (
                <li key={row.pair_key}>
                  <span>pair_key</span>
                  <strong>{row.pair_key}</strong>
                  <span>baseline</span>
                  <strong>{row.baseline_correlation ?? "n/a"}</strong>
                  <span>recent</span>
                  <strong>{row.recent_correlation ?? "n/a"}</strong>
                  <span>change</span>
                  <strong>{row.change ?? "n/a"}</strong>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="system-body__notes">
        {(findings.length > 0 ? findings : [{ title: "Awaiting baseline", detail: "Connect telemetry to activate relationship evidence." }]).map((item, idx) => (
          <article key={`${item.title}-${idx}`} className="system-note">
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

