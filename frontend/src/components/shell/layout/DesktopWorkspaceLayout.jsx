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
  const isGateWorkspace = activeWorkspace === "system-body";

  return (
    <main className={`platform-shell ${isGateWorkspace ? "platform-shell--gate" : ""}`}>
      {!isGateWorkspace ? (
        <aside className="platform-sidebar" aria-label="Workspace navigation">
          {navigation}
        </aside>
      ) : null}
      <div className="platform-main">
        <MobileWorkspaceLayout header={isGateWorkspace ? null : mobileHeader} drawer={isGateWorkspace ? null : drawer}>
          {!isGateWorkspace ? topStatus : null}
          <WorkspaceContentRegion activeWorkspace={activeWorkspace} workspaceRef={workspaceRef}>
            {children}
          </WorkspaceContentRegion>
        </MobileWorkspaceLayout>
      </div>
    </main>
  );
}
