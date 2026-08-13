# Run Performance — Current State

Last updated: 2026-08-13

## Goal
Garmin → Python Sync → SQLite → Streamlit Dashboard

Primary goals:
- Reduce athlete screenshot/manual reporting.
- Reduce coach system-maintenance work.
- Keep the system simple, reliable, and low-maintenance.
- Data stale != system failure.

## Production
- Repository: WayuOHm99/Run-Performance-Project
- Default branch: main
- Local path: D:\Run-Performance-Project
- Tests: discovered dynamically by unittest/CI (the total is intentionally not hard-coded)
- GitHub CI: passing

## Core System
- Garmin Connect → Garmin Cloud
- Python sync
- SQLite
- Streamlit Dashboard

## Automated Jobs
- Full Sync: 08:00 / 21:00
- Fast Sync
- Wellness Sync
- Reconcile
- DeepSync
- Backup: 22:00
- Encrypted Off-device Backup: 22:30
- Restore Drill: every 4 weeks
- Privacy-safe System Heartbeat: every 2 hours
- Full Sync catch-up enabled if computer was off
- Catch-up lookback: 48 hours

## Monitoring / Safety
- SQLite WAL
- Automated local backup
- Restic off-device backup to a private GitHub Release; only verified local backup generations are accepted.
- Restore drills download the off-device repository, restore it, and run SQLite `quick_check`.
- GitHub Actions checks a privacy-safe aggregate heartbeat hourly; athlete findings never leave the machine.
- Healthchecks.io monitors Backup
- GitHub Actions CI
- Production data/tokens are not committed to Git
- Field-level data-quality monitoring is read-only and uses Asia/Bangkok calendar boundaries.
- `check_drift.py` reports 30-day coverage per field, compares both 30-day and 7-day windows, and detects partial completed-day snapshots.
- Health reporting also surfaces per-athlete core-field coverage, sentinel/range violations, and invalid field relationships such as Body Battery high below low.

## Important Recent Changes
- 2026-08-13 — Off-device durability and external monitoring
  - Restic snapshots use DPAPI CurrentUser locally and a GitHub Actions recovery secret; no plaintext password file exists.
  - The encrypted repository retains 7 daily, 8 weekly, and 12 monthly snapshots; the release keeps the newest 3 repository archives.
  - A guarded manual workflow verifies the asset digest, restores the latest snapshot, and validates SQLite; uploading the private 7-day recovery artifact is explicit opt-in.
  - `health_report.py` treats missing, failed, or stale off-site backup/restore proof as an error; the published heartbeat contains counts only.

- 2026-08-09 — Wellness/recovery correctness hardening
  - Fast wellness can repair yesterday's late Garmin Cloud snapshot, with a six-hour per-athlete/day cooldown.
  - Full/deep wellness upserts preserve existing values when an endpoint temporarily returns no value.
  - Training Readiness selects the newest timestamped snapshot, preserves score `0`, and stores source context/timestamps.
  - Recovery Time is stored and migrated as Garmin minutes (`recovery_time_min`); the dashboard formats hours/minutes and honors `REACHED_ZERO`.
  - Today/Team/Recovery select latest values per field, disclose sample counts, include finalized overnight Sleep/RHR, exclude unfinished intraday aggregates such as BB-high/Stress, and do not create empty Plotly traces or bridge missing days.
  - Read-only monitoring reports calendar-day coverage/drift (including missing/empty whole-day snapshots), partial snapshots, invalid ranges/relations, and uses Asia/Bangkok day boundaries.
  - Device model/capability inventory is refreshed only during full extras sync; identifiers are not exposed in UI/logs.

- `9a9b810` — Athlete wellness Data Freshness
  - 🟢 updated today
  - 🟠 waiting for upstream Garmin sync
  - 🔴 stale / no data

- `0b41023` — Preserve short Garmin splits
  - Garmin watch laps may be shorter than 100 m
  - Dashboard must not filter valid short laps or hide a whole activity by total distance
  - Session detail includes every recorded activity; zero-distance activities remain viewable even when splits do not apply
  - Splits UI now treats them as laps/splits, not kilometers
  - Do not reintroduce a minimum-distance activity/split filter

## Current Rules
- Diagnose root cause before changing code.
- Prefer minimal fixes.
- Do not overengineer.
- Do not change sync/schema/scheduler/backup unless required.
- Do not add infrastructure without a real operational need.
- Check GitHub for current repository facts before making claims.
- Real pipeline failures and stale upstream Garmin data are separate issues.
- Preserve existing working behavior when fixing bugs.

## Known Notes
- Some Garmin activities may contain 0 m laps.
- Currently preserve them as Garmin recorded them.
- If they become a UX problem, suppress only zero-distance laps specifically.
- Never use a general minimum-distance threshold again.

## Deferred
- Cloud/VPS migration
- Sentry / additional monitoring
- Larger infrastructure changes

Only revisit these when there is a real operational need.

## Current Priority
Use the system in production and observe real-world behavior.

Fix confirmed bugs when found.
Avoid adding features simply to improve an abstract system score.
