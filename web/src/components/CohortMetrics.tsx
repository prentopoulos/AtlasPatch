import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { TERMINAL_OUTCOMES, type RunView } from "@/lib/snapshot";
import { verdictMeta } from "@/lib/verdict";

/**
 * The cohort-metrics KPI stat-tiles (task 2.2): cohort size + the four structural tallies,
 * each keyed to the shared verdict token so the color reads the same as the table and history.
 */
export function CohortMetrics({ run }: { run: RunView }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <StatTile label="Cohort" value={run.cohort_size} accent="text-foreground" index={0} />
      {TERMINAL_OUTCOMES.map((outcome, i) => {
        const meta = verdictMeta(outcome);
        return (
          <StatTile
            key={outcome}
            label={meta.label}
            value={run.counts[outcome] ?? 0}
            accent={meta.text}
            dot={meta.dot}
            index={i + 1}
          />
        );
      })}
    </div>
  );
}

function StatTile({
  label,
  value,
  accent,
  dot,
  index,
}: {
  label: string;
  value: number;
  accent: string;
  dot?: string;
  index: number;
}) {
  return (
    <Card className="ap-enter p-4" style={{ animationDelay: `${index * 45}ms` }}>
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        {dot && <span className={cn("size-2 rounded-full", dot)} aria-hidden="true" />}
        {label}
      </div>
      <div className={cn("mt-1 text-2xl font-semibold tabular-nums", accent)}>{value}</div>
    </Card>
  );
}
