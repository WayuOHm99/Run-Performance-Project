import { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Notice } from "@/components/notice";
import { PrimaryButton } from "@/components/primary-button";
import { colors, radius, spacing, type } from "@/theme/tokens";

import { ChoiceGroup, type Choice } from "./choice-group";
import {
  CHECK_IN_COPY,
  PAIN_STATUS_LABELS,
  overallFeelingAccessibilityLabel,
  overallFeelingLabel,
  rpeAccessibilityLabel,
} from "./copy";
import {
  OVERALL_FEELING_VALUES,
  PAIN_STATUSES,
  RPE_VALUES,
  type PainStatus,
} from "./domain";
import { checkInErrorMessage } from "./errors";
import { readLocalDateStamp } from "./local-date";
import {
  EMPTY_DRAFT,
  draftFromCheckIn,
  isDraftComplete,
  planSubmission,
  type CheckInDraft,
} from "./submission";
import {
  useDailyCheckInQuery,
  useSaveDailyCheckIn,
} from "./use-daily-check-in";

const RPE_CHOICES: readonly Choice<number>[] = RPE_VALUES.map((value) => ({
  value,
  label: String(value),
  accessibilityLabel: rpeAccessibilityLabel(value),
}));

const FEELING_CHOICES: readonly Choice<number>[] = OVERALL_FEELING_VALUES.map(
  (value) => ({
    value,
    label: overallFeelingLabel(value),
    accessibilityLabel: overallFeelingAccessibilityLabel(value),
  }),
);

const PAIN_CHOICES: readonly Choice<PainStatus>[] = PAIN_STATUSES.map(
  (value) => ({
    value,
    label: PAIN_STATUS_LABELS[value],
    accessibilityLabel: PAIN_STATUS_LABELS[value],
  }),
);

/**
 * The inline daily check-in, rendered on the Athlete Today screen.
 *
 * Reachable only through the existing active-athlete route, which the root layout
 * gates on `canEnterRoleArea(gate, "athlete")`. This card adds no route and no
 * navigation entry, so pending, revoked, unauthenticated, and coach-only users
 * gain nothing from it. The database policies remain the actual boundary.
 *
 * Two pieces of state carry the whole behaviour:
 *
 * - `stamp` is the local calendar date the form was created for. It is part of
 *   the query key, so crossing midnight or a timezone loads a different day
 *   rather than reusing this one.
 * - `draft` holds the three answers, in memory only. It starts empty with no
 *   preselected value, is prefilled once from a loaded row, and is never
 *   persisted, queued, or retried. Closing the app loses it, which is the
 *   intended online-only behaviour.
 */
