import { describe, expect, it, vi } from "vitest";

import { captureError } from "../../test-support/capture-error";

import {
  AuthActionError,
  classifySignUpResult,
  restoreIdentity,
  signInWithPassword,
  signOutGlobally,
  signUpWithPassword,
  type AuthClient,
} from "./auth-repository";

const CREDENTIALS = {
  email: "athlete-a@example.test",
  password: "synthetic-password",
};

const SESSION = {
  access_token: "synthetic-access-token",
  user: { id: "00000000-0000-4000-9000-000000000001" },
};

type AuthDouble = {
  signUp: ReturnType<typeof vi.fn>;
  signInWithPassword: ReturnType<typeof vi.fn>;
  signOut: ReturnType<typeof vi.fn>;
  getSession: ReturnType<typeof vi.fn>;
};

function createAuthDouble(overrides: Partial<AuthDouble> = {}) {
  const auth: AuthDouble = {
    signUp: vi.fn(async () => ({ data: { session: null }, error: null })),
    signInWithPassword: vi.fn(async () => ({
      data: { session: SESSION },
      error: null,
    })),
    signOut: vi.fn(async () => ({ error: null })),
    getSession: vi.fn(async () => ({
      data: { session: SESSION },
      error: null,
    })),
    ...overrides,
  };

  return { auth, client: { auth } as unknown as AuthClient };
}

describe("classifySignUpResult", () => {
  it("reports a session when one came back", () => {
    expect(classifySignUpResult({ session: SESSION })).toEqual({
      kind: "session",
    });
  });

  it("reports confirmation-required when the session is null", () => {
    expect(classifySignUpResult({ session: null })).toEqual({
      kind: "confirmation-required",
    });
  });

  it("reports confirmation-required for an unusable session object", () => {
    // A session that cannot authorize a request is treated as no session, not
    // as a half-signed-in state.
    expect(classifySignUpResult({ session: { user: { id: "u" } } })).toEqual({
      kind: "confirmation-required",
    });
  });
});

describe("signUpWithPassword", () => {
  it("sends the email and password and nothing else", async () => {
    const { auth, client } = createAuthDouble();

    await signUpWithPassword(client, CREDENTIALS);

    expect(auth.signUp).toHaveBeenCalledTimes(1);

    const payload = auth.signUp.mock.calls[0]?.[0] as Record<string, unknown>;

    // No display name, role, team, membership, or options.data. Anything sent
    // here would land in user metadata, which is user-controlled and must never
    // be an authorization input.
    expect(Object.keys(payload).sort()).toEqual(["email", "password"]);
    expect(payload).not.toHaveProperty("options");
    expect(payload).not.toHaveProperty("data");
  });

  it("reports the confirmation-required outcome", async () => {
    const { client } = createAuthDouble();

    await expect(signUpWithPassword(client, CREDENTIALS)).resolves.toEqual({
      kind: "confirmation-required",
    });
  });

  it("reports the session outcome", async () => {
    const { client } = createAuthDouble({
      signUp: vi.fn(async () => ({ data: { session: SESSION }, error: null })),
    });

    await expect(signUpWithPassword(client, CREDENTIALS)).resolves.toEqual({
      kind: "session",
    });
  });

  it("raises a sanitized error that leaks nothing", async () => {
    const { client } = createAuthDouble({
      signUp: vi.fn(async () => ({
        data: { session: null },
        error: {
          code: "user_already_exists",
          message: "User athlete-a@example.test already registered",
          status: 400,
        },
      })),
    });

    await expect(signUpWithPassword(client, CREDENTIALS)).rejects.toThrow(
      AuthActionError,
    );

    const error = await captureError(
      signUpWithPassword(client, CREDENTIALS),
      AuthActionError,
    );

    expect(error.message).not.toContain("@");
    expect(error.message).not.toContain("already registered");
    // Collapsed to the same category as a wrong password, so an existing
    // account cannot be detected from the response.
    expect(error.failure).toBe("invalid-credentials");
  });
});

describe("signInWithPassword", () => {
  it("returns the identity on success", async () => {
    const { auth, client } = createAuthDouble();

    await expect(signInWithPassword(client, CREDENTIALS)).resolves.toEqual({
      userId: SESSION.user.id,
    });
    expect(auth.signInWithPassword).toHaveBeenCalledWith(CREDENTIALS);
  });

  it("fails closed when success arrives without a usable session", async () => {
    const { client } = createAuthDouble({
      signInWithPassword: vi.fn(async () => ({
        data: { session: null },
        error: null,
      })),
    });

    await expect(signInWithPassword(client, CREDENTIALS)).rejects.toThrow(
      AuthActionError,
    );
  });

  it("raises a sanitized error for bad credentials", async () => {
    const { client } = createAuthDouble({
      signInWithPassword: vi.fn(async () => ({
        data: { session: null },
        error: { code: "invalid_credentials", message: "Invalid login" },
      })),
    });

    const error = await captureError(
      signInWithPassword(client, CREDENTIALS),
      AuthActionError,
    );

    expect(error).toBeInstanceOf(AuthActionError);
    expect(error.message).not.toContain("Invalid login");
  });
});

describe("signOutGlobally", () => {
  it("signs out with global scope", async () => {
    const { auth, client } = createAuthDouble();

    await signOutGlobally(client);

    expect(auth.signOut).toHaveBeenCalledWith({ scope: "global" });
  });

  it("raises a sanitized error on failure", async () => {
    const { client } = createAuthDouble({
      signOut: vi.fn(async () => ({ error: { code: "http_500" } })),
    });

    await expect(signOutGlobally(client)).rejects.toThrow(AuthActionError);
  });
});

describe("restoreIdentity", () => {
  it("returns the identity from a stored session", async () => {
    const { client } = createAuthDouble();

    await expect(restoreIdentity(client)).resolves.toEqual({
      userId: SESSION.user.id,
    });
  });

  it("fails closed when there is no stored session", async () => {
    const { client } = createAuthDouble({
      getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
    });

    await expect(restoreIdentity(client)).resolves.toBeNull();
  });

  it("fails closed when the stored session is corrupt", async () => {
    const { client } = createAuthDouble({
      getSession: vi.fn(async () => ({
        data: { session: { access_token: "trunc" } },
        error: null,
      })),
    });

    await expect(restoreIdentity(client)).resolves.toBeNull();
  });

  it("fails closed when reading storage errors", async () => {
    const { client } = createAuthDouble({
      getSession: vi.fn(async () => ({
        data: { session: null },
        error: { code: "storage_error" },
      })),
    });

    await expect(restoreIdentity(client)).resolves.toBeNull();
  });

  it("fails closed when reading storage throws", async () => {
    const { client } = createAuthDouble({
      getSession: vi.fn(() => {
        throw new Error("unreadable storage");
      }),
    });

    // A corrupt blob must not wedge the app on the loading screen.
    await expect(restoreIdentity(client)).resolves.toBeNull();
  });
});
