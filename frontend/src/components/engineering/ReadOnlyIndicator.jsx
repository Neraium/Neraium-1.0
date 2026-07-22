import React from "react";

export default function ReadOnlyIndicator({ compact = false }) {
  return <div className={compact ? "readonly-indicator readonly-indicator--compact" : "readonly-indicator"} role="note"><span aria-hidden="true">◇</span> Read-only intelligence <span aria-hidden="true">·</span> No control actions</div>;
}
