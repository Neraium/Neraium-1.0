export default function SkipToMainContent({ targetId = "main-content" }) {
  const handleActivate = (event) => {
    event.preventDefault();
    const target = document.getElementById(targetId);
    if (!target) return;
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start" });
  };

  return (
    <a className="skip-link" href={`#${targetId}`} onClick={handleActivate}>
      Skip to main content
    </a>
  );
}