export function DailyCheckInCard() {
  const [stamp, setStamp] = useState(() => readLocalDateStamp());
  const [draft, setDraft] = useState<CheckInDraft>(EMPTY_DRAFT);
  const [rolledOver, setRolledOver] = useState(false);

  const query = useDailyCheckInQuery(stamp.date);
  const mutation = useSaveDailyCheckIn();

  // The date whose loaded value has already been copied into the draft. A ref,
  // so re-prefilling is decided without adding a render.
  const prefilledFor = useRef<string | null>(null);

  useEffect(() => {
    if (!query.isSuccess || prefilledFor.current === stamp.date) {
      return;
    }

    prefilledFor.current = stamp.date;
    // `null` means no row today, which yields the empty draft — an existing row
    // yields an editable prefill. Both come from the same call, so the empty and
    // the edit state cannot drift apart.
    setDraft(draftFromCheckIn(query.data ?? null));
  }, [query.isSuccess, query.data, stamp.date]);

  const busy = mutation.isPending;
  const locked = busy || query.isPending || query.isError;

  // Any edit clears the previous outcome, so a stale "saved" or error banner is
  // never shown next to unsaved changes.
  const change = (next: CheckInDraft) => {
    setDraft(next);
    setRolledOver(false);

    if (mutation.isSuccess || mutation.isError) {
      mutation.reset();
    }
  };

  const submit = () => {
    const plan = planSubmission({
      captured: stamp,
      // Recomputed here, not reused from render, so the check reflects the moment
      // of submission.
      current: readLocalDateStamp(),
      draft,
    });

    if (plan.kind === "rollover") {
      // The answers are dropped rather than filed under the previous day. The
      // new date drives a fresh query, and the draft resets so nothing is
      // carried across the boundary.
      setStamp(plan.stamp);
      prefilledFor.current = null;
      setDraft(EMPTY_DRAFT);
      setRolledOver(true);
      mutation.reset();

      return;
    }

    if (plan.kind === "incomplete") {
      return;
    }

    setRolledOver(false);
    mutation.mutate({ localDate: plan.localDate, input: plan.input });
  };

  return (
    <View style={styles.card}>
      <Text style={styles.label}>{CHECK_IN_COPY.label}</Text>
      <Text style={styles.title}>{CHECK_IN_COPY.title}</Text>
      <Text style={styles.intro}>{CHECK_IN_COPY.intro}</Text>
      <Text style={styles.date}>
        {CHECK_IN_COPY.dateLabel} {stamp.date}
      </Text>

      {query.isPending ? (
        <Text style={styles.status}>{CHECK_IN_COPY.loading}</Text>
      ) : null}

      {query.isError ? (
        <View style={styles.stack}>
          <Notice
            title={CHECK_IN_COPY.loadErrorTitle}
            message={checkInErrorMessage(query.error)}
          />
          <PrimaryButton
            label={CHECK_IN_COPY.retry}
            variant="quiet"
            onPress={() => {
              void query.refetch();
            }}
          />
        </View>
      ) : null}

      {query.isSuccess ? (
        <Text style={styles.status}>
          {query.data === null
            ? CHECK_IN_COPY.emptyState
            : CHECK_IN_COPY.editState}
        </Text>
      ) : null}

      <ChoiceGroup
        legend={CHECK_IN_COPY.rpeLegend}
        hint={CHECK_IN_COPY.rpeHint}
        choices={RPE_CHOICES}
        selected={draft.rpe}
        disabled={locked}
        busy={busy}
        layout="wrap"
        onSelect={(rpe) => {
          change({ ...draft, rpe });
        }}
      />

      <ChoiceGroup
        legend={CHECK_IN_COPY.feelingLegend}
        hint={CHECK_IN_COPY.feelingHint}
        choices={FEELING_CHOICES}
        selected={draft.overallFeeling}
        disabled={locked}
        busy={busy}
        layout="wrap"
        onSelect={(overallFeeling) => {
          change({ ...draft, overallFeeling });
        }}
      />

      <ChoiceGroup
        legend={CHECK_IN_COPY.painLegend}
        choices={PAIN_CHOICES}
        selected={draft.painStatus}
        disabled={locked}
        busy={busy}
        layout="stack"
        onSelect={(painStatus) => {
          change({ ...draft, painStatus });
        }}
      />

      <Text style={styles.safety}>{CHECK_IN_COPY.painSafety}</Text>

      {rolledOver ? (
        <Notice
          title={CHECK_IN_COPY.rolloverTitle}
          message={CHECK_IN_COPY.rolloverMessage}
        />
      ) : null}

      {mutation.isSuccess && !rolledOver ? (
        <Notice
          title={CHECK_IN_COPY.savedTitle}
          message={CHECK_IN_COPY.savedMessage}
        />
      ) : null}

      {mutation.isError ? (
        <Notice
          title={CHECK_IN_COPY.saveErrorTitle}
          message={checkInErrorMessage(mutation.error)}
        />
      ) : null}

      <PrimaryButton
        label={busy ? CHECK_IN_COPY.saving : CHECK_IN_COPY.save}
        busy={busy}
        // Disabled until all three answers exist, and while a save is in flight,
        // which is the duplicate-submission guard.
        disabled={locked || !isDraftComplete(draft)}
        onPress={submit}
      />

      {isDraftComplete(draft) ? null : (
        <Text style={styles.status}>{CHECK_IN_COPY.incompleteHint}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
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
  intro: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 21,
  },
  date: {
    color: colors.ink,
    fontSize: type.small,
    fontWeight: "700",
  },
  status: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 21,
  },
  safety: {
    color: colors.inkMuted,
    fontSize: type.caption,
    lineHeight: 18,
  },
  stack: {
    gap: spacing.sm,
  },
});
