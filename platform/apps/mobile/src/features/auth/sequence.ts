/**
 * Token issuing for asynchronous auth work.
 *
 * Session validation is asynchronous, so results can arrive out of order: a
 * restore started at app launch can resolve *after* a sign-out that was
 * observed later. Each auth signal takes the next token at the moment it is
 * observed, which gives the reducer in `auth-state.ts` a total order to reason
 * about.
 *
 * Whether a *result* may be applied is decided by `canApplyValidation` in
 * `auth-state.ts`, not here. That predicate needs the latest observed token as
 * well as the last applied one, and an earlier revision of this file exported a
 * two-argument "is it newer than what we applied" helper that looked sufficient
 * and was not. It is deliberately gone rather than deprecated.
 */

export type SequenceToken = number;

/** No signal has been observed yet. Every issued token is greater than this. */
export const INITIAL_SEQUENCE_TOKEN: SequenceToken = 0;

export function nextSequenceToken(current: SequenceToken): SequenceToken {
  return current + 1;
}

/**
 * Whether an observed signal is newer than the newest one seen so far.
 *
 * Used only to order *observations*. Applying a validation result is a
 * different and stricter question.
 */
export function isNewerSignal(
  token: SequenceToken,
  latestToken: SequenceToken,
): boolean {
  return token > latestToken;
}
