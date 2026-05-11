import { useMemo } from "react";

const FIELD_NODES = [
  { id: "n1", x: 0.5, y: 0.12, g: "top" },
  { id: "n2", x: 0.41, y: 0.16, g: "top" },
  { id: "n3", x: 0.59, y: 0.16, g: "top" },
  { id: "n4", x: 0.33, y: 0.24, g: "left" },
  { id: "n5", x: 0.45, y: 0.24, g: "core" },
  { id: "n6", x: 0.55, y: 0.24, g: "core" },
  { id: "n7", x: 0.67, y: 0.24, g: "right" },
  { id: "n8", x: 0.28, y: 0.36, g: "left" },
  { id: "n9", x: 0.38, y: 0.33, g: "left" },
  { id: "n10", x: 0.5, y: 0.34, g: "core" },
  { id: "n11", x: 0.62, y: 0.33, g: "right" },
  { id: "n12", x: 0.72, y: 0.36, g: "right" },
  { id: "n13", x: 0.25, y: 0.49, g: "left" },
  { id: "n14", x: 0.36, y: 0.45, g: "core" },
  { id: "n15", x: 0.45, y: 0.46, g: "core" },
  { id: "n16", x: 0.55, y: 0.46, g: "core" },
  { id: "n17", x: 0.64, y: 0.45, g: "core" },
  { id: "n18", x: 0.75, y: 0.49, g: "right" },
  { id: "n19", x: 0.29, y: 0.63, g: "left" },
  { id: "n20", x: 0.4, y: 0.59, g: "core" },
  { id: "n21", x: 0.5, y: 0.6, g: "core" },
  { id: "n22", x: 0.6, y: 0.59, g: "core" },
  { id: "n23", x: 0.71, y: 0.63, g: "right" },
  { id: "n24", x: 0.37, y: 0.75, g: "bottom" },
  { id: "n25", x: 0.5, y: 0.79, g: "bottom" },
  { id: "n26", x: 0.63, y: 0.75, g: "bottom" },
];

const FIELD_LINKS = [
  ["n1", "n2"], ["n1", "n3"], ["n1", "n5"], ["n1", "n6"],
  ["n2", "n4"], ["n2", "n5"], ["n2", "n9"], ["n3", "n6"], ["n3", "n7"], ["n3", "n11"],
  ["n4", "n8"], ["n4", "n9"], ["n4", "n14"], ["n5", "n9"], ["n5", "n10"], ["n5", "n15"],
  ["n6", "n10"], ["n6", "n11"], ["n6", "n16"], ["n7", "n11"], ["n7", "n12"], ["n7", "n17"],
  ["n8", "n9"], ["n8", "n13"], ["n8", "n14"], ["n9", "n10"], ["n9", "n14"], ["n9", "n15"],
  ["n10", "n11"], ["n10", "n15"], ["n10", "n16"], ["n10", "n21"], ["n11", "n12"], ["n11", "n16"],
  ["n11", "n17"], ["n12", "n18"], ["n12", "n17"], ["n13", "n14"], ["n13", "n19"], ["n14", "n15"],
  ["n14", "n20"], ["n15", "n16"], ["n15", "n20"], ["n15", "n21"], ["n16", "n17"], ["n16", "n21"],
  ["n16", "n22"], ["n17", "n18"], ["n17", "n22"], ["n18", "n23"], ["n19", "n20"], ["n19", "n24"],
  ["n20", "n21"], ["n20", "n24"], ["n20", "n25"], ["n21", "n22"], ["n21", "n25"], ["n22", "n23"],
  ["n22", "n25"], ["n22", "n26"], ["n23", "n26"], ["n24", "n25"], ["n25", "n26"],
];

