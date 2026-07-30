import { StyleSheet, Text, View } from "react-native";

import { Notice } from "@/components/notice";
import { PrimaryButton } from "@/components/primary-button";
import { colors, radius, spacing, type } from "@/theme/tokens";

import { planSharingAction } from "./action-plan";
import {
  SHARING_COPY,
  sharingActionAccessibilityLabel,
  sharingStateAccessibilityLabel,
} from "./copy";
import type { TeamSharingState } from "./domain";
import { sharingErrorMessage } from "./errors";
import { SharingActionButton } from "./sharing-action-button";
import {
  useCheckInSharingQuery,
  useSharingAction,
} from "./use-check-in-sharing";

/** Stable identity, so `teams` does not change reference on every render. */
const NO_TEAMS: readonly TeamSharingState[] = [];

/**
 * The "Daily Check-in sharing" section of the Profile/Me screen.
 *
 * Adds no route and no navigation entry, so a pending, revoked, coach-only, or
 * unauthenticated user gains no capability from it — and cannot, because the two
 * RPCs both require an active athlete membership that PostgreSQL checks under a row
 * lock. A coach-only user simply sees the empty state. The TASK-011 policies and
 * RPC checks remain the actual boundary; everything here is presentation.
 *
 * Three display rules are load-bearing:
 *
 * 1. **A load failure is never rendered as "not sharing".** The error branch comes
 *    before the list branch and replaces it entirely, so an athlete is never shown
 *    a confident "ไม่ได้แชร์" that is really "we could not find out".
 *
 * 2. **The state shown is always the query's.** Nothing here derives a sharing
 *    state from a press, a pending mutation, or the mutation's result. The only way
 *    a row changes is a refetched server list, which `mutationFn` awaits before it
 *    reports success.
 *
 * 3. **One action at a time.** Any in-flight action disables every control,
 *    including other teams', which is both the duplicate-press guard and the
 *    reason a Team A action can never be confused with a Team B one.
 */
export function CheckInSharingSection() {
  const query = useCheckInSharingQuery();

  // The loaded list is also what authorizes a write: `useSharingAction` resolves
  // the pressed id against it, so a team the server did not return is unwritable.
  const teams = query.data ?? NO_TEAMS;
  const mutation = useSharingAction(teams);

  const busy = mutation.isPending;
  const busyTeamId = busy ? mutation.variables?.teamId : undefined;

  const press = (teamId: string) => {
    // The plan is where "refuse a press while busy" and "take the direction from
    // server-loaded state, not from the press" are decided. The controls are
    // already unpressable while busy; this is what makes a duplicate press a
    // no-op rather than a second consent operation.
    const plan = planSharingAction({ busy, teams, teamId });

    if (!plan.accepted) {
      return;
    }

    mutation.mutate(plan.variables);
  };

  const outcome = mutation.isSuccess ? mutation.data : null;
  const failedAction = mutation.isError
    ? mutation.variables?.action
    : undefined;

  return (
    <View style={styles.section}>
      <Text style={styles.label}>{SHARING_COPY.label}</Text>
      <Text style={styles.title}>{SHARING_COPY.title}</Text>
      <Text style={styles.body}>{SHARING_COPY.contents}</Text>
      <Text style={styles.body}>{SHARING_COPY.teamScope}</Text>
      <Text style={styles.body}>{SHARING_COPY.defaultOff}</Text>

      {query.isError ? (
        <View style={styles.stack}>
          <Notice
            title={SHARING_COPY.loadErrorTitle}
            message={sharingErrorMessage(query.error)}
          />
          <PrimaryButton
            label={SHARING_COPY.retry}
            variant="quiet"
            onPress={() => {
              void query.refetch();
            }}
          />
        </View>
      ) : query.data === undefined ? (
        <Text style={styles.status}>{SHARING_COPY.loading}</Text>
      ) : teams.length === 0 ? (
        <View style={styles.card}>
          <Text style={styles.teamName}>{SHARING_COPY.emptyTitle}</Text>
          <Text style={styles.body}>{SHARING_COPY.emptyMessage}</Text>
        </View>
      ) : (
        <View style={styles.stack}>
          {teams.length > 1 ? (
            <Text style={styles.status}>{SHARING_COPY.perTeamHint}</Text>
          ) : null}

          {teams.map((team) => {
            const teamBusy = busyTeamId === team.teamId;

            return (
              <View key={team.teamId} style={styles.card}>
                <Text style={styles.teamName}>{team.teamName}</Text>
                <Text
                  accessibilityLabel={sharingStateAccessibilityLabel(team)}
                  style={team.sharing ? styles.stateOn : styles.stateOff}
                >
                  {team.sharing ? SHARING_COPY.stateOn : SHARING_COPY.stateOff}
                </Text>
                <SharingActionButton
                  label={
                    teamBusy
                      ? SHARING_COPY.working
                      : team.sharing
                        ? SHARING_COPY.revokeAction
                        : SHARING_COPY.grantAction
                  }
                  accessibilityLabel={sharingActionAccessibilityLabel(team)}
                  intent={team.sharing ? "revoke" : "grant"}
                  busy={teamBusy}
                  disabled={busy}
                  onPress={() => {
                    press(team.teamId);
                  }}
                />
              </View>
            );
          })}

          {busy ? (
            <Text style={styles.status}>{SHARING_COPY.waitHint}</Text>
          ) : null}

          {outcome === null ? null : (
            <Notice
              title={
                outcome.action === "grant"
                  ? SHARING_COPY.grantedTitle
                  : SHARING_COPY.revokedTitle
              }
              message={
                outcome.action === "grant"
                  ? SHARING_COPY.grantedMessage
                  : SHARING_COPY.revokedMessage
              }
            />
          )}

          {failedAction === undefined ? null : (
            <Notice
              title={
                failedAction === "grant"
                  ? SHARING_COPY.grantErrorTitle
                  : SHARING_COPY.revokeErrorTitle
              }
              message={sharingErrorMessage(mutation.error)}
            />
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.md,
    padding: spacing.lg,
  },
  label: {
    color: colors.primaryStrong,
    fontSize: type.caption,
    fontWeight: "800",
  },
  title: {
    color: colors.ink,
    fontSize: type.subtitle,
    fontWeight: "700",
  },
  body: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 21,
  },
  status: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 21,
  },
  stack: {
    gap: spacing.md,
  },
  card: {
    backgroundColor: colors.canvas,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  teamName: {
    color: colors.ink,
    fontSize: type.label,
    fontWeight: "700",
  },
  stateOn: {
    color: colors.primaryStrong,
    fontSize: type.small,
    fontWeight: "700",
  },
  stateOff: {
    color: colors.inkMuted,
    fontSize: type.small,
    fontWeight: "700",
  },
});
