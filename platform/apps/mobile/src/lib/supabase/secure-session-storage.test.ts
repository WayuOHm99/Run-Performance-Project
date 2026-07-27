/**
 * Tests for the encrypted session storage adapter.
 *
 * The AES-GCM port under test is backed by **WebCrypto**, which is a real
 * authenticated AES-256-GCM implementation present in the Node runtime. That is
 * a deliberate choice: the cryptography is not reimplemented here, so tamper
 * detection, nonce freshness, and AAD binding are genuinely exercised rather
 * than simulated by a stand-in that would pass by construction. The production
 * port maps the same interface onto `expo-crypto`'s native AES-GCM.
 *
 * Every fixture is synthetic. The markers below are recognisable strings used
 * to prove they never appear in stored data, an error, or a log.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { canEnterRoleArea, resolveAuthGate } from "../../features/auth/gate";
import {
  additionalDataFor,
  createSecureSessionStorage,
  encodeEnvelope,
  readEnvelope,
  sessionKeyName,
  SessionStorageError,
  type CiphertextStore,
  type SessionCrypto,
  type SessionKeyStore,
} from "./secure-session-storage";

const STORAGE_KEY = "sb-synthetic-project-auth-token";
const KEY_NAME = sessionKeyName(STORAGE_KEY);

const NONCE_BYTES = 12;

/** Synthetic markers. None of these is a real credential or a real person. */
const MARKERS = {
  accessToken: "SYNTHETIC-ACCESS-TOKEN-MARKER",
  refreshToken: "SYNTHETIC-REFRESH-TOKEN-MARKER",
  email: "athlete-a@example.test",
  userId: "00000000-0000-4000-8000-000000000001",
  claim: "SYNTHETIC-CLAIM-MARKER",
} as const;

function syntheticSession(padding = 0): string {
  return JSON.stringify({
    access_token: MARKERS.accessToken,
    refresh_token: MARKERS.refreshToken,
    expires_at: 4102444800,
    token_type: "bearer",
    user: {
      id: MARKERS.userId,
      email: MARKERS.email,
      app_metadata: { claim: MARKERS.claim },
    },
    padding: "p".repeat(padding),
  });
}

// --- base64 helpers, test-side only -----------------------------------------

function toBase64(bytes: Uint8Array): string {
  let binary = "";

  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }

  return btoa(binary);
}

function fromBase64(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
}

function utf8(value: string): ArrayBuffer {
  const bytes = new TextEncoder().encode(value);

  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
}

/**
 * `SupportedStorage` lets an implementation be synchronous, so its methods are
 * typed as possibly-not-a-promise. Ours are async; this makes that usable.
 */
function ignoringFailure(operation: void | Promise<void>): Promise<void> {
  return Promise.resolve(operation).catch(() => undefined);
}

// --- a real AES-256-GCM port -------------------------------------------------

async function importAesKey(keyMaterial: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    fromBase64(keyMaterial) as unknown as ArrayBuffer,
    { name: "AES-GCM" },
    true,
    ["encrypt", "decrypt"],
  );
}

const webCryptoSessionCrypto: SessionCrypto = {
  async generateKey() {
    const key = await crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      true,
      ["encrypt", "decrypt"],
    );
    const raw = await crypto.subtle.exportKey("raw", key);

    return toBase64(new Uint8Array(raw));
  },

  async seal({ keyMaterial, plaintext, additionalData }) {
    const key = await importAesKey(keyMaterial);
    // Fresh per call. This is what makes two identical writes differ.
    const nonce = crypto.getRandomValues(new Uint8Array(NONCE_BYTES));
    const ciphertext = await crypto.subtle.encrypt(
      {
        name: "AES-GCM",
        iv: nonce,
        additionalData: utf8(additionalData),
        tagLength: 128,
      },
      key,
      utf8(plaintext),
    );
    // nonce ‖ ciphertext ‖ tag, matching expo-crypto's combined layout.
    const combined = new Uint8Array(NONCE_BYTES + ciphertext.byteLength);
    combined.set(nonce, 0);
    combined.set(new Uint8Array(ciphertext), NONCE_BYTES);

    return toBase64(combined);
  },

  async open({ keyMaterial, sealed, additionalData }) {
    const key = await importAesKey(keyMaterial);
    const combined = fromBase64(sealed);
    const plaintext = await crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: combined.slice(0, NONCE_BYTES),
        additionalData: utf8(additionalData),
        tagLength: 128,
      },
      key,
      combined.slice(NONCE_BYTES) as unknown as ArrayBuffer,
    );

    return new TextDecoder().decode(plaintext);
  },
};

