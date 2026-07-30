# TASK-015: Garmin low-latency sync

Status: Ready for review

Writer: ChatGPT/Codex

Reviewers: Product Owner

## Goal and user value

Reduce the delay between an athlete syncing a completed activity to Garmin Connect
and that activity becoming visible in the local Garmin database, while preserving
the existing full wellness/detail sync and its recovery behavior.

## In scope

- Add a lightweight activity-only sync path for frequent polling.
- Run independent athlete sync subprocesses concurrently with a small,
  configurable worker limit.
- Add a hidden Windows launcher and Scheduled Task definition for the fast path.
- Preserve the existing twice-daily full sync, weekly reconcile, and deep sync.
- Add synthetic automated tests for orchestration and fast-mode behavior.
- Update legacy Garmin operating documentation.

## Out of scope

- Garmin Developer Program, webhooks, OAuth application integration, or changes to
  the new mobile app.
- Reading or modifying production tokens, the Garmin SQLite database, sync status,
  logs, environment files, or athlete records.
- Changing health-data fields, coaching logic, dashboard behavior, or Notion/LINE
  integration.
- Installing dependencies or upgrading `garminconnect`.
- Deploying or merging.

## Owned paths

- `garmin/scripts/fetch_all.py`
- `garmin/scripts/03_backfill.py`
- `garmin/scripts/notify_sync.ps1`
- `garmin/tests/`
- `garmin/garmin-fast-sync-auto.bat`
- `garmin/garmin-fast-sync-hidden.vbs`
- `scripts/setup_scheduled_tasks.ps1`
- `CLAUDE.md` (Garmin operations section only)
- `docs/app/tasks/TASK-015-garmin-low-latency-sync.md`

## Forbidden paths

- `platform/`
- `athletes/`
- `team_data/`
- `garmin/tokens/`
- `garmin/data/`
- root `supabase/`
- environment files, logs, database files, and credentials

## References

- Root `AGENTS.md`
- `docs/app/AI-WORKING-AGREEMENT.md`
- Existing Garmin operations section in `CLAUDE.md`
- Product Owner's explicit instruction in the active task

## Acceptance criteria

- [x] A frequent fast sync fetches the current activity list without fetching
      wellness, extras, activity detail, weather, or splits.
- [x] Fast sync never erases enriched data already stored by a full sync.
- [x] Full sync behavior remains backward-compatible.
- [x] All-athlete orchestration supports bounded concurrency, isolates a failed or
      timed-out athlete, and writes one deterministic aggregate status.
- [x] The scheduler source defines a hidden fast sync every 15 minutes and retains
      the existing 08:00 and 21:00 full sync.
- [x] No overlapping instance of the fast/full Garmin scheduled task can run.
- [x] Tests use synthetic slugs and in-memory/mock storage only.
- [x] No `platform/` file is changed.

## Privacy classification

The production feature processes protected health data, but implementation and
tests must use synthetic data only. No production token, database, log, status
file, athlete name, or measurement may be read or printed.

## Verification

```text
garmin\.venv\Scripts\python.exe -m unittest discover -s garmin\tests -v
garmin\.venv\Scripts\python.exe -m py_compile garmin\scripts\fetch_all.py garmin\scripts\03_backfill.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_scheduled_tasks.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_scheduled_tasks.ps1 -TaskName Run-Performance-Garmin-Fast -DryRun
git diff --check
git status --short
```

## Dependencies and open decisions

- The fast path uses the existing pinned `garminconnect` dependency.
- Fifteen minutes is the initial polling interval. Garmin Connect is an
  unofficial upstream for this legacy integration and publishes no contractual
  freshness or rate-limit guarantee.
- Installing the Scheduled Task changes live machine state and is performed only
  after Product Owner approval.

## Required handoff

- Changed files
- Verification commands and results
- Privacy/security impact
- Known limitations
- Rollback instructions
