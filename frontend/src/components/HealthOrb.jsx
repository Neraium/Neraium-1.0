const BUD_NODES = [
  { id: "n1", x: 160, y: 58 },
  { id: "n2", x: 140, y: 76 },
  { id: "n3", x: 180, y: 76 },
  { id: "n4", x: 120, y: 102 },
  { id: "n5", x: 152, y: 98 },
  { id: "n6", x: 188, y: 98 },
  { id: "n7", x: 204, y: 122 },
  { id: "n8", x: 112, y: 132 },
  { id: "n9", x: 144, y: 126 },
  { id: "n10", x: 176, y: 126 },
  { id: "n11", x: 206, y: 146 },
  { id: "n12", x: 124, y: 160 },
  { id: "n13", x: 154, y: 156 },
  { id: "n14", x: 184, y: 156 },
  { id: "n15", x: 198, y: 178 },
  { id: "n16", x: 146, y: 188 },
  { id: "n17", x: 170, y: 196 },
  { id: "n18", x: 184, y: 206 },
];

const BUD_LINKS = [
  ["n1", "n2"], ["n1", "n3"], ["n2", "n5"], ["n3", "n6"],
  ["n2", "n4"], ["n3", "n7"], ["n4", "n9"], ["n5", "n9"], ["n5", "n10"],
  ["n6", "n10"], ["n6", "n11"], ["n8", "n9"], ["n9", "n10"], ["n10", "n11"],
  ["n8", "n12"], ["n9", "n13"], ["n10", "n14"], ["n11", "n15"],
  ["n12", "n13"], ["n13", "n14"], ["n14", "n15"],
  ["n13", "n16"], ["n14", "n17"], ["n16", "n17"], ["n17", "n18"],
  ["n9", "n14"], ["n10", "n13"],
];

function normalizeGateState(systemState) {
  const value = String(systemState ?? "").toLowerCase();
  if (["watch", "watching", "drift", "warning"].includes(value)) return "watch";
  if (["alert", "critical", "propagation", "propagation_active"].includes(value)) return "alert";
  return "stable";
}

function theme(state) {
  if (state === "alert") {
    return {
      className: "health-orb--bud-alert",
      stroke: "rgba(221, 102, 88, 0.94)",
      fill: "rgba(110, 28, 24, 0.2)",
      link: "rgba(232, 124, 110, 0.86)",
      node: "rgba(255, 222, 216, 0.98)",
    };
  }
  if (state === "watch") {
    return {
      className: "health-orb--bud-watch",
      stroke: "rgba(196, 156, 92, 0.92)",
      fill: "rgba(97, 76, 36, 0.18)",
      link: "rgba(205, 163, 100, 0.78)",
      node: "rgba(246, 226, 188, 0.96)",
    };
  }
  return {
    className: "health-orb--bud-stable",
    stroke: "rgba(141, 150, 160, 0.9)",
    fill: "rgba(65, 73, 82, 0.16)",
    link: "rgba(150, 159, 169, 0.62)",
    node: "rgba(220, 228, 235, 0.92)",
  };
}

export default function HealthOrb({ systemState = "stable", intensity = 0.4, animated = true }) {
  const state = normalizeGateState(systemState);
  const tone = theme(state);
  const pathClass = state === "alert" ? " gate-bud__pathway--critical" : state === "watch" ? " gate-bud__pathway--watch" : "";
  const resolvedIntensity = Math.max(0, Math.min(1, Number(intensity) || 0.4));

  return (
    <div
      className={`health-orb health-orb--gate-bud ${tone.className} ${animated ? "health-orb--gate-bud-animated" : ""}`}
      style={{ "--gate-intensity": resolvedIntensity }}
    >
      <svg className="health-orb__svg health-orb__svg--gate-bud" viewBox="0 0 320 280" role="img" aria-label="Aletheia Gate cultivation intelligence field">
        <g className="gate-bud">
          <path
            className="gate-bud__leaf gate-bud__leaf--core"
            d="M160 48 C142 76 138 110 152 148 C160 172 164 196 160 226 C180 210 192 184 194 150 C196 114 186 80 160 48 Z"
            fill={tone.fill}
            stroke={tone.stroke}
            strokeWidth="1.8"
          />
          <path
            className="gate-bud__leaf gate-bud__leaf--left"
            d="M154 74 C124 88 104 116 98 148 C92 178 100 198 120 212 C126 188 132 166 144 142 C154 120 158 98 154 74 Z"
            fill={tone.fill}
            stroke={tone.stroke}
            strokeWidth="1.6"
          />
          <path
            className="gate-bud__leaf gate-bud__leaf--right"
            d="M166 74 C196 88 216 116 222 148 C228 178 220 198 200 212 C194 188 188 166 176 142 C166 120 162 98 166 74 Z"
            fill={tone.fill}
            stroke={tone.stroke}
            strokeWidth="1.6"
          />

          <path className="gate-bud__vein" d="M160 62 L160 214" stroke={tone.stroke} />
          <path className="gate-bud__vein" d="M152 112 C136 128 126 146 120 170" stroke={tone.stroke} />
          <path className="gate-bud__vein" d="M168 112 C184 128 194 146 200 170" stroke={tone.stroke} />

          {BUD_LINKS.map(([from, to], index) => {
            const a = BUD_NODES.find((node) => node.id === from);
            const b = BUD_NODES.find((node) => node.id === to);
            return (
              <line
                key={`${from}-${to}`}
                className={`gate-bud__pathway${pathClass}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={tone.link}
                style={{ "--gate-delay": `${index * 70}ms` }}
              />
            );
          })}

          {BUD_NODES.map((node, index) => (
            <circle
              key={node.id}
              className={`gate-bud__node${state === "alert" && index % 3 === 0 ? " gate-bud__node--critical" : ""}`}
              cx={node.x}
              cy={node.y}
              r={index % 4 === 0 ? 3.2 : 2.6}
              fill={tone.node}
              style={{ "--gate-delay": `${index * 85}ms` }}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}
