import { describe, expect, it } from "vitest";

import type { AppSupabaseClient } from "../../lib/supabase/app-client";
import { captureError } from "../../test-support/capture-error";

import {
  AccountDataError,
  loadAccount,
  saveDisplayName,
} from "./account-repository";

const USER_ID = "00000000-0000-4000-9000-000000000001";

type QueryResult = { data: unknown; error: unknown };

type Recorded = { table: string; op: string; argument: unknown };

/**
 * A minimal stand-in for the PostgREST builder.
 *
 * Every method returns `this`, and the object is thenable, so both an awaited
 * chain and a `.maybeSingle()` chain resolve to the queued result. That is
 * enough to exercise the repository without a network or a real client.
 */
class FakeQuery implements PromiseLike<QueryResult> {
  constructor(
    private readonly result: QueryResult,
    private readonly record: (op: string, argument: unknown) => void,
  ) {}

  select(columns: string): this {
    this.record("select", columns);
    return this;
  }

  update(values: unknown): this {
    this.record("update", values);
    return this;
  }

  eq(column: string, value: unknown): this {
    this.record("eq", `${column}=${String(value)}`);
    return this;
  }

  async maybeSingle(): Promise<QueryResult> {
    return this.result;
  }

  then<TResult1 = QueryResult, TResult2 = never>(
    onfulfilled?:
      ((value: QueryResult) => TResult1 | PromiseLike<TResult1>) | null,
    onrejected?: ((reason: unknown) => TResult2 | PromiseLike<TResult2>) | null,
  ): PromiseLike<TResult1 | TResult2> {
    return Promise.resolve(this.result).then(onfulfilled, onrejected);
  }
}

function createClientDouble(results: Record<string, QueryResult>) {
  const calls: Recorded[] = [];

  const client = {
    from(table: string) {
      calls.push({ table, op: "from", argument: table });

      return new FakeQuery(
        results[table] ?? { data: null, error: null },
        (op, argument) => calls.push({ table, op, argument }),
      );
    },
  } as unknown as AppSupabaseClient;

  return { client, calls };
}

const PROFILE_OK = {
  data: { id: USER_ID, display_name: "athlete-a" },
  error: null,
};

describe("loadAccount", () => {
  it("returns the caller profile and memberships", async () => {
    const { client } = createClientDouble({
      profiles: PROFILE_OK,
      team_memberships: {
        data: [{ team_id: "team-1", role: "athlete", status: "active" }],
        error: null,
      },
    });

    await expect(loadAccount(client, USER_ID)).resolves.toEqual({
      userId: USER_ID,
      displayName: "athlete-a",
      memberships: [{ team_id: "team-1", role: "athlete", status: "active" }],
    });
  });

  it("scopes both queries to the caller", async () => {
    const { client, calls } = createClientDouble({
      profiles: PROFILE_OK,
      team_memberships: { data: [], error: null },
    });

    await loadAccount(client, USER_ID);

    const filters = calls
      .filter((call) => call.op === "eq")
      .map((call) => call.argument);

    expect(filters).toEqual([`id=${USER_ID}`, `profile_id=${USER_ID}`]);
  });

  it("reads only the two tables this task is allowed to read", async () => {
    const { client, calls } = createClientDouble({
      profiles: PROFILE_OK,
      team_memberships: { data: [], error: null },
    });

    await loadAccount(client, USER_ID);

    expect([...new Set(calls.map((call) => call.table))].sort()).toEqual([
      "profiles",
      "team_memberships",
    ]);
  });

  it("treats an empty membership list as a real answer", async () => {
    const { client } = createClientDouble({
      profiles: PROFILE_OK,
      team_memberships: { data: [], error: null },
    });

    const account = await loadAccount(client, USER_ID);

    // Not an error: this is what a pending or fully revoked user looks like.
    expect(account.memberships).toEqual([]);
  });

  it("raises rather than returning an empty list when memberships fail", async () => {
    const { client } = createClientDouble({
      profiles: PROFILE_OK,
      team_memberships: { data: null, error: { code: "42501" } },
    });

    // The distinction this whole module exists to preserve: a failed load must
    // never be indistinguishable from "this user has no team".
    await expect(loadAccount(client, USER_ID)).rejects.toThrow(
      AccountDataError,
    );
  });

  it("raises when the profile read fails", async () => {
    const { client } = createClientDouble({
      profiles: { data: null, error: { code: "PGRST301" } },
    });

    await expect(loadAccount(client, USER_ID)).rejects.toThrow(
      AccountDataError,
    );
  });

  it("raises when the profile row is absent", async () => {
    const { client } = createClientDouble({
      profiles: { data: null, error: null },
      team_memberships: { data: [], error: null },
    });

    // The signup trigger guarantees the row, so its absence is a refusal, not
    // a user who has not chosen a name yet.
    await expect(loadAccount(client, USER_ID)).rejects.toThrow(
      AccountDataError,
    );
  });

  it("classifies a transport failure as offline", async () => {
    const { client } = createClientDouble({
      profiles: { data: null, error: new TypeError("Network request failed") },
    });

    const error = await captureError(
      loadAccount(client, USER_ID),
      AccountDataError,
    );

    expect(error.failure).toBe("offline");
  });

  it("never leaks the server error into the message", async () => {
    const { client } = createClientDouble({
      profiles: {
        data: null,
        error: {
          code: "42501",
          message: "permission denied for table profiles",
          details: "athlete-a@example.test",
        },
      },
    });

    const error = await captureError(
      loadAccount(client, USER_ID),
      AccountDataError,
    );

    expect(error.message).not.toContain("@");
    expect(error.message).not.toContain("permission denied");
  });

  it("preserves a null display name for a user who has not onboarded", async () => {
    const { client } = createClientDouble({
      profiles: { data: { id: USER_ID, display_name: null }, error: null },
      team_memberships: { data: [], error: null },
    });

    const account = await loadAccount(client, USER_ID);

    expect(account.displayName).toBeNull();
  });
});

