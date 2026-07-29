# Workflow

AtlasPatch development is driven by an OpenSpec, phase-based loop. Each phase is one
self-contained change that ships as a single pull request. The `next-phase` skill is the
condensed, actionable version of this document; read this file for the rationale.

## The loop

One phase = one change = one PR. Each phase runs the same five steps:

1. **Confirm `main` is up to date.** Check `git status` and the tracked remote before
   branching. Nothing starts from a dirty or stale `main`.

2. **Propose.** Run `/opsx:propose` for the phase — pick the next unstarted phase from the
   list in `PROJECT.md` (ask if ambiguous). This writes
   `openspec/changes/<name>/{proposal,design,tasks}.md` plus per-capability delta specs.

3. **Branch and open the PR.** `git checkout -b <name>`, commit **only** the
   `openspec/changes/<name>/` files as the first commit, push, and open a PR. This
   spec-only commit is the review checkpoint *before any code exists* — pause here if the
   spec should be reviewed before implementation.

4. **Implement.** Run `/opsx:apply`, committing per task (or per logical group) so commits
   map to `tasks.md` items. With the first implementation commit, flip this phase's row in
   `PROJECT.md`'s phase table from `Planned` to `In progress`.

5. **Archive, then merge.** Once every task in `tasks.md` is checked off, run
   `/opsx:archive <name>` on the same branch, flip this phase's `PROJECT.md` status from
   `In progress` to `Done` in the same commit, and commit the result as the final commit.
   Confirm CI is green (the `specs` job runs `openspec validate`; the `app` job runs
   typecheck/lint/test/build), then merge with a **regular merge commit** — not squash —
   to preserve the spec → tasks → archive commit structure. Merging the PR lands the
   accurate `Done` status on `main`, so the status column never drifts.

After merge, the next invocation of `next-phase` starts again at step 1 from the updated
`main`.

## Conventions

- **One PR per phase, staged commits** — not a separate spec-approval PR followed by an
  implementation PR. The spec-only first commit is the review point within the single PR.
- **Do not archive before all tasks are complete**, and **do not merge before archiving.**
- **Keep `PROJECT.md`'s phase-status column current within each phase's own PR** — `In
  progress` when implementation starts, `Done` in the archive commit — so it never drifts
  from what has actually merged to `main`.
- **Never squash-merge** a phase — the linear spec → implementation → archive history is
  the audit trail.
- The upstream ML pipeline in `atlas_patch/` is not modified by orchestration-layer
  phases; see each change's design doc for its integration boundary.

## Boundary with upstream

AtlasPatch is a fork of `AtlasAnalyticsLab/AtlasPatch` (tracked as the `upstream` remote).
Phase work targets this fork's `origin/main`. Changes are additive extensions layered on
top of the upstream package; keep the fork mergeable with upstream by not editing
`atlas_patch/` internals unless a phase explicitly scopes that.
