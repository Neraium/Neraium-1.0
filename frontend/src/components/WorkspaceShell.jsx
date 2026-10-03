import { useEffect, useRef, useState } from "react";
import SkipToMainContent from "./SkipToMainContent";
import "../styles/engineering-reasoning.css";

export function primaryNavigationItems({ currentUser, showSites = false } = {}) {
  return [
    ["work", "Work"], ["site", "System Status"], ["systems", "Systems"],
    ["findings", "Analysis Findings"], ["investigations", "Evidence & Outcomes"],
    ["data-connections", "Data"],
    ...(showSites ? [["portfolio", "Sites"]] : []),
    ["observation-center", "Historical review"], ["system-story", "Historical replay"],
    ["help-changelog", "Help & Status"],
    ...(currentUser?.role === "admin" ? [["governance-admin", "Administration"]] : []),
  ];
}

export default function WorkspaceShell({ activeNavigation, onNavigate, currentUser, workspaceSession, currentWorkspace, onWorkspaceChange, onSignOut, signOutPending = false, showSites = false, topbarContent, mainRef, mainId = "forensic-main", mainLabel = "Neraium operational workspace", route, testId, children }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(max-width: 1024px)")?.matches);
  const mobileMenuButtonRef = useRef(null);
  const mobileSidebarRef = useRef(null);
  const navItems = primaryNavigationItems({ currentUser, showSites });
  const availableWorkspaces = (workspaceSession?.workspaces ?? currentUser?.workspaces ?? []).filter((workspace) => workspace?.is_active !== false);
  const currentWorkspaceId = String(currentWorkspace?.workspace_id ?? currentWorkspace?.workspaceId ?? workspaceSession?.default_workspace_id ?? "default");
  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 1024px)");
    if (!media) return undefined;
    const syncNavigationMode = () => {
      setCompactNavigation(media.matches);
      if (!media.matches) setMobileNavOpen(false);
    };
    syncNavigationMode();
    media.addEventListener?.("change", syncNavigationMode);
    return () => media.removeEventListener?.("change", syncNavigationMode);
  }, []);

  useEffect(() => {
    if (!mobileNavOpen) return undefined;
    const sidebar = mobileSidebarRef.current;
    const previousOverflow = document.body.style.overflow;
    const focusable = Array.from(sidebar?.querySelectorAll("button:not([disabled]), select:not([disabled])") ?? []);
    const activeNavigationItem = sidebar?.querySelector('nav[aria-label="Primary navigation"] [aria-current="page"]');
    (activeNavigationItem ?? focusable[0])?.focus();
    if (window.matchMedia?.("(max-width: 1024px)")?.matches) document.body.style.overflow = "hidden";

    function handleMenuKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileNavOpen(false);
        mobileMenuButtonRef.current?.focus();
        return;
      }
      if (event.key !== "Tab" || !focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleMenuKeyDown);
    return () => {
      document.removeEventListener("keydown", handleMenuKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileNavOpen]);

  return (
    <div className="forensic-shell" data-testid={testId}>
      <SkipToMainContent targetId={mainId} />
      <aside id="forensic-navigation" ref={mobileSidebarRef} className={`forensic-sidebar${mobileNavOpen ? " is-open" : ""}`} aria-label="Application sidebar" aria-hidden={compactNavigation && !mobileNavOpen} inert={compactNavigation && !mobileNavOpen ? "" : undefined}>
        <div className="forensic-brand"><span className="forensic-brand__mark" aria-hidden="true">N</span><div><strong>Neraium</strong><small>Operational evidence</small></div></div>
        <nav aria-label="Primary navigation">
          {navItems.map(([id, label]) => <button key={id} type="button" className={activeNavigation === id ? "is-active" : ""} aria-current={activeNavigation === id ? "page" : undefined} onClick={() => { setMobileNavOpen(false); onNavigate(id); }}><span aria-hidden="true" className={`nav-glyph nav-glyph--${id}`} />{label}</button>)}
        </nav>
        <div className="forensic-sidebar__account">
          <span>{currentUser?.name || currentUser?.email || "Signed in"}</span><small>{currentUser?.role || "engineer"}</small>
          {availableWorkspaces.length > 1 ? <label className="forensic-workspace-selector forensic-workspace-selector--sidebar"><span>Facility workspace</span><select value={currentWorkspaceId} onChange={(event) => onWorkspaceChange?.(event.target.value)}>{availableWorkspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.display_name}</option>)}</select></label> : null}
          {onSignOut ? <button type="button" onClick={onSignOut} disabled={signOutPending}>{signOutPending ? "Signing out..." : "Sign out"}</button> : null}
        </div>
      </aside>
      {mobileNavOpen ? <button type="button" className="forensic-sidebar-scrim" aria-label="Close navigation" onClick={() => { setMobileNavOpen(false); mobileMenuButtonRef.current?.focus(); }} /> : null}
      <div className="forensic-app">
        <header className="forensic-topbar" aria-label="Workspace controls">
          <button
            ref={mobileMenuButtonRef}
            type="button"
            className="forensic-mobile-menu"
            aria-expanded={mobileNavOpen}
            aria-controls="forensic-navigation"
            aria-label={mobileNavOpen ? "Close menu" : "Open menu"}
            onClick={() => setMobileNavOpen((value) => !value)}
          ><span className="forensic-mobile-menu__label">Menu</span><svg className="forensic-mobile-menu__icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button>
          {topbarContent}
        </header>
        <main ref={mainRef} id={mainId} aria-label={mainLabel} tabIndex={-1} data-route={route ?? activeNavigation}>
          {children}
        </main>
      </div>
    </div>
  );
}
