import React from 'react';

export default function ShellLayout({ sidebar, mobileHeader, topStatus, workspace, drawer }) {
  return (
    <main className='platform-shell'>
      <aside className='platform-sidebar' aria-label='Workspace navigation'>{sidebar}</aside>
      <div className='platform-main'>
        {mobileHeader}
        {topStatus}
        {workspace}
      </div>
      {drawer}
    </main>
  );
}
