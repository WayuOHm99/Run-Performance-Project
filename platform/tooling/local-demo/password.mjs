// The generated local demo password, decision 7.
//
// Random per reset, never printed, never committed. It exists only so the two
// synthetic accounts can be created through the real Auth signup flow and then
// signed into by hand.
//
// `randomBytes` rather than `Math.random`: this is a credential, and using a
// non-cryptographic source for one is the kind of thing that gets copied into
// somewhere it matters.

import { randomBytes } from "node:crypto";

// 24 bytes of entropy, base64url-encoded to 32 characters. Comfortably above the
// local `minimum_password_length = 6`, and URL-safe so it survives being pasted
// into any field without escaping.
const PASSWORD_ENTROPY_BYTES = 24;

export function generateLocalDemoPassword() {
  return randomBytes(PASSWORD_ENTROPY_BYTES).toString("base64url");
}

// Used by the tests, and by nothing else. A password that fails this is a bug in
// generation, not a user-supplied value to validate.
export function isPlausibleLocalDemoPassword(value) {
  return typeof value === "string" && /^[A-Za-z0-9_-]{32}$/.test(value);
}
