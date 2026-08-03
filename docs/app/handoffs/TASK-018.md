Task: TASK-018 Streamlit dashboard auto-refresh

Writer: ChatGPT

Branch/worktree: `fix/TASK-018-streamlit-auto-refresh` / `D:\Run-Performance-Project`

Commit SHA: `677af88`

Changed files:

- `garmin/scripts/dashboard.py`
- `docs/app/tasks/TASK-018-streamlit-auto-refresh.md`

Acceptance criteria:

- The dashboard registers a Streamlit fragment with a 60-second interval.
- The scheduled fragment clears cached data and requests a full-app rerun.
- A monotonic timestamp prevents ordinary reruns from causing a refresh loop.
- The sidebar caption now states the actual 60-second auto-refresh behavior.
- No protected health data, secret, or real-athlete fixture was added.

Commands run and results:

- `garmin\.venv\Scripts\python.exe -m py_compile garmin\scripts\dashboard.py`
  — passed.
- `garmin\.venv\Scripts\python.exe -m unittest discover -s garmin\tests -p
  "test_*.py"` — passed, 14 tests.
- Isolated AST/mock timing check at 0, 30, and 60 seconds — passed; cache clear
  and full-app rerun occurred only at 60 seconds.
- `git diff --check` — passed (Git reported only the repository's expected
  LF-to-CRLF working-copy warning).

Privacy/security impact:

- Refresh scheduling only. No health value is logged, copied, or added to a
  fixture or artifact. Verification did not open or inspect production records.

Known limitations:

- Automatic refresh requires an active Streamlit browser session. Browser or OS
  background throttling may delay a timer while the device is suspended.
- No browser session was opened during automated verification to avoid loading
  live athlete records into test output or artifacts.

Rollback:

- Revert implementation commit `677af88`. This removes the timer, restores the
  previous caption, and leaves collection/scheduled-task behavior unchanged.

Reviewer findings remaining: None; Product Owner approval is still required before
merge.
