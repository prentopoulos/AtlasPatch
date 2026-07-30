import { useMemo, useState } from "react";
import { AlertTriangle, Activity } from "lucide-react";
import { SnapshotLoader } from "@/components/SnapshotLoader";
import { RunHistory } from "@/components/RunHistory";
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
        <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-lg bg-muted p-2 text-accent">
              <Activity className="size-5" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                AtlasPatch Conductor — Observability
              </h1>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                Read-only view over the PHI-free snapshot — verdicts, not predictions; decision
                trace, not saliency; no slide pixels.
              </p>
            </div>
          </div>
          <SnapshotLoader onLoad={handleLoad} />
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
            {selectedRun && (
              <p className="text-xs text-muted-foreground">
                Showing run{" "}
                <span className="font-mono text-foreground">{selectedRun.job_id}</span> ·{" "}
                {selectedRun.cohort_size} slides · source: {view.source}
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
