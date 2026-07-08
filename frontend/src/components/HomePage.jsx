import { useCallback, useRef } from "react";

import SystemStateMark from "./SystemStateMark";
import "../styles/home.css";

const PLATFORM_CARDS = [
  {
    title: "Behavior Intelligence",
    body: "Learns normal operating relationships across systems.",
  },
  {
    title: "Operational Insights",
    body: "Identifies subsystem changes and explains why they matter.",
  },
  {
    title: "Decision Support",
    body: "Prioritizes operational investigation instead of overwhelming operators with alarms.",
  },
];

const WORKFLOW_STEPS = [
  {
    title: "Learn",
    body: "Builds a working model of normal behavior across connected infrastructure.",
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
  "Treatment",
  "Pumping",
  "Distribution",
  "Storage",
  "Process loops",
  "Telemetry integrity",
];

export default function HomePage({ onLaunchWorkspace }) {
  const orbRef = useRef(null);

  const scrollToSection = useCallback((sectionId) => {
    if (typeof document === "undefined") return;
    document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
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
        <button type="button" className="home-nav__launch" onClick={onLaunchWorkspace}>Launch Workspace</button>
      </header>

      <main>
        <section id="home-hero" className="home-hero" aria-labelledby="home-title">
          <div className="home-hero__copy">
            <p className="home-eyebrow">Operational Intelligence Platform</p>
            <h1 id="home-title">Operational Intelligence for Critical Infrastructure</h1>
            <p>
              Neraium continuously learns how operational systems normally behave and identifies meaningful behavioral changes before traditional alarms reveal the problem.
            </p>
          </div>

          <div
            ref={orbRef}
            className="home-orb"
            onPointerMove={handleOrbPointerMove}
            onPointerLeave={resetOrbPointer}
            aria-label="Animated Neraium operational intelligence orb"
          >
            <div className="home-orb__energy home-orb__energy--outer" aria-hidden="true" />
            <div className="home-orb__energy home-orb__energy--inner" aria-hidden="true" />
            <div className="home-orb__trace home-orb__trace--a" aria-hidden="true" />
            <div className="home-orb__trace home-orb__trace--b" aria-hidden="true" />
            <div className="home-orb__body">
              <SystemStateMark systemState="stable" intensity={0.18} animated />
            </div>
          </div>

          <div className="home-hero__actions" aria-label="Primary actions">
            <button type="button" className="home-command" onClick={onLaunchWorkspace}>Launch Workspace</button>
            <button type="button" className="home-secondary" onClick={() => scrollToSection("platform")}>View Platform</button>
          </div>
        </section>

        <section id="platform" className="home-section home-section--platform" aria-labelledby="platform-title">
          <div className="home-section__header">
            <p className="home-eyebrow">Platform</p>
            <h2 id="platform-title">Built for operational teams watching complex infrastructure.</h2>
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
            <p className="home-eyebrow">Systems</p>
            <h2 id="systems-title">Designed around system relationships, not isolated tags.</h2>
          </div>
          <div className="home-system-list" aria-label="Infrastructure system areas">
            {SYSTEM_AREAS.map((area) => <span key={area}>{area}</span>)}
          </div>
        </section>

        <section id="about" className="home-section home-section--about" aria-labelledby="about-title">
          <div className="home-section__header">
            <p className="home-eyebrow">About</p>
            <h2 id="about-title">Explainable intelligence for operational change detection.</h2>
            <p>
              Neraium gives operators a focused view of infrastructure behavior, relationship changes, and investigation priorities across monitored systems.
            </p>
          </div>
          <button type="button" className="home-command" onClick={onLaunchWorkspace}>Launch Workspace</button>
        </section>
      </main>
    </div>
  );
}
