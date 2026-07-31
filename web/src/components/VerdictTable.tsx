import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { VerdictBadge } from "@/components/VerdictBadge";
import { cn } from "@/lib/utils";
import type { SlideView } from "@/lib/snapshot";
import { verdictMeta, verdictRank } from "@/lib/verdict";

type SortKey = "slide_stem" | "outcome" | "reason_code";
type SortDir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "slide_stem", label: "Slide" },
  { key: "outcome", label: "Verdict" },
  { key: "reason_code", label: "Reason" },
];

/**
 * The sortable per-slide verdict table (task 2.3): pseudonymized stem, structural verdict,
 * reason code, and detail. There is deliberately **no score column** — a verdict is the
 * validator's pass/fail with a reason, never a likelihood (spec: no clinical scores).
 */
export function VerdictTable({ slides }: { slides: SlideView[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("outcome");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const sorted = useMemo(() => {
    const rows = [...slides];
    rows.sort((a, b) => {
      const cmp =
        sortKey === "outcome"
          ? verdictRank(a.outcome) - verdictRank(b.outcome)
          : a[sortKey].localeCompare(b[sortKey]);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [slides, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Per-slide verdicts</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {COLUMNS.map((col) => {
                const active = col.key === sortKey;
                const Icon = !active ? ChevronsUpDown : sortDir === "asc" ? ChevronUp : ChevronDown;
                return (
                  <TableHead key={col.key} aria-sort={active ? sortAria(sortDir) : "none"}>
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      className={cn(
                        "-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 hover:text-foreground",
                        active && "text-foreground",
                      )}
                    >
                      {col.label}
                      <Icon className="size-3.5" aria-hidden="true" />
                    </button>
                  </TableHead>
                );
              })}
              <TableHead>Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((slide, i) => {
              const meta = verdictMeta(slide.outcome);
              return (
                <TableRow
                  key={slide.slide_stem}
                  className="ap-enter"
                  style={{ animationDelay: `${Math.min(i, 12) * 30}ms` }}
                >
                  <TableCell className="relative pl-4 font-mono text-xs">
                    {/* Leading verdict color-rail: bg-current picks up the verdict text color. */}
                    <span
                      aria-hidden="true"
                      className={cn(
                        "pointer-events-none absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-current opacity-80",
                        meta.text,
                      )}
                    />
                    {slide.slide_stem}
                  </TableCell>
                  <TableCell>
                    <VerdictBadge outcome={slide.outcome} />
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {slide.reason_code}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{slide.detail}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function sortAria(dir: SortDir): "ascending" | "descending" {
  return dir === "asc" ? "ascending" : "descending";
}
