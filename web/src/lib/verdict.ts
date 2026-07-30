/**
 * The semantic verdict system — the design spine (design D-REACT-3).
 *
 * The four terminal structural outcomes drive one color + label token set, reused across the
 * stat-tiles, the verdict table's status cells, the run history, and the choreography markers,
 * so a verdict reads the same everywhere. Class strings are whole literals (Tailwind v4 scans
 * source for complete class names — never build them by concatenation).
 */
import type { Verdict } from "@/lib/snapshot";

export interface VerdictMeta {
  label: string;
  /** Badge fill: soft tint background + saturated foreground + hairline border. */
  badge: string;
  /** Solid marker/dot color. */
  dot: string;
  /** Foreground text color. */
  text: string;
  /** Soft tint background (stat-tile accents). */
  soft: string;
}

export const VERDICT_META: Record<Verdict, VerdictMeta> = {
  valid: {
    label: "Valid",
    badge: "bg-verdict-valid-soft text-verdict-valid border-verdict-valid/30",
    dot: "bg-verdict-valid",
    text: "text-verdict-valid",
    soft: "bg-verdict-valid-soft",
  },
  skipped: {
    label: "Skipped",
    badge: "bg-verdict-skipped-soft text-verdict-skipped border-verdict-skipped/30",
    dot: "bg-verdict-skipped",
    text: "text-verdict-skipped",
    soft: "bg-verdict-skipped-soft",
  },
  quarantined: {
    label: "Quarantined",
    badge: "bg-verdict-quarantined-soft text-verdict-quarantined border-verdict-quarantined/30",
    dot: "bg-verdict-quarantined",
    text: "text-verdict-quarantined",
    soft: "bg-verdict-quarantined-soft",
  },
  blocked: {
    label: "Blocked",
    badge: "bg-verdict-blocked-soft text-verdict-blocked border-verdict-blocked/30",
    dot: "bg-verdict-blocked",
    text: "text-verdict-blocked",
    soft: "bg-verdict-blocked-soft",
  },
};

const UNKNOWN: VerdictMeta = {
  label: "Unknown",
  badge: "bg-muted text-muted-foreground border-border",
  dot: "bg-muted-foreground",
  text: "text-muted-foreground",
  soft: "bg-muted",
};

/** Rank used to sort by verdict severity (report order); unknown outcomes sort last. */
export const VERDICT_ORDER: Verdict[] = ["valid", "skipped", "quarantined", "blocked"];

export function verdictMeta(outcome: string): VerdictMeta {
  return (VERDICT_META as Record<string, VerdictMeta>)[outcome] ?? UNKNOWN;
}

export function verdictRank(outcome: string): number {
  const index = VERDICT_ORDER.indexOf(outcome as Verdict);
  return index === -1 ? VERDICT_ORDER.length : index;
}
