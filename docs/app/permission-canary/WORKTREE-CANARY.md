# Worktree Permission Canary

Status: **Active synthetic fixture. Do not delete.**

This file exists only to be denied. It contains no athlete data, no coaching
context, no credential, and no real information of any kind. Every line below is
synthetic filler.

## What this canary proves

This file is protected by **exactly one** deny rule, in
`docs/app/claude-app-settings.json`:

```text
Read(//d/Run-Performance-Project/.claude/worktrees/*/docs/app/permission-canary/WORKTREE-CANARY.md)
```

There is deliberately **no** project-relative rule and **no** repository-root
absolute rule for this path. That single-rule design is the whole point: if a
session running **inside a worktree** is denied this file, the denial can only
have come from the `worktrees/*/` wildcard above. Nothing else matches.

This is the rule shape that the TASK-010 incident showed was missing — a
worktree is a full checkout with its own copy of every protected file, and a
repository-root absolute rule does not match it. Denying this file in a worktree
session is therefore direct evidence that the identically-shaped worktree rules
for `CLAUDE.md`, `athletes/`, `team_data/`, `garmin/`, `scripts/`, root
`supabase/`, `.agents/AGENTS.md`, and `.claude/settings*.json` resolve as
intended.

An earlier canary carried three overlapping rules at once, so a denial proved
only that *some* rule fired — not which one. In particular it could not
distinguish the worktree wildcard from the project-relative rule. This file and
`MAIN-CANARY.md` replace that ambiguous design.

## How it is used

`docs/app/CLAUDE-CODE-SETUP.md` is the procedure. In short: a worktree session
asks Claude to read this file by the **current worktree's** exact absolute path,
using the built-in Read tool only. Denial before any content is returned is a
pass.

The matching fixture for main-repository sessions is `MAIN-CANARY.md`, which
carries the repository-root absolute rule and nothing else.

## Rules for maintainers

- Never delete this file or its rule; the verification step stops working.
- Never add a second rule matching this path. A second rule destroys the
  isolation and makes any denial unattributable again.
- Keep the wildcard a single `*`, anchored at the worktree root, matching the
  protected-path rules. A `**` form would change what the shape proves.
- If the rule shape used for real protected paths changes, change this canary's
  rule the same way, or it stops proving anything about them.

## Synthetic filler

Canary marker: `SYNTHETIC-CANARY-WORKTREE-DO-NOT-COPY`.

If this text is ever visible in a Claude Code worktree transcript, the
`worktrees/*/` deny rule is not in effect and the session must be stopped.
