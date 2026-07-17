export default function SkipToMainContent({ targetId = "main-content" }) {
  const handleActivate = () => {
    const target = document.getElementById(targetId);
    if (!target) return;
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start" });
  };

  return (
    <button type="button" className="skip-link" onClick={handleActivate}>
      Skip to main content
    </button>
  );
}
