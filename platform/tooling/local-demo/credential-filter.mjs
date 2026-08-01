// The credential-filter boundary.
//
// `supabase status -o json` returns a document containing, among other things:
//
//   ANON_KEY, DB_URL, JWT_SECRET, SECRET_KEY, SERVICE_ROLE_KEY,
//   S3_PROTOCOL_ACCESS_KEY_ID, S3_PROTOCOL_ACCESS_KEY_SECRET
//
// Decision 5: only the validated publishable field may cross this boundary. This
// module is therefore the *only* place in the tooling that holds that document,
// and the only value it ever returns is a freshly constructed object with two
// fields. The raw text is never returned, logged, written, cached, or attached to
// an error.
//
// The parsed document is deliberately not spread, merged, or destructured with a
// rest element anywhere below. Every field is read by name, so a future Supabase
// CLI release that adds a new secret cannot widen what escapes.
//
// Note on the pinned CLI (2.109.1): it exposes `PUBLISHABLE_KEY` in the
// `sb_publishable_` format, so no weakening of the rule and no blocker report is
// required. If a future pin stops providing it, `extractLocalCredentials` fails
// closed here rather than falling back to `ANON_KEY`, which is a legacy JWT.

import { assertCanonicalLocalUrl } from "./endpoint.mjs";
import {
  runCapturedStdout,
  subprocessFailure,
  succeeded,
} from "./subprocess.mjs";

const PUBLISHABLE_KEY_PATTERN = /^sb_publishable_[A-Za-z0-9_-]{20,}$/;

const SERVER_CAPABLE_KEY_PREFIXES = [
  "sb_secret_",
  "eyJ",
  "postgres://",
  "postgresql://",
  "service_role",
];

export class DemoCredentialError extends Error {
  name = "DemoCredentialError";
}

// Every message here is a fixed string. None includes the offending value, the
// surrounding document, or a substring of either.
export function extractLocalCredentials(statusJsonText) {
  let document;

  try {
    document = JSON.parse(statusJsonText);
  } catch {
    // The parse error's message would quote the input. It is discarded.
    throw new DemoCredentialError(
      "Could not read the local Supabase status document.",
    );
  }

  if (document === null || typeof document !== "object") {
    throw new DemoCredentialError(
      "The local Supabase status document has an unexpected shape.",
    );
  }

  const apiUrl = document.API_URL;
  const publishableKey = document.PUBLISHABLE_KEY;

  if (typeof apiUrl !== "string" || apiUrl === "") {
    throw new DemoCredentialError(
      "The local Supabase status document has no API URL.",
    );
  }

  // Fail closed if the running stack is not the canonical local one. This is
  // what stops the tooling handing the app a hosted or LAN endpoint even if the
  // CLI were pointed somewhere unexpected.
  assertCanonicalLocalUrl(apiUrl);

  if (typeof publishableKey !== "string" || publishableKey === "") {
    throw new DemoCredentialError(
      "The local Supabase stack did not provide a publishable key. Refusing to fall back to any other credential.",
    );
  }

  if (
    SERVER_CAPABLE_KEY_PREFIXES.some((prefix) =>
      publishableKey.startsWith(prefix),
    )
  ) {
    throw new DemoCredentialError(
      "The local publishable field holds a server-capable credential. Refusing to use it.",
    );
  }

  if (!PUBLISHABLE_KEY_PATTERN.test(publishableKey)) {
    throw new DemoCredentialError(
      "The local publishable key has an unexpected format.",
    );
  }

  // A new object built field by field, not a filtered copy of the input.
  return Object.freeze({ apiUrl, publishableKey });
}

// Runs the CLI and returns only the filtered result. The captured stdout is
// scoped to this function and is unreachable from the outside.
export async function readLocalCredentials(options) {
  const { exitCode, signal, stdout } = await runCapturedStdout(
    options.command,
    options.args,
    { cwd: options.cwd, env: options.env, label: "supabase status" },
  );

  // A status call killed part-way through returns a truncated document, which
  // would fail the parse below with a less useful message. It is reported as the
  // subprocess failure it is instead.
  if (!succeeded({ exitCode, signal })) {
    throw subprocessFailure(
      "The local Supabase stack is not running. Start it with `corepack pnpm demo:start` (which starts it and rebuilds nothing) or `corepack pnpm demo:reset` (which also rebuilds the baseline). Both keep the stack's credential output suppressed",
      exitCode,
      signal,
    );
  }

  return extractLocalCredentials(stdout);
}
