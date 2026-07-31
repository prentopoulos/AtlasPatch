import { useMemo, useState } from "react";
import { AlertTriangle, Activity } from "lucide-react";
import { SnapshotLoader } from "@/components/SnapshotLoader";
import { RunHistory } from "@/components/RunHistory";
import { CohortMetrics } from "@/components/CohortMetrics";
import { VerdictTable } from "@/components/VerdictTable";
import { DecisionTrace } from "@/components/DecisionTrace";
import { Choreography } from "@/components/Choreography";
import {
  SNAPSHOT_SCHEMA_VERSION,
  parseSnapshot,
  type LoadResult,
  type RunView,
  type Snapshot,
} from "@/lib/snapshot";
import demoSnapshotJson from "@/fixtures/demo-snapshot.json";

// The committed demo renders on first load with no operator input (spec: default demo). It is
// produced by the same assemble_snapshot path as a real export, so it is a valid payload.
const DEMO = (() => {
  const result = parseSnapshot(demoSnapshotJson);
  if (result.status !== "ok") {
    throw new Error(`Bundled demo snapshot is invalid: ${JSON.stringify(result)}`);
  }
  return result.snapshot;
})();

type View =
  | { kind: "snapshot"; snapshot: Snapshot; source: string }
  | { kind: "version-mismatch"; found: unknown };

export default function App() {
  const [view, setView] = useState<View>({
    kind: "snapshot",
    snapshot: DEMO,
    source: "bundled demo",
  });
  const [error, setError] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const runs: RunView[] = view.kind === "snapshot" ? view.snapshot.runs : [];

  // Resolve the selected run defensively: the explicit selection if it still exists, else the
  // most recent run (append order → last).
  const selectedRun = useMemo<RunView | null>(() => {
    if (runs.length === 0) return null;
    return runs.find((r) => r.job_id === selectedJobId) ?? runs[runs.length - 1];
  }, [runs, selectedJobId]);

  function handleLoad(result: LoadResult) {
    if (result.status === "ok") {
      setView({ kind: "snapshot", snapshot: result.snapshot, source: "loaded snapshot" });
      setSelectedJobId(null);
      setError(null);
    } else if (result.status === "version-mismatch") {
      setView({ kind: "version-mismatch", found: result.found });
      setError(null);
    } else {
      // Malformed: keep the current view intact, surface a dismissible error.
      setError(result.message);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="ap-inner relative mb-6 overflow-hidden rounded-2xl border border-border/60 bg-card/40 px-5 py-5">
          {/* Decorative aurora wash: two blurred color fields hinting depth behind the lockup. */}
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 opacity-70">
            <div className="absolute -left-20 -top-24 size-64 rounded-full bg-accent/25 blur-3xl" />
            <div className="absolute -top-28 right-0 size-64 rounded-full bg-accent-aurora/25 blur-3xl" />
          </div>
          <div className="relative z-10 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="ap-halo mt-0.5 grid size-10 place-items-center rounded-xl bg-gradient-to-br from-accent/20 to-accent-aurora/20 text-accent">
                <Activity className="size-5" aria-hidden="true" />
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight sm:text-[1.4rem]">
                  AtlasPatch Conductor
                  <span className="font-medium text-muted-foreground"> — Observability</span>
                </h1>
                <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                  Read-only view over the PHI-free snapshot — structural verdicts with reason
                  codes, the decision trace, and no slide pixels.
                </p>
                {/* The four-verdict spine hinted as an accent rule — no score/id text. */}
                <div aria-hidden="true" className="mt-3 flex items-center gap-1.5">
                  <span className="h-1 w-8 rounded-full bg-verdict-valid" />
                  <span className="h-1 w-8 rounded-full bg-verdict-skipped" />
                  <span className="h-1 w-8 rounded-full bg-verdict-quarantined" />
                  <span className="h-1 w-8 rounded-full bg-verdict-blocked" />
                </div>
              </div>
            </div>
            <SnapshotLoader onLoad={handleLoad} />
          </div>
        </header>

        {error && (
          <div
            role="alert"
            className="mb-6 flex items-start justify-between gap-4 rounded-lg border border-verdict-blocked/40 bg-verdict-blocked-soft px-4 py-3 text-sm"
          >
            <span className="flex items-center gap-2 text-foreground">
              <AlertTriangle className="size-4 shrink-0 text-verdict-blocked" aria-hidden="true" />
              {error}
            </span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Dismiss
            </button>
          </div>
        )}

        {view.kind === "version-mismatch" ? (
          <VersionMismatch found={view.found} />
        ) : (
          <main className="flex flex-col gap-6">
            <RunHistory
              runs={runs}
              selectedJobId={selectedRun?.job_id ?? null}
              onSelect={setSelectedJobId}
            />
            {selectedRun ? (
              <>
                <p className="-mt-2 text-xs text-muted-foreground">
                  Showing run{" "}
                  <span className="font-mono text-foreground">{selectedRun.job_id}</span> ·{" "}
                  {selectedRun.cohort_size} slides · source: {view.source}
                </p>
                <CohortMetrics run={selectedRun} />
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                  <div className="lg:col-span-2">
                    <VerdictTable slides={selectedRun.slides} />
                  </div>
                  <Choreography run={selectedRun} agents={view.snapshot.agents} />
                </div>
                <DecisionTrace slides={selectedRun.slides} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                This snapshot contains no runs to display.
              </p>
            )}
          </main>
        )}
      </div>
    </div>
  );
}

/** The explicit schema-incompatibility state (spec): shown instead of the run panels. */
function VersionMismatch({ found }: { found: unknown }) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-verdict-quarantined/40 bg-verdict-quarantined-soft p-8 text-center"
    >
      <AlertTriangle
        className="mx-auto mb-3 size-8 text-verdict-quarantined"
        aria-hidden="true"
      />
      <h2 className="text-base font-semibold">Incompatible snapshot version</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        This viewer renders snapshot schema version{" "}
        <span className="font-mono text-foreground">{SNAPSHOT_SCHEMA_VERSION}</span>, but the
        loaded file reports version{" "}
        <span className="font-mono text-foreground">{String(found)}</span>. Load a snapshot
        exported by a matching Conductor build.
      </p>
    </div>
  );
}
