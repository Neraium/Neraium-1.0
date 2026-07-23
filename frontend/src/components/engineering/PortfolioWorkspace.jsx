import React from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

export default function PortfolioWorkspace({ sites = [], onSelectSite }) {
  return (
    <div className="portfolio-workspace">
      <header className="forensic-page-header">
        <div>
          <span className="forensic-kicker">Portfolio</span>
          <h1>Sites</h1>
          <p>Open a site to review its active findings and evidence.</p>
        </div>
      </header>
      <section className="portfolio-site-list" aria-label="Portfolio sites">
        {sites.map((site) => (
          <article key={site.id} className="portfolio-site-card">
            <div>
              <span>Status</span>
              <strong>{site.status}</strong>
            </div>
            <div>
              <span>Site</span>
              <h2>{site.name}</h2>
            </div>
            <div>
              <span>Active findings</span>
              <strong>{site.activeInvestigations}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <ConfidenceTierChip tier={site.evidenceQuality} />
            </div>
            <button type="button" className="forensic-button" onClick={() => onSelectSite(site)}>Open Site</button>
          </article>
        ))}
      </section>
    </div>
  );
}
