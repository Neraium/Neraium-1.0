export default function WorkspaceContentRegion({ activeWorkspace, workspaceRef, children }) {
  return (
    <section
      key={activeWorkspace}
      ref={workspaceRef}
      className={`platform-workspace workspace-view workspace-view--${activeWorkspace}`}
      aria-labelledby="page-title"
    >
      {children}
    </section>
  );
}
