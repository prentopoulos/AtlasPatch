import { useLayoutEffect, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { RunView } from "@/lib/snapshot";

interface Pt {
  x: number;
  y: number;
}

/**
 * The agent-choreography panel (task 2.5; elevated in phase 10): Level-1 component-state (each
 * agent lit/idle + the now-processing ticker) and Level-2 message-flow rendered as an inline
 * `<svg>` directed graph — edges drawn between the real, measured positions of the agent node
 * pills, the latest edge emphasized, each edge drawing in exactly once on mount. When a run
 * recorded no message flow the panel degrades cleanly to the component-state view alone — the
 * GUI is a read-only tailer, never a live A2A subscriber, so nothing here loops or streams.
 *
 * The `<svg>` layer is decorative (`aria-hidden`); the accessible content is the HTML node pills
 * and the per-edge count chips (each carrying an `aria-label` describing the directed edge).
 */
export function Choreography({ run, agents }: { run: RunView; agents: string[] }) {
  const { choreography, message_flow } = run;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const nodeEls = useRef<Map<string, HTMLElement>>(new Map());
  const [centers, setCenters] = useState<Map<string, Pt>>(new Map());
  const [box, setBox] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  // Measure each pill's center relative to the container so the SVG edges connect the nodes
  // wherever they wrap. Custom-property-free reads only; recomputed on resize. In jsdom (unit
  // tests) there is no layout, so centers stay empty and no edge geometry is produced — the
  // container and its accessible chips still render, which is all the unit test asserts.
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const measure = () => {
      const base = container.getBoundingClientRect();
      const next = new Map<string, Pt>();
      for (const [agent, el] of nodeEls.current) {
        const r = el.getBoundingClientRect();
        next.set(agent, { x: r.left - base.left + r.width / 2, y: r.top - base.top + r.height / 2 });
      }
      setCenters(next);
      setBox({ w: base.width, h: base.height });
    };
    measure();
    // ResizeObserver is absent in jsdom (unit tests) — measurement still runs once above; the
    // observer only adds responsive re-measurement where the platform provides it.
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(container);
    return () => ro.disconnect();
  }, [agents, message_flow]);

  const agentIndex = (a: string) => agents.indexOf(a);
  const hasFlow = message_flow.has_flow;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent choreography</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <section>
          <h4 className="mb-3 text-xs font-medium text-muted-foreground">
            {hasFlow ? "Message flow" : "Component state"}
          </h4>

          {/* The graph stage: measured pills over a decorative SVG edge layer. */}
          <div ref={containerRef} className="relative">
            {hasFlow && box.w > 0 && (
              <svg
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 z-0 h-full w-full overflow-visible"
                viewBox={`0 0 ${box.w} ${box.h}`}
              >
                <defs>
                  <marker
                    id="ap-arrow"
                    viewBox="0 0 10 10"
                    refX="8"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--muted-foreground)" />
                  </marker>
                  <marker
                    id="ap-arrow-latest"
                    viewBox="0 0 10 10"
                    refX="8"
                    refY="5"
                    markerWidth="6.5"
                    markerHeight="6.5"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent)" />
                  </marker>
                </defs>
                {message_flow.edges.map((edge, i) => {
                  const a = centers.get(edge.from_agent);
                  const b = centers.get(edge.to_agent);
                  if (!a || !b) return null;
                  const latest =
                    message_flow.latest?.[0] === edge.from_agent &&
                    message_flow.latest?.[1] === edge.to_agent;
                  const geo = edgeGeometry(a, b, agentIndex(edge.from_agent), agentIndex(edge.to_agent));
                  return (
                    <path
                      key={`${edge.from_agent}->${edge.to_agent}`}
                      className="ap-edge"
                      style={{ animationDelay: `${i * 120 + 150}ms` }}
                      d={geo.path}
                      pathLength={1}
                      fill="none"
                      stroke={latest ? "var(--accent)" : "var(--muted-foreground)"}
                      strokeWidth={latest ? 2 : 1.25}
                      strokeOpacity={latest ? 0.95 : 0.45}
                      strokeLinecap="round"
                      markerEnd={`url(#${latest ? "ap-arrow-latest" : "ap-arrow"})`}
                    />
                  );
                })}
              </svg>
            )}

            {/* Level-1 node pills — accessible, positioned by normal flow, wrapping as needed. */}
            <div className="relative z-10 flex flex-wrap gap-2" data-testid="agent-nodes">
              {agents.map((agent, i) => {
                const lit = choreography.lit[agent] ?? false;
                return (
                  <div
                    key={agent}
                    data-active={lit}
                    ref={(el) => {
                      if (el) nodeEls.current.set(agent, el);
                      else nodeEls.current.delete(agent);
                    }}
                    style={{ animationDelay: `${i * 45}ms` }}
                    className={cn(
                      "ap-enter flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium capitalize",
                      lit
                        ? "ap-halo border-ring/50 bg-accent/10 text-foreground"
                        : "border-border bg-muted/30 text-muted-foreground",
                    )}
                  >
                    <span
                      className={cn("size-2 rounded-full", lit ? "bg-accent" : "bg-muted-foreground/40")}
                      aria-hidden="true"
                    />
                    {agent}
                  </div>
                );
              })}
            </div>

            {/* Edge count chips — accessible directed-edge labels, floated at each curve's apex.
                Rendered whenever the run has flow; individual chips need measured node centers,
                so they self-skip until layout is available (e.g. in jsdom). */}
            {hasFlow && (
              <div className="pointer-events-none absolute inset-0 z-20" data-testid="flow-edges">
                {message_flow.edges.map((edge) => {
                  const a = centers.get(edge.from_agent);
                  const b = centers.get(edge.to_agent);
                  if (!a || !b) return null;
                  const latest =
                    message_flow.latest?.[0] === edge.from_agent &&
                    message_flow.latest?.[1] === edge.to_agent;
                  const geo = edgeGeometry(a, b, agentIndex(edge.from_agent), agentIndex(edge.to_agent));
                  return (
                    <span
                      key={`${edge.from_agent}->${edge.to_agent}`}
                      aria-label={`${edge.from_agent} to ${edge.to_agent}, ${edge.count} message${
                        edge.count === 1 ? "" : "s"
                      }`}
                      style={{ left: geo.apex.x, top: geo.apex.y }}
                      className={cn(
                        "absolute -translate-x-1/2 -translate-y-1/2 rounded-full border px-1.5 py-0.5 text-[10px] font-medium tabular-nums shadow-sm",
                        latest
                          ? "border-ring/50 bg-accent/15 text-foreground"
                          : "border-border bg-card text-muted-foreground",
                      )}
                    >
                      {edge.count}
                    </span>
                  );
                })}
              </div>
            )}
          </div>

          <p className="mt-3 text-xs text-muted-foreground">
            Now processing:{" "}
            <span className="text-foreground">{choreography.now_processing ?? "idle"}</span>
          </p>

          {!hasFlow && (
            <p className="mt-2 text-xs text-muted-foreground" data-testid="no-flow">
              No message flow recorded for this run — showing component-state only.
            </p>
          )}
        </section>
      </CardContent>
    </Card>
  );
}

/**
 * A quadratic edge between two node centers, bowed perpendicular to the run so reciprocal edges
 * separate (bow sign follows roster direction) and the arrowhead lands just outside the target
 * pill rather than under it. Returns the SVG path plus the curve apex (t=0.5) for the count chip.
 */
function edgeGeometry(a: Pt, b: Pt, fromIdx: number, toIdx: number): { path: string; apex: Pt } {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;

  // Stop short of the target center so the arrowhead sits at the pill's edge.
  const trim = Math.min(20, len / 2);
  const end: Pt = { x: b.x - ux * trim, y: b.y - uy * trim };

  const mx = (a.x + end.x) / 2;
  const my = (a.y + end.y) / 2;
  const dir = toIdx >= fromIdx ? 1 : -1;
  const bow = Math.min(46, len * 0.28) * dir;
  const cx = mx - uy * bow;
  const cy = my + ux * bow;

  // Apex of the quadratic at t = 0.5.
  const apex: Pt = { x: 0.25 * a.x + 0.5 * cx + 0.25 * end.x, y: 0.25 * a.y + 0.5 * cy + 0.25 * end.y };
  return { path: `M ${a.x} ${a.y} Q ${cx} ${cy} ${end.x} ${end.y}`, apex };
}
