## 1. Design tokens & motion foundation

- [x] 1.1 Extend `web/src/index.css` OKLCH tokens (accent aurora stop, glow ring, translucent card tint) and map them through `@theme inline` — do not fork the verdict palette
- [x] 1.2 Add the one-shot motion utilities/keyframes: a spring-eased staggered entrance (richer than `ap-rise`), an edge draw-in keyframe (`stroke-dashoffset`), and a glow/halo util — all whole Tailwind class literals
- [x] 1.3 Ensure every new animation sits behind `@media (prefers-reduced-motion: reduce)` and resolves to the final resting state

## 2. Choreography flow graph (hero)

- [x] 2.1 Replace the message-flow list with an inline `<svg>` directed graph: positioned agent node pills (lit/idle) + directed edges with counts, latest edge emphasized
- [x] 2.2 Animate edges to draw in once via `stroke-dashoffset` (one-shot on mount, no loop); add a soft CSS halo to lit nodes
- [x] 2.3 Preserve clean degradation to component-state-only when `message_flow.has_flow` is false; keep the "now processing" ticker
- [x] 2.4 Mark all decorative SVG `aria-hidden`; keep node/edge labels accessible

## 3. Header presence

- [x] 3.1 Add a CSS aurora/gradient wash behind the header and a refined logotype lockup (keep the lucide mark, elevate type/tracking)
- [x] 3.2 Hint the verdict palette as an accent without introducing score/raw-id text

## 4. Shared panel polish

- [ ] 4.1 CohortMetrics tiles: cursor-tracking spotlight/glow border, hover-lift, number sheen, hairline inner-glow — no count-up
- [ ] 4.2 VerdictTable + RunHistory: leading verdict color-rail per row, hover row-glow, smooth selection state
- [ ] 4.3 Apply the new spring-eased staggered entrance consistently across panels (replace/upgrade `ap-enter` usage)
- [ ] 4.4 Implement the pointer-driven glow via CSS custom properties on `pointermove` (no layout writes), gated to hover-capable devices and inert under reduced-motion

## 5. Guardrails, tests & bundle

- [ ] 5.1 Add/extend a test asserting no infinite animation and full reduced-motion suppression (covers the new spec requirement)
- [ ] 5.2 Run `npm run test` and `npm run test:e2e` (incl. `guardrails.spec.ts`) — confirm no `<img>`/`<canvas>`, no score/raw-id vocabulary, no write controls, all green
- [ ] 5.3 Run `npm run build` / typecheck; re-vendor the static bundle deterministically (LF) and diff it for byte-reproducibility
- [ ] 5.4 Visual check in the browser (light + dark, reduced-motion on/off) before wrapping the change
