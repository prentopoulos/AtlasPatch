import { ArrowRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { RunView } from "@/lib/snapshot";

/**
 * The agent-choreography panel (task 2.5): Level-1 component-state (each agent active/idle +
 * the now-processing ticker) and Level-2 message-flow (directed edges with counts, latest
 * emphasized). When a run recorded no message flow the panel degrades cleanly to the
 * component-state view alone — the GUI is a read-only tailer, never a live A2A subscriber.
 */
export function Choreography({ run, agents }: { run: RunView; agents: string[] }) {
  const { choreography, message_flow } = run;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent choreography</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <section>
          <h4 className="mb-2 text-xs font-medium text-muted-foreground">
            Level 1 · component state
          </h4>
          <div className="flex flex-wrap gap-2" data-testid="agent-nodes">
            {agents.map((agent) => {
              const lit = choreography.lit[agent] ?? false;
              return (
                <div
                  key={agent}
                  data-active={lit}
                  className={cn(
                    "flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium capitalize transition-colors",
                    lit
                      ? "border-ring/50 bg-accent/10 text-foreground"
                      : "border-border bg-muted/30 text-muted-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "size-2 rounded-full",
                      lit ? "bg-accent" : "bg-muted-foreground/40",
                    )}
                    aria-hidden="true"
                  />
                  {agent}
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Now processing:{" "}
            <span className="text-foreground">{choreography.now_processing ?? "idle"}</span>
          </p>
        </section>

        <section>
          <h4 className="mb-2 text-xs font-medium text-muted-foreground">
            Level 2 · message flow
          </h4>
          {!message_flow.has_flow ? (
            <p className="text-xs text-muted-foreground" data-testid="no-flow">
              No message flow recorded for this run — showing component-state only.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5" data-testid="flow-edges">
              {message_flow.edges.map((edge) => {
                const latest =
                  message_flow.latest?.[0] === edge.from_agent &&
                  message_flow.latest?.[1] === edge.to_agent;
                return (
                  <li
                    key={`${edge.from_agent}->${edge.to_agent}`}
                    data-latest={latest}
                    className={cn(
                      "flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs",
                      latest
                        ? "border-ring/50 bg-accent/10 text-foreground"
                        : "border-border/60 text-muted-foreground",
                    )}
                  >
                    <span className="font-medium capitalize text-foreground">
                      {edge.from_agent}
                    </span>
                    <ArrowRight className="size-3.5 shrink-0" aria-hidden="true" />
                    <span className="font-medium capitalize text-foreground">{edge.to_agent}</span>
                    <span className="ml-auto tabular-nums text-muted-foreground">
                      {edge.count} msg{edge.count === 1 ? "" : "s"}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
