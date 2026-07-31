import { StyleSheet, Text, View } from "react-native";

import { Notice } from "@/components/notice";
import { PrimaryButton } from "@/components/primary-button";
import { useAuth } from "@/features/auth/auth-provider";
import { colors, radius, spacing, type } from "@/theme/tokens";

import { AthleteCheckInCard } from "./athlete-check-in-card";
import { COACH_REVIEW_COPY } from "./copy";
import { coachReviewErrorMessage } from "./errors";
import { useCoachCheckInReviewQuery } from "./use-coach-check-in-review";
import {
  coachReviewIdentityBoundaryKey,
  readCoachReviewView,
  visibleTeams,
} from "./view-state";

/**
 * The "เช็กอินล่าสุดที่แชร์กับทีม" section of the Coach Team screen.
 *
 * Replaces the Team placeholder in place. It adds **no route and no navigation
 * entry**, so a signed-out, pending, revoked, or athlete-only user gains no
 * capability from it — and could not use one, because every read it performs is
 * gated by `private.can_current_user_read_shared_data`, which requires an active
 * coach membership, an active athlete membership in the same team, and an active
 * `check_in` grant. The route gate is UX; the TASK-011 and TASK-012 policies remain
 * the actual boundary.
 *
 * Four display rules are load-bearing:
 *
 * 1. **Everything rendered comes from `readCoachReviewView`.** Nothing here reads
 *    `query.data` directly, so the "hide health values while refreshing and after a
 *    failed refresh" rule cannot be lost to a JSX edit. `visibleTeams` is a second
 *    gate over the same value.
 *
 * 2. **A load failure is never rendered as an absence.** The error branch replaces
 *    the list entirely, so a coach is never shown a confident "ยังไม่ได้เช็กอิน"
 *    that is really "we could not find out".
 *
 * 3. **A team with no consenting athlete describes the team, not any athlete.**
 *    Decision 3 forbids naming who has not shared, so the empty case is worded as a
 *    property of the team's shared data.
 *
 * 4. **Refresh is deliberate.** There is no polling and no Realtime, so the only
 *    ways this re-reads consent are mounting the screen and pressing the button.
 *
 * This component is the identity boundary. It reads the verified identity and
 * renders the hook-owning subtree under a key derived from it, so a verified
 * identity change **unmounts** the old query observer and mounts a fresh one — see
 * `view-state.ts` for why `clearAuthScopedQueries` alone does not achieve that.
 */
export function CoachCheckInReviewSection() {
  const { identity } = useAuth();

  // Keyed, not reset by an effect. A reset effect would render one frame of the
  // previous coach's list before clearing it; a changed key means the old observer
  // no longer exists when the new one is created.
  return <CoachReview key={coachReviewIdentityBoundaryKey(identity?.userId)} />;
}

/**
 * The review for exactly one verified identity.
 *
 * Owns the query. Mounted under an identity-derived key, so every piece of observer
 * state it can read belongs to the identity it was mounted for.
 */
function CoachReview() {
  const query = useCoachCheckInReviewQuery();

  // The single place observer state becomes something rendered. Pure and total, so
  // "a refreshing screen carries no health value" is asserted directly against a
  // real observer result rather than inferred from a rendered tree.
  const view = readCoachReviewView(query);
  const teams = visibleTeams(view);

  return (
    <View style={styles.section}>
      <Text style={styles.label}>{COACH_REVIEW_COPY.label}</Text>
      <Text style={styles.title}>{COACH_REVIEW_COPY.title}</Text>
      <Text style={styles.body}>{COACH_REVIEW_COPY.intro}</Text>

      {view.status === "error" ? (
        <View style={styles.stack}>
          <Notice
            title={
              view.capacity
                ? COACH_REVIEW_COPY.capacityErrorTitle
                : COACH_REVIEW_COPY.loadErrorTitle
            }
            message={coachReviewErrorMessage(query.error)}
          />
          <PrimaryButton
            label={COACH_REVIEW_COPY.retry}
            variant="quiet"
            onPress={() => {
              void query.refetch();
            }}
          />
        </View>
      ) : view.status === "loading" ? (
        <Text style={styles.status}>{COACH_REVIEW_COPY.loading}</Text>
      ) : view.status === "refreshing" ? (
        <Text style={styles.status}>{COACH_REVIEW_COPY.refreshing}</Text>
      ) : teams.length === 0 ? (
        <View style={styles.teamCard}>
          <Text style={styles.teamName}>{COACH_REVIEW_COPY.noTeamTitle}</Text>
          <Text style={styles.body}>{COACH_REVIEW_COPY.noTeamMessage}</Text>
        </View>
      ) : (
        <View style={styles.stack}>
          {teams.map((team) => (
            <View key={team.teamId} style={styles.teamCard}>
              <Text style={styles.teamName}>{team.teamName}</Text>

              {team.athletes.length === 0 ? (
                <>
                  <Text style={styles.emptyTitle}>
                    {COACH_REVIEW_COPY.noConsentTitle}
                  </Text>
                  <Text style={styles.body}>
                    {COACH_REVIEW_COPY.noConsentMessage}
                  </Text>
                </>
              ) : (
                <View style={styles.stack}>
                  {team.athletes.map((athlete) => (
                    <AthleteCheckInCard
                      key={athlete.athleteProfileId}
                      athlete={athlete}
                    />
                  ))}
                </View>
              )}
            </View>
          ))}

          <Text style={styles.body}>{COACH_REVIEW_COPY.safetyNote}</Text>
        </View>
      )}

      <PrimaryButton
        label={COACH_REVIEW_COPY.refresh}
        variant="quiet"
        // Disabled while a fetch is in flight, which is also every state in which
        // health values are hidden. A second press cannot start a second read.
        disabled={view.status === "loading" || view.status === "refreshing"}
        onPress={() => {
          void query.refetch();
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    backgroundColor: colors.surface,
    borderColor: colors.primarySoft,
    borderLeftColor: colors.primary,
    borderLeftWidth: 4,
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
  teamCard: {
    backgroundColor: colors.surface,
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
  emptyTitle: {
    color: colors.inkMuted,
    fontSize: type.small,
    fontWeight: "700",
  },
});
