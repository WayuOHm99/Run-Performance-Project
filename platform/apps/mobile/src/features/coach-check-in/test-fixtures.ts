/**
 * Synthetic fixtures and the injected Supabase double for the TASK-016 tests.
 *
 * **Every value here is invented.** No real athlete, team, coach, display name, or
 * recorded check-in appears in this repository, and none may be added: decision 10
 * restricts this task to local Supabase and synthetic fixtures.
 *
 * The identifiers are deliberately shaped like UUIDs but are obviously fabricated,
 * and every assertion that has to mention one maps it through `LABELS` first, so a
 * failing test prints `team-a` rather than an identifier.
 *
 * The client double records **table names and method names only**. It never records
 * a response body, so a test that asserts against the recording cannot print a
 * health value even when it fails. The write methods exist on it precisely so
 * "nothing in this feature ever calls one" is a counted fact rather than an
 * assumption — a double that lacked them would make a write throw a `TypeError`
 * and pass as a sanitized failure.
 *
 * Lives in the feature directory because it is TASK-016-owned. Like
 * `failure-probe.ts` it is test support: no runtime module imports it, and the
 * source scan's import-closure check is what proves that.
 */

import type { AppSupabaseClient } from "../../lib/supabase/app-client";

export const COACH_ID = "00000000-0000-4000-9000-000000000016";
export const OTHER_COACH_ID = "00000000-0000-4000-9000-000000000017";
export const TEAM_A = "00000000-0000-4000-8000-00000000000a";
export const TEAM_B = "00000000-0000-4000-8000-00000000000b";
export const TEAM_UNCOACHED = "00000000-0000-4000-8000-0000000000ff";
export const ATHLETE_1 = "00000000-0000-4000-9000-000000000001";
export const ATHLETE_2 = "00000000-0000-4000-9000-000000000002";

export const TEAM_A_NAME = "Alpha Runners";
export const TEAM_B_NAME = "Bravo Runners";
export const ATHLETE_1_NAME = "Athlete One";
export const ATHLETE_2_NAME = "Athlete Two";

/** Identifier → fixed label, so no identifier reaches a failure message. */
export const LABELS = new Map<unknown, string>([
  [COACH_ID, "coach-a"],
  [OTHER_COACH_ID, "coach-b"],
  [TEAM_A, "team-a"],
  [TEAM_B, "team-b"],
  [TEAM_UNCOACHED, "team-uncoached"],
  [ATHLETE_1, "athlete-1"],
  [ATHLETE_2, "athlete-2"],
]);

export function label(value: unknown): string {
  return LABELS.get(value) ?? "unknown";
}

// ---------------------------------------------------------------------------
// Row builders
// ---------------------------------------------------------------------------

export function membershipRow(overrides?: {
  readonly team_id?: unknown;
  readonly role?: unknown;
  readonly status?: unknown;
  readonly teams?: unknown;
}): unknown {
  return {
    team_id: TEAM_A,
    role: "coach",
    status: "active",
    teams: { name: TEAM_A_NAME },
    ...overrides,
  };
}

export function grantRow(overrides?: {
  readonly team_id?: unknown;
  readonly athlete_profile_id?: unknown;
  readonly data_category?: unknown;
}): unknown {
  return {
    team_id: TEAM_A,
    athlete_profile_id: ATHLETE_1,
    data_category: "check_in",
    ...overrides,
  };
}

/** A synthetic check-in. The three values are invented and in range. */
export function checkInRow(overrides?: {
  readonly check_in_date?: unknown;
  readonly rpe?: unknown;
  readonly overall_feeling?: unknown;
  readonly pain_status?: unknown;
}): unknown {
  return {
    check_in_date: "2026-07-30",
    rpe: 6,
    overall_feeling: 3,
    pain_status: "none",
    ...overrides,
  };
}

