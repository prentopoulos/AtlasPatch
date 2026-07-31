## Why

The React observability GUI is functionally complete but visually utilitarian — flat cards,
a plain text header, and a list-based choreography panel that reads as a form rather than a
system view. The surface is where operators build trust in the Conductor's structural verdicts,
so its perceived quality matters. We can raise that quality substantially without touching a
single behavioral or safety requirement, because none of the existing `observability-gui`
requirements constrain visual style or motion. This change elevates the aesthetic within the
exact same read-only, PHI-free, guardrail-enforced envelope — and promotes the previously
tribal "motion is one-shot, never implies live data" rule into a durable, testable requirement.

## What Changes

- **Choreography panel (hero)**: re-render the agent message-flow as an animated inline `<svg>`
  flow graph — lit/idle node pills with a soft CSS halo, directed edges that draw in once via
  `stroke-dashoffset`, the latest edge emphasized — degrading cleanly to component-state-only
  when a run recorded no flow.
- **Header**: give it presence — a logotype lockup and a CSS aurora/gradient wash — replacing
  the plain icon-plus-text treatment.
- **Stat tiles, verdict table, entrances**: lighter polish using a legal elevation toolkit —
  cursor-tracking spotlight/glow borders, hover-lift, a leading verdict color-rail on table
  rows, and a spring-eased one-shot staggered entrance.
- **Design tokens**: extend the existing OKLCH token system in `index.css` (never fork the
  verdict palette) with the gradient/glow/surface tokens the new treatments need.
- **Motion contract promoted to spec**: add a new `observability-gui` requirement asserting
  that animation is one-shot / interaction-driven, never implies live/streaming/polling data,
  and is fully disabled under `prefers-reduced-motion`.
- **No** KPI count-up animation (it flirts with implying live data), **no** `<img>`/`<canvas>`,
  **no** framer-motion dependency (keeps the vendored bundle byte-reproducible and lean).

## Capabilities

### New Capabilities
<!-- None — this change modifies an existing capability. -->

### Modified Capabilities
- `observability-gui`: adds one new requirement — "Motion is one-shot and never implies live
  data" — codifying the animation-honesty rule (one-shot/interaction-driven only, no
  live/streaming/polling motion, disabled under reduced-motion). No existing requirement's
  behavior changes; the visual/motion refresh itself is an implementation detail under the
  already-holding requirements (read-only, no pixels/scores, panels present).

## Impact

- **Code**: `web/src/index.css` (token/util/keyframe additions); `web/src/components/`
  (`Choreography.tsx`, `CohortMetrics.tsx`, `VerdictTable.tsx`, `RunHistory.tsx`), `web/src/App.tsx`
  header; possibly small shared primitives (`ui/card.tsx`).
- **Tests**: `web/tests/e2e/guardrails.spec.ts` and the unit suites must stay green; a new
  reduced-motion / no-loop assertion may be added to cover the promoted requirement.
- **Dependencies**: none added — CSS-first, inline SVG only.
- **Build/distribution**: the vendored, byte-reproducible static bundle must remain
  deterministic (LF, no new heavyweight deps).
