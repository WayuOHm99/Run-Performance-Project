// The real local Auth and PostgREST surfaces.
//
// Decision 6: the two accounts are created through the **real public signup
// flow**. There is no direct write into `auth.users`, no Auth Admin call, no
// service-role key, and no demo authentication bypass anywhere in this tooling.
// The credential used here is the publishable key — exactly what the mobile app
// uses — so if signup works here it works in the app for the same reason.
//
// Nothing in this module returns a token, a session, a user object, or a
// response body to its caller. Sign-in yields an opaque handle whose token is
// used to build request headers and is never rendered. Reads return **counts**,
// never rows.
//
// Every request is asserted against the canonical local endpoint first, so a
// password or a token cannot be sent anywhere but the local stack.
//
// Response bodies are never parsed with `response.json()`. That method surfaces
// `JSON.parse`'s own error, which quotes the body — see `parseJsonBody` below.

import { assertCanonicalLocalUrl } from "./endpoint.mjs";

export class DemoApiError extends Error {
  name = "DemoApiError";

  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// A response body may contain a token, a session, an email, or a database error
// string. It is never read for content and never attached to an error; only the
// numeric status reaches the message.
async function discardBody(response) {
  try {
    await response.arrayBuffer();
  } catch {
    // A body that cannot be drained is not an error worth reporting, and its
    // failure carries no information this tooling is allowed to surface.
  }
}

function failure(what, status) {
  return new DemoApiError(
    `${what} failed (HTTP ${status}). The response body was discarded unread on purpose.`,
    status,
  );
}

// The leak path that `await response.json()` opens directly.
//
// `JSON.parse` reports the input in its own error message — "Unexpected token
// 'x', \"...\" is not valid JSON" quotes the body verbatim. A malformed body is
// exactly the case where that body is most likely to be a PostgREST or GoTrue
// error document carrying a database error string, a hint naming a column, or a
// partially written session. Letting that SyntaxError propagate would print all
// of it.
//
// So the body is read as text, parsed inside a `catch` that discards the parse
// error entirely, and the text goes out of scope unreferenced. Neither the body
// nor any substring of it can reach the caller, a log line, or a stack trace.
async function parseJsonBody(response, what) {
  let text;

  try {
    text = await response.text();
  } catch {
    throw new DemoApiError(
      `${what} returned a response body that could not be read. It was discarded unread on purpose.`,
      response.status,
    );
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new DemoApiError(
      `${what} returned a malformed response body. The body was discarded unread on purpose; re-run the request yourself against the local stack if you need to see it.`,
      response.status,
    );
  }
}

function authHeaders(publishableKey, accessToken) {
  const headers = {
    apikey: publishableKey,
    "Content-Type": "application/json",
  };

  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  return headers;
}

export async function signUp({ apiUrl, publishableKey, email, password }) {
  assertCanonicalLocalUrl(apiUrl);

  const response = await fetch(`${apiUrl}/auth/v1/signup`, {
    method: "POST",
    headers: authHeaders(publishableKey),
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    await discardBody(response);
    throw failure("Local Auth signup", response.status);
  }

  await discardBody(response);

  return true;
}

// Returns a handle, not a session. `accessToken` and `userId` are held so
// subsequent requests can be made as this user; neither is ever printed, and the
// object is frozen so a caller cannot decorate it with anything else.
export async function signIn({ apiUrl, publishableKey, email, password }) {
  assertCanonicalLocalUrl(apiUrl);

  const response = await fetch(`${apiUrl}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: authHeaders(publishableKey),
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    await discardBody(response);
    throw failure("Local Auth sign-in", response.status);
  }

  const payload = await parseJsonBody(response, "Local Auth sign-in");
  const accessToken = payload?.access_token;
  const userId = payload?.user?.id;

  if (typeof accessToken !== "string" || typeof userId !== "string") {
    throw new DemoApiError(
      "Local Auth sign-in returned an unusable session.",
      200,
    );
  }

  return Object.freeze({ accessToken, userId });
}

// Returns the number of matching rows and nothing else. `select=id` keeps every
// health column out of the response in the first place, so no protected value is
// ever in this process's memory, let alone its output.
export async function countRows({
  apiUrl,
  publishableKey,
  session,
  table,
  filters,
}) {
  assertCanonicalLocalUrl(apiUrl);

  const query = new URLSearchParams({ select: "id", ...filters });
  const response = await fetch(`${apiUrl}/rest/v1/${table}?${query}`, {
    method: "GET",
    headers: authHeaders(publishableKey, session.accessToken),
  });

  if (!response.ok) {
    await discardBody(response);
    throw failure(`Reading ${table}`, response.status);
  }

  const rows = await parseJsonBody(response, `Reading ${table}`);

  if (!Array.isArray(rows)) {
    throw new DemoApiError(
      `Reading ${table} returned an unexpected shape.`,
      200,
    );
  }

  return rows.length;
}

// `Prefer: return=minimal` so the inserted health row is not echoed back.
export async function insertCheckIn({
  apiUrl,
  publishableKey,
  session,
  checkInDate,
  rpe,
  overallFeeling,
  painStatus,
}) {
  assertCanonicalLocalUrl(apiUrl);

  const response = await fetch(`${apiUrl}/rest/v1/daily_check_ins`, {
    method: "POST",
    headers: {
      ...authHeaders(publishableKey, session.accessToken),
      Prefer: "return=minimal",
    },
    body: JSON.stringify({
      athlete_profile_id: session.userId,
      check_in_date: checkInDate,
      rpe,
      overall_feeling: overallFeeling,
      pain_status: painStatus,
    }),
  });

  if (!response.ok) {
    await discardBody(response);
    throw failure("Inserting a synthetic check-in", response.status);
  }

  await discardBody(response);

  return true;
}

// The same two RPCs the app's sharing controls call. Consent is never created by
// the fixture; it is created here only inside the consent verification, which
// restores the zero-grant baseline afterwards.
export async function callSharingRpc({
  apiUrl,
  publishableKey,
  session,
  fn,
  teamId,
  dataCategory,
}) {
  assertCanonicalLocalUrl(apiUrl);

  const response = await fetch(`${apiUrl}/rest/v1/rpc/${fn}`, {
    method: "POST",
    headers: authHeaders(publishableKey, session.accessToken),
    body: JSON.stringify({
      p_team_id: teamId,
      p_data_category: dataCategory,
    }),
  });

  if (!response.ok) {
    await discardBody(response);
    throw failure(`Calling ${fn}`, response.status);
  }

  await discardBody(response);

  return true;
}
