# AI Working Agreement

Status: **Active**

Date: 2026-07-27

## Operating model

Use **one decision lead, one writer per task, and independent reviewers**. AI tools
do not work as three simultaneous editors in the same checkout.

| Participant | Primary responsibility | Must not do by default |
|---|---|---|
| Product Owner | Approve scope, UX, release, and any production action | Delegate final health/safety judgment to AI |
| ChatGPT 5.6 sol | Product and architecture lead; write task packets, contracts, ADRs, RLS/security design; integrate and perform final review | Let another tool silently change scope or deploy |
| Claude Code | Default implementation engineer for a scoped feature; write code and tests; fix lint/type/build failures | Invent requirements, change an ADR, or deploy production |
| Claude chat | Optional read-only UX/copy challenger or second opinion | Edit the same branch as Claude Code |
| Google Antigravity (`agy`) | Free control plane for spec review, isolated worktrees, test execution, browser/UI verification, and security review | Be a second writer in an active implementation checkout |

ChatGPT may implement a task when its packet explicitly says `Writer: ChatGPT`.
Claude Code remains the preferred writer for isolated mobile feature tickets.
Antigravity is a reviewer by default and becomes a writer only when a task explicitly
assigns it an isolated worktree.

## Practical ownership map

| Workstream | Lead | Review |
|---|---|---|
| Product scope and acceptance criteria | ChatGPT | Product Owner |
| Architecture, contracts, privacy, and RLS | ChatGPT | Claude/AGY read-only review |
| Mobile screens and feature implementation | Claude Code | AGY UI/test review, then ChatGPT |
| Native health adapters | Assigned per task | ChatGPT security/privacy review |
| Automated test execution and browser evidence | AGY | ChatGPT |
| Merge, migration, and release approval | Product Owner | ChatGPT release checklist |

Dependency manifests, lockfiles, shared contracts, and database migrations have a
serial owner. Two tasks may not edit them concurrently.

## Source-of-truth split

- App requirements and engineering decisions: `docs/app/`
- App code: `platform/`
- Current coaching records: Notion and the existing Garmin database
- Training-plan writing style: `.agents/AGENTS.md`
- AI conversations: temporary discussion, not an approved decision record

## Feature cycle

1. **Specify** — ChatGPT creates or updates one task packet.
2. **Approve scope** — Product Owner confirms meaningful product choices.
3. **Review before build** — AGY or Claude checks feasibility read-only.
4. **Assign one writer** — use a dedicated branch/worktree.
5. **Implement** — writer changes only owned files and writes tests.
6. **Verify** — run format, lint, typecheck, tests, and relevant build/E2E checks.
7. **Independent review** — reviewer reports findings without editing implementation.
8. **Fix** — the original writer resolves accepted findings.
9. **Close** — ChatGPT checks acceptance criteria; Product Owner approves merge or
   deployment.

Use Antigravity's normal Rules, Workflows, and isolated subagents. Do not use the
paid `/teamwork-preview` workflow for this free-first project.

## Branch and worktree policy

- Branches: `feat/TASK-###-short-name`, `fix/TASK-###-short-name`
- One task packet maps to one implementation branch.
- Use Antigravity `New Worktree Mode` for parallel implementation or extensive
  review.
- Local mode is acceptable for a quick read-only review.
- Before handing off, the writer must provide a clean commit SHA.
- Never run two database migration writers in parallel.

## Task packet

Every task uses `docs/app/tasks/TASK-TEMPLATE.md` and records:

- goal and user value;
- in scope and out of scope;
- writer and reviewers;
- owned and forbidden paths;
- acceptance criteria;
- privacy classification;
- verification commands;
- dependencies and open decisions;
- output and rollback requirements.

## Handoff format

```text
Task:
Writer:
Branch/worktree:
Commit SHA:
Changed files:
Acceptance criteria:
Commands run and results:
Privacy/security impact:
Known limitations:
Rollback:
Reviewer findings remaining:
```

A handoff without a clean commit and verification evidence is incomplete.

## Human approval gates

The Product Owner must approve before:

- merging a feature branch;
- applying a remote database migration;
- using a service-role credential;
- sending notifications to real users;
- accessing, exporting, or deleting production athlete data;
- releasing to TestFlight, Google Play, or production;
- adding a paid service or exceeding a free-tier quota.

## Privacy rules for every AI

- Use synthetic users and synthetic measurements only.
- Do not paste real athlete names, email addresses, injuries, sleep, HR, GPS, tokens,
  or screenshots into AI prompts.
- Do not give an AI production database credentials or a Supabase service-role key.
- Reviewers start read-only.
- Any test that needs health data generates fixtures locally.
- Redact PII and health values from logs, crash reports, screenshots, and review
  artifacts.

## How the Product Owner talks to each tool

### ChatGPT

Ask for the next task, product decision, architecture, final review, or guided
implementation. ChatGPT owns the canonical sequence and should stop at the current
gate.

### Claude Code

Give it one approved task packet:

```text
Implement docs/app/tasks/TASK-###.md.
You are the only writer for this task. Stay inside the owned paths, run every
verification command, and return the handoff format from
docs/app/AI-WORKING-AGREEMENT.md. Do not deploy or change scope.
```

Launch it through `docs/app/CLAUDE-CODE-SETUP.md`. A plain Claude Code session at
the repository root loads the legacy coaching `CLAUDE.md`, which contains real
athlete context and is not appropriate for app engineering.

### Antigravity

Use `/feature-cycle` or invoke `app-reviewer`:

```text
Review docs/app/tasks/TASK-###.md and the current diff read-only.
Check acceptance criteria, scope creep, tests, privacy, and legacy-path safety.
Do not edit implementation files.
```
