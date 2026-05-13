import { useState } from 'react';

export default function useWorkspaceNavigation(defaultWorkspace) {
  const [activeWorkspace, setActiveWorkspace] = useState(() => {
    if (typeof window === 'undefined') {
      return defaultWorkspace;
    }
    const params = new URLSearchParams(window.location.search);
    return params.get('workspace') ?? defaultWorkspace;
  });
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);

  return {
    activeWorkspace,
    setActiveWorkspace,
    isWorkspaceMenuOpen,
    setIsWorkspaceMenuOpen,
  };
}
