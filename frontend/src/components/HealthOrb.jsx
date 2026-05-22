function normalizeGateState(systemState) {
  const value = String(systemState ?? "").toLowerCase().trim();
  if (["", "empty", "none", "no data", "no_data", "unknown", "offline", "reset"].includes(value)) return "neutral";
  if (["watch", "watching", "drift", "warning"].includes(value)) return "watch";
  if (["alert", "critical", "propagation", "propagation_active"].includes(value)) return "alert";
  return "stable";
}

function paletteFor(state) {
  if (state === "neutral") {
    return {
      className: "health-orb--iris-neutral",
      accent: "#9ca3af",
      accentSoft: "rgba(156, 163, 175, 0.18)",
      core: "#e5e7eb",
    };
  }
  if (state === "alert") {
    return {
      className: "health-orb--iris-alert",
      accent: "#f87171",
      accentSoft: "rgba(248, 113, 113, 0.28)",
      core: "#ffe5e5",
    };
  }
  if (state === "watch") {
    return {
      className: "health-orb--iris-watch",
      accent: "#f4c95d",
      accentSoft: "rgba(244, 201, 93, 0.24)",
      core: "#fff4d2",
    };
  }
  return {
    className: "health-orb--iris-stable",
    accent: "#67d3a7",
    accentSoft: "rgba(103, 211, 167, 0.22)",
    core: "#e3fff4",
  };
}

export default function HealthOrb({ systemState = "neutral", intensity = 0.4, animated = true }) {
  const state = normalizeGateState(systemState);
  const palette = paletteFor(state);
  const resolvedIntensity = Math.max(0, Math.min(1, Number(intensity) || 0.4));

  return (
    <div
      className={`health-orb health-orb--premium ${palette.className} ${animated ? "health-orb--premium-animated" : ""}`}
      style={{
        "--orb-accent": palette.accent,
        "--orb-accent-soft": palette.accentSoft,
        "--orb-core": palette.core,
        "--orb-intensity": resolvedIntensity,
      }}
    >
      <svg
        className="health-orb__svg health-orb__svg--premium"
        viewBox="0 0 320 280"
        role="img"
        aria-label="Neraium system orb"
        shapeRendering="geometricPrecision"
        textRendering="geometricPrecision"
      >
        <defs>
          <radialGradient id="orbCoreGradient" cx="42%" cy="34%" r="64%">
            <stop offset="0%" stopColor="var(--orb-core)" stopOpacity="0.96" />
            <stop offset="42%" stopColor="var(--orb-accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#05090f" stopOpacity="0.94" />
          </radialGradient>
          <radialGradient id="orbHaloGradient" cx="50%" cy="50%" r="56%">
            <stop offset="0%" stopColor="var(--orb-accent)" stopOpacity="0.3" />
            <stop offset="100%" stopColor="var(--orb-accent)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <g className="premium-orb">
          <circle className="premium-orb__halo" cx="160" cy="140" r="122" fill="url(#orbHaloGradient)" />
          <circle className="premium-orb__shell" cx="160" cy="140" r="92" fill="url(#orbCoreGradient)" />
          <circle className="premium-orb__rim premium-orb__rim--outer" cx="160" cy="140" r="99" />
          <circle className="premium-orb__rim premium-orb__rim--inner" cx="160" cy="140" r="75" />
          <ellipse className="premium-orb__equator" cx="160" cy="140" rx="78" ry="28" />
          <path className="premium-orb__arc premium-orb__arc--a" d="M83 140 A77 77 0 0 1 237 140" />
          <path className="premium-orb__arc premium-orb__arc--b" d="M93 114 A64 64 0 0 1 227 114" />
          <circle className="premium-orb__core" cx="160" cy="140" r="18" />
          <circle className="premium-orb__spec" cx="133" cy="109" r="16" />
        </g>
      </svg>
    </div>
  );
}
