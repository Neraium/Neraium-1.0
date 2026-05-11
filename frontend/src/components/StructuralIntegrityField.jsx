import { useMemo } from "react";

const BASE_NODES = [
  { id: "n1", x: 0.22, y: 0.34, c: "a" },
  { id: "n2", x: 0.31, y: 0.27, c: "a" },
  { id: "n3", x: 0.38, y: 0.36, c: "a" },
  { id: "n4", x: 0.28, y: 0.45, c: "a" },
  { id: "n5", x: 0.50, y: 0.33, c: "core" },
  { id: "n6", x: 0.58, y: 0.28, c: "core" },
  { id: "n7", x: 0.66, y: 0.36, c: "core" },
  { id: "n8", x: 0.56, y: 0.46, c: "core" },
  { id: "n9", x: 0.75, y: 0.32, c: "b" },
  { id: "n10", x: 0.82, y: 0.40, c: "b" },
  { id: "n11", x: 0.74, y: 0.49, c: "b" },
  { id: "n12", x: 0.65, y: 0.56, c: "b" },
];

const LINKS = [
  ["n1", "n2"], ["n2", "n3"], ["n1", "n4"], ["n2", "n4"], ["n3", "n5"],
  ["n4", "n5"], ["n5", "n6"], ["n6", "n7"], ["n5", "n8"], ["n7", "n8"],
  ["n7", "n9"], ["n9", "n10"], ["n10", "n11"], ["n11", "n12"], ["n8", "n12"],
  ["n6", "n9"], ["n3", "n6"], ["n4", "n8"],
];

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function stateClass(systemState) {
  if (systemState === "drift") return "sif--drift";
  if (systemState === "separation") return "sif--separation";
  return "sif--stable";
}

export default function StructuralIntegrityField({ systemState = "stable", intensity = 0, animated = true }) {
  const level = clamp(Number(intensity) / 100, 0, 1);

  const nodes = useMemo(() => {
    return BASE_NODES.map((node, idx) => {
      let dx = 0;
      let dy = 0;
      if (systemState === "drift") {
        dx = (node.c === "a" ? -0.06 : node.c === "b" ? 0.07 : 0.02) * level;
        dy = (idx % 2 === 0 ? -0.03 : 0.04) * level;
      }
      if (systemState === "separation") {
        dx = (node.c === "a" ? -0.16 : node.c === "b" ? 0.18 : 0.05) * level;
        dy = (idx % 3 === 0 ? -0.08 : 0.09) * level;
      }
      return {
        ...node,
        x: clamp(node.x + dx, 0.06, 0.94),
        y: clamp(node.y + dy, 0.08, 0.92),
      };
    });
  }, [level, systemState]);

  const nodeMap = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const linkBreakThreshold = systemState === "separation" ? 0.38 : 1;

  return (
    <div className={`sif ${stateClass(systemState)} ${animated ? "sif--animated" : ""}`}>
      <svg className="sif__svg" viewBox="0 0 1000 560" role="img" aria-label="Structural integrity field">
        <defs>
          <radialGradient id="sifGlow" cx="50%" cy="50%" r="52%">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.2" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect x="0" y="0" width="1000" height="560" className="sif__bg" />
        <ellipse cx="500" cy="280" rx={320 + level * 120} ry={170 + level * 85} className="sif__field" />
        <ellipse cx="500" cy="280" rx={245 + level * 92} ry={126 + level * 62} className="sif__field" />

        <g className="sif__links">
          {LINKS.map(([a, b], i) => {
            const n1 = nodeMap[a];
            const n2 = nodeMap[b];
            const dx = n2.x - n1.x;
            const dy = n2.y - n1.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const broken = dist > linkBreakThreshold;
            const weak = systemState !== "stable" && dist > 0.23;
            return (
              <line
                key={`${a}-${b}`}
                x1={n1.x * 1000}
                y1={n1.y * 560}
                x2={n2.x * 1000}
                y2={n2.y * 560}
                className={`sif__link ${weak ? "sif__link--weak" : ""} ${broken ? "sif__link--broken" : ""}`}
                style={{ animationDelay: `${(i % 7) * 120}ms` }}
              />
            );
          })}
        </g>

        <g className="sif__nodes">
          {nodes.map((n, i) => (
            <circle
              key={n.id}
              cx={n.x * 1000}
              cy={n.y * 560}
              r={systemState === "separation" ? 8 + (i % 3) : 7}
              className="sif__node"
              style={{ animationDelay: `${(i % 6) * 90}ms` }}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}
