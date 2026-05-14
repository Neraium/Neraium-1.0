import WorkspaceContentRegion from "./WorkspaceContentRegion";
import MobileWorkspaceLayout from "./MobileWorkspaceLayout";

export default function DesktopWorkspaceLayout({
  activeWorkspace,
  workspaceRef,
  navigation,
  mobileHeader,
  topStatus,
  children,
  drawer,
}) {
  return (
    <main className="platform-shell">
      <aside className="platform-sidebar" aria-label="Workspace navigation">
        {navigation}
      </aside>
      <div className="platform-main">
        <MobileWorkspaceLayout header={mobileHeader} drawer={drawer}>
          {activeWorkspace === "system-body" ? topStatus : null}
          <WorkspaceContentRegion activeWorkspace={activeWorkspace} workspaceRef={workspaceRef}>
            {children}
          </WorkspaceContentRegion>
        </MobileWorkspaceLayout>
      </div>
    </main>
  );
}
