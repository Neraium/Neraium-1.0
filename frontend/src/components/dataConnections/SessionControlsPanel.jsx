import { Panel } from "../workspacePrimitives";

export default function SessionControlsPanel({
  onResetEverything,
  onResumePreviousSession,
  onOpenUpload,
  disableActions = false,
}) {
  return (
    <Panel title="Session Controls" className="span-12">
      <p className="narrative-text">
        Link a live source or resume the latest validated session.
      </p>
      <div className="intake-flow__controls">
        <button type="button" className="secondary-command-button" onClick={onResetEverything} disabled={disableActions}>
          Reset Everything
        </button>
        <button type="button" className="secondary-command-button" onClick={onResumePreviousSession} disabled={disableActions}>
          Resume Previous Session
        </button>
        <button type="button" className="command-button" onClick={onOpenUpload} disabled={disableActions}>
          Open Upload
        </button>
      </div>
    </Panel>
  );
}
