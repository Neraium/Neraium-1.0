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

const FRACTURE_RAYS = [
  { x1: 170, y1: 132, x2: 76, y2: 88 },
  { x1: 170, y1: 132, x2: 260, y2: 84 },
  { x1: 170, y1: 132, x2: 92, y2: 182 },
  { x1: 170, y1: 132, x2: 252, y2: 196 },
  { x1: 170, y1: 132, x2: 170, y2: 238 },
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function normalizeOrbState(systemState) {
  const value = String(systemState ?? "").toLowerCase();
  if (["unknown", "neutral", "none", "no_upload", "disconnected"].includes(value)) return "unknown";
  if (["watching", "watch"].includes(value)) return "watching";
  if (["drift", "warning", "alert"].includes(value)) return "drift";
  if (["propagation_active", "propagation", "critical"].includes(value)) return "propagation_active";
  if (["recovery", "recovering", "convergence"].includes(value)) return "recovery";
  return "stable";
}

function toneMeta(systemState) {
  const mode = normalizeOrbState(systemState);
  if (mode === "unknown") {
    return { className: "health-orb--neutral health-orb--state-unknown", hue: "#6e7d8a", coreOpacity: 0.52, pulse: 0.18 };
  }
  if (mode === "watching") {
    return { className: "health-orb--watch health-orb--state-watching", hue: "#c8a06a", coreOpacity: 0.78, pulse: 0.48 };
  }
  if (mode === "drift") {
    return { className: "health-orb--warning health-orb--drift health-orb--state-drift", hue: "#d28a52", coreOpacity: 0.88, pulse: 0.72 };
  }
  if (mode === "propagation_active") {
    return { className: "health-orb--critical health-orb--separation health-orb--state-propagation", hue: "#d46b5f", coreOpacity: 0.94, pulse: 0.92 };
  }
  if (mode === "recovery") {
    return { className: "health-orb--stable health-orb--recovery health-orb--state-recovery", hue: "#3f9fa0", coreOpacity: 0.82, pulse: 0.38 };
  }
  return { className: "health-orb--stable health-orb--state-stable", hue: "#6cba9c", coreOpacity: 0.8, pulse: 0.3 };
}

function transformNode(node, systemState, intensity) {
  const mode = normalizeOrbState(systemState);

  if (mode === "stable" || mode === "unknown") {
    return node;
  }

  if (mode === "watching" || mode === "drift" || mode === "recovery") {
    const shiftScale = mode === "watching" ? 0.42 : mode === "recovery" ? 0.34 : 0.86;
    const horizontalShift = (node.g === "left" ? -24 : node.g === "right" ? 24 : 0) * shiftScale;
    const verticalShift = (node.g === "top" ? -14 : node.g === "bottom" ? 11 : ((node.x + node.y) % 3 - 1) * 7) * shiftScale;
    return {
      ...node,
      x: clamp(node.x + horizontalShift * intensity, 66, 274),
      y: clamp(node.y + verticalShift * intensity, 42, 236),
    };
  }

  const outwardShift = node.g === "left"
    ? { x: -56, y: 14 }
    : node.g === "right"
      ? { x: 58, y: 16 }
      : node.g === "top"
        ? { x: 0, y: -38 }
        : node.g === "bottom"
          ? { x: 0, y: 30 }
          : { x: (node.x % 2 === 0 ? -14 : 16), y: (node.y % 2 === 0 ? 20 : -16) };

  return {
    ...node,
    x: clamp(node.x + outwardShift.x * intensity, 36, 304),
    y: clamp(node.y + outwardShift.y * intensity, 26, 254),
  };
}

function edgeVisibility(linkIndex, systemState) {
  const mode = normalizeOrbState(systemState);
  if (mode === "stable" || mode === "unknown" || mode === "recovery") {
    return "solid";
  }
  if (mode === "watching") {
    if (linkIndex % 8 === 0) {
      return "faint";
    }
    return "solid";
  }
  if (mode === "drift") {
    if (linkIndex % 6 === 0) {
      return "broken";
    }
    if (linkIndex % 3 === 0) {
      return "faint";
    }
    return "solid";
  }
  if (linkIndex % 3 === 0) {
    return "broken";
  }
  if (linkIndex % 4 === 0) {
    return "faint";
  }
  return "hidden";
}

export default function HealthOrb({ systemState = "stable", intensity = 0.4, animated = true }) {
  const mode = normalizeOrbState(systemState);
  const isCritical = mode === "propagation_active";
  const isWarning = mode === "drift";
  const isWatch = mode === "watching" || mode === "recovery";
  const isStable = mode === "stable" || mode === "unknown";
  const normalizedIntensity = clamp(Number(intensity) || 0, 0, 1);
  const tone = toneMeta(systemState);
  const nodes = ORB_NODES.map((node) => transformNode(node, systemState, normalizedIntensity));
  const nodeMap = Object.fromEntries(nodes.map((node) => [node.id, node]));

  return (
    <div
      className={`health-orb ${tone.className} ${animated ? "health-orb--animated" : ""}`}
      style={{
        "--orb-hue": tone.hue,
        "--orb-core-opacity": tone.coreOpacity,
        "--orb-pulse": tone.pulse,
        "--orb-signal-duration": `${(3.8 - tone.pulse * 1.6).toFixed(2)}s`,
        "--orb-node-duration": `${(5.4 - tone.pulse * 2).toFixed(2)}s`,
      }}
    >
      <svg className="health-orb__svg" viewBox="0 0 340 300" role="img" aria-label="System health orb">
        <defs>
          <radialGradient id="orbSphereGlow" cx="50%" cy="44%" r="52%">
            <stop offset="0%" stopColor="var(--orb-hue)" stopOpacity="0.36" />
            <stop offset="58%" stopColor="var(--orb-hue)" stopOpacity="0.1" />
            <stop offset="100%" stopColor="var(--orb-hue)" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="orbSpecularBloom" cx="34%" cy="24%" r="48%">
            <stop offset="0%" stopColor="white" stopOpacity="0.28" />
            <stop offset="52%" stopColor="white" stopOpacity="0.08" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="orbCoreGlow" cx="50%" cy="50%" r="54%">
            <stop offset="0%" stopColor="white" stopOpacity="0.94" />
            <stop offset="18%" stopColor="var(--orb-hue)" stopOpacity="0.92" />
            <stop offset="100%" stopColor="var(--orb-hue)" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="orbRimLight" x1="18%" y1="10%" x2="84%" y2="86%">
            <stop offset="0%" stopColor="white" stopOpacity="0.36" />
            <stop offset="36%" stopColor="white" stopOpacity="0.08" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="orbDirectionalAura" x1="8%" y1="18%" x2="92%" y2="82%">
            <stop offset="0%" stopColor="var(--orb-hue)" stopOpacity="0" />
            <stop offset="42%" stopColor="var(--orb-hue)" stopOpacity="0.34" />
            <stop offset="100%" stopColor="var(--orb-hue)" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="orbTelemetryTrace" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="var(--orb-hue)" stopOpacity="0" />
            <stop offset="46%" stopColor="white" stopOpacity="0.46" />
            <stop offset="100%" stopColor="var(--orb-hue)" stopOpacity="0" />
          </linearGradient>
          <clipPath id="orbSphereMask">
            <circle cx="170" cy="132" r={isCritical ? 92 : isWarning ? 90 : 88} />
          </clipPath>
        </defs>

        <g className="health-orb__base">
          <ellipse cx="170" cy="258" rx="72" ry="11" className="health-orb__base-core" />
          <ellipse cx="170" cy="258" rx="92" ry="16" className="health-orb__base-ring" />
          <ellipse cx="170" cy="258" rx="114" ry="22" className="health-orb__base-ring" />
          <ellipse cx="170" cy="258" rx="138" ry="28" className="health-orb__base-ring" />
        </g>

        <g className="health-orb__environment" aria-hidden="true">
          <path d="M60 116 C98 54 234 44 284 108" className="health-orb__directional-aura health-orb__directional-aura--upper" />
          <path d="M48 158 C96 226 236 232 296 158" className="health-orb__directional-aura health-orb__directional-aura--lower" />
          <path d="M82 132 C126 102 210 104 258 132" className="health-orb__telemetry-trace" />
          <path d="M76 88 C132 68 212 68 266 91" className="health-orb__telemetry-trace health-orb__telemetry-trace--slow" />
          <path d="M70 188 C124 214 220 214 274 188" className="health-orb__telemetry-trace health-orb__telemetry-trace--reverse" />
        </g>
        <circle cx="170" cy="132" r={isCritical ? 118 : isWarning ? 110 : isWatch ? 104 : 100} className="health-orb__propagation health-orb__propagation--outer" />
        <circle cx="170" cy="132" r={isCritical ? 100 : isWarning ? 96 : isWatch ? 92 : 88} className="health-orb__propagation health-orb__propagation--inner" />
        <circle cx="170" cy="132" r={isCritical ? 98 : isWarning ? 95 : isWatch ? 93 : 92} className="health-orb__aura" />
        <circle cx="170" cy="132" r={isStable ? 89 : isWatch ? 91 : isWarning ? 93 : 96} className="health-orb__shell" />
        <circle cx="170" cy="132" r={isStable ? 86 : isWatch ? 88 : isWarning ? 90 : 93} className="health-orb__specular" />
        <circle cx="170" cy="132" r={isStable ? 89 : isWatch ? 91 : isWarning ? 93 : 96} className="health-orb__rim" />

        <g className="health-orb__scan" clipPath="url(#orbSphereMask)">
          <line x1="82" y1="96" x2="258" y2="96" className="health-orb__scan-line" />
          <line x1="92" y1="168" x2="248" y2="168" className="health-orb__scan-line health-orb__scan-line--delayed" />
          <line x1="112" y1="74" x2="228" y2="194" className="health-orb__scan-line health-orb__scan-line--diagonal" />
        </g>

        <g className="health-orb__cognition-rings" aria-hidden="true">
          <ellipse cx="170" cy="132" rx="104" ry="36" className="health-orb__cognition-ring health-orb__cognition-ring--equator" />
          <ellipse cx="170" cy="132" rx="44" ry="102" className="health-orb__cognition-ring health-orb__cognition-ring--meridian" />
          <ellipse cx="170" cy="132" rx="72" ry="92" className="health-orb__cognition-ring health-orb__cognition-ring--tilt" />
        </g>

        <g className="health-orb__field" clipPath={isCritical ? undefined : "url(#orbSphereMask)"}>
          {ORB_LINKS.map(([from, to], index) => {
            const n1 = nodeMap[from];
            const n2 = nodeMap[to];
            const visibility = edgeVisibility(index, systemState);
            if (visibility === "hidden") {
              return null;
            }
            return (
              <g key={`${from}-${to}`}>
                <line
                  x1={n1.x}
                  y1={n1.y}
                  x2={n2.x}
                  y2={n2.y}
                  className={`health-orb__link health-orb__link--${visibility}`}
                />
                {(mode !== "unknown" && index % (isCritical ? 2 : isWarning ? 3 : 5) === 0) ? (
                  <line
                    x1={n1.x}
                    y1={n1.y}
                    x2={n2.x}
                    y2={n2.y}
                    className="health-orb__signal-packet"
                    style={{ "--orb-delay": `${index * 70}ms` }}
                  />
                ) : null}
              </g>
            );
          })}

          {nodes.map((node, index) => (
            <circle
              key={node.id}
              cx={node.x}
              cy={node.y}
              r={node.g === "core" ? 4.6 : node.g === "top" || node.g === "bottom" ? 3.6 : 3.2}
              className={`health-orb__node health-orb__node--${node.g} ${node.g === "core" ? "health-orb__node--core" : ""}`}
              style={{ "--orb-delay": `${index * 80}ms` }}
            />
          ))}
        </g>

        {isCritical && (
          <g className="health-orb__fractures">
            {FRACTURE_RAYS.map((ray, index) => (
              <line
                key={`${ray.x1}-${ray.y1}-${ray.x2}-${ray.y2}`}
                x1={ray.x1}
                y1={ray.y1}
                x2={ray.x2}
                y2={ray.y2}
                className="health-orb__fracture"
                style={{ "--orb-delay": `${index * 120}ms` }}
              />
            ))}
          </g>
        )}

        {isCritical && (
          <g className="health-orb__fragments health-orb__fragments--separation">
            {FRAGMENT_SPARKS.map((spark, index) => (
              <circle
                key={`${spark.x}-${spark.y}`}
                cx={spark.x}
                cy={spark.y}
                r={spark.r}
                className="health-orb__spark"
                style={{ "--orb-delay": `${index * 110}ms` }}
              />
            ))}
          </g>
        )}

        <circle cx="170" cy="132" r="34" className="health-orb__core" />
        <ellipse cx="154" cy="110" rx="20" ry="10" className="health-orb__core-sheen" />
        <circle cx="170" cy="132" r="14" className="health-orb__core-hotspot" />
      </svg>
    </div>
  );
}
