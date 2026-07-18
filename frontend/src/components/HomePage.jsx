import { useCallback, useRef } from "react";

import SkipToMainContent from "./SkipToMainContent";
import SystemStateMark from "./SystemStateMark";
import { PRODUCT_DESCRIPTOR, PRODUCT_NAME } from "../content/productLanguage";
import "../styles/home.css";

const PLATFORM_CARDS = [
  {
    title: "Facility behavior",
    body: "Learns how systems normally interact across the full operating environment.",
  },
  {
    title: "Prioritized insights",
    body: "Ranks operational changes by severity, confidence, and investigation value.",
  },
  {
    title: "Investigation support",
    body: "Explains why behavior changed and where operators should begin.",
  },
];

const HERO_SIGNALS = [
  ["Operational state", "Current facility behavior"],
  ["What changed", "Relationships outside baseline"],
  ["Where to begin", "Highest-priority insight"],
];

const WORKFLOW_STEPS = [
  {
    title: "Baseline",
    body: "Builds a learned model of normal behavior across connected infrastructure.",
  },
  {
    title: "Observe",
    body: "Tracks system relationships as operations shift through changing demand and conditions.",
  },
  {
    title: "Explain",
    body: "Surfaces meaningful behavioral change with system context and recommended investigation focus.",
  },
];

const SYSTEM_AREAS = [
  "Resorts",
  "Commercial buildings",
  "Hospitals",
  "Manufacturing",
  "District energy",
  "Water treatment",
  "Data centers",
  "Chilled water",
  "Boilers",
  "Cooling towers",
  "Domestic water",
  "Pools",
  "Irrigation",
  "Electrical distribution",
  "Lighting",
  "Elevators",
  "Kitchen equipment",
  "Laundry",
  "Transportation",
  "Wastewater",
  "Refrigeration",
  "Fire/life safety",
  "Guest room systems",
  "Renewable energy",
  "Fuel systems",
  "Compressed air",
  "Building automation",
  "Utility infrastructure",
];

export default function HomePage({ onLaunchWorkspace }) {
  const orbRef = useRef(null);

  const scrollToSection = useCallback((sectionId) => {
    if (typeof document === "undefined") return;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    document.getElementById(sectionId)?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }, []);

  const handleOrbPointerMove = useCallback((event) => {
    const element = orbRef.current;
    if (!element) return;
    const bounds = element.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
    const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
    element.style.setProperty("--orb-x", x.toFixed(3));
    element.style.setProperty("--orb-y", y.toFixed(3));
  }, []);

  const resetOrbPointer = useCallback(() => {
    const element = orbRef.current;
    if (!element) return;
    element.style.setProperty("--orb-x", "0");
    element.style.setProperty("--orb-y", "0");
  }, []);

  return (
    <div className="home-page" data-testid="home-page">
      <SkipToMainContent />
      <header className="home-nav" aria-label="Neraium site navigation">
        <button type="button" className="home-brand" onClick={() => scrollToSection("home-hero")} aria-label="Neraium home">
          <span className="home-brand__mark" aria-hidden="true" />
          <span>Neraium</span>
        </button>
        <nav className="home-nav__links" aria-label="Primary navigation">
          <button type="button" onClick={() => scrollToSection("platform")}>Platform</button>
          <button type="button" onClick={() => scrollToSection("intelligence")}>Intelligence</button>
          <button type="button" onClick={() => scrollToSection("systems")}>Systems</button>
          <button type="button" onClick={() => scrollToSection("about")}>About</button>
        </nav>
        <button type="button" className="home-nav__launch" onClick={onLaunchWorkspace}>Open Command Center</button>
      </header>

      <main id="main-content" tabIndex={-1}>
        <section id="home-hero" className="home-hero" aria-labelledby="home-title">
          <div className="home-hero__copy">
            <p className="home-eyebrow">{PRODUCT_NAME}</p>
            <h1 id="home-title">{PRODUCT_DESCRIPTOR} for Critical Infrastructure</h1>
            <p>
              Neraium is the platform. Its SII learns how facilities normally behave, identifies meaningful operational change, and shows operators where to investigate first.
            </p>
          </div>

          <div className="home-signal-strip" role="list" aria-label="Neraium command center focus">
            {HERO_SIGNALS.map(([label, value]) => (
              <div className="home-signal-strip__item" key={label} role="listitem">
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>

          <div
            ref={orbRef}
            className="home-orb"
            onPointerMove={handleOrbPointerMove}
            onPointerLeave={resetOrbPointer}
            role="img"
            aria-label="Animated Systemic Infrastructure Intelligence status"
          >
            <div className="home-orb__energy home-orb__energy--outer" aria-hidden="true" />
            <div className="home-orb__energy home-orb__energy--inner" aria-hidden="true" />
            <div className="home-orb__trace home-orb__trace--a" aria-hidden="true" />
            <div className="home-orb__trace home-orb__trace--b" aria-hidden="true" />
            <div className="home-orb__body">
              <SystemStateMark systemState="stable" intensity={0.18} animated />
            </div>
          </div>

          <div className="home-hero__actions" role="group" aria-label="Primary actions">
            <button type="button" className="home-command" onClick={onLaunchWorkspace}>Open Command Center</button>
            <button type="button" className="home-secondary" onClick={() => scrollToSection("platform")}>View Platform</button>
          </div>
        </section>

        <section id="platform" className="home-section home-section--platform" aria-labelledby="platform-title">
          <div className="home-section__header">
            <p className="home-eyebrow">Platform</p>
            <h2 id="platform-title">The Neraium platform is built for teams operating complex infrastructure.</h2>
          </div>
          <div className="home-card-grid">
            {PLATFORM_CARDS.map((card) => (
              <article className="home-card" key={card.title}>
                <h3>{card.title}</h3>
                <p>{card.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="intelligence" className="home-section home-section--workflow" aria-labelledby="workflow-title">
          <div className="home-section__header">
            <p className="home-eyebrow">How It Works</p>
            <h2 id="workflow-title">Learn. Observe. Explain.</h2>
          </div>
          <div className="home-workflow">
            {WORKFLOW_STEPS.map((step, index) => (
              <article className="home-workflow__step" key={step.title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="systems" className="home-section home-section--systems" aria-labelledby="systems-title">
          <div className="home-section__header">
            <p className="home-eyebrow">Domains</p>
            <h2 id="systems-title">Designed for infrastructure behavior, not a single equipment category.</h2>
          </div>
          <div className="home-system-list" role="list" aria-label="Infrastructure system areas">
            {SYSTEM_AREAS.map((area) => <span key={area} role="listitem">{area}</span>)}
          </div>
        </section>

        <section id="about" className="home-section home-section--about" aria-labelledby="about-title">
          <div className="home-section__header">
            <p className="home-eyebrow">About</p>
            <h2 id="about-title">Systemic Infrastructure Intelligence that operators can review.</h2>
            <p>
              Neraium presents SII analyses as prioritized insights with supporting evidence, while keeping every connector and recommendation read-only.
            </p>
          </div>
          <button type="button" className="home-command" onClick={onLaunchWorkspace}>Open Command Center</button>
        </section>
      </main>
    </div>
  );
}
