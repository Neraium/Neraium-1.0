import { useId } from "react";

function normalizeMarkState(systemState) {
  const value = String(systemState ?? "").toLowerCase().trim();
  if (["", "empty", "none", "no data", "no_data", "unknown", "offline", "reset"].includes(value)) return "neutral";
  if (["alert", "critical", "propagation", "propagation_active", "elevated", "risk"].includes(value)) return "alert";
  if (["watch", "watching", "drift", "warning", "change", "change_detected"].includes(value)) return "watch";
  return "stable";
}

function paletteFor(state) {
  if (state === "neutral") {
    return {
      className: "system-mark--neutral",
      accent: "#8a98a6",
      accentSoft: "rgba(138, 152, 166, 0.18)",
      track: "rgba(138, 152, 166, 0.42)",
      core: "#c3ccd5",
    };
  }
  if (state === "alert") {
    return {
      className: "system-mark--alert",
      accent: "#d45f55",
      accentSoft: "rgba(212, 95, 85, 0.3)",
      track: "rgba(212, 95, 85, 0.54)",
      core: "#ffd6d0",
    };
  }
  if (state === "watch") {
    return {
      className: "system-mark--watch",
      accent: "#d3a547",
      accentSoft: "rgba(211, 165, 71, 0.28)",
      track: "rgba(211, 165, 71, 0.52)",
      core: "#ffe7b5",
    };
  }
  return {
    className: "system-mark--stable",
    accent: "#35a7a0",
    accentSoft: "rgba(53, 167, 160, 0.26)",
    track: "rgba(87, 190, 196, 0.5)",
    core: "#d9fbf8",
  };
}