// --- harness -----------------------------------------------------------------

type FailurePoints = {
  read?: boolean;
  write?: boolean;
  remove?: boolean;
};

type Harness = {
  storage: ReturnType<typeof createSecureSessionStorage>;
  keys: Map<string, string>;
  ciphertexts: Map<string, string>;
  attempts: string[];
};

function createHarness(
  options: {
    keyFailures?: FailurePoints;
    ciphertextFailures?: FailurePoints;
    crypto?: Partial<SessionCrypto>;
  } = {},
): Harness {
  const keys = new Map<string, string>();
  const ciphertexts = new Map<string, string>();
  const attempts: string[] = [];
  const keyFailures = options.keyFailures ?? {};
  const ciphertextFailures = options.ciphertextFailures ?? {};

  const keyStore: SessionKeyStore = {
    async read(name) {
      attempts.push("keys.read");
      if (keyFailures.read) throw new Error("synthetic keystore read failure");
      return keys.get(name) ?? null;
    },
    async write(name, material) {
      attempts.push("keys.write");
      if (keyFailures.write)
        throw new Error("synthetic keystore write failure");
      keys.set(name, material);
    },
    async remove(name) {
      attempts.push("keys.remove");
      if (keyFailures.remove) {
        throw new Error("synthetic keystore remove failure");
      }
      keys.delete(name);
    },
  };

  const ciphertextStore: CiphertextStore = {
    async read(key) {
      attempts.push("ciphertexts.read");
      if (ciphertextFailures.read) {
        throw new Error("synthetic ciphertext read failure");
      }
      return ciphertexts.get(key) ?? null;
    },
    async write(key, envelope) {
      attempts.push("ciphertexts.write");
      if (ciphertextFailures.write) {
        throw new Error("synthetic ciphertext write failure");
      }
      ciphertexts.set(key, envelope);
    },
    async remove(key) {
      attempts.push("ciphertexts.remove");
      if (ciphertextFailures.remove) {
        throw new Error("synthetic ciphertext remove failure");
      }
      ciphertexts.delete(key);
    },
  };

  return {
    storage: createSecureSessionStorage({
      keys: keyStore,
      ciphertexts: ciphertextStore,
      crypto: { ...webCryptoSessionCrypto, ...options.crypto },
    }),
    keys,
    ciphertexts,
    attempts,
  };
}

/** Rewrites the payload of a stored envelope, keeping the envelope shape. */
function mutateSealed(
  harness: Harness,
  mutate: (bytes: Uint8Array) => Uint8Array,
): void {
  const stored = harness.ciphertexts.get(STORAGE_KEY);
  if (stored === undefined) throw new Error("expected a stored envelope");

  const envelope = readEnvelope(stored);
  if (envelope.kind !== "envelope") throw new Error("expected an envelope");

  harness.ciphertexts.set(
    STORAGE_KEY,
    encodeEnvelope(toBase64(mutate(fromBase64(envelope.sealed)))),
  );
}

function flipByte(bytes: Uint8Array, index: number): Uint8Array {
  const copy = Uint8Array.from(bytes);
  const current = copy[index];
  if (current === undefined) throw new Error("index out of range");
  copy[index] = current ^ 0xff;

  return copy;
}

afterEach(() => {
  vi.restoreAllMocks();
});

// --- round trip --------------------------------------------------------------

