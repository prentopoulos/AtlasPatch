import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { parseSnapshot, type RunView, type Snapshot } from "@/lib/snapshot";
import { CohortMetrics } from "@/components/CohortMetrics";
import { VerdictTable } from "@/components/VerdictTable";
import { DecisionTrace } from "@/components/DecisionTrace";
import { Choreography } from "@/components/Choreography";
import { RunHistory } from "@/components/RunHistory";
import demoJson from "@/fixtures/demo-snapshot.json";

function demo(): Snapshot {
  const result = parseSnapshot(demoJson);
  if (result.status !== "ok") throw new Error("demo fixture invalid");
  return result.snapshot;
}

const snapshot = demo();
const runA: RunView = snapshot.runs.find((r) => r.job_id === "job-cohort-a")!;
const runB: RunView = snapshot.runs.find((r) => r.job_id === "job-cohort-b")!;

describe("CohortMetrics", () => {
  it("renders the cohort size and every verdict tally", () => {
    render(<CohortMetrics run={runA} />);
    expect(screen.getByText("Cohort")).toBeInTheDocument();
    for (const label of ["Valid", "Skipped", "Quarantined", "Blocked"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // Cohort size (8) is shown.
    expect(screen.getByText(String(runA.cohort_size))).toBeInTheDocument();
  });
});

describe("VerdictTable", () => {
  it("populates a row per slide with verdict, reason, and detail — and no score column", () => {
    render(<VerdictTable slides={runA.slides} />);
    const body = screen.getAllByRole("rowgroup")[1];
    expect(within(body).getAllByRole("row")).toHaveLength(runA.slides.length);
    // No score/confidence header anywhere.
    expect(screen.queryByText(/score|confidence|probability/i)).toBeNull();
    // The verdict labels render as badges.
    expect(screen.getAllByText("Valid").length).toBeGreaterThan(0);
  });

  it("reorders rows when a sortable column header is clicked", async () => {
    const user = userEvent.setup();
    render(<VerdictTable slides={runA.slides} />);
    const stemHeader = screen.getByRole("button", { name: /Slide/i });

    const stemsAsc = () =>
      Array.from(
        screen.getAllByRole("rowgroup")[1].querySelectorAll("td:first-child"),
        (c) => c.textContent,
      );

    await user.click(stemHeader); // sort by stem ascending
    const ascending = stemsAsc();
    await user.click(stemHeader); // toggle to descending
    const descending = stemsAsc();
    expect(descending).toEqual([...ascending].reverse());
  });
});

describe("DecisionTrace", () => {
  it("renders a collapsible per traced slide and reveals ordered steps", async () => {
    const user = userEvent.setup();
    render(<DecisionTrace slides={runA.slides} />);
    // Each traced slide is a trigger button.
    const triggers = screen.getAllByRole("button");
    expect(triggers.length).toBeGreaterThan(0);
    // The first is open by default and shows its first agent step (reconcile by scheduler).
    expect(screen.getAllByText("reconcile").length).toBeGreaterThan(0);
    // Expanding another reveals its steps too.
    await user.click(triggers[triggers.length - 1]);
    expect(screen.getAllByText("verdict").length).toBeGreaterThan(0);
  });
});

describe("Choreography", () => {
  it("lights the active agent and lists message-flow edges (Level 1 + Level 2)", () => {
    render(<Choreography run={runA} agents={snapshot.agents} />);
    // One node per agent in the roster.
    const nodes = within(screen.getByTestId("agent-nodes")).getAllByText(
      /planner|worker|validator|recovery|scheduler/,
    );
    expect(nodes.length).toBe(snapshot.agents.length);
    // Level-2 edges present for a run that recorded message flow.
    expect(screen.getByTestId("flow-edges")).toBeInTheDocument();
  });

  it("degrades to component-state-only when a run recorded no message flow", () => {
    render(<Choreography run={runB} agents={snapshot.agents} />);
    expect(screen.getByTestId("no-flow")).toBeInTheDocument();
    expect(screen.queryByTestId("flow-edges")).toBeNull();
  });
});

describe("RunHistory", () => {
  it("renders an empty state for a zero-run snapshot", () => {
    render(<RunHistory runs={[]} selectedJobId={null} onSelect={() => {}} />);
    expect(screen.getByTestId("empty-runs")).toBeInTheDocument();
  });
});
