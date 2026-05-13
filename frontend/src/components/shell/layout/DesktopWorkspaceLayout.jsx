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
    <main className="neraium-sidebar-emergency-fix platform-shell">
      <aside className="platform-sidebar" aria-label="Workspace navigation">
        {navigation}
      </aside>
      <div className="platform-main">
        <MobileWorkspaceLayout header={mobileHeader} drawer={drawer}>
          {topStatus}
          <WorkspaceContentRegion activeWorkspace={activeWorkspace} workspaceRef={workspaceRef}>
            {children}
          </WorkspaceContentRegion>
        </MobileWorkspaceLayout>
      </div>
    </main>
  );
}
