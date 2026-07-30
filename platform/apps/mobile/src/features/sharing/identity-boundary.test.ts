import {
  MutationObserver,
  QueryClient,
  type MutationObserverResult,
} from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { clearAuthScopedQueries } from "../../lib/query/client";

import { targetTeamId, type TeamSharingState } from "./domain";
import { SharingDataError } from "./errors";
import {
  IDLE_SHARING_OUTCOME,
  NO_IDENTITY_BOUNDARY,
  isIdleSharingOutcome,
  readSharingOutcome,
  sharingBoundaryChanged,
  sharingIdentityBoundaryKey,
} from "./identity-boundary";
import {
  sharingActionMutationOptions,
  type SharingActionResult,
  type SharingActionVariables,
} from "./query-options";

/**
 * The identity boundary around the sharing section's mutation observer.
 *
 * **The defect this file exists for (Round 2, Medium).** An *active*
 * `MutationObserver` survives the removal of its mutation from the
 * `MutationCache`. `clearAuthScopedQueries` calls `MutationCache.clear()`, which
 * removes the mutation but neither aborts it nor detaches its observers. So when the
 * previous account's in-flight action finally settles, the same observer transitions
 * to success or error and reports the **previous account's** result and variables.
 * Rendered through the section that is the previous account's banner, the previous
 * account's team in the busy slot, and controls disabled by a request the current
 * account never made.
 *
 * Round 1 already proved the *write* and the *refetch* cannot be redirected. Those
 * tests are untouched and still pass. This file proves the separate property that
 * the old observer's **state** cannot appear under the new identity.
 *
 * **Failure-output safety.** Nothing here passes a `MutationObserverResult`, a
 * variables object, a query key, a user id, a team id, an RPC argument, or a captured
 * error to an assertion:
 *
 * - an observer result is reduced by `describeObserver` to a string of fixed words
 *   and booleans such as `idle|no-data|no-error|no-variables|not-pending`;
 * - a rendered outcome is reduced by `describeOutcome` to
 *   `idle|no-busy-team|no-success|no-failure` or a direction word;
 * - team ids are reduced to the case labels `A`, `B`, or `unknown`;
 * - query keys are reduced to `owner-old` / `owner-new` / `unknown` owner labels;
 * - sets of cases are asserted as lists of **case names**.
 *
 * All identifiers are synthetic.
 */

const OLD_USER = "00000000-0000-4000-9000-0000000000a1";
const NEW_USER = "00000000-0000-4000-9000-0000000000b2";
const TEAM_A = "00000000-0000-4000-8000-00000000000a";
const TEAM_B = "00000000-0000-4000-8000-00000000000b";

const TEAM_LABELS = new Map<string, string>([
  [TEAM_A, "A"],
  [TEAM_B, "B"],
]);

const OWNER_LABELS = new Map<unknown, string>([
  [OLD_USER, "owner-old"],
  [NEW_USER, "owner-new"],
]);

const OLD_TEAMS: readonly TeamSharingState[] = [
  { teamId: TEAM_A, teamName: "Alpha Runners", sharing: false },
];

const NEW_TEAMS: readonly TeamSharingState[] = [
  { teamId: TEAM_B, teamName: "Beta Runners", sharing: false },
];

const GRANT_A: SharingActionVariables = { teamId: TEAM_A, action: "grant" };

function teamLabel(teamId: string): string {
  return TEAM_LABELS.get(teamId) ?? "unknown";
}

/** Safe: an owner *label*, never the id. */
function ownerOf(queryKey: readonly unknown[]): string {
  return OWNER_LABELS.get(queryKey[1]) ?? "unknown";
}

