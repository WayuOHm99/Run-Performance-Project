/**
 * Encrypted Supabase session storage.
 *
 * TASK-009 persisted the Supabase session as plaintext JSON in AsyncStorage,
 * which is not encrypted at rest on device. This module replaces that with an
 * AES-256-GCM envelope:
 *
 *   - the AES key lives in the platform keystore (Expo SecureStore);
 *   - only a versioned, authenticated ciphertext envelope lives in AsyncStorage;
 *   - the plaintext session, its tokens, the email, the user id, and the claims
 *     are never written to either backend in readable form.
 *
 * Everything here is pure with respect to the platform: the keystore, the
 * ciphertext store, and the AES-GCM primitive are injected as ports. That is
 * what lets the whole failure matrix be tested in plain Node with a real
 * AES-GCM implementation, rather than with a hand-rolled stand-in cipher. The
 * native bindings live in `native-session-storage.ts`.
 *
 * ## The one rule
 *
 * **Fail closed, never fall back to plaintext.** A missing key, a missing
 * ciphertext, a legacy plaintext value, a malformed envelope, an unknown
 * version, a tampered tag, and a backend that throws all resolve to "no
 * session", which the auth gate reads as signed-out. There is no code path that
 * returns a session that was not authenticated by GCM.
 *
 * Because a size limit forced AES-CTR in older examples, note explicitly: GCM
 * is used precisely so that tampering is *detected* rather than silently
 * decrypted into a forged session.
 */

import type { SupportedStorage } from "@supabase/supabase-js";

/** Bumping this invalidates every stored envelope, which signs users out. */
const ENVELOPE_VERSION = 1;
const ENVELOPE_ALGORITHM = "AES-256-GCM";
const KEY_NAME_PREFIX = "runperf.sessionkey.";

/**
 * The AES key, held in the platform keystore.
 *
 * Only ever holds base64 key material. A session, a token, an email, or a user
 * id must never be passed to this port.
 */
export type SessionKeyStore = {
  read(keyName: string): Promise<string | null>;
  write(keyName: string, keyMaterial: string): Promise<void>;
  remove(keyName: string): Promise<void>;
};

/** The ciphertext envelope, held in AsyncStorage. Never plaintext. */
export type CiphertextStore = {
  read(storageKey: string): Promise<string | null>;
  write(storageKey: string, envelope: string): Promise<void>;
  remove(storageKey: string): Promise<void>;
};

export type SealInput = {
  readonly keyMaterial: string;
  readonly plaintext: string;
  /** Bound into the GCM tag; a mismatch must fail authentication. */
  readonly additionalData: string;
};

export type OpenInput = {
  readonly keyMaterial: string;
  /** base64 of nonce ‖ ciphertext ‖ tag. */
  readonly sealed: string;
  readonly additionalData: string;
};

/**
 * An authenticated AES-256-GCM primitive.
 *
 * `seal` must generate a fresh nonce per call, so sealing identical plaintext
 * twice produces different output. `open` must reject on a failed tag.
 */
export type SessionCrypto = {
  generateKey(): Promise<string>;
  seal(input: SealInput): Promise<string>;
  open(input: OpenInput): Promise<string>;
};

export type SecureSessionStoragePorts = {
  readonly keys: SessionKeyStore;
  readonly ciphertexts: CiphertextStore;
  readonly crypto: SessionCrypto;
};

/**
 * The only error shape that leaves this module.
 *
 * The message is chosen from a closed set and no `cause` is ever attached, so a
 * raw native error, a storage value, a key, a token, an email, or a user id
 * cannot escape through an error that some caller decides to render or log.
 */
export class SessionStorageError extends Error {
  override readonly name = "SessionStorageError";
  readonly code: "write-failed" | "remove-failed";

  constructor(code: "write-failed" | "remove-failed") {
    super(
      code === "write-failed"
        ? "The session could not be stored securely."
        : "The stored session could not be fully removed.",
    );
    this.code = code;
  }
}

/**
 * SecureStore keys accept alphanumerics, `.`, `-`, and `_` only, so anything
 * else in the Supabase storage key is folded to `_`.
 */
export function sessionKeyName(storageKey: string): string {
  return `${KEY_NAME_PREFIX}${storageKey.replace(/[^A-Za-z0-9._-]/g, "_")}`;
}

/**
 * The additional authenticated data bound into every envelope.
 *
 * Binding the version, the algorithm, and the storage key means an envelope
 * cannot be replayed under a different storage key or relabelled as a different
 * version without failing the tag.
 */
export function additionalDataFor(storageKey: string): string {
  return `runperf.session|v${ENVELOPE_VERSION}|${ENVELOPE_ALGORITHM}|${storageKey}`;
}

type EnvelopeReadResult =
  | { readonly kind: "envelope"; readonly sealed: string }
  /** Legacy plaintext, corrupt JSON, or a shape we do not recognise. */
  | { readonly kind: "unrecognized" }
  | { readonly kind: "unsupported-version" };

export function encodeEnvelope(sealed: string): string {
  return JSON.stringify({
    v: ENVELOPE_VERSION,
    alg: ENVELOPE_ALGORITHM,
    d: sealed,
  });
}