export function profileRow(overrides?: {
  readonly id?: unknown;
  readonly display_name?: unknown;
  readonly daily_check_ins?: unknown;
}): unknown {
  return {
    id: ATHLETE_1,
    display_name: ATHLETE_1_NAME,
    daily_check_ins: [checkInRow()],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// The injected client double
// ---------------------------------------------------------------------------

/** How one stage behaves. Exactly one field is set. */
export type StageBehaviour =
  /** A resolved PostgREST response. */
  | { readonly data: unknown; readonly error?: unknown }
  /** A resolved `{ error }` refusal. */
  | { readonly error: unknown; readonly data?: unknown }
  /** The builder rejects — a transport failure. */
  | { readonly reject: unknown }
  /** `from()` throws synchronously. */
  | { readonly throwSync: unknown };

export type StageTable = "team_memberships" | "sharing_grants" | "profiles";

/** Table names and method names only. No response body is ever recorded. */
export type ClientRecording = {
  readonly tables: readonly string[];
  readonly methods: readonly string[];
  readonly rpcCalls: number;
  readonly writeCalls: number;
  /** The referenced-table order/limit options stage c used, as a fixed string. */
  readonly embeddedOptions: readonly string[];
};

export type ClientDouble = {
  readonly client: AppSupabaseClient;
  readonly recording: () => ClientRecording;
};

const WRITE_METHODS = ["insert", "update", "upsert", "delete"] as const;

/**
 * A Supabase client double driven by one behaviour per stage.
 *
 * A stage with no behaviour configured throws when it is reached, which is what
 * makes "stage c was never issued" a hard failure rather than a silent pass: a
 * repository that issued it anyway would get an unconfigured-stage rejection and
 * the test asserting the recording would fail on the table list.
 */
export function clientDouble(
  behaviours: Partial<Record<StageTable, StageBehaviour>>,
): ClientDouble {
  const tables: string[] = [];
  const methods: string[] = [];
  const embeddedOptions: string[] = [];
  let rpcCalls = 0;
  let writeCalls = 0;

  const from = (table: string): unknown => {
    tables.push(table);

    const behaviour = behaviours[table as StageTable];

    if (behaviour === undefined) {
      throw new Error("test double: stage was not configured");
    }

    if ("throwSync" in behaviour) {
      throw behaviour.throwSync;
    }

    const builder: Record<string, unknown> = {
      then: (
        onfulfilled?: (value: unknown) => unknown,
        onrejected?: (reason: unknown) => unknown,
      ) =>
        "reject" in behaviour
          ? Promise.reject(behaviour.reject).then(undefined, onrejected)
          : Promise.resolve({
              data: "data" in behaviour ? behaviour.data : null,
              error: "error" in behaviour ? behaviour.error : null,
            }).then(onfulfilled),
    };

    for (const method of ["select", "eq", "is", "in"]) {
      builder[method] = () => {
        methods.push(method);

        return builder;
      };
    }

    builder.order = (column: unknown, options?: unknown) => {
      methods.push("order");
      embeddedOptions.push(describeOrder(column, options));

      return builder;
    };

    builder.limit = (count: unknown, options?: unknown) => {
      methods.push("limit");
      embeddedOptions.push(describeLimit(count, options));

      return builder;
    };

    for (const method of WRITE_METHODS) {
      builder[method] = () => {
        writeCalls += 1;

        return builder;
      };
    }

    return builder;
  };

  const client = {
    from,
    rpc: () => {
      rpcCalls += 1;

      return {
        then: (onfulfilled?: (value: unknown) => unknown) =>
          Promise.resolve({ data: null, error: null }).then(onfulfilled),
      };
    },
  } as unknown as AppSupabaseClient;

  return {
    client,
    recording: () => ({
      tables: [...tables],
      methods: [...methods],
      rpcCalls,
      writeCalls,
      embeddedOptions: [...embeddedOptions],
    }),
  };
}

/** `order:check_in_date:daily_check_ins:desc` — fixed vocabulary, no values. */
function describeOrder(column: unknown, options: unknown): string {
  const referenced = readOption(options, "referencedTable");
  const ascending = readOption(options, "ascending");

  return [
    "order",
    typeof column === "string" ? column : "unknown",
    typeof referenced === "string" ? referenced : "none",
    ascending === false ? "desc" : "asc",
  ].join(":");
}

/** `limit:1:daily_check_ins` or `limit:101:none`. Counts only. */
function describeLimit(count: unknown, options: unknown): string {
  const referenced = readOption(options, "referencedTable");

  return [
    "limit",
    typeof count === "number" ? String(count) : "unknown",
    typeof referenced === "string" ? referenced : "none",
  ].join(":");
}

function readOption(options: unknown, field: string): unknown {
  if (typeof options !== "object" || options === null) {
    return undefined;
  }

  return (options as Record<string, unknown>)[field];
}

/**
 * A raw server error carrying everything that must never be logged or displayed:
 * a message naming a policy and an athlete id, plus details, hint, and cause.
 */
export function rawServerError(): Error {
  return Object.assign(
    new Error(
      "permission denied for relation daily_check_ins: policy daily_check_ins_select_shared_for_coach denied athlete 00000000-0000-4000-9000-000000000001",
    ),
    {
      code: "42501",
      details: "active check_in grant required",
      hint: "private.can_current_user_read_check_in",
      cause: { athlete_profile_id: ATHLETE_1, rpe: 6 },
    },
  );
}
