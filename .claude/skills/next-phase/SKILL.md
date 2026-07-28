---
name: next-phase
description: Run one iteration of AtlasPatch's phase workflow — propose, branch, implement, archive, merge. Use when the user wants to start a new build phase, continue an in-progress one, or asks to "start the next phase" / "run the phase workflow".
---

# Next phase

Executes one cycle of the loop documented in `WORKFLOW.md` (read it for full rationale — this skill is the condensed, actionable version).

## Steps

1. **Confirm `main` is up to date.** Check `git status` and the tracked remote before branching.
2. **Propose.** Run `/opsx:propose` for the phase (use the next unstarted phase from `PROJECT.md`'s phase list, or ask the user which phase if ambiguous). This writes `openspec/changes/<name>/{proposal,design,tasks}.md`.
3. **Branch and open the PR.** `git checkout -b <name>`, commit only the `openspec/changes/<name>/` files as the first commit, push, open a PR. This spec-only commit is the review point before any code exists — pause here if the user wants to review the spec before continuing.
4. **Implement.** Run `/opsx:apply`, committing per task (or logical group) so commits map to `tasks.md` items.
5. **Archive on the same branch**, once every task in `tasks.md` is checked off. Run `/opsx:archive <name>` and commit the result as the final commit on the branch. Do not archive before all tasks are complete, and do not merge before archiving.
6. **Confirm CI is green** (`specs` job: `openspec validate`; `app` job: typecheck/lint/test/build) before suggesting merge. Use a regular merge commit, not squash — preserves the spec → tasks → archive commit structure.
7. **After merge**, the next invocation of this skill starts back at step 1 from the updated `main`.

## Notes

- One PR per phase, staged commits — not a separate spec-approval PR followed by an implementation PR.
- If asked to skip a step (e.g. archive before tasks are done, or squash-merge), flag that it breaks the convention in `WORKFLOW.md` before doing it.
