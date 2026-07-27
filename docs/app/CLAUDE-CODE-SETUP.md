# Claude Code App Setup

Status: **Active**

## Why app sessions are isolated

The repository root `CLAUDE.md` is the live coaching brain. It contains athlete
context and gives Claude a sports-science role. Loading it during mobile app
development would:

- send unnecessary real-athlete context into an engineering session;
- mix coaching instructions with software requirements;
- make the shared app rules less reliable.

Claude Code normally discovers `CLAUDE.md` files from the current directory and
its ancestors. App work must therefore use the dedicated settings file
`docs/app/claude-app-settings.json`, which excludes all `CLAUDE.md` files, disables
auto memory, denies sensitive reads and legacy edits, blocks the existing Notion and
Supabase MCPs, and blocks push/deploy commands.

The deny list contains both project-relative paths and absolute Windows paths.
The absolute entries currently target `D:\Run-Performance-Project`. If the
repository moves, update every `//d/Run-Performance-Project/...` entry before
starting Claude Code, then repeat the protected-read check below.

`//d/...` is intentional Claude Code permission syntax. Claude Code normalizes
native Windows paths such as `D:\...` to POSIX form and requires a double slash
for a filesystem-root absolute rule.

### Worktrees need their own rules

**A worktree is a full checkout, so it has its own copy of every protected
file**, including `CLAUDE.md`, at
`.claude/worktrees/<name>/CLAUDE.md`. An absolute rule written for the
repository root does **not** match that path.

This was a real incident, not a hypothetical: during TASK-010 the protected-read
check returned five lines of the worktree copy of `CLAUDE.md` because only
repository-root paths were denied. Auto-loading was still prevented — the
`claudeMdExcludes` glob covers every copy — but the read rule did not fire.

Every protected path therefore has three deny entries: the project-relative
form, the repository-root absolute form, and a worktree form using a single
wildcard for the worktree name:

```text
Read(//d/Run-Performance-Project/.claude/worktrees/*/CLAUDE.md)
```

The wildcard is deliberately `*` and not `**`. A worktree rule must be anchored
at the worktree root so it matches root `supabase/` and `scripts/` without also
matching the legitimate `platform/supabase/`, which app tasks own and must be
able to edit.

### Settings are read at launch, not live

Claude Code loads `--settings` when the session starts. **Editing the settings
file during a session does not change that session's permissions.** After any
change to the deny list, exit and relaunch before relying on it, and re-run the
check below. A session cannot validate its own settings edits.

On native Windows these rules protect Claude's built-in Read and Edit tools, but
Claude Code's OS-level shell sandbox is unavailable. Review every proposed shell
command before approval. For unattended or higher-assurance sessions, run the
same workflow inside WSL2 with the Claude sandbox enabled.

## Required launch pattern

Start from the repository root. Use one isolated Git worktree per task:

```powershell
$repoPath = (Resolve-Path -LiteralPath '.').Path
$appSettings = Join-Path $repoPath 'docs\app\claude-app-settings.json'

claude -w "task-###-short-name" `
  --setting-sources user,project `
  --settings $appSettings `
  --permission-mode default `
  "Read AGENTS.md, docs/app/PRODUCT-CHARTER.md,
  docs/app/AI-WORKING-AGREEMENT.md, and docs/app/tasks/TASK-###.md.
  You are the only writer for this task. Implement only its owned paths,
  run its verification commands, and return the required handoff.
  Do not deploy or change scope."
```

Why each option exists:

- `-w`: creates an isolated worktree. Ignored production data is not copied there.
- `--setting-sources user,project`: loads shared app rules while the additional
  settings exclude the legacy `CLAUDE.md`.
- `--settings`: applies the app-specific privacy and deployment denials.
- `--permission-mode default`: reads are automatic, while writes and commands still
  require review unless narrowly allowed.

Never use `--dangerously-skip-permissions`, bypass mode, or auto mode for this
project.

## Verify before the first implementation

In the Claude Code session:

1. Run `/memory`.
2. Confirm the root coaching `CLAUDE.md` is not loaded.
3. Confirm `.claude/rules/app-engineering.md` is available.
4. Run `/permissions`.
5. Confirm sensitive `Read(...)`, legacy `Edit(...)`, production MCP, push, and
   deployment rules appear under Deny.
6. Confirm the deny list contains `worktrees/*/` entries, and that they name the
   current worktree's location.
7. Ask Claude to read `docs/app/permission-canary/CANARY.md`. It must report
   that the operation is denied without revealing file contents.

If the canary can be read, stop the session without working and correct the
launch command. If `/memory` shows the root `CLAUDE.md`, stop as well.

### Verify with the canary, never with a real protected file

Step 7 deliberately targets a **synthetic** file. The old procedure asked Claude
to read the root `CLAUDE.md`, which has an obvious flaw: when the rules are
wrong, the check itself exposes the content it exists to protect. That is
precisely how the TASK-010 incident happened.

`docs/app/permission-canary/CANARY.md` holds no athlete data, no coaching
context, and no secret, and its deny rules are written in the **same shape** as
the protected ones — including the `worktrees/*/` wildcard. A denial therefore
proves three things at once:

1. the settings file is actually loaded in this session;
2. the absolute-path rule syntax is correct for this machine;
3. the `worktrees/*/` wildcard resolves as the protected-path rules assume.

Because the shapes match, a denied canary means the `CLAUDE.md` rules are denied
too — established without ever requesting a protected file. Never delete the
canary or its rules, and if the rule shape for protected paths changes, change
the canary's rules the same way or it stops proving anything.

## Claude chat without Claude Code

For a read-only second opinion, provide only:

- the relevant `docs/app/` files;
- a task packet;
- synthetic screenshots or fixtures.

Never upload the root `CLAUDE.md`, athlete directories, Garmin screenshots,
database exports, or real check-in/sleep/injury details.
