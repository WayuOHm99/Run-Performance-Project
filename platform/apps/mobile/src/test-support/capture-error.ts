/**
 * Awaits a promise that is expected to reject, and returns the rejection typed.
 *
 * `promise.catch((error) => error as T)` widens the result to
 * `T | ResolvedValue`, which then needs a cast at every property access. This
 * keeps the assertion sites readable and additionally fails loudly if the call
 * resolved when the test expected it to reject.
 */
export async function captureError<E extends Error>(
  promise: Promise<unknown>,
  kind: new (...args: never[]) => E,
): Promise<E> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof kind) {
      return error;
    }

    throw error;
  }

  throw new Error(`Expected the call to reject with ${kind.name}.`);
}
