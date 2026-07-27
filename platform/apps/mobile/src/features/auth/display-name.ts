/**
 * Display-name normalization and validation.
 *
 * The bounds mirror the `profiles_display_name_valid` constraint and the
 * `profiles_update_self` policy so the client refuses a value the database
 * would refuse anyway. The database remains the enforcing side; this only
 * avoids a pointless round trip and gives a usable message.
 */

export const DISPLAY_NAME_MAX_LENGTH = 80;

export type DisplayNameRejection = "empty" | "too-long";

export type DisplayNameResult =
  | { readonly ok: true; readonly value: string }
  | { readonly ok: false; readonly reason: DisplayNameRejection };

/**
 * Trims the ends and collapses internal whitespace runs to a single space.
 *
 * Collapsing matters because the database bounds `char_length(display_name)`
 * as well as `char_length(btrim(display_name))`; a name padded with interior
 * runs could otherwise pass the trimmed check and fail the raw one.
 */
export function normalizeDisplayName(raw: string): string {
  return raw.replace(/\s+/gu, " ").trim();
}

export function validateDisplayName(raw: string): DisplayNameResult {
  const value = normalizeDisplayName(raw);

  if (value.length === 0) {
    return { ok: false, reason: "empty" };
  }

  if (value.length > DISPLAY_NAME_MAX_LENGTH) {
    return { ok: false, reason: "too-long" };
  }

  return { ok: true, value };
}

/**
 * Whether onboarding is complete.
 *
 * A profile row always exists (the signup trigger creates it), so a missing
 * name is `null` or blank rather than a missing row. Anything that would not
 * survive validation is treated as not yet onboarded.
 */
export function hasCompletedProfile(
  displayName: string | null | undefined,
): boolean {
  if (typeof displayName !== "string") {
    return false;
  }

  return validateDisplayName(displayName).ok;
}

const DISPLAY_NAME_MESSAGES: Record<DisplayNameRejection, string> = {
  empty: "กรุณากรอกชื่อที่ใช้แสดง",
  "too-long": `ชื่อที่ใช้แสดงต้องไม่เกิน ${String(DISPLAY_NAME_MAX_LENGTH)} ตัวอักษร`,
};

export function displayNameMessage(reason: DisplayNameRejection): string {
  return DISPLAY_NAME_MESSAGES[reason];
}
