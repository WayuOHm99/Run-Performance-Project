/**
 * Error sanitization.
 *
 * Nothing from a server error object ever reaches the user or a log. Every
 * failure is collapsed into one of a handful of categories, and each category
 * maps to a fixed Thai string written here.
 *
 * The account-existence rule is the important one: sign-in and sign-up must not
 * let a caller distinguish "this email is registered" from "this email is not".
 * `invalid-credentials` and an already-registered address therefore produce the
 * same generic wording, and the sign-up screen shows its check-email state
 * regardless.
 *
 * Nothing in this module reads or emits an email address, password, token,
 * user id, request payload, or raw error string.
 */

export type AuthFailure =
  | "invalid-credentials"
  | "weak-password"
  | "rate-limited"
  | "offline"
  | "unknown";

export type DataFailure = "offline" | "denied" | "unknown";

/** Narrow an unknown thrown value to its error code without exposing it. */
function readErrorCode(error: unknown): string {
  if (typeof error !== "object" || error === null) {
    return "";
  }

  const candidate = error as { code?: unknown; status?: unknown };

  if (typeof candidate.code === "string") {
    return candidate.code;
  }

  if (typeof candidate.status === "number") {
    return `http_${String(candidate.status)}`;
  }

  return "";
}

function isNetworkError(error: unknown): boolean {
  if (typeof error !== "object" || error === null) {
    return false;
  }

  const candidate = error as { name?: unknown; message?: unknown };

  // supabase-js surfaces a transport failure as a TypeError from fetch, or as
  // an AuthRetryableFetchError. Matching on the name avoids inspecting the
  // message, which can contain a URL.
  return (
    candidate.name === "AuthRetryableFetchError" ||
    candidate.name === "TypeError" ||
    candidate.name === "AbortError"
  );
}

export function classifyAuthError(error: unknown): AuthFailure {
  if (isNetworkError(error)) {
    return "offline";
  }

  const code = readErrorCode(error);

  switch (code) {
    case "invalid_credentials":
    case "email_not_confirmed":
    case "user_not_found":
    case "user_already_exists":
    case "email_exists":
    case "http_400":
    case "http_401":
      // All five collapse deliberately. Separating them would let a caller
      // enumerate which addresses hold an account.
      return "invalid-credentials";
    case "weak_password":
      return "weak-password";
    case "over_request_rate_limit":
    case "over_email_send_rate_limit":
    case "http_429":
      return "rate-limited";
    default:
      return "unknown";
  }
}

export function classifyDataError(error: unknown): DataFailure {
  if (isNetworkError(error)) {
    return "offline";
  }

  const code = readErrorCode(error);

  // 42501 is an insufficient-privilege refusal and PGRST301 is a rejected JWT.
  // Both mean the caller is not allowed, which is different from a transport
  // failure and different again from an empty result.
  if (code === "42501" || code === "PGRST301" || code === "http_403") {
    return "denied";
  }

  return "unknown";
}

const AUTH_MESSAGES: Record<AuthFailure, string> = {
  "invalid-credentials": "อีเมลหรือรหัสผ่านไม่ถูกต้อง",
  "weak-password": "รหัสผ่านไม่ปลอดภัยพอ กรุณาตั้งรหัสผ่านที่ยาวขึ้น",
  "rate-limited": "ลองใหม่บ่อยเกินไป กรุณารอสักครู่แล้วลองอีกครั้ง",
  offline: "เชื่อมต่อไม่สำเร็จ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่",
  unknown: "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง",
};

const DATA_MESSAGES: Record<DataFailure, string> = {
  offline: "เชื่อมต่อไม่สำเร็จ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่",
  denied: "ไม่มีสิทธิ์เข้าถึงข้อมูลนี้",
  unknown: "โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
};

export function authErrorMessage(error: unknown): string {
  return AUTH_MESSAGES[classifyAuthError(error)];
}

export function dataErrorMessage(error: unknown): string {
  return DATA_MESSAGES[classifyDataError(error)];
}
