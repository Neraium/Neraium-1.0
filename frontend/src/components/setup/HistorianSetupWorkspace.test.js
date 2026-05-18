/* @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HistorianSetupWorkspace from "./HistorianSetupWorkspace";
import { TAG_MAP_ROWS } from "./setupConstants";

describe("HistorianSetupWorkspace", () => {
  it("advances through setup stages and keeps connection test before baseline", () => {
    render(<HistorianSetupWorkspace tagMapRows={TAG_MAP_ROWS} />);

    expect(screen.getByText("Step 1 of 6: Historian / BMS / SCADA")).toBeTruthy();

    const nextButton = screen.getByRole("button", { name: "Next" });
    fireEvent.click(nextButton);
    expect(screen.getByText("Step 2 of 6: Read-only Ingestion")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 3 of 6: Connection Method")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 4 of 6: Signal Mapping")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 5 of 6: Connection Test")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 6 of 6: Baseline Builder")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByText("Step 5 of 6: Connection Test")).toBeTruthy();
  });
});