describe("round trip", () => {
  it("stores and restores a session", async () => {
    const harness = createHarness();
    const session = syntheticSession();

    await harness.storage.setItem(STORAGE_KEY, session);

    expect(await harness.storage.getItem(STORAGE_KEY)).toBe(session);
  });

  it("round-trips a payload larger than 4 KB", async () => {
    const harness = createHarness();
    const session = syntheticSession(6000);

    expect(session.length).toBeGreaterThan(4096);

    await harness.storage.setItem(STORAGE_KEY, session);

    expect(await harness.storage.getItem(STORAGE_KEY)).toBe(session);
  });

  it("keeps only key material in the keystore", async () => {
    const harness = createHarness();

    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    const stored = [...harness.keys.values()].join("|");

    expect(harness.keys.size).toBe(1);
    expect(harness.keys.has(KEY_NAME)).toBe(true);
    // A 256-bit key is 32 bytes, so it cannot contain a session.
    expect(fromBase64(stored)).toHaveLength(32);

    for (const marker of Object.values(MARKERS)) {
      expect(stored).not.toContain(marker);
    }
  });

  it("stores only a recognisable versioned envelope", async () => {
    const harness = createHarness();

    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    const stored = harness.ciphertexts.get(STORAGE_KEY) ?? "";

    expect(JSON.parse(stored)).toMatchObject({ v: 1, alg: "AES-256-GCM" });
    expect(readEnvelope(stored).kind).toBe("envelope");
  });

  it("leaves no readable token, email, user id, or claim in the ciphertext", async () => {
    const harness = createHarness();

    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    const stored = harness.ciphertexts.get(STORAGE_KEY) ?? "";
    const envelope = readEnvelope(stored);
    if (envelope.kind !== "envelope") throw new Error("expected an envelope");

    const decodedBytes = new TextDecoder().decode(fromBase64(envelope.sealed));

    for (const marker of Object.values(MARKERS)) {
      expect(stored).not.toContain(marker);
      // Also checked after base64-decoding, so a merely-encoded value fails.
      expect(decodedBytes).not.toContain(marker);
    }
  });

  it("produces a different envelope each time the same session is written", async () => {
    const harness = createHarness();
    const session = syntheticSession();

    await harness.storage.setItem(STORAGE_KEY, session);
    const first = harness.ciphertexts.get(STORAGE_KEY);

    await harness.storage.setItem(STORAGE_KEY, session);
    const second = harness.ciphertexts.get(STORAGE_KEY);

    expect(first).not.toBe(second);
    // The key is reused, so it is the fresh nonce that differs.
    expect(harness.keys.size).toBe(1);
    expect(await harness.storage.getItem(STORAGE_KEY)).toBe(session);
  });
});

// --- negative: stored value ---------------------------------------------------

