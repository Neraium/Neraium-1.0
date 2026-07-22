import React, { useState } from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

function bubbleTone(tier, stability) {
  if (tier === "Withheld" || tier === "Deferred") return "insufficient";
  if (tier === "Narrowed") return "emerging";
  if (stability !== null && stability < 75) return "weakening";
  return "stable";
}

export default function PortfolioWorkspace({ sites = [], onSelectSite }) {
  const [focused, setFocused] = useState(null);
  return (
    <div className="portfolio-workspace">
      <header className="forensic-page-header"><div><span className="forensic-kicker">Portfolio</span><h1>Where does the evidence warrant attention?</h1><p>Sites are positioned by structural stability and the recency of meaningful evidence, not alarm state.</p></div><div className="forensic-window"><span>Comparison axis</span><strong>Recent evidence window</strong></div></header>
      <section className="portfolio-scatter" aria-labelledby="portfolio-scatter-title">
        <header><div><span className="forensic-kicker">Structural field</span><h2 id="portfolio-scatter-title">Site evidence distribution</h2></div><span>{sites.length} {sites.length === 1 ? "site" : "sites"}</span></header>
        <div className="portfolio-scatter__plot">
          <span className="portfolio-scatter__axis portfolio-scatter__axis--y">Structural stability</span><span className="portfolio-scatter__axis portfolio-scatter__axis--x">Recent comparison window →</span>
          {[25, 50, 75].map((line) => <i key={line} style={{ bottom: `${line}%` }} />)}
          {sites.map((site, index) => {
            const stability = site.stabilityPercent ?? 20;
            const size = Math.max(42, Math.min(78, 42 + site.activeInvestigations * 8));
            return <button key={site.id} type="button" className={`site-bubble site-bubble--${bubbleTone(site.evidenceQuality, site.stabilityPercent)}`} style={{ left: `${22 + (index * 29) % 66}%`, bottom: `${Math.max(12, Math.min(84, stability))}%`, width: size, height: size }} onMouseEnter={() => setFocused(site)} onFocus={() => setFocused(site)} onClick={() => onSelectSite(site)}><span>{site.name}</span><strong>{site.activeInvestigations}</strong></button>;
          })}
        </div>
        <div className="portfolio-scatter__legend"><span><i className="is-stable" />Stable</span><span><i className="is-weakening" />Weakening</span><span><i className="is-emerging" />Emerging / unusual</span><span><i className="is-insufficient" />Insufficient evidence</span></div>
        <div className="portfolio-governance" role="status" aria-live="polite"><span className="forensic-kicker">Governance boundary</span><p>{focused?.governanceStatement ?? "Focus a site to inspect its configured data-governance statement."}</p></div>
      </section>
      <section className="portfolio-list" aria-labelledby="portfolio-list-title"><header><div><span className="forensic-kicker">Accessible site index</span><h2 id="portfolio-list-title">Portfolio sites</h2></div></header><div className="forensic-table-wrap"><table><thead><tr><th>Site</th><th>Structural stability</th><th>Active investigations</th><th>Evidence quality</th><th>Data coverage</th><th>Most recent meaningful change</th><th>Governance</th><th><span className="sr-only">Open site</span></th></tr></thead><tbody>{sites.map((site) => <tr key={site.id} onFocus={() => setFocused(site)}><th scope="row">{site.name}</th><td>{site.stabilityPercent === null ? "Not established" : `${site.stabilityPercent}%`}</td><td>{site.activeInvestigations}</td><td><ConfidenceTierChip tier={site.evidenceQuality} /></td><td>{site.coverage === null ? "Not supplied" : `${Math.round(site.coverage * 100)}%`}</td><td>{site.lastMeaningfulChange}</td><td>{site.governanceStatus}</td><td><button type="button" onClick={() => onSelectSite(site)}>Open site</button></td></tr>)}</tbody></table></div></section>
    </div>
  );
}
