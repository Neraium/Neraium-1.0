function normalizeGateState(systemState) {
  const value = String(systemState ?? "").toLowerCase();
  if (["watch", "watching", "drift", "warning"].includes(value)) return "watch";
  if (["alert", "critical", "propagation", "propagation_active"].includes(value)) return "alert";
  return "stable";
}

function tone(state) {
  if (state === "alert") {
    return {
      className: "health-orb--iris-alert",
      ring: "rgba(67, 144, 255, 0.96)",
      plate: "rgba(14, 48, 92, 0.28)",
      line: "rgba(126, 183, 255, 0.9)",
      node: "rgba(226, 240, 255, 0.98)",
    };
  }
  if (state === "watch") {
    return {
      className: "health-orb--iris-watch",
      ring: "rgba(52, 122, 255, 0.92)",
      plate: "rgba(20, 44, 84, 0.24)",
      line: "rgba(102, 168, 255, 0.82)",
      node: "rgba(218, 236, 255, 0.96)",
    };
  }
  return {
    className: "health-orb--iris-stable",
    ring: "rgba(124, 183, 255, 0.94)",
    plate: "rgba(38, 66, 108, 0.25)",
    line: "rgba(154, 203, 255, 0.8)",
    node: "rgba(236, 246, 255, 0.98)",
  };
}

const IRIS_CONNECTIONS = [
  [160, 74, 130, 104], [160, 74, 190, 104], [130, 104, 112, 140], [190, 104, 208, 140],
  [112, 140, 126, 176], [208, 140, 194, 176], [126, 176, 160, 194], [194, 176, 160, 194],
  [130, 104, 160, 138], [190, 104, 160, 138], [112, 140, 160, 138], [208, 140, 160, 138],
  [160, 138, 160, 194],
];

const IRIS_NODES = [
  [160, 74, 3.3], [130, 104, 2.8], [190, 104, 2.8], [112, 140, 2.9], [208, 140, 2.9],
  [126, 176, 2.7], [194, 176, 2.7], [160, 194, 3.2], [160, 138, 3.4],
];

const BLADES = [
  "M160 86 C146 92 138 106 138 122 C138 138 146 152 160 160 C172 152 180 138 180 122 C180 106 172 92 160 86 Z",
  "M208 122 C198 112 182 108 166 112 C150 116 136 126 128 140 C136 152 150 160 166 162 C182 164 198 158 208 146 Z",
  "M194 176 C194 162 186 146 174 136 C162 126 146 122 132 124 C128 138 132 154 140 166 C148 178 162 186 176 188 Z",
  "M126 176 C138 186 154 190 170 186 C186 182 198 172 204 158 C194 148 180 142 164 142 C148 142 134 148 124 158 Z",
  "M112 122 C122 134 138 140 154 138 C170 136 184 126 192 112 C184 100 170 92 154 90 C138 88 122 96 112 108 Z",
  "M160 86 C172 96 178 112 176 128 C174 144 164 158 150 166 C138 156 132 140 134 124 C136 108 146 94 160 86 Z",
];

export default function HealthOrb({ systemState = "stable", intensity = 0.4, animated = true }) {
  const state = normalizeGateState(systemState);
  const palette = tone(state);
  const resolvedIntensity = Math.max(0, Math.min(1, Number(intensity) || 0.4));

  return (
    <div
      className={`health-orb health-orb--gate-iris ${palette.className} ${animated ? "health-orb--gate-iris-animated" : ""}`}
      style={{ "--iris-intensity": resolvedIntensity }}
    >
      <svg
        className="health-orb__svg health-orb__svg--gate-iris"
        viewBox="0 0 320 280"
        role="img"
        aria-label="Aletheia Gate governed aperture"
        shapeRendering="geometricPrecision"
        textRendering="geometricPrecision"
      >
        <g className="gate-iris">
          <circle className="gate-iris__outer-ring" cx="160" cy="140" r="96" stroke={palette.ring} />
          <circle className="gate-iris__inner-ring" cx="160" cy="140" r="62" stroke={palette.ring} />

          {BLADES.map((d, index) => (
            <path key={`blade-${index}`} className="gate-iris__blade" d={d} fill={palette.plate} stroke={palette.ring} style={{ "--iris-delay": `${index * 90}ms` }} />
          ))}

          <circle className="gate-iris__aperture" cx="160" cy="140" r="22" />

          {IRIS_CONNECTIONS.map(([x1, y1, x2, y2], index) => (
            <line
              key={`line-${index}`}
              className={`gate-iris__pathway${state === "alert" ? " gate-iris__pathway--alert" : state === "watch" ? " gate-iris__pathway--watch" : ""}`}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={palette.line}
              style={{ "--iris-delay": `${index * 70}ms` }}
            />
          ))}

          {IRIS_NODES.map(([x, y, r], index) => (
            <circle
              key={`node-${index}`}
              className={`gate-iris__node${state === "alert" && index % 2 === 0 ? " gate-iris__node--alert" : ""}`}
              cx={x}
              cy={y}
              r={r}
              fill={palette.node}
              style={{ "--iris-delay": `${index * 80}ms` }}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}