describe("unusable stored values fail closed", () => {
  it("deletes a legacy TASK-009 plaintext session and signs out", async () => {
    const harness = createHarness();
    // Exactly what TASK-009 wrote: the raw session JSON, unencrypted.
    harness.ciphertexts.set(STORAGE_KEY, syntheticSession());
    harness.keys.set(KEY_NAME, "synthetic-legacy-key-material");

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
    // Deleted, never migrated.
    expect(harness.ciphertexts.has(STORAGE_KEY)).toBe(false);
    expect(harness.keys.has(KEY_NAME)).toBe(false);
  });

  it("fails closed on a modified ciphertext", async () => {
    const harness = createHarness();
    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    // A byte inside the ciphertext body, past the nonce.
    mutateSealed(harness, (bytes) => flipByte(bytes, NONCE_BYTES + 1));

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
    expect(harness.ciphertexts.has(STORAGE_KEY)).toBe(false);
    expect(harness.keys.has(KEY_NAME)).toBe(false);
  });

  it("fails closed on a modified authentication tag", async () => {
    const harness = createHarness();
    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    // The tag is the trailing 16 bytes.
    mutateSealed(harness, (bytes) => flipByte(bytes, bytes.length - 1));

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
    expect(harness.ciphertexts.has(STORAGE_KEY)).toBe(false);
  });

  it("fails closed on a modified nonce", async () => {
    const harness = createHarness();
    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    mutateSealed(harness, (bytes) => flipByte(bytes, 0));

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("fails closed when the envelope is replayed under another storage key", async () => {
    const harness = createHarness();
    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    const envelope = harness.ciphertexts.get(STORAGE_KEY) ?? "";
    const otherKey = "sb-other-project-auth-token";
    harness.ciphertexts.set(otherKey, envelope);
    harness.keys.set(
      sessionKeyName(otherKey),
      harness.keys.get(KEY_NAME) ?? "",
    );

    // The storage key is bound into the AAD, so the tag no longer verifies.
    expect(await harness.storage.getItem(otherKey)).toBeNull();
  });

  it.each([
    ["not json at all", "this-is-not-json"],
    ["a json array", "[]"],
    ["a json string", '"just-a-string"'],
    ["an envelope with no version", JSON.stringify({ alg: "AES-256-GCM" })],
    [
      "an envelope with the wrong algorithm",
      JSON.stringify({ v: 1, alg: "AES-256-CTR", d: "AAAA" }),
    ],
    [
      "an envelope with no payload",
      JSON.stringify({ v: 1, alg: "AES-256-GCM", d: "" }),
    ],
    [
      "an envelope with a non-string payload",
      JSON.stringify({ v: 1, alg: "AES-256-GCM", d: 42 }),
    ],
  ])("deletes %s and signs out", async (_label, stored) => {
    const harness = createHarness();
    harness.ciphertexts.set(STORAGE_KEY, stored);
    harness.keys.set(KEY_NAME, "synthetic-key-material");

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
    expect(harness.ciphertexts.has(STORAGE_KEY)).toBe(false);
    expect(harness.keys.has(KEY_NAME)).toBe(false);
  });

  it("deletes an unsupported envelope version and signs out", async () => {
    const harness = createHarness();
    harness.ciphertexts.set(
      STORAGE_KEY,
      JSON.stringify({ v: 99, alg: "AES-256-GCM", d: "AAAA" }),
    );
    harness.keys.set(KEY_NAME, "synthetic-key-material");

    expect(readEnvelope(harness.ciphertexts.get(STORAGE_KEY) ?? "").kind).toBe(
      "unsupported-version",
    );
    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
    expect(harness.ciphertexts.has(STORAGE_KEY)).toBe(false);
    expect(harness.keys.has(KEY_NAME)).toBe(false);
  });
});

// --- negative: missing halves -------------------------------------------------

describe("missing key material or ciphertext", () => {
  it("returns null and clears the orphaned key when no ciphertext exists", async () => {
    const harness = createHarness();
    harness.keys.set(KEY_NAME, "synthetic-orphaned-key-material");

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
    expect(harness.keys.has(KEY_NAME)).toBe(false);
  });

  it("returns null when nothing is stored at all", async () => {
    const harness = createHarness();

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("deletes an undecryptable envelope when the key is missing", async () => {
    const harness = createHarness();
    await harness.storage.setItem(STORAGE_KEY, syntheticSession());
    harness.keys.delete(KEY_NAME);

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
    expect(harness.ciphertexts.has(STORAGE_KEY)).toBe(false);
  });

  it("fails closed when the stored key is the wrong key", async () => {
    const harness = createHarness();
    await harness.storage.setItem(STORAGE_KEY, syntheticSession());
    harness.keys.set(KEY_NAME, await webCryptoSessionCrypto.generateKey());

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
  });
});

// --- negative: backend failures -----------------------------------------------

describe("storage backend failures", () => {
  it("returns null when the ciphertext store rejects a read", async () => {
    const harness = createHarness({ ciphertextFailures: { read: true } });

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("returns null when the keystore rejects a read", async () => {
    const good = createHarness();
    await good.storage.setItem(STORAGE_KEY, syntheticSession());
    const envelope = good.ciphertexts.get(STORAGE_KEY) ?? "";

    const harness = createHarness({ keyFailures: { read: true } });
    harness.ciphertexts.set(STORAGE_KEY, envelope);

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("does not destroy stored data on a transient read failure", async () => {
    const harness = createHarness({ ciphertextFailures: { read: true } });
    harness.ciphertexts.set(STORAGE_KEY, "an-envelope-we-could-not-read");
    harness.keys.set(KEY_NAME, "synthetic-key-material");

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
    // A backend that is merely unavailable must not cost the user their key.
    expect(harness.ciphertexts.has(STORAGE_KEY)).toBe(true);
    expect(harness.keys.has(KEY_NAME)).toBe(true);
  });

  it("reports failure and cleans up when the keystore write fails", async () => {
    const harness = createHarness({ keyFailures: { write: true } });

    await expect(
      harness.storage.setItem(STORAGE_KEY, syntheticSession()),
    ).rejects.toBeInstanceOf(SessionStorageError);

    expect(harness.keys.size).toBe(0);
    expect(harness.ciphertexts.size).toBe(0);
  });

  it("reports failure and cleans up the key when the ciphertext write fails", async () => {
    const harness = createHarness({ ciphertextFailures: { write: true } });

    await expect(
      harness.storage.setItem(STORAGE_KEY, syntheticSession()),
    ).rejects.toBeInstanceOf(SessionStorageError);

    // The key was written first; leaving it behind would be an unusable pair.
    expect(harness.keys.size).toBe(0);
    expect(harness.ciphertexts.size).toBe(0);
  });

  it("reports failure and cleans up when encryption fails", async () => {
    const harness = createHarness({
      crypto: {
        seal() {
          return Promise.reject(new Error("synthetic encryption failure"));
        },
      },
    });

    await expect(
      harness.storage.setItem(STORAGE_KEY, syntheticSession()),
    ).rejects.toBeInstanceOf(SessionStorageError);

    expect(harness.keys.size).toBe(0);
    expect(harness.ciphertexts.size).toBe(0);
  });

  it("reports failure when the keystore rejects the read before a write", async () => {
    const harness = createHarness({ keyFailures: { read: true } });

    await expect(
      harness.storage.setItem(STORAGE_KEY, syntheticSession()),
    ).rejects.toBeInstanceOf(SessionStorageError);

    expect(harness.ciphertexts.size).toBe(0);
  });

  it("never writes plaintext when encryption fails", async () => {
    const harness = createHarness({
      crypto: {
        seal() {
          return Promise.reject(new Error("synthetic encryption failure"));
        },
      },
    });

    await ignoringFailure(
      harness.storage.setItem(STORAGE_KEY, syntheticSession()),
    );

    const everythingStored = [
      ...harness.ciphertexts.values(),
      ...harness.keys.values(),
    ].join("|");

    for (const marker of Object.values(MARKERS)) {
      expect(everythingStored).not.toContain(marker);
    }
  });
});

// --- negative: removal --------------------------------------------------------

describe("removal", () => {
  it("clears both backends", async () => {
    const harness = createHarness();
    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    await harness.storage.removeItem(STORAGE_KEY);

    expect(harness.keys.size).toBe(0);
    expect(harness.ciphertexts.size).toBe(0);
    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("still clears the ciphertext when the keystore removal fails", async () => {
    const harness = createHarness({ keyFailures: { remove: true } });
    harness.keys.set(KEY_NAME, "synthetic-key-material");
    harness.ciphertexts.set(STORAGE_KEY, "an-envelope");

    await expect(
      harness.storage.removeItem(STORAGE_KEY),
    ).rejects.toBeInstanceOf(SessionStorageError);

    expect(harness.attempts).toContain("keys.remove");
    expect(harness.attempts).toContain("ciphertexts.remove");
    expect(harness.ciphertexts.size).toBe(0);
  });

  it("still clears the key when the ciphertext removal fails", async () => {
    const harness = createHarness({ ciphertextFailures: { remove: true } });
    harness.keys.set(KEY_NAME, "synthetic-key-material");
    harness.ciphertexts.set(STORAGE_KEY, "an-envelope");

    await expect(
      harness.storage.removeItem(STORAGE_KEY),
    ).rejects.toBeInstanceOf(SessionStorageError);

    expect(harness.attempts).toContain("keys.remove");
    expect(harness.attempts).toContain("ciphertexts.remove");
    // The surviving envelope is now permanently undecryptable.
    expect(harness.keys.size).toBe(0);
  });

  it("leaves a surviving envelope unreadable after a partial removal", async () => {
    const harness = createHarness({ ciphertextFailures: { remove: true } });
    await harness.storage.setItem(STORAGE_KEY, syntheticSession());

    await ignoringFailure(harness.storage.removeItem(STORAGE_KEY));

    expect(harness.ciphertexts.has(STORAGE_KEY)).toBe(true);
    // The key is gone, so the old identity cannot be resurrected.
    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();
  });
});

// --- no leakage ---------------------------------------------------------------

describe("nothing sensitive leaks", () => {
  it("logs nothing during any operation, including failures", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map(
      (level) => vi.spyOn(console, level).mockImplementation(() => undefined),
    );

    const good = createHarness();
    await good.storage.setItem(STORAGE_KEY, syntheticSession());
    await good.storage.getItem(STORAGE_KEY);
    await good.storage.removeItem(STORAGE_KEY);

    const legacy = createHarness();
    legacy.ciphertexts.set(STORAGE_KEY, syntheticSession());
    await legacy.storage.getItem(STORAGE_KEY);

    const failing = createHarness({
      keyFailures: { write: true, remove: true },
      ciphertextFailures: { read: true, write: true, remove: true },
    });
    await failing.storage.getItem(STORAGE_KEY);
    await ignoringFailure(
      failing.storage.setItem(STORAGE_KEY, syntheticSession()),
    );
    await ignoringFailure(failing.storage.removeItem(STORAGE_KEY));

    for (const spy of spies) {
      expect(spy).not.toHaveBeenCalled();
    }
  });

  it.each([
    [
      "a ciphertext write failure",
      { ciphertextFailures: { write: true } } as const,
    ],
    ["a keystore write failure", { keyFailures: { write: true } } as const],
  ])("throws a sanitized error on %s", async (_label, options) => {
    const harness = createHarness(options);
    let thrown: unknown;

    try {
      await harness.storage.setItem(STORAGE_KEY, syntheticSession());
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(SessionStorageError);

    const error = thrown as SessionStorageError;
    const serialized = `${error.name}|${error.message}|${error.stack ?? ""}`;

    // No raw native error is carried along for a caller to render.
    expect(error.cause).toBeUndefined();
    expect(serialized).not.toContain("synthetic keystore");
    expect(serialized).not.toContain("synthetic ciphertext");

    for (const marker of Object.values(MARKERS)) {
      expect(serialized).not.toContain(marker);
    }
  });

  it("does not echo the legacy value in anything it returns or throws", async () => {
    const harness = createHarness();
    harness.ciphertexts.set(STORAGE_KEY, syntheticSession());

    // Returns null rather than throwing, so nothing can carry the value out.
    await expect(harness.storage.getItem(STORAGE_KEY)).resolves.toBeNull();
  });
});

// --- the boundary with the auth gate -------------------------------------------

describe("a storage failure cannot authorize a role area", () => {
  it("keeps athlete and coach closed when nothing could be restored", async () => {
    const harness = createHarness({ ciphertextFailures: { read: true } });

    const restored = await harness.storage.getItem(STORAGE_KEY);
    expect(restored).toBeNull();

    // A null restore is a signed-out restore. This is the real gate.
    const gate = resolveAuthGate({
      sessionRestored: true,
      identity: null,
      awaitingEmailConfirmation: false,
      account: { kind: "loading" },
    });

    expect(gate.status).toBe("signed-out");
    expect(canEnterRoleArea(gate, "athlete")).toBe(false);
    expect(canEnterRoleArea(gate, "coach")).toBe(false);
  });

  it("keeps athlete and coach closed after a legacy session is purged", async () => {
    const harness = createHarness();
    harness.ciphertexts.set(STORAGE_KEY, syntheticSession());

    expect(await harness.storage.getItem(STORAGE_KEY)).toBeNull();

    const gate = resolveAuthGate({
      sessionRestored: true,
      identity: null,
      awaitingEmailConfirmation: false,
      account: { kind: "loading" },
    });

    expect(canEnterRoleArea(gate, "athlete")).toBe(false);
    expect(canEnterRoleArea(gate, "coach")).toBe(false);
  });
});

// --- helpers ------------------------------------------------------------------

describe("key naming and additional data", () => {
  it("derives a SecureStore-safe key name", () => {
    expect(sessionKeyName(STORAGE_KEY)).toBe(
      `runperf.sessionkey.${STORAGE_KEY}`,
    );
    expect(sessionKeyName("sb:weird/key token")).toBe(
      "runperf.sessionkey.sb_weird_key_token",
    );
  });

  it("binds version, algorithm, and storage key into the additional data", () => {
    const aad = additionalDataFor(STORAGE_KEY);

    expect(aad).toContain("v1");
    expect(aad).toContain("AES-256-GCM");
    expect(aad).toContain(STORAGE_KEY);
    expect(additionalDataFor("other-key")).not.toBe(aad);
  });
});
