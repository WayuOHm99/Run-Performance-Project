// The synthetic baseline, decision 8.
//
// Exactly two accounts, one team, one active athlete membership, one active
// coach membership. Zero sharing grants and zero check-ins, decision 9.
//
// `example.test` is reserved by RFC 6761 for testing and can never be delivered
// to, so a stray local email cannot reach a real inbox. The names are
// deliberately role labels rather than anything resembling a person.
//
// Roles here are documentation of what the fixture creates. The application
// reads roles only from `public.team_memberships` under RLS, never from this
// file, from Auth metadata, or from a JWT claim.

export const ATHLETE_EMAIL = "athlete-a@example.test";
export const COACH_EMAIL = "coach-a@example.test";

export const ATHLETE_DISPLAY_NAME = "Athlete A";
export const COACH_DISPLAY_NAME = "Coach A";

export const DEMO_TEAM_NAME = "Demo Team A";

// A fixed synthetic UUID, so a reset is deterministic and the fixture is
// idempotent. Version-4 shaped but not random: it is a constant, not a secret.
export const DEMO_TEAM_ID = "00000000-0000-4000-8000-000000000017";

export const DEMO_ACCOUNTS = Object.freeze([
  Object.freeze({
    email: ATHLETE_EMAIL,
    displayName: ATHLETE_DISPLAY_NAME,
    role: "athlete",
  }),
  Object.freeze({
    email: COACH_EMAIL,
    displayName: COACH_DISPLAY_NAME,
    role: "coach",
  }),
]);

// The exact baseline a reset must produce. `demo:verify` compares scalar counts
// against this object and nothing else.
export const EXPECTED_BASELINE = Object.freeze({
  auth_users: 2,
  example_test_users: 2,
  profiles: 2,
  named_profiles: 2,
  teams: 1,
  active_memberships: 2,
  active_athlete_memberships: 1,
  active_coach_memberships: 1,
  sharing_grants: 0,
  daily_check_ins: 0,
});
