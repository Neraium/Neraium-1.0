import React from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

export default function SiteStabilitySummary({ site }) {
  return (
    <section className="site-stability-summary" aria-labelledby="site-stability-title">
      <div><span className="forensic-kicker">Site stability</span><strong id="site-stability-title">{site.stabilityPercent === null ? "Not established" : `${site.stabilityPercent}%`}</strong><small>Structural relationship stability</small></div>
      <div><span className="forensic-kicker">Active investigations</span><strong>{site.activeInvestigations}</strong><small>Bounded findings requiring review</small></div>
      <div><span className="forensic-kicker">Evidence quality</span><ConfidenceTierChip tier={site.evidenceQuality} /><small>{site.coverage === null ? "Coverage not supplied" : `${Math.round(site.coverage * 100)}% data coverage`}</small></div>
    </section>
  );
}
