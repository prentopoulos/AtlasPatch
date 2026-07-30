import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { verdictMeta } from "@/lib/verdict";

/**
 * A verdict rendered as its shared color token — the structural pass/fail, never a score
 * (spec: "Verdicts carry no confidence score"). Used in the verdict table, the trace headers,
 * and anywhere an outcome appears.
 */
export function VerdictBadge({ outcome, className }: { outcome: string; className?: string }) {
  const meta = verdictMeta(outcome);
  return (
    <Badge variant="outline" className={cn(meta.badge, className)}>
      <span className={cn("size-1.5 rounded-full", meta.dot)} aria-hidden="true" />
      {meta.label}
    </Badge>
  );
}