describe("saveDisplayName", () => {
  it("writes only the display_name column", async () => {
    const { client, calls } = createClientDouble({
      profiles: { data: { display_name: "athlete-a" }, error: null },
    });

    await saveDisplayName(client, USER_ID, "athlete-a");

    const update = calls.find((call) => call.op === "update");

    // Sending id or created_at would be refused by the column-level grant, so
    // the payload is pinned here rather than left to a future edit.
    expect(update?.argument).toEqual({ display_name: "athlete-a" });
  });

  it("sends the normalized value, not the raw input", async () => {
    const { client, calls } = createClientDouble({
      profiles: { data: { display_name: "athlete a" }, error: null },
    });

    await saveDisplayName(client, USER_ID, "  athlete   a  ");

    const update = calls.find((call) => call.op === "update");

    expect(update?.argument).toEqual({ display_name: "athlete a" });
  });

  it("scopes the update to the caller row", async () => {
    const { client, calls } = createClientDouble({
      profiles: { data: { display_name: "athlete-a" }, error: null },
    });

    await saveDisplayName(client, USER_ID, "athlete-a");

    expect(
      calls.filter((call) => call.op === "eq").map((call) => call.argument),
    ).toEqual([`id=${USER_ID}`]);
  });

  it("returns the value the database actually stored", async () => {
    const { client } = createClientDouble({
      profiles: { data: { display_name: "stored-by-server" }, error: null },
    });

    await expect(saveDisplayName(client, USER_ID, "athlete-a")).resolves.toBe(
      "stored-by-server",
    );
  });

  it("rejects a blank name without contacting the database", async () => {
    const { client, calls } = createClientDouble({});

    await expect(saveDisplayName(client, USER_ID, "   ")).rejects.toThrow(
      AccountDataError,
    );
    expect(calls).toEqual([]);
  });

  it("rejects an over-length name without contacting the database", async () => {
    const { client, calls } = createClientDouble({});

    await expect(
      saveDisplayName(client, USER_ID, "x".repeat(81)),
    ).rejects.toThrow(AccountDataError);
    expect(calls).toEqual([]);
  });

  it("raises when the policy filtered the row out", async () => {
    const { client } = createClientDouble({
      profiles: { data: null, error: null },
    });

    // Zero rows updated is what a mismatched user id looks like: the policy
    // filters rather than raising, so a silent success must not be reported.
    const error = await captureError(
      saveDisplayName(client, USER_ID, "athlete-a"),
      AccountDataError,
    );

    expect(error).toBeInstanceOf(AccountDataError);
    expect(error.failure).toBe("denied");
  });

  it("raises a sanitized error when the write is refused", async () => {
    const { client } = createClientDouble({
      profiles: {
        data: null,
        error: {
          code: "42501",
          message: "new row violates row-level security",
        },
      },
    });

    const error = await captureError(
      saveDisplayName(client, USER_ID, "athlete-a"),
      AccountDataError,
    );

    expect(error.failure).toBe("denied");
    expect(error.message).not.toContain("row-level security");
  });
});
