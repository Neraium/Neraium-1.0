import React from "react";

export default function DataGapBand({ gap, compact = false }) {
  if (!gap) return null;
  return (
    <div className={compact ? "data-gap-band data-gap-band--compact" : "data-gap-band"} role="note" aria-label={`Data Gap from ${gap.source}`}>
      <span className="data-gap-band__pattern" aria-hidden="true" />
      <div><strong>Data Gap</strong><span>{gap.source}</span></div>
      {!compact ? <dl>
        <div><dt>Missing duration</dt><dd>{gap.duration}</dd></div>
        <div><dt>Signals affected</dt><dd>{gap.signals.length ? gap.signals.join(", ") : "Not identified"}</dd></div>
        <div><dt>Coverage</dt><dd>{gap.coverageImpact === null ? "Not supplied" : `${Math.round(gap.coverageImpact > 1 ? gap.coverageImpact : gap.coverageImpact * 100)}%`}</dd></div>
        <div><dt>Confidence impact</dt><dd>Conclusion tier is downgraded when it spans this gap</dd></div>
        <div><dt>Change-window overlap</dt><dd>{gap.overlapsChange === null ? "Not established" : gap.overlapsChange ? "Yes" : "No"}</dd></div>
      </dl> : null}
    </div>
  );
}
