# TASK-018: Streamlit dashboard auto-refresh

Status: Complete

Writer: ChatGPT (sole writer)

Reviewers: Product Owner

## Goal and user value

Keep the live Streamlit dashboard current while it remains open by refreshing the
full page automatically every 60 seconds.

## In scope

- Add a 60-second `st.fragment(run_every=...)` timer to the legacy Streamlit
  dashboard.
- Clear cached dashboard loaders before each automatic full-app rerun so values
  can reflect the latest database state.
- Update the refresh caption to state the actual 60-second behavior.

## Out of scope

- Changes to Garmin collection or scheduled-task cadence.
- Changes to dashboard metrics, health-data logic, or layout.
- Deployment or production-data operations.

## Owned paths

- `garmin/scripts/dashboard.py`
- `docs/app/tasks/TASK-018-streamlit-auto-refresh.md`
- `docs/app/handoffs/TASK-018.md`

## Forbidden paths

- `athletes/`
- `team_data/`
- all other paths under `garmin/`
- `scripts/`
- root `supabase/`
- `platform/`

## References

- Product Owner decision in the active request: option (a), automatic refresh
  every 60 seconds.
- `AGENTS.md`
- `docs/app/AI-WORKING-AGREEMENT.md`

## Acceptance criteria

- [x] An open dashboard schedules an automatic refresh every 60 seconds with
  `st.fragment(run_every=...)`.
- [x] Each scheduled refresh clears Streamlit data caches and reruns the full app.
- [x] Ordinary app reruns do not create an immediate refresh loop.
- [x] The sidebar caption accurately describes the 60-second auto-refresh.
- [x] No protected health data, secret, or real-athlete fixture is added.

## Privacy classification

No new user data is handled. The change only controls refresh timing and uses no
fixture or logged health value.

## Verification

```text
garmin\.venv\Scripts\python.exe -m py_compile garmin\scripts\dashboard.py
garmin\.venv\Scripts\python.exe -m unittest discover -s garmin\tests -p "test_*.py"
git diff --check
```

## Dependencies and open decisions

- The installed Streamlit runtime is 1.59.2 and supports `st.fragment` with
  `run_every` and full-app `st.rerun`.
- Product Owner selected automatic refresh over manual-only refresh.

## Required handoff

- Clean commit SHA
- Changed files
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
