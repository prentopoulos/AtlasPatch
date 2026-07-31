## ADDED Requirements

### Requirement: Motion is one-shot and never implies live data

The GUI SHALL restrict animation to one-shot on-mount transitions or direct interaction-driven
motion (hover, focus, selection). It SHALL NOT present any animation that loops indefinitely or
that implies live, streaming, or polling data — the surface renders a frozen point-in-time
snapshot and is a tailer, never a live subscriber. All animation SHALL be disabled when the
viewer requests `prefers-reduced-motion: reduce`.

#### Scenario: Reduced-motion preference disables animation

- **WHEN** the viewer has `prefers-reduced-motion: reduce` set and the GUI renders a snapshot
- **THEN** entrance, glow, edge-draw, and every other animation is suppressed and the surface
  renders in its final resting state with no motion

#### Scenario: No animation loops or implies data arrival

- **WHEN** any snapshot (including the default demo and a gated run) is rendered
- **THEN** all animation is one-shot on mount or bound to a user interaction, with no
  indefinitely repeating animation and nothing that implies a value is updating live or
  streaming in
