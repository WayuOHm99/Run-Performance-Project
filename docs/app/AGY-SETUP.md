# Google Antigravity (`agy`) Setup

Status: **Active**

This project uses Antigravity as a free development control plane and independent
reviewer. It is not a runtime dependency of the mobile app.

## Project setup

1. Open or create an Antigravity Project for the repository root.
2. Keep non-workspace file access disabled.
3. Keep terminal commands on Request Review.
4. Keep artifact actions on Request Review.
5. Enable the workspace rule `.agents/rules/app-engineering.md` as **Always On**.
6. Use New Worktree Mode for implementation or any review that may overlap another
   writer.

Do not enable paid `/teamwork-preview`. Normal Rules, Workflows, and isolated
subagents are sufficient for this project.

## Repository customizations

```text
.agents/
  rules/app-engineering.md
  workflows/feature-cycle.md
  agents/app-reviewer.md
```

- Run `/feature-cycle` for one approved task.
- Use `app-reviewer` only after the writer or main runner supplies changed files and
  verification evidence.
- Use the built-in browser reviewer later for synthetic UI/E2E flows.

## Safe CLI review

The CLI may start from its own scratch directory in headless mode. Add the absolute
repository directory explicitly:

```powershell
agy --add-dir "D:\Run-Performance-Project" --mode plan --sandbox -p "<review prompt>"
```

The read-only reviewer intentionally has no command or write tools. The writer or
main AGY runner executes task verification before delegating review.

## Recommended permission shape

In the local Antigravity CLI settings, allow reading this exact repository for
headless review, then add more-specific deny rules for real data:

```json
{
  "permissions": {
    "allow": [
      "read_file(D:/Run-Performance-Project)"
    ],
    "deny": [
      "read_file(D:/Run-Performance-Project/athletes)",
      "read_file(D:/Run-Performance-Project/team_data)",
      "read_file(D:/Run-Performance-Project/garmin/data)",
      "read_file(D:/Run-Performance-Project/garmin/tokens)",
      "read_file(D:/Run-Performance-Project/scripts/.env)",
      "write_file(D:/Run-Performance-Project/athletes)",
      "write_file(D:/Run-Performance-Project/team_data)",
      "write_file(D:/Run-Performance-Project/garmin)",
      "write_file(D:/Run-Performance-Project/scripts)",
      "write_file(D:/Run-Performance-Project/supabase)"
    ]
  }
}
```

Antigravity evaluates `Deny` before `Ask` and `Allow`, so the sensitive subpaths
remain inaccessible even though repository documentation and app source can be
reviewed.

Do not add `command(*)`, `write_file(*)`, `read_file(*)`, or
`--dangerously-skip-permissions`.

## Review prompt

```text
Review the active docs/app/tasks/TASK-###.md and supplied changed files read-only.
Check acceptance criteria, forbidden paths, role ownership, privacy, authorization,
tests, and rollback. Do not edit, deploy, access production data, or change scope.
Return findings by severity.
```
