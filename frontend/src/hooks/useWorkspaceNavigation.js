import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DEFAULT_WORKSPACE_ID,
  EXPERT_WORKSPACE_IDS,
  PRIMARY_WORKSPACE_ORDER,
  WORKSPACES,
} from "../config/workspaces";

export default function useWorkspaceNavigation({
  onWorkspaceSelect,
}) {
  const [activeWorkspace, setActiveWorkspace] = useState(() => {
    if (typeof window === "undefined") {
      return DEFAULT_WORKSPACE_ID;
    }
    const params = new URLSearchParams(window.location.search);
    const requestedWorkspace = params.get("workspace");
    return WORKSPACES.some((workspace) => workspace.id === requestedWorkspace)
      ? requestedWorkspace
      : DEFAULT_WORKSPACE_ID;
  });
  const [expertMode, setExpertMode] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem("neraium:expert-mode") === "true";
  });
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const workspaceRef = useRef(null);
  const workspaceDrawerRef = useRef(null);

  const visibleWorkspaces = useMemo(() => {
    const base = WORKSPACES.filter((workspace) => expertMode || !EXPERT_WORKSPACE_IDS.has(workspace.id));
    return base.sort((a, b) => {
      const ai = PRIMARY_WORKSPACE_ORDER.indexOf(a.id);
      const bi = PRIMARY_WORKSPACE_ORDER.indexOf(b.id);
      if (ai >= 0 && bi >= 0) return ai - bi;
      if (ai >= 0) return -1;
      if (bi >= 0) return 1;
      return a.label.localeCompare(b.label);
    });
  }, [expertMode]);

  const activeConfig = useMemo(
    () => visibleWorkspaces.find((workspace) => workspace.id === activeWorkspace) ?? visibleWorkspaces[0] ?? WORKSPACES[0],
    [activeWorkspace, visibleWorkspaces],
  );

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("neraium:expert-mode", String(expertMode));
    }
  }, [expertMode]);

  useEffect(() => {
    const activeIsHidden = !visibleWorkspaces.some((workspace) => workspace.id === activeWorkspace);
    if (activeIsHidden) {
      setActiveWorkspace(DEFAULT_WORKSPACE_ID);
    }
  }, [activeWorkspace, visibleWorkspaces]);

  useEffect(() => {
    if (workspaceRef.current) {
      workspaceRef.current.scrollTo({ top: 0, behavior: "auto" });
    }
  }, [activeWorkspace]);

  useEffect(() => {
    if (!isWorkspaceMenuOpen) {
      return undefined;
    }
    if (workspaceDrawerRef.current) {
      workspaceDrawerRef.current.scrollTop = 0;
    }

    const previousBodyOverflow = document.body.style.overflow;
    const previousBodyOverscroll = document.body.style.overscrollBehavior;
    const previousHtmlOverflow = document.documentElement.style.overflow;
    document.body.classList.add("workspace-menu-is-open");
    document.documentElement.classList.add("workspace-menu-is-open");
    document.body.style.overflow = "hidden";
    document.body.style.overscrollBehavior = "none";
    document.documentElement.style.overflow = "hidden";

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setIsWorkspaceMenuOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.classList.remove("workspace-menu-is-open");
      document.documentElement.classList.remove("workspace-menu-is-open");
      document.body.style.overflow = previousBodyOverflow;
      document.body.style.overscrollBehavior = previousBodyOverscroll;
      document.documentElement.style.overflow = previousHtmlOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isWorkspaceMenuOpen]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    function handleResize() {
      if (window.innerWidth > 1100) {
        setIsWorkspaceMenuOpen(false);
      }
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleWorkspaceSelect = useCallback((workspaceId) => {
    setActiveWorkspace(workspaceId);
    if (onWorkspaceSelect) {
      onWorkspaceSelect(workspaceId);
    }
    setIsWorkspaceMenuOpen(false);
  }, [onWorkspaceSelect]);

  return {
    activeWorkspace,
    setActiveWorkspace,
    activeConfig,
    expertMode,
    setExpertMode,
    visibleWorkspaces,
    isWorkspaceMenuOpen,
    setIsWorkspaceMenuOpen,
    workspaceRef,
    workspaceDrawerRef,
    handleWorkspaceSelect,
  };
}
