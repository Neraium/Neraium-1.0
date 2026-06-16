/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
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

  afterEach(() => {
    cleanup();
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

  it("keeps API setup on the connection details step until the operator explicitly continues", async () => {
    render(h(OnboardingWorkspace, { apiFetch: vi.fn() }));

    fireEvent.click(screen.getByRole("button", { name: "General Telemetry" }));
    fireEvent.click(screen.getByRole("button", { name: "API" }));

    fireEvent.change(screen.getByPlaceholderText("API base URL"), { target: { value: "https://example.test/telemetry" } });
    fireEvent.change(screen.getByPlaceholderText("API key / token"), { target: { value: "secret-token" } });
    fireEvent.change(screen.getByPlaceholderText("Polling interval (seconds)"), { target: { value: "30" } });
    fireEvent.change(screen.getByPlaceholderText("Deployment label"), { target: { value: "site-a" } });
    fireEvent.change(screen.getByPlaceholderText("Telemetry stream label"), { target: { value: "system-a" } });

    await new Promise((resolve) => window.setTimeout(resolve, 250));
    expect(screen.getByRole("heading", { name: "Connection Details", level: 2 })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Variable Mapping", level: 2 })).toBeTruthy();
  });

  it("runs API connection verification through the backend connector endpoint", async () => {
    const apiFetch = vi.fn(async (path, options = {}) => {
      if (path === "/api/connectors/rest/test") {
        expect(options.method).toBe("POST");
        expect(JSON.parse(String(options.body))).toEqual({
          endpoint: "https://example.test/telemetry",
          token: "secret-token",
          source_id: "site-a",
          system_id: "system-a",
        });
        return {
          ok: true,
          json: async () => ({
            connection_status: "ready",
            message: "REST API validated with 12 records.",
            sensors_detected: 4,
            records_ingested: 12,
            warnings: [],
          }),
        };
      }
      throw new Error(`Unexpected API path: ${path}`);
    });

    render(h(OnboardingWorkspace, { apiFetch }));

    fireEvent.click(screen.getByRole("button", { name: "General Telemetry" }));
    fireEvent.click(screen.getByRole("button", { name: "API" }));

    fireEvent.change(screen.getByPlaceholderText("API base URL"), { target: { value: "https://example.test/telemetry" } });
    fireEvent.change(screen.getByPlaceholderText("API key / token"), { target: { value: "secret-token" } });
    fireEvent.change(screen.getByPlaceholderText("Polling interval (seconds)"), { target: { value: "30" } });
    fireEvent.change(screen.getByPlaceholderText("Deployment label"), { target: { value: "site-a" } });
    fireEvent.change(screen.getByPlaceholderText("Telemetry stream label"), { target: { value: "system-a" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    const mappingInputs = screen.getAllByPlaceholderText("source field");
    fireEvent.change(mappingInputs[0], { target: { value: "timestamp" } });
    fireEvent.change(mappingInputs[1], { target: { value: "temperature" } });
    fireEvent.change(mappingInputs[2], { target: { value: "humidity" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    fireEvent.click(screen.getByRole("button", { name: "Run Connection Test" }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith("/api/connectors/rest/test", expect.objectContaining({
        method: "POST",
        accessCode: "",
      }));
    });

    expect(await screen.findByRole("heading", { name: "Reference Setup", level: 2 })).toBeTruthy();
  });
});
