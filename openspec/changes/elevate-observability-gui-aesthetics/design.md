## Context

The observability GUI (`web/`) is a static React 18 + Tailwind v4 client rendering a frozen,
PHI-free `gui-snapshot` payload. It ships as a vendored, byte-reproducible bundle carried in the
Python package. The current visual layer is functional but flat: a plain icon+text header,
uniform cards, KPI tiles, and a Choreography panel that lists agents and message-flow edges as
text rows. Motion today is a single `ap-rise` fade+rise on mount (design D-REACT-9), staggered
by inline `animation-delay`, disabled under `prefers-reduced-motion`.

The surface operates under a hard safety envelope enforced by `web/tests/e2e/guardrails.spec.ts`
and the unit suites: no `<img>` / `<canvas>`, no clinical-score vocabulary, only `slide_<hex>`
pseudonyms, no write controls. These are non-negotiable and shape every decision below — the
elevation must land entirely in CSS and inline SVG.

## Goals / Non-Goals

**Goals:**
- Substantially raise perceived quality (depth, polish, motion) across the six panels, led by a
  redesigned Choreography flow graph and a header with real presence.
- Keep the four-verdict OKLCH color spine as the identity; extend tokens, never fork the palette.
- Re-author 21st.dev-style treatments (spotlight/glow borders, magic-card depth, gradient
  auroras, animated edges) in pure CSS + inline SVG.
- Promote the motion-honesty rule from change-level folklore into a durable, testable spec
  requirement.
- Keep every existing test green and the vendored bundle byte-reproducible.

**Non-Goals:**
- No new runtime dependency (no framer-motion / animation lib), no `<canvas>`/WebGL, no `<img>`.
- No KPI count-up or any motion that implies live/streaming data.
- No behavioral change: still read-only, still snapshot-only, panels unchanged in what they show.
- Not necessarily all six panels to the same depth this pass — hero-led (see Decisions).

## Decisions

**1. Hero-led scope, not a uniform sweep.**
Invest deeply in Choreography (highest visual payoff) and the header, then apply a lighter shared
polish (glow borders, hover-lift, verdict rail, richer entrance) to tiles/table/history.
*Rationale:* biggest perceived-quality jump for the least risk; lets us view a real result in the
browser before deciding whether the remaining panels warrant more. *Alternative considered:* full
six-panel redesign in one change — rejected as higher risk against the guardrail suite and harder
to review.

**2. Choreography as an inline-SVG flow graph.**
Render agent nodes as positioned pills and message-flow as directed SVG edges that draw in once
via `stroke-dashoffset` animation, latest edge emphasized; lit nodes get a soft CSS halo. Degrade
to the component-state view alone when `message_flow.has_flow` is false.
*Rationale:* inline `<svg>` is explicitly allowed by the guardrails (decorative chrome); it gives
a true "system view" a text list cannot. *Alternative considered:* `<canvas>` graph — forbidden.
*Alternative considered:* a CSS-only grid of pills — keeps the list feel, misses the edges.

**3. CSS-first motion, one-shot only, reduced-motion honored.**
All new motion is CSS keyframes/transitions: staggered entrance (spring-like cubic-bezier),
one-shot edge draw-in, and interaction-driven hover/focus/selection micro-motion. Everything sits
behind `@media (prefers-reduced-motion: reduce)`.
*Rationale:* honors the promoted spec requirement, keeps the bundle lean/reproducible.
*Alternative considered:* framer-motion — rejected; weight + determinism cost against a vendored
byte-reproducible bundle, and unnecessary for one-shot motion.

**4. Extend OKLCH tokens; whole Tailwind class literals only.**
Add gradient/glow/surface tokens (e.g. an accent aurora stop, a glow ring, a translucent card
tint) alongside the existing verdict tokens in `index.css`, mapped through `@theme inline`. All
Tailwind classes stay whole literals (v4 scans source — no dynamic concatenation).
*Rationale:* preserves the single-source verdict spine and Tailwind v4's scan contract.

**5. Cursor-tracking spotlight borders via CSS mask + minimal pointer JS.**
The "magic card" glow follows the pointer using a CSS radial-gradient mask fed by a couple of CSS
custom properties updated on `pointermove`. Purely decorative, interaction-driven (not a loop),
and inert under reduced-motion.

### Referenced techniques (verified via Context7)

- **Tailwind v4 motion API**: define animations in `@theme` as `--animate-<name>: <name> <timing>`
  with the `@keyframes` block inside `@theme`; use the `motion-reduce:` / `motion-safe:` variants
  (and optionally the `starting:` variant for `@starting-style` entrances) instead of a hand-rolled
  `@media (prefers-reduced-motion)` block. This is the idiomatic way to add our entrance + edge-draw
  utilities and satisfy the reduced-motion requirement.
- **Magic UI `MagicCard` (spotlight border)**: re-author its pointer-following border in **pure CSS**
  — `background: linear-gradient(var(--card) 0 0) padding-box, radial-gradient(<size> circle at
  var(--mx) var(--my), <glow>, transparent) border-box` over a transparent border, with `--mx/--my`
  updated on `pointermove`. **No framer-motion / `motion/react`** — the library version depends on
  `useMotionValue`/`useMotionTemplate`, which we deliberately drop to keep the bundle reproducible.
- **REJECTED — `BorderBeam` and glow `DotPattern`**: both animate with `repeat: Infinity`. An
  infinitely looping border beam or pulsing dot field **violates the new "motion never implies live
  data / no indefinite loop" requirement** and is out of scope. A *static* dot-grid/aurora with a
  radial mask is fine (no animation); only the looping variants are banned. This is exactly the
  filter the promoted spec requirement is meant to enforce.

## Risks / Trade-offs

- **Guardrail regression (score/ID/img/canvas/write)** → Run `web` unit + e2e (`guardrails.spec.ts`)
  after each panel; keep all decorative SVG `aria-hidden`; add no new text that could match a
  score/raw-id pattern.
- **"Motion implies live data" creep** (e.g. edge draw-in reading as streaming) → Keep it strictly
  one-shot on mount, no repeat/alternate; add a test asserting no infinite animation and
  reduced-motion suppression, per the new requirement.
- **Bundle non-reproducibility** → Add no dependency; keep LF endings; re-vendor deterministically
  and diff the bundle before commit.
- **Tailwind v4 class purging** dropping dynamic classes → Use whole literals and the token map;
  verify computed styles render in the browser, not just in tests.
- **Pointer-driven glow cost / jank** → Throttle to CSS custom-property writes only (no layout),
  gate behind a hover-capable media query, and disable under reduced-motion.

## Open Questions

- Does the promoted requirement warrant a dedicated unit/e2e assertion (no infinite animation +
  reduced-motion suppression), or is manual verification enough for this pass? (Leaning: add the
  assertion — it makes the requirement testable, which is the point of promoting it.)
- Header logotype: a pure-CSS/SVG wordmark lockup vs. keeping the lucide `Activity` mark with an
  aurora wash behind it. (Leaning: keep the mark, add the wash + refined type — lower risk.)
