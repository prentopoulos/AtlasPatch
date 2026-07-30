import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

describe("App (Slice A skeleton)", () => {
  it("renders the bundled demo and populates the run-history panel", () => {
    render(<App />);
    // The header identifies the read-only surface.
    expect(
      screen.getByRole("heading", { name: /AtlasPatch Conductor — Observability/i }),
    ).toBeInTheDocument();
    // The history panel populates from the demo runs.
    expect(screen.getByText("Run history")).toBeInTheDocument();
    expect(screen.getByText("job-cohort-a")).toBeInTheDocument();
    // job-cohort-b appears in the history row and in the "Showing run" summary (default = last).
    expect(screen.getAllByText("job-cohort-b").length).toBeGreaterThanOrEqual(1);
    // A run is selected by default (the most recent).
    expect(screen.getByText(/Showing run/i)).toBeInTheDocument();
  });
});
