import { describe, expect, it, vi } from "vitest";

import { captureError } from "../../test-support/capture-error";

import {
  AuthActionError,
  classifySignUpResult,
  readStoredSession,
  resolveSignUpResponse,
  resolveVerifiedIdentity,
  signInWithPassword,
  signOutGlobally,
  signUpWithPassword,
  type AuthClient,
} from "./auth-repository";

const CREDENTIALS = {
  email: "athlete-a@example.test",
  password: "synthetic-password",
};

const USER_ID = "00000000-0000-4000-9000-000000000001";

const SESSION = {
  access_token: "synthetic-access-token",
  user: { id: USER_ID },
};

function validClaims(sub = USER_ID) {
  return {
    data: {
      claims: {
        iss: "http://127.0.0.1:54321/auth/v1",
        sub,
        aud: "authenticated",
        exp: Math.floor(Date.now() / 1000) + 3600,
        iat: Math.floor(Date.now() / 1000) - 60,
        role: "authenticated",
        aal: "aal1",
        session_id: "00000000-0000-4000-9000-0000000000f1",
      },
      header: { alg: "ES256", kid: "synthetic-kid", typ: "JWT" },
      signature: new Uint8Array([1, 2, 3]),
    },
    error: null,
  };
}

type AuthDouble = {
  signUp: ReturnType<typeof vi.fn>;
  signInWithPassword: ReturnType<typeof vi.fn>;
  signOut: ReturnType<typeof vi.fn>;
  getSession: ReturnType<typeof vi.fn>;
  getClaims: ReturnType<typeof vi.fn>;
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
    getClaims: vi.fn(async () => validClaims()),
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
    expect(classifySignUpResult({ session: { user: { id: "u" } } })).toEqual({
      kind: "confirmation-required",
    });
  });
});

/**
 * M1: an existing address must be indistinguishable from a new one whenever
 * the server gives us the chance to hide it.
 */
