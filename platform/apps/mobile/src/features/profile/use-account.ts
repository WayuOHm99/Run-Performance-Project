import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-provider";
import {
  resolveAuthGate,
  type AccountLoad,
  type AuthGate,
} from "@/features/auth/gate";
import { authScopedKeys } from "@/lib/query/keys";

import {
  loadAccount,
  saveDisplayName,
  type AccountSnapshot,
} from "./account-repository";

/**
 * The caller's own profile and memberships.
 *
 * Enabled only once an identity exists, so no query is ever issued with a
 * placeholder user id, and the key carries that id so the entry cannot be
 * shared across accounts.
 */
export function useAccountQuery() {
  const { client, identity } = useAuth();
  const userId = identity?.userId;

  return useQuery({
    queryKey: authScopedKeys.account(userId ?? "anonymous"),
    queryFn: () => loadAccount(client, userId as string),
    enabled: userId !== undefined,
  });
}

/**
 * The whole gate, assembled from restoration state plus the account query.
 *
 * The mapping from query status to `AccountLoad` is where the "an error is not
 * an empty result" rule is honoured on the React side: `isError` becomes
 * `{ kind: "error" }`, which `resolveAuthGate` turns into a retry state rather
 * than into "no active team".
 */
export function useAuthGate(): AuthGate {
  const { restored, identity, awaitingEmailConfirmation } = useAuth();
  const account = useAccountQuery();

  let load: AccountLoad;

  if (account.isError) {
    load = {
      kind: "error",
      message:
        account.error instanceof Error
          ? account.error.message
          : "โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
    };
  } else if (account.data === undefined) {
    load = { kind: "loading" };
  } else {
    load = {
      kind: "loaded",
      displayName: account.data.displayName,
      memberships: account.data.memberships,
    };
  }

  return resolveAuthGate({
    sessionRestored: restored,
    identity,
    awaitingEmailConfirmation,
    account: load,
  });
}

export function useRetryAccount(): () => void {
  const account = useAccountQuery();

  return () => {
    void account.refetch();
  };
}

/**
 * Saves the display name and refreshes the account.
 *
 * The cache is updated from the server's returned value rather than from the
 * submitted string, so what the app shows is what the database actually stored.
 */
export function useSaveDisplayName() {
  const { client, identity } = useAuth();
  const queryClient = useQueryClient();
  const userId = identity?.userId;

  return useMutation({
    mutationFn: (displayName: string) =>
      saveDisplayName(client, userId as string, displayName),
    onSuccess: (savedName) => {
      if (userId === undefined) {
        return;
      }

      queryClient.setQueryData<AccountSnapshot>(
        authScopedKeys.account(userId),
        (previous) =>
          previous === undefined
            ? previous
            : { ...previous, displayName: savedName },
      );
      void queryClient.invalidateQueries({
        queryKey: authScopedKeys.account(userId),
      });
    },
  });
}