/** Safe: fixed words and booleans describing an observer's state. */
function describeObserver(
  result: MutationObserverResult<
    SharingActionResult,
    Error,
    SharingActionVariables,
    unknown
  >,
): string {
  return [
    result.status,
    result.data === undefined ? "no-data" : "has-data",
    result.error === null ? "no-error" : "has-error",
    result.variables === undefined ? "no-variables" : "has-variables",
    result.isPending ? "pending" : "not-pending",
    result.isSuccess ? "success" : "not-success",
    result.isError ? "failure" : "not-failure",
  ].join("|");
}

/** Safe: fixed words describing what the section would render. */
function describeOutcome(state: {
  readonly isPending: boolean;
  readonly isSuccess: boolean;
  readonly isError: boolean;
  readonly data: SharingActionResult | undefined;
  readonly variables: SharingActionVariables | undefined;
}): string {
  const view = readSharingOutcome(state);

  return [
    view.busy ? "busy" : "idle",
    view.busyTeamId === undefined
      ? "no-busy-team"
      : `busy-team-${teamLabel(view.busyTeamId)}`,
    view.successAction === null
      ? "no-success"
      : `success-${view.successAction}`,
    view.failedAction === null ? "no-failure" : `failure-${view.failedAction}`,
  ].join("|");
}

const FULLY_IDLE_OBSERVER =
  "idle|no-data|no-error|no-variables|not-pending|not-success|not-failure";
const FULLY_IDLE_OUTCOME = "idle|no-busy-team|no-success|no-failure";

type HarnessOptions = {
  readonly userId: string;
  readonly teams: readonly TeamSharingState[];
  readonly defer?: boolean;
  readonly fail?: boolean;
};

/** Records only non-sensitive facts about one identity's action. */
function createHarness(options: HarnessOptions) {
  const writes: string[] = [];
  const refetchedOwners: string[] = [];
  let release: (() => void) | undefined;
  let markStarted: (() => void) | undefined;

  const started = new Promise<void>((resolve) => {
    markStarted = resolve;
  });

  const settle = (): Promise<void> => {
    markStarted?.();

    if (options.defer !== true) {
      return options.fail === true
        ? Promise.reject(new SharingDataError("grant", "denied"))
        : Promise.resolve();
    }

    return new Promise<void>((resolve, reject) => {
      release = () => {
        if (options.fail === true) {
          reject(new SharingDataError("grant", "denied"));
          return;
        }

        resolve();
      };
    });
  };

  const built = sharingActionMutationOptions({
    userId: options.userId,
    teams: options.teams,
    grant: (target) => {
      writes.push(`grant:${teamLabel(targetTeamId(target))}`);
      return settle();
    },
    revoke: (target) => {
      writes.push(`revoke:${teamLabel(targetTeamId(target))}`);
      return settle();
    },
    refetchKey: (queryKey) => {
      refetchedOwners.push(ownerOf(queryKey));
      return Promise.resolve();
    },
  });

  return {
    options: built,
    /** Safe: directions and case labels, in order. */
    writes: () => [...writes],
    /** Safe: owner labels only, in order. */
    refetchedOwners: () => [...refetchedOwners],
    started,
    release: () => {
      release?.();
    },
  };
}

function createClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: 0 } },
  });
  client.mount();

  return client;
}

function newObserver(
  client: QueryClient,
  options: ReturnType<typeof createHarness>["options"],
) {
  return new MutationObserver<
    SharingActionResult,
    Error,
    SharingActionVariables
  >(client, options);
}

