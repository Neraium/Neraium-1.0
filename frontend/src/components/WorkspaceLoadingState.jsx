export default function WorkspaceLoadingState({ label = "Opening workspace", detail = "Loading operational context.", fullScreen = false }) {
  return (
    <main
      className={`workspace-grid workspace-loading-shell${fullScreen ? " workspace-loading-shell--fullscreen" : ""}`}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <section className="ops-panel span-12 workspace-loading-panel">
        <div className="ops-panel__header"><h2>{label}</h2></div>
        <div className="ops-panel__body">
          <span className="sr-only">{detail}</span>
          <div className="cultivation-loading-panel__skeleton" aria-hidden="true">
            <div className="cultivation-loading-panel__hero" />
            <div className="cultivation-loading-panel__grid">
              <div className="cultivation-loading-panel__card" />
              <div className="cultivation-loading-panel__card" />
              <div className="cultivation-loading-panel__card" />
            </div>
          </div>
          <div className="workspace-loading-panel__meter" aria-hidden="true"><span /></div>
        </div>
      </section>
    </main>
  );
}
