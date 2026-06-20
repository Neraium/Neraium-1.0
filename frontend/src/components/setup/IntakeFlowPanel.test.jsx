/* @vitest-environment jsdom */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import IntakeFlowPanel from "./IntakeFlowPanel";

function renderPanel(overrides = {}) {
  const uploadInputRef = { current: null };
  return render(
    <IntakeFlowPanel
      handleUpload={vi.fn()}
      uploadInputRef={uploadInputRef}
      handleFileSelection={vi.fn()}
      selectedFiles={[]}
      latestUploadSnapshot={{ status: "empty", last_filename: "stale-upload.csv" }}
      pendingUploadKind="csv"
      selectedFileSize="Awaiting file"
      isUploadProcessing={(state) => ["uploading", "running_sii", "queued", "processing"].includes(state)}
      uploadState="idle"
      openFilePicker={vi.fn()}
      uploadJob={null}
      latestMessage="Awaiting file selection"
      visibleProgressPercent={null}
      propagationLabel=""
      queuedWorkerDetail=""
      uploadTransfer={null}
      uploadStateMessage={() => "Awaiting file selection"}
      batchResults={[]}
      onRetryFailedUploads={vi.fn()}
      onReprocessCurrentBatch={vi.fn()}
      onClearSelection={vi.fn()}
      onLoadLatestWorkspace={vi.fn()}
      onResetWorkspace={vi.fn()}
      workspaceStatusMessage=""
      {...overrides}
    />,
  );
}

describe("IntakeFlowPanel upload state", () => {
  it("does not show stale filenames while awaiting first file selection", () => {
    renderPanel();

    expect(screen.getAllByText("Awaiting file selection").length).toBeGreaterThan(0);
    expect(screen.queryByText("stale-upload.csv")).toBeNull();
    expect(screen.getByTestId("process-upload-button")).toBeDisabled();
  });

  it("shows only the selected filename before upload starts", () => {
    const file = new File(["timestamp,temp\n2026-06-20T00:00:00Z,72\n"], "selected.csv", { type: "text/csv" });
    renderPanel({ selectedFiles: [file], selectedFileSize: "1.0 KB", latestMessage: "Telemetry export validated", uploadState: "validated" });

    expect(screen.getByText("selected.csv")).toBeTruthy();
    expect(screen.queryByText("stale-upload.csv")).toBeNull();
    expect(screen.getByTestId("process-upload-button")).toBeEnabled();
  });
});