describe("sharingIdentityBoundaryKey", () => {
  it("distinguishes two verified identities", () => {
    // If this stopped being true, React would reuse the subtree and the observer
    // would survive the account change, which is the whole defect.
    expect(sharingBoundaryChanged(OLD_USER, NEW_USER)).toBe(true);
  });

  it("distinguishes signing out from being signed in", () => {
    expect(sharingBoundaryChanged(OLD_USER, undefined)).toBe(true);
    expect(sharingBoundaryChanged(undefined, OLD_USER)).toBe(true);
  });

  it("is stable for one unchanged identity", () => {
    // A rerender for any other reason must not remount and cancel a live action.
    expect(sharingBoundaryChanged(OLD_USER, OLD_USER)).toBe(false);
    expect(sharingBoundaryChanged(undefined, undefined)).toBe(false);
  });

  it("treats an empty user id as no identity", () => {
    expect(sharingIdentityBoundaryKey("")).toBe(NO_IDENTITY_BOUNDARY);
    expect(sharingIdentityBoundaryKey(undefined)).toBe(NO_IDENTITY_BOUNDARY);
  });

  it("never collides across the transitions the app can make", () => {
    const keys = [OLD_USER, NEW_USER, undefined, ""].map((userId) =>
      sharingIdentityBoundaryKey(userId),
    );

    // Three distinct keys: two identities plus one shared signed-out key. A count
    // only; no key text is compared.
    expect(new Set(keys).size).toBe(3);
  });
});

/**
 * The lifecycle regression, against the installed TanStack implementation.
 *
 * Both directions of the old action are covered: success and failure. In each, the
 * old action is genuinely in flight before the identity changes, the real
 * `clearAuthScopedQueries` runs, the old observer is detached exactly as a remount
 * detaches it, the new identity's observer is created, and only then does the old
 * action settle.
 */
