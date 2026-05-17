export default function SessionResetPanel({ onResetDemoClick, onResumePreviousSession, disabled }) {
  return (
    <>
      <button type="button" className="secondary-command-button" onClick={onResetDemoClick} disabled={disabled}>
        Reset Demo State
      </button>
      <button type="button" className="secondary-command-button" onClick={onResumePreviousSession} disabled={disabled}>
        Resume Previous Session
      </button>
    </>
  );
}
