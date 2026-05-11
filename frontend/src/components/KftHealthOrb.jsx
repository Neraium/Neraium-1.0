const ORB_NODES = [
  { id: "n1", x: 170, y: 48, g: "top" },
  { id: "n2", x: 138, y: 60, g: "top" },
  { id: "n3", x: 202, y: 60, g: "top" },
  { id: "n4", x: 114, y: 82, g: "left" },
  { id: "n5", x: 150, y: 84, g: "core" },
  { id: "n6", x: 190, y: 84, g: "core" },
  { id: "n7", x: 226, y: 84, g: "right" },
  { id: "n8", x: 100, y: 118, g: "left" },
  { id: "n9", x: 132, y: 110, g: "left" },
  { id: "n10", x: 168, y: 112, g: "core" },
  { id: "n11", x: 206, y: 110, g: "right" },
  { id: "n12", x: 240, y: 120, g: "right" },
  { id: "n13", x: 108, y: 152, g: "left" },
  { id: "n14", x: 144, y: 146, g: "core" },
  { id: "n15", x: 178, y: 144, g: "core" },
  { id: "n16", x: 214, y: 148, g: "core" },
  { id: "n17", x: 236, y: 154, g: "right" },
  { id: "n18", x: 124, y: 186, g: "left" },
  { id: "n19", x: 158, y: 182, g: "core" },
  { id: "n20", x: 194, y: 184, g: "core" },
  { id: "n21", x: 226, y: 188, g: "right" },
  { id: "n22", x: 144, y: 214, g: "bottom" },
  { id: "n23", x: 174, y: 220, g: "bottom" },
  { id: "n24", x: 202, y: 214, g: "bottom" },
];

const ORB_LINKS = [
  ["n1", "n2"], ["n1", "n3"], ["n1", "n5"], ["n1", "n6"],
  ["n2", "n4"], ["n2", "n5"], ["n2", "n9"], ["n3", "n6"],
  ["n3", "n7"], ["n3", "n11"], ["n4", "n8"], ["n4", "n9"],
  ["n5", "n9"], ["n5", "n10"], ["n5", "n14"], ["n6", "n10"],
  ["n6", "n11"], ["n6", "n16"], ["n7", "n11"], ["n7", "n12"],
  ["n8", "n9"], ["n8", "n13"], ["n9", "n10"], ["n9", "n14"],
  ["n10", "n11"], ["n10", "n15"], ["n10", "n19"], ["n11", "n12"],
  ["n11", "n16"], ["n12", "n17"], ["n13", "n14"], ["n13", "n18"],
  ["n14", "n15"], ["n14", "n19"], ["n15", "n16"], ["n15", "n20"],
  ["n16", "n17"], ["n16", "n20"], ["n17", "n21"], ["n18", "n19"],
  ["n18", "n22"], ["n19", "n20"], ["n19", "n23"], ["n20", "n21"],
  ["n20", "n24"], ["n21", "n24"], ["n22", "n23"], ["n23", "n24"],
  ["n8", "n14"], ["n9", "n15"], ["n10", "n16"], ["n11", "n17"],
  ["n13", "n19"], ["n14", "n20"], ["n15", "n21"],
];

