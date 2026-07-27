# Main-Repository Permission Canary

Status: **Active synthetic fixture. Do not delete.**

This file exists only to be denied. It contains no athlete data, no coaching
context, no credential, and no real information of any kind. Every line below is
synthetic filler.

## What this canary proves

This file is protected by **exactly one** deny rule, in
`docs/app/claude-app-settings.json`:

```text
Read(//d/Run-Performance-Project/docs/app/permission-canary/MAIN-CANARY.md)
```

There is deliberately **no** project-relative rule and **no** worktree rule for
this path. That single-rule design is the whole point: if a session running in
the **main repository checkout** is denied this file, the denial can only have
come from the repository-root absolute pattern above. Nothing else matches.

An earlier canary carried three overlapping rules at once, so a denial proved
only that *some* rule fired — not which one. This file and its worktree
counterpart replace that ambiguous design.

## How it is used

`docs/app/CLAUDE-CODE-SETUP.md` is the procedure. In short: a main-repository
session asks Claude to read this file by its exact absolute path, using the
built-in Read tool only. Denial before any content is returned is a pass.

The matching fixture for worktree sessions is `WORKTREE-CANARY.md`, which
carries the `worktrees/*/` wildcard rule and nothing else.

## Rules for maintainers

- Never delete this file or its rule; the verification step stops working.
- Never add a second rule matching this path. A second rule destroys the
  isolation and makes any denial unattributable again.
- If the rule shape used for real protected paths changes, change this canary's
  rule the same way, or it stops proving anything about them.

## Synthetic filler

Canary marker: `SYNTHETIC-CANARY-MAIN-DO-NOT-COPY`.

If this text is ever visible in a Claude Code transcript, the main-repository
absolute deny rule is not in effect and the session must be stopped.
