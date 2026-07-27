# TASK-006: VS Code beginner workspace

Status: Complete

Writer: ChatGPT/Codex

Reviewer: AGY (`app-reviewer`, read-only)

## Goal and user value

Make the repository safer and easier to navigate for a first-time VS Code user
through small workspace-only defaults, trusted extension recommendations, and a
Thai quickstart without changing application or legacy behavior.

## In scope

- Add root workspace settings for formatting, ESLint, line endings, TypeScript,
  generated-folder visibility, terminal location, and conservative Git actions.
- Set Claude Code's initial permission mode to Plan.
- Recommend the minimal trusted extensions used by this workflow.
- Mark Live Server as unwanted for this Expo workspace.
- Install ESLint and Expo Tools in the local editor.
- Add a concise Thai beginner guide.

## Out of scope

- Changing user-wide VS Code settings.
- Removing or disabling an installed extension.
- Editing application, backend, dependency, lockfile, or legacy code.
- Opening Claude or starting an AI implementation session.
- Pushing, merging, deploying, or connecting to Supabase.

## Owned paths

- `.vscode/settings.json`
- `.vscode/extensions.json`
- `docs/app/VS-CODE-QUICKSTART.md`
- `docs/app/tasks/TASK-006-vscode-workspace.md`
- `docs/app/reviews/TASK-006-AGY.md`
- Local VS Code extension installation state (not committed)

## Forbidden paths

- `platform/apps/mobile/.env.local`
- `athletes/`
- `team_data/`
- `garmin/`
- `scripts/`
- root `supabase/`
- `CLAUDE.md`
- `.agents/AGENTS.md`
- `.claude/settings.json`
- `.claude/settings.local.json`

## References

- `AGENTS.md`
- `platform/AGENTS.md`
- VS Code settings and extension-recommendation documentation
- Expo Tools documentation
- Claude Code VS Code documentation

## Acceptance criteria

- [x] Workspace JSON files parse successfully.
- [x] Format-on-save is limited to the app's text languages.
- [x] ESLint resolves from `platform/apps/mobile/`.
- [x] Workspace TypeScript resolves from
      `platform/apps/mobile/node_modules/typescript/lib`, the verified location
      for this pnpm installation.
- [x] New terminals start in `platform/`.
- [x] Generated dependency/build folders are hidden from Explorer, search, and
      file watching without hiding legacy source folders.
- [x] Git sync and destructive file actions retain confirmation prompts.
- [x] Claude Code starts in Plan mode.
- [x] Recommendations include ESLint, Prettier, Expo Tools, Claude Code, ChatGPT,
      Gemini Code Assist, and Markdownlint.
- [x] ESLint and Expo Tools are installed locally.
- [x] No app, backend, dependency, lockfile, environment, or legacy path changes.
- [x] AGY returns no blocker, high, or medium finding.

## Privacy classification

No user or health data. No environment or credential file is read or modified.

## Verification

```powershell
Get-Content -Raw .vscode/settings.json | ConvertFrom-Json | Out-Null
Get-Content -Raw .vscode/extensions.json | ConvertFrom-Json | Out-Null
code --list-extensions
git diff --check
git status --short
```

Run the existing app quality gates from `platform/` to ensure editor configuration
does not alter project behavior:

```powershell
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
```

## Dependencies and open decisions

- Docker and SQL tooling will be considered only when the backend task needs them.
- The first Claude implementation task remains the Athlete Today vertical slice
  after backend contracts and RLS are established.

## Required handoff

- Clean commit SHA
- Changed files
- Installed extension IDs
- Verification results
- Known limitations
- Rollback instructions