/**
 * Classifies a stored value without ever surfacing it.
 *
 * A TASK-009 plaintext session parses as JSON perfectly well, so recognition is
 * positive: a value counts as an envelope only if it carries our version, our
 * algorithm, and a non-empty payload. Nothing else about the value is read,
 * returned, or reported — that is what keeps a legacy token out of logs and
 * errors.
 */
export function readEnvelope(raw: string): EnvelopeReadResult {
  let parsed: unknown;

  try {
    parsed = JSON.parse(raw);
  } catch {
    return { kind: "unrecognized" };
  }

  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { kind: "unrecognized" };
  }

  const candidate = parsed as { v?: unknown; alg?: unknown; d?: unknown };

  if (typeof candidate.v !== "number" || candidate.alg !== ENVELOPE_ALGORITHM) {
    return { kind: "unrecognized" };
  }

  if (candidate.v !== ENVELOPE_VERSION) {
    return { kind: "unsupported-version" };
  }

  if (typeof candidate.d !== "string" || candidate.d.length === 0) {
    return { kind: "unrecognized" };
  }

  return { kind: "envelope", sealed: candidate.d };
}

/**
 * Builds the Supabase storage adapter.
 *
 * Supabase calls `getItem`/`setItem`/`removeItem` with its own storage key; we
 * derive the keystore entry name from it, so a project change cannot read a
 * previous project's envelope with the wrong key.
 */
export function createSecureSessionStorage(
  ports: SecureSessionStoragePorts,
): SupportedStorage {
  /**
   * Best-effort destruction of both sides.
   *
   * Always attempts both backends even when the first throws, because leaving
   * an orphaned key or an undecryptable envelope behind is exactly the state
   * that causes a confusing repeat failure on the next launch. Failures are
   * swallowed: purging is already the recovery path, and there is nothing
   * useful a caller could do with the reason.
   */
  async function purge(storageKey: string): Promise<void> {
    await Promise.allSettled([
      ports.keys.remove(sessionKeyName(storageKey)),
      ports.ciphertexts.remove(storageKey),
    ]);
  }

  return {
    async getItem(storageKey: string): Promise<string | null> {
      let raw: string | null;

      try {
        raw = await ports.ciphertexts.read(storageKey);
      } catch {
        // A backend that throws is treated as transient: fail closed to
        // signed-out, but do not destroy data we were simply unable to read.
        return null;
      }

      if (raw === null) {
        // Nothing to decrypt. Drop any orphaned key so a later write starts
        // from a clean pair rather than reusing a key with no ciphertext.
        await purge(storageKey);
        return null;
      }

      const envelope = readEnvelope(raw);

      if (envelope.kind !== "envelope") {
        // Legacy TASK-009 plaintext, a malformed envelope, and an unknown
        // version all land here. The value is deleted, never migrated, never
        // parsed for its contents, and never reported.
        await purge(storageKey);
        return null;
      }

      let keyMaterial: string | null;

      try {
        keyMaterial = await ports.keys.read(sessionKeyName(storageKey));
      } catch {
        return null;
      }

      if (keyMaterial === null) {
        // The envelope can never be opened again; keeping it serves no one.
        await purge(storageKey);
        return null;
      }

      try {
        return await ports.crypto.open({
          keyMaterial,
          sealed: envelope.sealed,
          additionalData: additionalDataFor(storageKey),
        });
      } catch {
        // Failed tag, corrupted ciphertext, or a decrypt error. The stored
        // value is permanently unusable, so it goes.
        await purge(storageKey);
        return null;
      }
    },

    async setItem(storageKey: string, value: string): Promise<void> {
      const keyName = sessionKeyName(storageKey);
      let keyMaterial: string | null;

      try {
        keyMaterial = await ports.keys.read(keyName);
      } catch {
        // Nothing was written, so there is no partial state to clean up.
        throw new SessionStorageError("write-failed");
      }

      if (keyMaterial === null) {
        try {
          keyMaterial = await ports.crypto.generateKey();
          await ports.keys.write(keyName, keyMaterial);
        } catch {
          await purge(storageKey);
          throw new SessionStorageError("write-failed");
        }
      }

      let sealed: string;

      try {
        sealed = await ports.crypto.seal({
          keyMaterial,
          plaintext: value,
          additionalData: additionalDataFor(storageKey),
        });
      } catch {
        await purge(storageKey);
        throw new SessionStorageError("write-failed");
      }

      try {
        await ports.ciphertexts.write(storageKey, encodeEnvelope(sealed));
      } catch {
        // The key and any previous envelope are now an inconsistent pair, so
        // both go and the user signs in again. Throwing is required: reporting
        // success here would let Supabase believe a session is persisted when
        // it is not.
        await purge(storageKey);
        throw new SessionStorageError("write-failed");
      }
    },

    async removeItem(storageKey: string): Promise<void> {
      const results = await Promise.allSettled([
        ports.keys.remove(sessionKeyName(storageKey)),
        ports.ciphertexts.remove(storageKey),
      ]);

      if (results.some((result) => result.status === "rejected")) {
        // Both sides were still attempted. Removing the key alone already
        // renders any surviving envelope undecryptable, so the common
        // single-side failure still ends in signed-out on the next launch.
        throw new SessionStorageError("remove-failed");
      }
    },
  };
}