const FRAGMENT_SPARKS = [
  { x: 86, y: 72, r: 2.1 }, { x: 100, y: 56, r: 1.6 }, { x: 110, y: 94, r: 1.8 },
  { x: 238, y: 68, r: 2.4 }, { x: 254, y: 88, r: 1.9 }, { x: 266, y: 112, r: 1.5 },
  { x: 76, y: 142, r: 1.7 }, { x: 92, y: 162, r: 1.5 }, { x: 256, y: 150, r: 1.7 },
  { x: 274, y: 174, r: 2.2 }, { x: 120, y: 236, r: 1.6 }, { x: 226, y: 238, r: 1.8 },
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function toneMeta(systemState) {
  if (systemState === "drift") {
    return { className: "kft-orb--drift", hue: "#f3bb47", coreOpacity: 0.9 };
  }
  if (systemState === "separation") {
    return { className: "kft-orb--separation", hue: "#ff4d52", coreOpacity: 0.94 };
  }
  return { className: "kft-orb--stable", hue: "#a7ff3c", coreOpacity: 0.88 };
}

function transformNode(node, systemState, intensity) {
  if (systemState === "stable") {
    return node;
  }

  if (systemState === "drift") {
    const horizontalShift = node.g === "left" ? -18 : node.g === "right" ? 18 : 0;
    const verticalShift = node.g === "top" ? -10 : node.g === "bottom" ? 8 : ((node.x + node.y) % 3 - 1) * 5;
    return {
      ...node,
      x: clamp(node.x + horizontalShift * intensity, 66, 274),
      y: clamp(node.y + verticalShift * intensity, 42, 236),
    };
  }

  const outwardShift = node.g === "left"
    ? { x: -46, y: 10 }
    : node.g === "right"
      ? { x: 48, y: 12 }
      : node.g === "top"
        ? { x: 0, y: -30 }
        : node.g === "bottom"
          ? { x: 0, y: 24 }
          : { x: (node.x % 2 === 0 ? -10 : 12), y: (node.y % 2 === 0 ? 16 : -12) };

  return {
    ...node,
    x: clamp(node.x + outwardShift.x * intensity, 36, 304),
    y: clamp(node.y + outwardShift.y * intensity, 26, 254),
  };
}

function edgeVisibility(linkIndex, systemState) {
  if (systemState === "stable") {
    return "solid";
  }
  if (systemState === "drift") {
    return linkIndex % 5 === 0 ? "faint" : "solid";
  }
  if (linkIndex % 3 === 0) {
    return "broken";
  }
  return linkIndex % 2 === 0 ? "faint" : "hidden";
}

export default function KftHealthOrb({ systemState = "stable", intensity = 0.4, animated = true }) {
  const normalizedIntensity = clamp(Number(intensity) || 0, 0, 1);
  const tone = toneMeta(systemState);
  const nodes = ORB_NODES.map((node) => transformNode(node, systemState, normalizedIntensity));
  const nodeMap = Object.fromEntries(nodes.map((node) => [node.id, node]));

  return (
    <div
      className={`kft-orb ${tone.className} ${animated ? "kft-orb--animated" : ""}`}
      style={{ "--kft-hue": tone.hue, "--kft-core-opacity": tone.coreOpacity }}
    >
      <svg className="kft-orb__svg" viewBox="0 0 340 300" role="img" aria-label="KFT system health orb">
        <defs>
          <radialGradient id="kftSphereGlow" cx="50%" cy="44%" r="52%">
            <stop offset="0%" stopColor="var(--kft-hue)" stopOpacity="0.36" />
            <stop offset="58%" stopColor="var(--kft-hue)" stopOpacity="0.1" />
            <stop offset="100%" stopColor="var(--kft-hue)" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="kftCoreGlow" cx="50%" cy="50%" r="54%">
            <stop offset="0%" stopColor="white" stopOpacity="0.94" />
            <stop offset="18%" stopColor="var(--kft-hue)" stopOpacity="0.92" />
            <stop offset="100%" stopColor="var(--kft-hue)" stopOpacity="0" />
          </radialGradient>
          <clipPath id="kftSphereMask">
            <circle cx="170" cy="132" r={systemState === "separation" ? 92 : 88} />
          </clipPath>
        </defs>

        <g className="kft-orb__base">
          <ellipse cx="170" cy="258" rx="72" ry="11" className="kft-orb__base-core" />
          <ellipse cx="170" cy="258" rx="92" ry="16" className="kft-orb__base-ring" />
          <ellipse cx="170" cy="258" rx="114" ry="22" className="kft-orb__base-ring" />
          <ellipse cx="170" cy="258" rx="138" ry="28" className="kft-orb__base-ring" />
        </g>

        <circle cx="170" cy="132" r={systemState === "separation" ? 98 : 92} className="kft-orb__aura" />
        <circle cx="170" cy="132" r={systemState === "stable" ? 89 : systemState === "drift" ? 92 : 96} className="kft-orb__shell" />

        <g className="kft-orb__field" clipPath={systemState === "separation" ? undefined : "url(#kftSphereMask)"}>
          {ORB_LINKS.map(([from, to], index) => {
            const n1 = nodeMap[from];
            const n2 = nodeMap[to];
            const visibility = edgeVisibility(index, systemState);
            if (visibility === "hidden") {
              return null;
            }
            return (
              <line
                key={`${from}-${to}`}
                x1={n1.x}
                y1={n1.y}
                x2={n2.x}
                y2={n2.y}
                className={`kft-orb__link kft-orb__link--${visibility}`}
              />
            );
          })}

          {nodes.map((node, index) => (
            <circle
              key={node.id}
              cx={node.x}
              cy={node.y}
              r={node.g === "core" ? 4.6 : node.g === "top" || node.g === "bottom" ? 3.6 : 3.2}
              className={`kft-orb__node ${node.g === "core" ? "kft-orb__node--core" : ""}`}
              style={{ "--kft-delay": `${index * 80}ms` }}
            />
          ))}
        </g>

        {systemState === "separation" && (
          <g className="kft-orb__fragments">
            {FRAGMENT_SPARKS.map((spark, index) => (
              <circle
                key={`${spark.x}-${spark.y}`}
                cx={spark.x}
                cy={spark.y}
                r={spark.r}
                className="kft-orb__spark"
                style={{ "--kft-delay": `${index * 110}ms` }}
              />
            ))}
          </g>
        )}

        <circle cx="170" cy="132" r="34" className="kft-orb__core" />
        <circle cx="170" cy="132" r="14" className="kft-orb__core-hotspot" />
      </svg>
    </div>
  );
}