describe("an old identity's action settling after an identity change", () => {
  const CASES: readonly (readonly [name: string, fail: boolean])[] = [
    ["old-action-succeeds", false],
    ["old-action-fails", true],
  ];

  it("never updates the new identity's rendered state", async () => {
    const wrong: string[] = [];

    for (const [name, fail] of CASES) {
      const client = createClient();

      try {
        const old = createHarness({
          userId: OLD_USER,
          teams: OLD_TEAMS,
          defer: true,
          fail,
        });

        // 1. The old identity's action starts and is genuinely in flight.
        const oldObserver = newObserver(client, old.options);
        const detachOldObserver = oldObserver.subscribe(() => undefined);
        const settled = oldObserver.mutate(GRANT_A).catch(() => undefined);

        await old.started;

        if (client.isMutating() !== 1) {
          wrong.push(`${name}:not-in-flight`);
        }

        // 2. The identity changed: the real auth-scoped clear runs.
        clearAuthScopedQueries(client);

        if (client.getMutationCache().getAll().length !== 0) {
          wrong.push(`${name}:cache-not-cleared`);
        }

        // 3. The delivered boundary: the key changed, so React unmounts the old
        //    subtree, which detaches its observer.
        if (!sharingBoundaryChanged(OLD_USER, NEW_USER)) {
          wrong.push(`${name}:boundary-did-not-change`);
        }

        detachOldObserver();

        // 4. The new identity's observer is created fresh.
        const replacement = createHarness({
          userId: NEW_USER,
          teams: NEW_TEAMS,
        });
        const newObserverInstance = newObserver(client, replacement.options);
        // Counted, not inspected. Any notification at all while the old action
        // settles would be the previous account's outcome reaching this render.
        let newNotifications = 0;
        const detachNewObserver = newObserverInstance.subscribe(() => {
          newNotifications += 1;
        });

        // 5. Only now does the old action settle.
        old.release();
        await settled;
        await Promise.resolve();

        if (newNotifications !== 0) {
          wrong.push(`${name}:new-observer-notified`);
        }

        const newState = newObserverInstance.getCurrentResult();

        // 6a. The new observer is untouched and fully idle.
        if (describeObserver(newState) !== FULLY_IDLE_OBSERVER) {
          wrong.push(`${name}:new-observer-not-idle`);
        }

        // 6b. Nothing from the previous account would be rendered, and the new
        //     account's controls are not disabled.
        if (describeOutcome(newState) !== FULLY_IDLE_OUTCOME) {
          wrong.push(`${name}:new-outcome-not-idle`);
        }

        if (!isIdleSharingOutcome(readSharingOutcome(newState))) {
          wrong.push(`${name}:new-controls-disabled`);
        }

        // 6c. The old action used only the original write scope...
        if (old.writes().join(",") !== "grant:A") {
          wrong.push(`${name}:old-write-scope`);
        }

        // ...and its refetch never targeted the new identity's key.
        const owners = old.refetchedOwners();

        if (owners.includes("owner-new") || owners.includes("unknown")) {
          wrong.push(`${name}:old-refetch-redirected`);
        }

        if (!fail && owners.join(",") !== "owner-old") {
          wrong.push(`${name}:old-refetch-missing`);
        }

        // 6d. The replacement identity was never written to or refreshed.
        if (replacement.writes().length !== 0) {
          wrong.push(`${name}:replacement-written`);
        }

        if (replacement.refetchedOwners().length !== 0) {
          wrong.push(`${name}:replacement-refetched`);
        }

        detachNewObserver();
      } finally {
        client.unmount();
        client.clear();
      }
    }

    // Case names only.
    expect(wrong).toEqual([]);
  });

  /**
   * The guard. Removing the identity boundary — reusing the same observer and only
   * swapping its options, which is what `clearAuthScopedQueries` alone leaves you
   * with — reproduces the defect against the installed TanStack version.
   *
   * This is a positive control: it fails if TanStack ever starts detaching
   * observers on `MutationCache.clear()`, at which point the boundary above would
   * be belt-and-braces rather than load-bearing.
   */
  it("would leak into the new identity without the boundary", async () => {
    const leaked: string[] = [];

    for (const [name, fail] of CASES) {
      const client = createClient();

      try {
        const old = createHarness({
          userId: OLD_USER,
          teams: OLD_TEAMS,
          defer: true,
          fail,
        });

        const observer = newObserver(client, old.options);
        let notifications = 0;
        const detach = observer.subscribe(() => {
          notifications += 1;
        });
        const settled = observer.mutate(GRANT_A).catch(() => undefined);

        await old.started;

        clearAuthScopedQueries(client);

        // No boundary: the very same observer is reused for the new identity.
        const replacement = createHarness({
          userId: NEW_USER,
          teams: NEW_TEAMS,
        });
        observer.setOptions(replacement.options);

        const beforeSettle = notifications;

        old.release();
        await settled;
        await Promise.resolve();

        // The reused observer is notified by the previous account's action, which is
        // exactly the update the boundary prevents.
        if (notifications <= beforeSettle) {
          leaked.push(`${name}:no-notification`);
        }

        const state = observer.getCurrentResult();

        // The defect: the reused observer is no longer idle, so the new identity
        // would render the previous account's outcome.
        if (describeObserver(state) === FULLY_IDLE_OBSERVER) {
          leaked.push(`${name}:unexpectedly-idle`);
        }

        if (describeOutcome(state) === FULLY_IDLE_OUTCOME) {
          leaked.push(`${name}:outcome-unexpectedly-idle`);
        }

        detach();
      } finally {
        client.unmount();
        client.clear();
      }
    }

    // Case names only. Empty means the hazard is real and still reproducible.
    expect(leaked).toEqual([]);
  });

  it("keeps a live action visible when the identity did not change", async () => {
    // The boundary must not be so eager that an ordinary rerender cancels a live
    // action or hides its busy state.
    const client = createClient();

    try {
      const harness = createHarness({
        userId: OLD_USER,
        teams: OLD_TEAMS,
        defer: true,
      });

      const observer = newObserver(client, harness.options);
      const detach = observer.subscribe(() => undefined);
      const settled = observer.mutate(GRANT_A).catch(() => undefined);

      await harness.started;

      expect(sharingBoundaryChanged(OLD_USER, OLD_USER)).toBe(false);
      // Busy, with the pressed team in the busy slot.
      expect(describeOutcome(observer.getCurrentResult())).toBe(
        "busy|busy-team-A|no-success|no-failure",
      );

      harness.release();
      await settled;
      await Promise.resolve();

      expect(describeOutcome(observer.getCurrentResult())).toBe(
        "idle|no-busy-team|success-grant|no-failure",
      );

      detach();
    } finally {
      client.unmount();
      client.clear();
    }
  });
});

