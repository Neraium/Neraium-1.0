export default function WorkspaceContentRegion({ activeWorkspace, workspaceRef, children }) {
  const isGateWorkspace = activeWorkspace === "system-body";

  return (
    <section
      key={activeWorkspace}
      ref={workspaceRef}
      className={`platform-workspace workspace-view workspace-view--${activeWorkspace}`}
      aria-label={isGateWorkspace ? "The Gate operator interface" : undefined}
      aria-labelledby={isGateWorkspace ? undefined : "page-title"}
    >
      {children}
    </section>
  );
}
