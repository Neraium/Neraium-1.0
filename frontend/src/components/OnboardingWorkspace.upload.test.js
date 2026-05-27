/* @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import OnboardingWorkspace from "./OnboardingWorkspace";
import { uploadTelemetryFileWithProgress } from "../services/api/uploadApi";

vi.mock("../services/api/uploadApi", () => ({
  uploadTelemetryFileWithProgress: vi.fn(),
}));

describe("OnboardingWorkspace CSV propagation", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("uploads through backend pipeline, polls job status, and propagates completion", async () => {
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: { job_id: "job-123", message: "Upload accepted. Processing is queued." },
    });

    const apiFetch = vi.fn(async (path) => {
      if (path.includes("/api/data/upload-status/job-123")) {
        return {
          ok: true,
          json: async () => ({ status: "COMPLETE", message: "Telemetry processing complete." }),
        };
      }
      if (path.includes("/api/data/latest-upload")) {
        return {
          ok: true,
          json: async () => ({
            status: "COMPLETE",
            latest_result: { job_id: "job-123", filename: "telemetry.csv", row_count: 2, column_count: 3 },
          }),
        };
      }
      throw new Error(`Unexpected API path: ${path}`);
    });

    const onUploadComplete = vi.fn(async () => {});

    render(<OnboardingWorkspace apiFetch={apiFetch} onUploadComplete={onUploadComplete} />);

    fireEvent.click(screen.getByRole("button", { name: "Cannabis Grow" }));
    fireEvent.click(screen.getByRole("button", { name: "CSV Upload" }));

    const fileInput = document.querySelector("input[type='file']");
    const file = new File(["timestamp,temperature,humidity\n2026-05-01T08:00:00Z,75.2,58\n"], "telemetry.csv", { type: "text/csv" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(uploadTelemetryFileWithProgress).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith("/api/data/upload-status/job-123", expect.objectContaining({ accessCode: "" }));
    });

    await waitFor(() => {
      expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-123" }));
    });

    expect(await screen.findByText(/\| complete/i)).toBeTruthy();
  });
});
