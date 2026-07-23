import { useEffect, useRef, useState } from "react";

import OperatorInsightDetail from "./OperatorInsightDetail";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function prefersReducedMotion() {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}

function focusableElements(panel) {
  return Array.from(panel?.querySelectorAll(FOCUSABLE_SELECTOR) ?? [])
    .filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");
}

export default function InvestigationDrawer({
  route,
  insight,
  title,
  onClose,
  onExpand,
}) {
  const [presented, setPresented] = useState(null);
  const [phase, setPhase] = useState("closed");
  const panelRef = useRef(null);
  const closeButtonRef = useRef(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (route) setPresented({ route, insight, title });
  }, [insight, route, title]);

  useEffect(() => {
    let frame;
    let timer;

    if (route) {
      setPhase("opening");
      frame = window.requestAnimationFrame?.(() => setPhase("open"));
    } else {
      setPhase((current) => current === "closed" ? current : "closing");
      const duration = prefersReducedMotion() ? 0 : 180;
      timer = window.setTimeout(() => {
        setPresented(null);
        setPhase("closed");
      }, duration);
    }

    return () => {
      if (frame && window.cancelAnimationFrame) window.cancelAnimationFrame(frame);
      if (timer) window.clearTimeout(timer);
    };
  }, [route]);

  useEffect(() => {
    if (!route) return undefined;

    const previousBodyOverflow = document.body.style.overflow;
    const previousRootOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";

    const focusFrame = window.requestAnimationFrame?.(() => {
      const focusTarget = route.focusTarget
        ? panelRef.current?.querySelector(`#${route.focusTarget}`)
        : null;
      (focusTarget ?? closeButtonRef.current)?.focus({ preventScroll: true });
    });

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current?.();
        return;
      }

      if (event.key !== "Tab") return;
      const elements = focusableElements(panelRef.current);
      if (!elements.length) {
        event.preventDefault();
        panelRef.current?.focus({ preventScroll: true });
        return;
      }

      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      if (focusFrame && window.cancelAnimationFrame) window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousRootOverflow;
    };
  }, [route]);

  if (!route && !presented) return null;

  const visibleRoute = route ?? presented.route;
  const visibleInsight = insight ?? presented.insight;
  const visibleTitle = title ?? presented.title ?? "Investigation";
  const isFullWorkspace = visibleRoute.mode === "full";
  const isInteractive = Boolean(route) && phase !== "closing";

  return (
    <div
      className={`investigation-surface investigation-surface--${isFullWorkspace ? "full" : "drawer"} is-${phase}`}
      data-testid="investigation-surface"
      data-investigation-mode={isFullWorkspace ? "full" : "drawer"}
      aria-hidden={!isInteractive}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && isInteractive) onClose?.();
      }}
    >
      <section
        ref={panelRef}
        className="investigation-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="investigation-panel-title"
        aria-describedby="investigation-panel-subsystem"
        tabIndex={-1}
      >
        <header className="investigation-panel__header">
          <div className="investigation-panel__identity">
            <span className="section-token">{isFullWorkspace ? "Full evidence page" : "Evidence"}</span>
            <h2 id="investigation-panel-title">{visibleTitle}</h2>
            <p id="investigation-panel-subsystem" className="investigation-panel__finding-state">
              <span>Change detected</span>
              <span aria-hidden="true">·</span>
              <strong>{(visibleInsight?.changedRelationshipCount || visibleInsight?.affectedRelationships?.length || visibleInsight?.observedFacts?.length) ? "Narrowed" : "Broad"}</strong>
            </p>
          </div>
          <div className="investigation-panel__actions">
            {!isFullWorkspace ? (
              <button
                type="button"
                className="secondary-command-button investigation-panel__expand"
                onClick={onExpand}
                aria-label="Expand investigation to full workspace"
              >
                Expand to Full Workspace
              </button>
            ) : null}
            <button
              ref={closeButtonRef}
              type="button"
              className="secondary-command-button investigation-panel__close"
              onClick={onClose}
              aria-label={isFullWorkspace ? "Close full investigation workspace" : "Close investigation drawer"}
            >
              Close
            </button>
          </div>
        </header>
        <div className="investigation-panel__body">
          {visibleInsight ? (
            <OperatorInsightDetail insight={visibleInsight} inline focusMode />
          ) : (
            <div className="operational-empty" role="status">
              <strong>Finding unavailable</strong>
              <p>This investigation is not present in the current Command Center data.</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
