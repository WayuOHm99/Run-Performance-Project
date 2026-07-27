# Permission Canary

Status: **Active** — this file is a test fixture, not documentation.

## What this is

Synthetic bait. This file exists so the protected-read check in
`docs/app/CLAUDE-CODE-SETUP.md` can be verified **without reading a real
protected file**.

It contains no athlete data, no coaching context, no credential, and no secret.
Nothing here is sensitive, and nothing here should ever be treated as a source
of truth.

## Why it exists

The verification step used to ask Claude to read the root `CLAUDE.md`. That has
an obvious flaw: if the deny rules are wrong, the check itself exposes the very
content it is meant to protect. That is exactly what happened during TASK-010 —
five lines of the worktree copy of `CLAUDE.md` were returned before the read was
stopped, because the deny rules covered only repository-root absolute paths and
not `.claude/worktrees/**`.

A canary removes that risk. Its deny rules are written in the **same shape** as
the real ones, including the `worktrees/*/` wildcard:

```text
Read(//d/Run-Performance-Project/docs/app/permission-canary/CANARY.md)
Read(//d/Run-Performance-Project/.claude/worktrees/*/docs/app/permission-canary/CANARY.md)
```

So a denial here demonstrates three things at once:

1. the settings file is actually loaded in this session;
2. the absolute-path rule syntax is correct for this repository;
3. the `worktrees/*/` wildcard resolves the way the protected-path rules assume.

If the canary is denied, the identically-shaped `CLAUDE.md` rules are denied
too. If the canary can be read, the deny rules are **not** in force, and the
session must be stopped and relaunched before any protected path is touched.

## Rules

- Never delete this file or its deny rules; the verification depends on both.
- Never put real content in it. Its only job is to be unreadable.
- If you change the rule shape for protected paths, change it here in the same
  way, or the canary stops proving anything.