describe("readSharingOutcome", () => {
  type State = {
    isPending: boolean;
    isSuccess: boolean;
    isError: boolean;
    data: SharingActionResult | undefined;
    variables: SharingActionVariables | undefined;
  };

  const IDLE: State = {
    isPending: false,
    isSuccess: false,
    isError: false,
    data: undefined,
    variables: undefined,
  };

  it("renders nothing for a fresh observer", () => {
    expect(describeOutcome(IDLE)).toBe(FULLY_IDLE_OUTCOME);
    expect(isIdleSharingOutcome(IDLE_SHARING_OUTCOME)).toBe(true);
  });

  it("reports the success direction", () => {
    expect(
      describeOutcome({
        ...IDLE,
        isSuccess: true,
        data: { action: "grant" },
      }),
    ).toBe("idle|no-busy-team|success-grant|no-failure");

    expect(
      describeOutcome({
        ...IDLE,
        isSuccess: true,
        data: { action: "revoke" },
      }),
    ).toBe("idle|no-busy-team|success-revoke|no-failure");
  });

  it("reports the failed direction from the variables", () => {
    expect(
      describeOutcome({
        ...IDLE,
        isError: true,
        variables: { teamId: TEAM_A, action: "revoke" },
      }),
    ).toBe("idle|no-busy-team|no-success|failure-revoke");
  });

  it("selects the busy team from the in-flight variables", () => {
    expect(
      describeOutcome({
        ...IDLE,
        isPending: true,
        variables: { teamId: TEAM_B, action: "grant" },
      }),
    ).toBe("busy|busy-team-B|no-success|no-failure");
  });

  it("prefers busy over any lingering outcome", () => {
    // A second action starting must disable everything even if the previous
    // outcome has not been cleared yet.
    expect(
      describeOutcome({
        isPending: true,
        isSuccess: true,
        isError: false,
        data: { action: "grant" },
        variables: { teamId: TEAM_A, action: "revoke" },
      }),
    ).toBe("busy|busy-team-A|no-success|no-failure");
  });

  it("renders no banner from an inconsistent state", () => {
    const INCONSISTENT: readonly (readonly [string, State])[] = [
      ["success-without-data", { ...IDLE, isSuccess: true }],
      ["error-without-variables", { ...IDLE, isError: true }],
    ];

    const rendered = INCONSISTENT.filter(
      ([, state]) => describeOutcome(state) !== FULLY_IDLE_OUTCOME,
    ).map(([name]) => name);

    // Case names only.
    expect(rendered).toEqual([]);
  });

  it("shows no busy team when pending variables are absent", () => {
    expect(describeOutcome({ ...IDLE, isPending: true })).toBe(
      "busy|no-busy-team|no-success|no-failure",
    );
  });
});

describe("SharingActionResult minimization", () => {
  it("carries only the direction", async () => {
    // Mutation data outlives its identity on an active observer, so it must hold no
    // authorization metadata: no user id, no team id, no query key.
    const harness = createHarness({ userId: OLD_USER, teams: OLD_TEAMS });

    const result = await harness.options.mutationFn(GRANT_A);

    // Field names only.
    expect(Object.keys(result).sort()).toEqual(["action"]);
    expect(result.action).toBe("grant");

    const serialized = JSON.stringify(result);
    const leaks = (
      [
        ["old-user", OLD_USER],
        ["new-user", NEW_USER],
        ["team-a", TEAM_A],
        ["team-b", TEAM_B],
        ["auth-scope", "auth-scoped"],
        ["team-name", "Runners"],
      ] as const
    )
      .filter(([, fragment]) => serialized.includes(fragment))
      .map(([label]) => label);

    // Fragment names only.
    expect(leaks).toEqual([]);
  });
});
