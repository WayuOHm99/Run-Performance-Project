/**
 * Ordering guard for asynchronous auth results.
 *
 * Session validation is asynchronous, so results can arrive out of order: a
 * restore started at app launch can resolve *after* a sign-out event that was
 * emitted later. Applying it would resurrect a signed-out session, which is the
 * worst possible ordering bug in this file's neighbourhood.
 *
 * The rule is monotonic. Each auth signal takes the next token at the moment it
 * is observed, and a result may only be applied if its token is newer than the
 * last one applied. Kept pure so the ordering can be tested exhaustively
 * without React, timers, or a Supabase client.
 */

export type SequenceToken = number;

/** No result has been applied yet. Every real token is greater than this. */
export const INITIAL_SEQUENCE_TOKEN: SequenceToken = 0;

export function nextSequenceToken(current: SequenceToken): SequenceToken {
  return current + 1;
}

/**
 * Whether a result that carries `resultToken` may overwrite what is applied.
 *
 * Strictly greater, not greater-or-equal: a token is applied at most once, so a
 * repeated or replayed result cannot re-apply an outcome that a newer signal
 * has already superseded.
 */
export function shouldApplyResult(
  resultToken: SequenceToken,
  lastAppliedToken: SequenceToken,
): boolean {
  return resultToken > lastAppliedToken;
}