export default function SystemStateMark({ systemState = "neutral", intensity = 0.4, animated = true }) {
  const state = normalizeMarkState(systemState);
  const palette = paletteFor(state);
  const resolvedIntensity = Math.max(0, Math.min(1, Number(intensity) || 0.35));
  const svgId = useId().replace(/:/g, "");
  const frameGradientId = `${svgId}-frame`;
  const markGradientId = `${svgId}-mark`;
  const glowGradientId = `${svgId}-glow`;
  const glowFilterId = `${svgId}-soft-glow`;
  const orbitStyle = {
    fill: "none",
    stroke: "var(--mark-track)",
    strokeWidth: 1.2,
    opacity: 0.78,
    vectorEffect: "non-scaling-stroke",
  };
  const tileBackgroundStyle = {
    fill: `url(#${frameGradientId})`,
    stroke: "rgba(255, 255, 255, 0.08)",
    strokeWidth: 1,
  };
  const tileRimStyle = {
    fill: "rgba(255, 255, 255, 0.02)",
    stroke: "rgba(255, 255, 255, 0.14)",
    strokeWidth: 1,
  };
  const mazeOuterStyle = {
    fill: `url(#${markGradientId})`,
    opacity: 0.94,
  };
  const mazeInnerStyle = {
    fill: "none",
    stroke: "rgba(255, 255, 255, 0.3)",
    strokeWidth: 1.5,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    vectorEffect: "non-scaling-stroke",
  };
  const mazeCircuitStyle = {
    fill: "none",
    stroke: "rgba(255, 255, 255, 0.22)",
    strokeWidth: 1.1,
    strokeLinecap: "round",
    vectorEffect: "non-scaling-stroke",
  };
  const scanStyle = {
    fill: "none",
    stroke: "rgba(255, 255, 255, 0.28)",
    strokeWidth: 1,
    strokeLinecap: "round",
    opacity: 0.78,
    vectorEffect: "non-scaling-stroke",
  };
  const nodeStyle = {
    fill: "var(--mark-core)",
    opacity: 0.92,
  };

  return (
    <div
      className={`system-mark ${palette.className} ${animated ? "system-mark--animated" : ""}`}
      style={{
        "--mark-accent": palette.accent,
        "--mark-accent-soft": palette.accentSoft,
        "--mark-track": palette.track,
        "--mark-core": palette.core,
        "--mark-intensity": resolvedIntensity,
      }}
    >
      <svg
        className="system-mark__svg"
        viewBox="0 0 320 320"
        role="img"
        aria-label="Neraium active system state"
        shapeRendering="geometricPrecision"
        textRendering="geometricPrecision"
      >
        <defs>
          <linearGradient id={frameGradientId} x1="42" y1="34" x2="278" y2="286" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.18" />
            <stop offset="38%" stopColor="var(--mark-accent)" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#03080e" stopOpacity="0.92" />
          </linearGradient>
          <linearGradient id={markGradientId} x1="83" y1="78" x2="238" y2="246" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="var(--mark-core)" />
            <stop offset="56%" stopColor="var(--mark-accent)" />
            <stop offset="100%" stopColor="var(--mark-core)" stopOpacity="0.82" />
          </linearGradient>
          <radialGradient id={glowGradientId} cx="50%" cy="50%" r="58%">
            <stop offset="0%" stopColor="var(--mark-accent)" stopOpacity="0.35" />
            <stop offset="62%" stopColor="var(--mark-accent)" stopOpacity="0.1" />
            <stop offset="100%" stopColor="var(--mark-accent)" stopOpacity="0" />
          </radialGradient>
          <filter id={glowFilterId} x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feColorMatrix in="blur" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.58 0" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g className="system-mark__field" aria-hidden="true">
          <circle cx="160" cy="160" r="132" fill={`url(#${glowGradientId})`} />
          <path className="system-mark__orbit system-mark__orbit--a" d="M78 86 C120 44 201 47 243 93 C285 138 278 211 230 250 C180 291 105 279 70 226 C41 181 45 119 78 86Z" style={orbitStyle} />
          <path className="system-mark__orbit system-mark__orbit--b" d="M56 164 C98 122 121 99 160 99 C199 99 222 122 264 164" style={{ ...orbitStyle, opacity: 0.58 }} />
        </g>

        <g className="system-mark__tile" filter={`url(#${glowFilterId})`}>
          <rect className="system-mark__tile-bg" x="52" y="52" width="216" height="216" rx="54" style={tileBackgroundStyle} />
          <rect className="system-mark__tile-rim" x="59" y="59" width="202" height="202" rx="48" style={tileRimStyle} />
          <path className="system-mark__maze system-mark__maze--outer" d="M92 218 V104 C92 96 98 90 106 90 H124 C132 90 138 96 138 104 V154 L188 96 C193 91 198 90 206 90 H218 C226 90 232 96 232 104 V218 C232 226 226 232 218 232 H200 C192 232 186 226 186 218 V166 L136 226 C131 231 125 232 118 232 H106 C98 232 92 226 92 218Z" style={mazeOuterStyle} />
          <path className="system-mark__maze system-mark__maze--inner" d="M117 207 V113 H119 L193 207 H207 V113" style={mazeInnerStyle} />
          <path className="system-mark__maze system-mark__maze--circuit" d="M116 116 H139 M116 143 H158 M116 170 H181 M181 116 H207 M160 207 H207" style={mazeCircuitStyle} />
          <path className="system-mark__scan" d="M93 218 V104 C93 96 99 91 106 91 H123 C131 91 137 97 137 104 V153 L187 97 C193 91 199 91 206 91 H217 C225 91 231 97 231 104 V218" style={scanStyle} />
          <circle className="system-mark__node system-mark__node--a" cx="117" cy="116" r="4" style={nodeStyle} />
          <circle className="system-mark__node system-mark__node--b" cx="207" cy="207" r="4" style={nodeStyle} />
          <circle className="system-mark__node system-mark__node--c" cx="162" cy="160" r="3.5" style={nodeStyle} />
        </g>
      </svg>
    </div>
  );
}
