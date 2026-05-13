import React from 'react';
import SidebarNavigation from './SidebarNavigation';

export default function WorkspaceDrawer({
  isWorkspaceMenuOpen,
  setIsWorkspaceMenuOpen,
  workspaceDrawerRef,
  activeConfig,
  workspaces,
  activeWorkspace,
  roomContext,
  timeCoverage,
  liveOps,
  onSelectWorkspace,
  StatusDot,
  SidebarTelemetry,
}) {
  return (
    <>
      <div className={workspace-drawer-backdrop } hidden={!isWorkspaceMenuOpen} onClick={() => setIsWorkspaceMenuOpen(false)} />
      <aside ref={workspaceDrawerRef} className={workspace-drawer } id='mobile-workspace-drawer' aria-label='Workspace drawer' aria-hidden={!isWorkspaceMenuOpen}>
        <div className='workspace-drawer__header'>
          <div><p className='sidebar-kicker'>Navigation</p><strong>{activeConfig.label}</strong></div>
          <button className='workspace-drawer__close' type='button' aria-label='Close workspace menu' onClick={() => setIsWorkspaceMenuOpen(false)}>Close</button>
        </div>
        <SidebarNavigation
          workspaces={workspaces}
          activeWorkspace={activeWorkspace}
          roomContext={roomContext}
          timeCoverage={timeCoverage}
          liveOps={liveOps}
          onSelectWorkspace={onSelectWorkspace}
          StatusDot={StatusDot}
          SidebarTelemetry={SidebarTelemetry}
        />
      </aside>
    </>
  );
}
