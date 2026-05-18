/* @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HistorianSetupWorkspace from "./HistorianSetupWorkspace";
import { TAG_MAP_ROWS } from "./setupConstants";

describe("HistorianSetupWorkspace", () => {
  it("advances through setup stages 1 to 7 and supports back navigation", () => {
    render(<HistorianSetupWorkspace tagMapRows={TAG_MAP_ROWS} />);

    expect(screen.getByText("Step 1 of 7: 1. Historian / BMS / SCADA")).toBeTruthy();

    const nextButton = screen.getByRole("button", { name: "Next" });
    fireEvent.click(nextButton);
    expect(screen.getByText("Step 2 of 7: 2. Read-only Ingestion")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 3 of 7: 3. Neraium Intake Connector")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 4 of 7: 4. Signal Mapping")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 5 of 7: 5. Baseline Builder")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 6 of 7: 6. Live Structural Analysis")).toBeTruthy();

    fireEvent.click(nextButton);
    expect(screen.getByText("Step 7 of 7: 7. Operator UI / Reports")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByText("Step 6 of 7: 6. Live Structural Analysis")).toBeTruthy();
  });
});
