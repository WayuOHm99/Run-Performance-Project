# TASK-015 handoff

Task: TASK-015 Garmin low-latency sync

Writer: ChatGPT/Codex

Branch/worktree: `feat/mobile-foundation` / `D:\Run-Performance-Project`

Commit SHA: `716e0045aa3e7339da1e3340a2d38ea450820d6d`

Changed files:

- `garmin/scripts/fetch_all.py`
- `garmin/scripts/03_backfill.py`
- `garmin/scripts/notify_sync.ps1`
- `garmin/garmin-fast-sync-auto.bat`
- `garmin/garmin-fast-sync-hidden.vbs`
- `garmin/tests/test_fast_sync.py`
- `scripts/setup_scheduled_tasks.ps1`
- `CLAUDE.md`
- `docs/app/tasks/TASK-015-garmin-low-latency-sync.md`

Acceptance criteria:

- Fast polling fetches only today's activity summaries.
- Full sync still fetches activity enrichment, splits, wellness, extras, and
  reconciliation.
- Fast upserts preserve non-null enrichment from previous full syncs.
- Three athlete accounts can sync concurrently; completion is aggregated in a
  deterministic order.
- A cross-task file lock prevents fast/full/reconcile overlap. Fast polling skips
  a collision; full jobs wait up to ten minutes.
- `Run-Performance-Garmin-Fast` is installed, ready, hidden, set to every 15
  minutes, and configured with `MultipleInstances=IgnoreNew`.
- No `platform/` file changed.

Commands run and results:

- `garmin\.venv\Scripts\python.exe -m unittest discover -s garmin\tests -v`
  — 3 tests passed.
- `garmin\.venv\Scripts\python.exe -m py_compile
  garmin\scripts\fetch_all.py garmin\scripts\03_backfill.py` — passed.
- `powershell -NoProfile -ExecutionPolicy Bypass -File
  scripts\setup_scheduled_tasks.ps1 -TaskName
  Run-Performance-Garmin-Fast -DryRun` — one selected task validated.
- `git diff --check` — passed.
- Encoding check — modified `.ps1` files retain UTF-8 BOM; the new `.bat` is
  ASCII-only.
- Read-only Scheduled Task inspection — state `Ready`, interval `PT15M`, action
  `wscript.exe` with the repository fast launcher, `MultipleInstances=IgnoreNew`.

Privacy/security impact:

- Tests use synthetic activity IDs, dates, slugs, and measurements in an in-memory
  database or mocks.
- No production token, database, status file, log, environment file, or athlete
  record was read for implementation or verification.
- The installed task will use the existing protected legacy credentials and
  database when Windows runs it; no credential format or storage changed.

Known limitations:

- Freshness begins only after the watch/phone has uploaded the activity to Garmin
  Connect. This legacy integration cannot accelerate the device-to-cloud step.
- Polling latency is up to 15 minutes plus the short fetch runtime.
- The fast path covers the computer's current calendar day. An activity uploaded
  after midnight may wait for the next full sync.
- Garmin Connect is accessed through an unofficial library and has no contractual
  freshness or rate-limit guarantee. Existing retry/backoff remains in place.
- The real task was not manually started during verification to avoid an
  unapproved read of production tokens and health data. Its first scheduled run
  provides the operational proof.

Rollback:

1. Disable or unregister `Run-Performance-Garmin-Fast`.
2. Revert implementation commit
   `716e0045aa3e7339da1e3340a2d38ea450820d6d`.
3. The original `Run-Performance-Garmin` 08:00/21:00 full sync remains intact and
   requires no database rollback or migration.

Reviewer findings remaining:

- Product Owner review is pending.
- Confirm the first scheduled run completes without a rate-limit or lock warning
  before considering TASK-015 closed.
