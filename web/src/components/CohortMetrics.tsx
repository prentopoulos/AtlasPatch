import type { PointerEvent } from "react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { TERMINAL_OUTCOMES, type RunView } from "@/lib/snapshot";
import { verdictMeta } from "@/lib/verdict";

/**
 * The cohort-metrics KPI stat-tiles (task 2.2): cohort size + the four structural tallies,
 * each keyed to the shared verdict token so the color reads the same as the table and history.
 * Phase-10 polish: a cursor-tracking spotlight, hover-lift, and hairline inner-glow — the value
 * is rendered statically (never counted up), since a count-up would imply a value arriving live.
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

// Feed the cursor-tracking spotlight: write the pointer position into two CSS custom properties
// (repaint-only, no layout write) that the `.ap-spotlight` radial-gradient reads. Hover-gated and
// inert under reduced-motion in CSS, so no guard is needed here.
function trackPointer(e: PointerEvent<HTMLDivElement>) {
  const el = e.currentTarget;
  const rect = el.getBoundingClientRect();
  el.style.setProperty("--mx", `${e.clientX - rect.left}px`);
  el.style.setProperty("--my", `${e.clientY - rect.top}px`);
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
    <Card
      onPointerMove={trackPointer}
      className="ap-enter ap-spotlight ap-lift ap-inner relative overflow-hidden p-4"
      style={{ animationDelay: `${index * 45}ms` }}
    >
      <div className="relative z-10">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          {dot && <span className={cn("size-2 rounded-full", dot)} aria-hidden="true" />}
          {label}
        </div>
        <div
          className={cn(
            "mt-1 text-2xl font-semibold tabular-nums [text-shadow:0_1px_0_rgb(255_255_255/0.06)]",
            accent,
          )}
        >
          {value}
        </div>
      </div>
    </Card>
  );
}
