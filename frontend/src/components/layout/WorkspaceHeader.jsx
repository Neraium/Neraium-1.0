export default function WorkspaceHeader({
  kicker,
  title,
  subtitle,
  description,
  statusLabel,
  statusTone = "info",
}) {
  return (
    <header className="workspace-header">
      {kicker ? <p className="workspace-header__kicker">{kicker}</p> : null}
      <h2 className="workspace-header__title">{title}</h2>
      {subtitle ? <p className="workspace-header__subtitle">{subtitle}</p> : null}
      {description ? <p className="workspace-header__description">{description}</p> : null}
      {statusLabel ? (
        <div className={`workspace-header__status workspace-header__status--${statusTone}`}>
          <span className="metadata-text">Connection status</span>
          <strong>{statusLabel}</strong>
        </div>
      ) : null}
    </header>
  );
}
