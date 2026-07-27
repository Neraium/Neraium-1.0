export default function WorkspaceLoadingState({
  label = "Opening workspace",
  detail = "Loading operational context.",
  fullScreen = false,
  variant = "loading",
  actionLabel = "",
  onAction = null,
}) {
  const isError = variant === "error";
  return (
    <main
      className={`workspace-grid workspace-loading-shell${fullScreen ? " workspace-loading-shell--fullscreen" : ""}${isError ? " workspace-loading-shell--error" : ""}`}
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
      aria-label={label}
      data-testid={isError ? "startup-error" : "workspace-loading-state"}
    >
      <section className="ops-panel span-12 workspace-loading-panel">
        <div className="ops-panel__header"><h2>{label}</h2></div>
        <div className="ops-panel__body">
          {isError ? (
            <div className="workspace-loading-panel__failure">
              <p>{detail}</p>
              {typeof onAction === "function" && actionLabel ? (
                <button type="button" className="command-button" onClick={onAction}>{actionLabel}</button>
              ) : null}
            </div>
          ) : (
            <>
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
            </>
          )}
        </div>
      </section>
    </main>
  );
}
