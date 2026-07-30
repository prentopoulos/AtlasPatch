import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { TERMINAL_OUTCOMES, type RunView, type Verdict } from "@/lib/snapshot";

// Literal class names per verdict (Tailwind v4 scans for whole class strings — no dynamic
// concatenation). The shared verdict token system (Slice B) reuses these same colors.
const COUNT_TEXT: Record<Verdict, string> = {
  valid: "text-verdict-valid",
  skipped: "text-verdict-skipped",
  quarantined: "text-verdict-quarantined",
  blocked: "text-verdict-blocked",
};

interface RunHistoryProps {
  runs: RunView[];
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
}

/**
 * The run-history panel + run selector (task 1.6): one row per recorded run (job id, status,
 * cohort size, per-outcome tallies). Rows double as the run selector — selecting one drives
 * the rest of the panels. Renders an empty state for a zero-run snapshot.
 */
export function RunHistory({ runs, selectedJobId, onSelect }: RunHistoryProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Run history</CardTitle>
      </CardHeader>
      <CardContent>
        {runs.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground" data-testid="empty-runs">
            No runs recorded in this snapshot.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Run</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium text-right">Cohort</th>
                  {TERMINAL_OUTCOMES.map((outcome) => (
                    <th key={outcome} className="py-2 pr-4 font-medium text-right capitalize">
                      {outcome}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const selected = run.job_id === selectedJobId;
                  return (
                    <tr
                      key={run.job_id}
                      onClick={() => onSelect(run.job_id)}
                      aria-selected={selected}
                      className={cn(
                        "cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-muted/50",
                        selected && "bg-muted/70",
                      )}
                    >
                      <td className="py-2 pr-4 font-mono text-xs">{run.job_id}</td>
                      <td className="py-2 pr-4 text-muted-foreground">
                        {String(run.job.status ?? "—")}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">{run.cohort_size}</td>
                      {TERMINAL_OUTCOMES.map((outcome) => (
                        <td
                          key={outcome}
                          className={cn(
                            "py-2 pr-4 text-right tabular-nums",
                            run.counts[outcome] > 0
                              ? COUNT_TEXT[outcome]
                              : "text-muted-foreground/50",
                          )}
                        >
                          {run.counts[outcome] ?? 0}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
