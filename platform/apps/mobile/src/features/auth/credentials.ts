/**
 * Credential normalization and validation.
 *
 * Two rules here are security rules, not style choices:
 *
 *   * the email is trimmed and lower-cased, because a user typing a leading
 *     space or a capital would otherwise fail to match their own account;
 *   * the password is never trimmed, lower-cased, collapsed, or altered in any
 *     other way. Whitespace is legitimate password content, and silently
 *     changing it would lock a user out of an account they typed correctly.
 *
 * Neither value is stored anywhere by this module. Callers hold them in live
 * form state only.
 */

/**
 * Stricter than the local `minimum_password_length = 6`. The server still
 * enforces its own minimum; this only avoids offering an obviously weak
 * password to it.
 */
export const PASSWORD_MIN_LENGTH = 8;

/**
 * Deliberately permissive. A client-side email regex that tries to be clever
 * rejects valid addresses; the authoritative check is the confirmation email
 * actually arriving.
 */
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/u;

export type CredentialField = "email" | "password";

export type CredentialRejection =
  | "email-required"
  | "email-invalid"
  | "password-required"
  | "password-too-short";

export type Credentials = {
  readonly email: string;
  readonly password: string;
};

export type CredentialsResult =
  | { readonly ok: true; readonly value: Credentials }
  | {
      readonly ok: false;
      readonly field: CredentialField;
      readonly reason: CredentialRejection;
    };

/** Trim and lower-case only. Never applied to a password. */
export function normalizeEmail(raw: string): string {
  return raw.trim().toLowerCase();
}

export function validateCredentials(input: {
  email: string;
  password: string;
}): CredentialsResult {
  const email = normalizeEmail(input.email);

  if (email.length === 0) {
    return { ok: false, field: "email", reason: "email-required" };
  }

  if (!EMAIL_PATTERN.test(email)) {
    return { ok: false, field: "email", reason: "email-invalid" };
  }

  // input.password is passed through untouched on purpose.
  if (input.password.length === 0) {
    return { ok: false, field: "password", reason: "password-required" };
  }

  if (input.password.length < PASSWORD_MIN_LENGTH) {
    return { ok: false, field: "password", reason: "password-too-short" };
  }

  return { ok: true, value: { email, password: input.password } };
}

const CREDENTIAL_MESSAGES: Record<CredentialRejection, string> = {
  "email-required": "กรุณากรอกอีเมล",
  "email-invalid": "รูปแบบอีเมลไม่ถูกต้อง",
  "password-required": "กรุณากรอกรหัสผ่าน",
  "password-too-short": `รหัสผ่านต้องมีอย่างน้อย ${String(PASSWORD_MIN_LENGTH)} ตัวอักษร`,
};

export function credentialMessage(reason: CredentialRejection): string {
  return CREDENTIAL_MESSAGES[reason];
}