describe("resolveSignUpResponse: account enumeration resistance", () => {
  const GENERIC = { kind: "confirmation-required" };

  it("returns the generic outcome for a null session", () => {
    expect(resolveSignUpResponse({ session: null, error: null })).toEqual(
      GENERIC,
    );
  });

  it("returns the generic outcome for user_already_exists", () => {
    expect(
      resolveSignUpResponse({
        session: null,
        error: { code: "user_already_exists", status: 422 },
      }),
    ).toEqual(GENERIC);
  });

  it("returns the generic outcome for email_exists", () => {
    expect(
      resolveSignUpResponse({
        session: null,
        error: { code: "email_exists", status: 422 },
      }),
    ).toEqual(GENERIC);
  });

  it("returns the generic outcome for user_already_registered", () => {
    expect(
      resolveSignUpResponse({
        session: null,
        error: { code: "user_already_registered", status: 400 },
      }),
    ).toEqual(GENERIC);
  });

  it("makes an existing address indistinguishable from an unconfirmed new one", () => {
    // The whole point of M1. Two server responses that mean different things
    // must produce one identical outcome in the app:
    //
    //   * a new account awaiting confirmation -> null session, no error;
    //   * an existing address while confirmations are disabled -> an
    //     existing-account error code.
    //
    // The third case, an existing address while confirmations are enabled,
    // needs no separate assertion: Supabase returns an obfuscated user with a
    // null session, which is byte-for-byte the first case at this boundary.
    const unconfirmedNewAccount = resolveSignUpResponse({
      session: null,
      error: null,
    });
    const existingAddress = resolveSignUpResponse({
      session: null,
      error: { code: "user_already_exists" },
    });

    expect(unconfirmedNewAccount).toEqual(existingAddress);
  });

  it("never throws for an existing-account response", () => {
    expect(() =>
      resolveSignUpResponse({
        session: null,
        error: { code: "user_already_exists" },
      }),
    ).not.toThrow();
  });

  it("still reports a returned session as a session", () => {
    expect(resolveSignUpResponse({ session: SESSION, error: null })).toEqual({
      kind: "session",
    });
  });

  it("still raises for a genuine failure", () => {
    expect(() =>
      resolveSignUpResponse({
        session: null,
        error: { code: "weak_password" },
      }),
    ).toThrow(AuthActionError);
  });

  it("still raises for a rate limit", () => {
    expect(() =>
      resolveSignUpResponse({
        session: null,
        error: { code: "over_email_send_rate_limit" },
      }),
    ).toThrow(AuthActionError);
  });

  it("still raises for a transport failure", () => {
    expect(() =>
      resolveSignUpResponse({
        session: null,
        error: new TypeError("Network request failed"),
      }),
    ).toThrow(AuthActionError);
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

  it("normalizes an existing address to the generic outcome rather than an error", async () => {
    const { client } = createAuthDouble({
      signUp: vi.fn(async () => ({
        data: { session: null },
        error: {
          code: "user_already_exists",
          message: "User athlete-a@example.test already registered",
          status: 422,
        },
      })),
    });

    await expect(signUpWithPassword(client, CREDENTIALS)).resolves.toEqual({
      kind: "confirmation-required",
    });
  });

  it("raises a sanitized error that leaks nothing for a real failure", async () => {
    const { client } = createAuthDouble({
      signUp: vi.fn(async () => ({
        data: { session: null },
        error: {
          code: "weak_password",
          message: "Password for athlete-a@example.test is too weak",
          status: 422,
        },
      })),
    });

    const error = await captureError(
      signUpWithPassword(client, CREDENTIALS),
      AuthActionError,
    );

    expect(error.message).not.toContain("@");
    expect(error.message).not.toContain("too weak");
  });
});

describe("signInWithPassword", () => {
  it("resolves on success", async () => {
    const { auth, client } = createAuthDouble();

    await expect(
      signInWithPassword(client, CREDENTIALS),
    ).resolves.toBeUndefined();
    expect(auth.signInWithPassword).toHaveBeenCalledWith(CREDENTIALS);
  });

  it("returns no identity, so verified claims stay the only source", async () => {
    const { client } = createAuthDouble();

    // A returned identity here would be a second, weaker source of truth than
    // the JWT verification the provider performs.
    await expect(
      signInWithPassword(client, CREDENTIALS),
    ).resolves.toBeUndefined();
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

describe("readStoredSession", () => {
  it("returns the stored session", async () => {
    const { client } = createAuthDouble();

    await expect(readStoredSession(client)).resolves.toEqual(SESSION);
  });

  it("returns null when storage reports an error", async () => {
    const { client } = createAuthDouble({
      getSession: vi.fn(async () => ({
        data: { session: null },
        error: { code: "storage_error" },
      })),
    });

    await expect(readStoredSession(client)).resolves.toBeNull();
  });

  it("returns null when reading storage throws", async () => {
    const { client } = createAuthDouble({
      getSession: vi.fn(() => {
        throw new Error("unreadable storage");
      }),
    });

    // A corrupt blob must not wedge the app on the loading screen.
    await expect(readStoredSession(client)).resolves.toBeNull();
  });
});

/**
 * M2: a stored session is only a claim. The identity must come from a verified
 * JWT, never from the stored user id.
 */
describe("resolveVerifiedIdentity", () => {
  it("returns the identity when the JWT verifies", async () => {
    const { client } = createAuthDouble();

    await expect(resolveVerifiedIdentity(client, SESSION)).resolves.toEqual({
      userId: USER_ID,
    });
  });

  it("verifies the JWT rather than trusting the stored session", async () => {
    const { auth, client } = createAuthDouble();

    await resolveVerifiedIdentity(client, SESSION);

    expect(auth.getClaims).toHaveBeenCalledTimes(1);
  });

  it("takes the identity from the verified sub", async () => {
    // Storage and the token agree here; the value returned is the sub.
    const { client } = createAuthDouble({
      getClaims: vi.fn(async () => validClaims(USER_ID)),
    });

    const identity = await resolveVerifiedIdentity(client, SESSION);

    expect(identity).toEqual({ userId: USER_ID });
  });

  it("skips verification entirely when nothing usable is stored", async () => {
    const { auth, client } = createAuthDouble();

    await expect(resolveVerifiedIdentity(client, null)).resolves.toBeNull();
    expect(auth.getClaims).not.toHaveBeenCalled();
  });

  it("fails closed for a corrupt stored session without a round trip", async () => {
    const { auth, client } = createAuthDouble();

    await expect(
      resolveVerifiedIdentity(client, { access_token: "trunc" }),
    ).resolves.toBeNull();
    expect(auth.getClaims).not.toHaveBeenCalled();
  });

  it("fails closed when the JWT is invalid", async () => {
    const { client } = createAuthDouble({
      getClaims: vi.fn(async () => ({
        data: null,
        error: { code: "bad_jwt", message: "invalid signature" },
      })),
    });

    await expect(resolveVerifiedIdentity(client, SESSION)).resolves.toBeNull();
  });

  it("fails closed when the JWT has expired", async () => {
    const expired = validClaims();

    expired.data.claims.exp = Math.floor(Date.now() / 1000) - 10;

    const { client } = createAuthDouble({
      getClaims: vi.fn(async () => expired),
    });

    await expect(resolveVerifiedIdentity(client, SESSION)).resolves.toBeNull();
  });

  it("fails closed when the claims carry no sub", async () => {
    const noSub = validClaims();

    delete (noSub.data.claims as Record<string, unknown>).sub;

    const { client } = createAuthDouble({
      getClaims: vi.fn(async () => noSub),
    });

    await expect(resolveVerifiedIdentity(client, SESSION)).resolves.toBeNull();
  });

  it("fails closed when the verified subject does not match the stored user", async () => {
    // A stored session whose user was swapped while the token was left intact.
    const { client } = createAuthDouble({
      getClaims: vi.fn(async () =>
        validClaims("00000000-0000-4000-9000-0000000000ff"),
      ),
    });

    await expect(resolveVerifiedIdentity(client, SESSION)).resolves.toBeNull();
  });

  it("fails closed when verification throws", async () => {
    const { client } = createAuthDouble({
      getClaims: vi.fn(() => {
        throw new Error("jwks fetch failed");
      }),
    });

    await expect(resolveVerifiedIdentity(client, SESSION)).resolves.toBeNull();
  });

  it("fails closed when verification rejects", async () => {
    const { client } = createAuthDouble({
      getClaims: vi.fn(async () => {
        throw new Error("network down");
      }),
    });

    await expect(resolveVerifiedIdentity(client, SESSION)).resolves.toBeNull();
  });

  it("never propagates a verification error to the caller", async () => {
    const { client } = createAuthDouble({
      getClaims: vi.fn(async () => ({
        data: null,
        error: {
          code: "bad_jwt",
          message: "token for athlete-a@example.test failed verification",
        },
      })),
    });

    // Returns null rather than raising, so no raw error can reach a screen.
    await expect(resolveVerifiedIdentity(client, SESSION)).resolves.toBeNull();
  });
});
