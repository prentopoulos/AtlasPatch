import { ArrowRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { RunView } from "@/lib/snapshot";

/**
 * The agent-choreography panel (task 2.5): Level-1 component-state and Level-2 message-flow.
 *
 * Legibility-first layout (phase-10 feedback): lead with an explicit "In action" callout naming
 * the single active agent, list every agent with an unambiguous active/idle state, then present
 * the message flow as readable rows that spell out the message count and mark the latest hop.
 * When a run recorded no message flow the panel degrades to the component-state view alone — the
 * GUI is a read-only tailer, never a live A2A subscriber.
 */
export function Choreography({ run, agents }: { run: RunView; agents: string[] }) {
  const { choreography, message_flow } = run;
  const active = choreography.active;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent choreography</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {/* In action: the single agent currently (or last) processing, called out plainly. */}
        <section>
          <h4 className="mb-2 text-xs font-medium text-muted-foreground">In action</h4>
          {active ? (
            <span className="ap-halo inline-flex items-center gap-2 rounded-lg border border-ring/50 bg-accent/10 px-3 py-1.5 text-sm font-medium capitalize text-foreground">
              <span className="size-2 rounded-full bg-accent" aria-hidden="true" />
              {active}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">Idle</span>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            Now processing:{" "}
            <span className="text-foreground">{choreography.now_processing ?? "idle"}</span>
          </p>
        </section>

        {/* Every agent, with an explicit active/idle state so the roster reads at a glance. */}
        <section>
          <h4 className="mb-2 text-xs font-medium text-muted-foreground">Agents</h4>
          <ul className="flex flex-col gap-1" data-testid="agent-nodes">
            {agents.map((agent, i) => {
              const isActive = agent === active;
              return (
                <li
                  key={agent}
                  data-active={isActive}
                  style={{ animationDelay: `${i * 45}ms` }}
                  className={cn(
                    "ap-enter flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors",
                    isActive
                      ? "border-ring/50 bg-accent/10 font-medium text-foreground"
                      : "border-border/60 text-muted-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "size-2 rounded-full",
                      isActive ? "bg-accent" : "bg-muted-foreground/40",
                    )}
                    aria-hidden="true"
                  />
                  <span className="capitalize">{agent}</span>
                  <span
                    className={cn(
                      "ml-auto text-[10px] uppercase tracking-wide",
                      isActive ? "text-accent" : "text-muted-foreground/70",
                    )}
                  >
                    {isActive ? "active" : "idle"}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>

        {/* Message flow: readable directed rows with the count spelled out and the latest marked. */}
        <section>
          <h4 className="mb-2 text-xs font-medium text-muted-foreground">Message flow</h4>
          {!message_flow.has_flow ? (
            <p className="text-xs text-muted-foreground" data-testid="no-flow">
              No message flow recorded for this run — showing component state only.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5" data-testid="flow-edges">
              {message_flow.edges.map((edge, i) => {
                const latest =
                  message_flow.latest?.[0] === edge.from_agent &&
                  message_flow.latest?.[1] === edge.to_agent;
                return (
                  <li
                    key={`${edge.from_agent}->${edge.to_agent}`}
                    data-latest={latest}
                    style={{ animationDelay: `${i * 40}ms` }}
                    className={cn(
                      "ap-enter flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs",
                      latest
                        ? "border-ring/50 bg-accent/10 text-foreground"
                        : "border-border/60 text-muted-foreground",
                    )}
                  >
                    <span className="font-medium capitalize text-foreground">{edge.from_agent}</span>
                    <ArrowRight className="size-3.5 shrink-0" aria-hidden="true" />
                    <span className="font-medium capitalize text-foreground">{edge.to_agent}</span>
                    <span className="ml-auto tabular-nums">
                      {edge.count} message{edge.count === 1 ? "" : "s"}
                      {latest && <span className="ml-1.5 font-medium text-accent">· latest</span>}
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
