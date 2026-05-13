export default function WorkspaceHeader({ kicker, title, description }) {
  return (
    <header className="workspace-header">
      {kicker ? <p className="workspace-header__kicker">{kicker}</p> : null}
      <h2 className="workspace-header__title">{title}</h2>
      {description ? <p className="workspace-header__description">{description}</p> : null}
    </header>
  );
}