const FIELD_SPARKS = [
  { x: 0.14, y: 0.18, r: 3.2 }, { x: 0.19, y: 0.29, r: 2.4 }, { x: 0.1, y: 0.47, r: 2.1 },
  { x: 0.21, y: 0.69, r: 2.8 }, { x: 0.83, y: 0.16, r: 3.4 }, { x: 0.89, y: 0.3, r: 2.2 },
  { x: 0.92, y: 0.51, r: 2.8 }, { x: 0.8, y: 0.73, r: 2.1 }, { x: 0.48, y: 0.07, r: 1.8 },
  { x: 0.53, y: 0.91, r: 2.2 }, { x: 0.32, y: 0.09, r: 1.7 }, { x: 0.69, y: 0.88, r: 1.9 },
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function stateClass(systemState) {
  if (systemState === "drift") return "sif--drift";
  if (systemState === "separation") return "sif--separation";
  return "sif--stable";
}

function transformNode(node, systemState, level) {
  if (systemState === "stable") {
    return node;
  }

  if (systemState === "drift") {
    const driftX = node.g === "left" ? -0.08 : node.g === "right" ? 0.09 : node.g === "top" ? 0.01 : 0;
    const driftY = node.g === "top" ? -0.05 : node.g === "bottom" ? 0.03 : ((node.x + node.y) % 0.04 > 0.02 ? 0.032 : -0.024);
    return {
      ...node,
      x: clamp(node.x + driftX * level, 0.08, 0.92),
      y: clamp(node.y + driftY * level, 0.08, 0.9),
    };
  }

  const separationShift = node.g === "left"
    ? { x: -0.17, y: 0.04 }
    : node.g === "right"
      ? { x: 0.18, y: 0.05 }
      : node.g === "top"
        ? { x: 0, y: -0.1 }
        : node.g === "bottom"
          ? { x: 0, y: 0.09 }
          : { x: node.x < 0.5 ? -0.06 : 0.06, y: node.y < 0.5 ? -0.02 : 0.04 };

  return {
    ...node,
    x: clamp(node.x + separationShift.x * level, 0.06, 0.94),
    y: clamp(node.y + separationShift.y * level, 0.06, 0.92),
  };
}

function edgeVisibility(index, systemState) {
  if (systemState === "stable") {
    return "solid";
  }
  if (systemState === "drift") {
    return index % 6 === 0 ? "faint" : "solid";
  }
  if (index % 4 === 0) {
    return "broken";
  }
  return index % 2 === 0 ? "faint" : "hidden";
}

export default function StructuralIntegrityField({ systemState = "stable", intensity = 0, animated = true }) {
  const level = clamp(Number(intensity) / 100, 0, 1);

  const nodes = useMemo(
    () => FIELD_NODES.map((node) => transformNode(node, systemState, level)),
    [level, systemState],
  );

  const nodeMap = useMemo(() => Object.fromEntries(nodes.map((node) => [node.id, node])), [nodes]);
  const shellRx = systemState === "stable" ? 285 : systemState === "drift" ? 318 : 346;
  const shellRy = systemState === "stable" ? 166 : systemState === "drift" ? 184 : 208;

  return (
    <div className={`sif ${stateClass(systemState)} ${animated ? "sif--animated" : ""}`}>
      <svg className="sif__svg" viewBox="0 0 1000 560" role="img" aria-label="Structural integrity field">
        <defs>
          <radialGradient id="sifGlow" cx="50%" cy="44%" r="56%">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.32" />
            <stop offset="65%" stopColor="currentColor" stopOpacity="0.08" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="sifCore" cx="50%" cy="50%" r="58%">
            <stop offset="0%" stopColor="white" stopOpacity="0.9" />
            <stop offset="24%" stopColor="currentColor" stopOpacity="0.85" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </radialGradient>
          <clipPath id="sifSphereMask">
            <ellipse cx="500" cy="230" rx={systemState === "separation" ? 335 : 295} ry={systemState === "separation" ? 204 : 174} />
          </clipPath>
        </defs>

        <rect x="0" y="0" width="1000" height="560" className="sif__bg" />

        <g className="sif__base">
          <ellipse cx="500" cy="492" rx="98" ry="15" className="sif__base-core" />
          <ellipse cx="500" cy="492" rx="146" ry="24" className="sif__base-ring" />
          <ellipse cx="500" cy="492" rx="204" ry="36" className="sif__base-ring" />
          <ellipse cx="500" cy="492" rx="274" ry="48" className="sif__base-ring" />
        </g>

        <ellipse cx="500" cy="230" rx={shellRx + 34} ry={shellRy + 26} className="sif__aura" />
        <ellipse cx="500" cy="230" rx={shellRx} ry={shellRy} className="sif__shell" />

        <g className="sif__mesh" clipPath={systemState === "separation" ? undefined : "url(#sifSphereMask)"}>
          {FIELD_LINKS.map(([from, to], index) => {
            const first = nodeMap[from];
            const second = nodeMap[to];
            const visibility = edgeVisibility(index, systemState);
            if (visibility === "hidden") {
              return null;
            }

            return (
              <line
                key={`${from}-${to}`}
                x1={first.x * 1000}
                y1={first.y * 460}
                x2={second.x * 1000}
                y2={second.y * 460}
                className={`sif__link sif__link--${visibility}`}
                style={{ animationDelay: `${(index % 9) * 110}ms` }}
              />
            );
          })}

          {nodes.map((node, index) => (
            <circle
              key={node.id}
              cx={node.x * 1000}
              cy={node.y * 460}
              r={node.g === "core" ? 8 : node.g === "top" || node.g === "bottom" ? 6.4 : 5.6}
              className={`sif__node ${node.g === "core" ? "sif__node--core" : ""}`}
              style={{ animationDelay: `${(index % 8) * 90}ms` }}
            />
          ))}
        </g>

        {systemState === "separation" && (
          <g className="sif__fragments">
            {FIELD_SPARKS.map((spark, index) => (
              <circle
                key={`${spark.x}-${spark.y}`}
                cx={spark.x * 1000}
                cy={spark.y * 460}
                r={spark.r}
                className="sif__spark"
                style={{ animationDelay: `${index * 120}ms` }}
              />
            ))}
          </g>
        )}

        <circle cx="500" cy="230" r="46" className="sif__core" />
        <circle cx="500" cy="230" r="18" className="sif__hotspot" />
      </svg>
    </div>
  );
}
