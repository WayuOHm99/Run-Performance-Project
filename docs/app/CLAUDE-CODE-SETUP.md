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
7. Run the canary check for the kind of session you are in — see below. Claude
   must report that the operation is denied **before any content is returned**.

If a canary can be read, stop the session without working and correct the launch
command. If `/memory` shows the root `CLAUDE.md`, stop as well.

### Verify with a canary, never with a real protected file

Step 7 deliberately targets a **synthetic** file. The old procedure asked Claude
to read the root `CLAUDE.md`, which has an obvious flaw: when the rules are
wrong, the check itself exposes the content it exists to protect. That is
precisely how the TASK-010 incident happened.

Neither canary holds athlete data, coaching context, or any secret.

#### One canary per rule shape, one rule per canary

There are **two** canaries, and each is matched by **exactly one** deny rule:

| Session kind    | File to request                                | The only rule that can deny it                                                                     |
| --------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Main repository | `docs/app/permission-canary/MAIN-CANARY.md`    | `Read(//d/Run-Performance-Project/docs/app/permission-canary/MAIN-CANARY.md)`                       |
| Worktree        | `docs/app/permission-canary/WORKTREE-CANARY.md` | `Read(//d/Run-Performance-Project/.claude/worktrees/*/docs/app/permission-canary/WORKTREE-CANARY.md)` |

**This isolation is the entire design, and it must not be eroded.** An earlier
single `CANARY.md` carried three overlapping rules at once — project-relative,
repository-root absolute, and the worktree wildcard. A denial proved only that
*some* rule had fired. In particular, a worktree session requesting it by a
project-relative path could have been denied by the project-relative rule, so
the check could not demonstrate that the `worktrees/*/` wildcard resolved at all
— which was the one thing the TASK-010 incident made it necessary to prove.

So: **never add a project-relative or second absolute rule for either canary.**
A denial must remain attributable to exactly one pattern.

**Expected consequence — do not mistake this for a failure.** Because each
canary has only its own rule, each is *readable from the other kind of session*:
a worktree session can read `MAIN-CANARY.md`, and a main-repository session can
read `WORKTREE-CANARY.md`. That is the design working correctly, not a hole. Run
only the row that matches your session, and judge the result on that row alone.

#### How to run the check

Ask Claude to read the file **by its exact absolute path**, not a
project-relative one, so the request cannot be satisfied by a rule you did not
intend to test:

```text
Main repository session:
  D:\Run-Performance-Project\docs\app\permission-canary\MAIN-CANARY.md

Worktree session (substitute the current worktree name):
  D:\Run-Performance-Project\.claude\worktrees\<name>\docs\app\permission-canary\WORKTREE-CANARY.md
```

Constraints on the check itself:

- **Built-in `Read` tool only.**
- **No Bash, PowerShell, `grep`, `cat`, or any other fallback**, and no retry
  through a different path form. A fallback that succeeds tells you nothing
  about the Read rules and defeats the check.
- A **pass** is a denial returned **before any file content**. Partial content
  followed by a refusal is a **failure**.

A denied worktree canary shows that the settings file is loaded, that the
absolute-path syntax is right for this machine, and that the `worktrees/*/`
wildcard resolves. Because the protected paths use the identical rule shape,
that is evidence for them — established without ever requesting a protected
file. It remains shape evidence, not a per-path test: the real protected paths
are deliberately never requested.

Never delete either canary or its rule, and if the rule shape for protected
paths changes, change the canary rules the same way or they stop proving
anything.

## Claude chat without Claude Code

For a read-only second opinion, provide only:

- the relevant `docs/app/` files;
- a task packet;
- synthetic screenshots or fixtures.

Never upload the root `CLAUDE.md`, athlete directories, Garmin screenshots,
database exports, or real check-in/sleep/injury details.
