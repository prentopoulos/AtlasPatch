import { ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { VerdictBadge } from "@/components/VerdictBadge";
import type { SlideView, TraceEvent } from "@/lib/snapshot";

/**
 * The decision-trace tree (task 2.4): each slide with a recorded chain is a collapsible node;
 * expanding it reveals the ordered reconcile -> dispatch -> verdict -> (recover|blocked) steps
 * that produced the outcome. Every field is operational metadata — the trace is the visible
 * artifact of the orchestrator's *decisions*, never saliency.
 */
export function DecisionTrace({ slides }: { slides: SlideView[] }) {
  const traced = slides.filter((s) => s.trace.length > 0);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Decision trace</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-1.5">
        {traced.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">No decision trace recorded.</p>
        ) : (
          traced.map((slide, index) => (
            <SlideTrace key={slide.slide_stem} slide={slide} defaultOpen={index === 0} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function SlideTrace({ slide, defaultOpen }: { slide: SlideView; defaultOpen: boolean }) {
  return (
    <Collapsible
      defaultOpen={defaultOpen}
      className="rounded-lg border border-border/60 bg-muted/20"
    >
      <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2 text-left">
        <ChevronRight className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
        <span className="font-mono text-xs">{slide.slide_stem}</span>
        <VerdictBadge outcome={slide.outcome} className="ml-auto" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="ml-[1.65rem] flex flex-col gap-0 border-l border-border pb-2 pl-4">
          {slide.trace.map((event, i) => (
            <TraceStep key={i} event={event} />
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}

function TraceStep({ event }: { event: TraceEvent }) {
  return (
    <li className="relative py-1 text-xs">
      <span className="absolute -left-[1.28rem] top-[0.85rem] size-1.5 rounded-full bg-border" />
      <span className="font-mono text-muted-foreground">{event.agent}</span>
      <span className="mx-1.5 font-medium text-foreground">{event.event}</span>
      {event.reason_code && (
        <span className="font-mono text-muted-foreground">· {event.reason_code}</span>
      )}
      {event.stage && <span className="ml-1.5 text-muted-foreground/70">({event.stage})</span>}
    </li>
  );
}
