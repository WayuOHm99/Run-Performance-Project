import { describe, expect, it } from "vitest";

import { clearAuthScopedQueries, createQueryClient } from "./client";
import { authScopedKeys } from "./keys";

const USER_A = "00000000-0000-4000-9000-00000000000a";
const USER_B = "00000000-0000-4000-9000-00000000000b";

describe("createQueryClient", () => {
  it("does not persist the cache", () => {
    const client = createQueryClient();

    // No persister is attached, so profile and membership data never reach
    // disk. A future health-data task depends on this staying true.
    expect(
      (client as unknown as { persister?: unknown }).persister,
    ).toBeUndefined();
  });

  it("keeps auth-bound data stale quickly so a revocation surfaces", () => {
    const client = createQueryClient();
    const staleTime = client.getDefaultOptions().queries?.staleTime;

    expect(typeof staleTime).toBe("number");
    expect(staleTime as number).toBeLessThanOrEqual(60_000);
  });
});

describe("clearAuthScopedQueries", () => {
  it("removes every auth-bound entry", () => {
    const client = createQueryClient();

    client.setQueryData(authScopedKeys.account(USER_A), {
      displayName: "athlete-a",
    });
    client.setQueryData(authScopedKeys.profile(USER_A), { id: USER_A });
    client.setQueryData(authScopedKeys.memberships(USER_A), []);

    clearAuthScopedQueries(client);

    expect(client.getQueryData(authScopedKeys.account(USER_A))).toBeUndefined();
    expect(client.getQueryData(authScopedKeys.profile(USER_A))).toBeUndefined();
    expect(
      client.getQueryData(authScopedKeys.memberships(USER_A)),
    ).toBeUndefined();
  });

  it("removes data belonging to every user, not just the current one", () => {
    const client = createQueryClient();

    client.setQueryData(authScopedKeys.account(USER_A), { name: "a" });
    client.setQueryData(authScopedKeys.account(USER_B), { name: "b" });

    clearAuthScopedQueries(client);

    expect(client.getQueryData(authScopedKeys.account(USER_A))).toBeUndefined();
    expect(client.getQueryData(authScopedKeys.account(USER_B))).toBeUndefined();
  });

  it("removes rather than invalidates, so nothing stale stays readable", () => {
    const client = createQueryClient();

    client.setQueryData(authScopedKeys.account(USER_A), { name: "a" });
    clearAuthScopedQueries(client);

    // Invalidation would leave the previous account's data readable until a
    // refetch resolved, which is long enough to render it to the new user.
    expect(client.getQueryCache().findAll()).toHaveLength(0);
  });

  it("leaves data that is not auth-bound alone", () => {
    const client = createQueryClient();

    client.setQueryData(["app-config"], { locale: "th" });
    client.setQueryData(authScopedKeys.account(USER_A), { name: "a" });

    clearAuthScopedQueries(client);

    expect(client.getQueryData(["app-config"])).toEqual({ locale: "th" });
  });

  it("clears pending mutations too", () => {
    const client = createQueryClient();

    client.getMutationCache().build(client, { mutationKey: ["save-name"] });
    expect(client.getMutationCache().getAll().length).toBeGreaterThan(0);

    clearAuthScopedQueries(client);

    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });

  it("is safe to call when nothing is cached", () => {
    const client = createQueryClient();

    expect(() => {
      clearAuthScopedQueries(client);
    }).not.toThrow();
  });
});
