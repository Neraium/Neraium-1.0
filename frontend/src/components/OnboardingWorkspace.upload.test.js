/* @vitest-environment jsdom */
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import OnboardingWorkspace from "./OnboardingWorkspace";
import { uploadTelemetryFileWithProgress } from "../services/api/uploadApi";

const h = React.createElement;
const storage = new Map();

function installStorageMock() {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key) => (storage.has(key) ? storage.get(key) : null),
      setItem: (key, value) => {
        storage.set(String(key), String(value));
      },
      removeItem: (key) => {
        storage.delete(String(key));
      },
      clear: () => {
        storage.clear();
      },
    },
  });
}

vi.mock("../services/api/uploadApi", () => ({
  uploadTelemetryFileWithProgress: vi.fn(),
}));

describe("OnboardingWorkspace CSV propagation", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    installStorageMock();
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

    render(h(OnboardingWorkspace, { apiFetch, onUploadComplete }));

    fireEvent.click(screen.getByRole("button", { name: "General Telemetry" }));
    fireEvent.click(screen.getByRole("button", { name: "CSV Upload" }));

    const fileInput = document.querySelector("input[type='file']");
    const file = new File(["timestamp,variable_a,variable_b\n2026-05-01T08:00:00Z,75.2,58\n"], "telemetry.csv", { type: "text/csv" });
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

    expect(await screen.findByRole("heading", { name: "Variable Mapping", level: 2 })).toBeTruthy();
  });
});
