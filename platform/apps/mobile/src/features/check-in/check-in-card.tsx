import { useEffect, useReducer } from "react";
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
import {
  generationKey,
  initialFormState,
  needsDeliberateRefresh,
  reduceForm,
} from "./hydration";
import { readLocalDateStamp } from "./local-date";
import {
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
 * All state decisions are delegated: `hydration.ts` decides when server data may
 * replace what the athlete sees, and `submission.ts` decides what a save press
 * does. Both are pure and tested directly, which is what keeps this component to
 * wiring only. The three answers live in this component's state and nowhere else
 * — never persisted, queued, or retried.
 */
export function DailyCheckInCard() {
  const [form, dispatch] = useReducer(reduceForm, undefined, () =>
    initialFormState(readLocalDateStamp()),
  );

  // The key carries the date only, so an offset-only rollover keeps the same
  // entry and must be refreshed deliberately; see `needsDeliberateRefresh`.
  const query = useDailyCheckInQuery(form.stamp.date);
  const mutation = useSaveDailyCheckIn();

  const generation = generationKey(form.stamp);

  useEffect(() => {
    if (!query.isSuccess) {
      return;
    }

    // The reducer decides whether to adopt this, and returns the same state
    // reference when it does not, which is what keeps this effect from looping.
    dispatch({
      kind: "server-data",
      generation,
      checkIn: query.data ?? null,
    });
  }, [query.isSuccess, query.data, query.dataUpdatedAt, generation]);

  const busy = mutation.isPending;
  const locked = busy || query.isPending || query.isError;

  const choose = (draft: CheckInDraft) => {
    dispatch({ kind: "answer-chosen", draft });

    // Any edit clears the previous outcome, so a stale "saved" or error banner is
    // never shown next to unsaved changes.
    if (mutation.isSuccess || mutation.isError) {
      mutation.reset();
    }
  };

  const submit = () => {
    const plan = planSubmission({
      captured: form.stamp,
      // Recomputed here, not reused from render, so the check reflects the moment
      // of submission.
      current: readLocalDateStamp(),
      draft: form.draft,
    });

    if (plan.kind === "rollover") {
      const refreshNeeded = needsDeliberateRefresh(form.stamp, plan.stamp);

      // The answers are dropped rather than filed under the previous day.
      dispatch({ kind: "rollover", stamp: plan.stamp });
      mutation.reset();

      if (refreshNeeded) {
        // Same calendar date, new offset: the query key is unchanged, so nothing
        // would refetch on its own and the existing row could never rehydrate.
        void query.refetch();
      }

      return;
    }

    if (plan.kind === "incomplete") {
      return;
    }

    mutation.mutate(
      { localDate: plan.localDate, input: plan.input },
      {
        // Marks the draft clean and opts the following refetch in, so the
        // controls end up showing what the database actually stored.
        onSuccess: () => {
          dispatch({ kind: "save-succeeded" });
        },
      },
    );
  };

  return (
    <View style={styles.card}>
      <Text style={styles.label}>{CHECK_IN_COPY.label}</Text>
      <Text style={styles.title}>{CHECK_IN_COPY.title}</Text>
      <Text style={styles.intro}>{CHECK_IN_COPY.intro}</Text>
      <Text style={styles.date}>
        {CHECK_IN_COPY.dateLabel} {form.stamp.date}
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

      {query.isSuccess && form.hydratedFor === generation ? (
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
        selected={form.draft.rpe}
        disabled={locked}
        busy={busy}
        layout="wrap"
        onSelect={(rpe) => {
          choose({ ...form.draft, rpe });
        }}
      />

      <ChoiceGroup
        legend={CHECK_IN_COPY.feelingLegend}
        hint={CHECK_IN_COPY.feelingHint}
        choices={FEELING_CHOICES}
        selected={form.draft.overallFeeling}
        disabled={locked}
        busy={busy}
        layout="wrap"
        onSelect={(overallFeeling) => {
          choose({ ...form.draft, overallFeeling });
        }}
      />

      <ChoiceGroup
        legend={CHECK_IN_COPY.painLegend}
        choices={PAIN_CHOICES}
        selected={form.draft.painStatus}
        disabled={locked}
        busy={busy}
        layout="stack"
        onSelect={(painStatus) => {
          choose({ ...form.draft, painStatus });
        }}
      />

      <Text style={styles.safety}>{CHECK_IN_COPY.painSafety}</Text>

      {form.rolledOver ? (
        <Notice
          title={CHECK_IN_COPY.rolloverTitle}
          message={CHECK_IN_COPY.rolloverMessage}
        />
      ) : null}

      {mutation.isSuccess && !form.rolledOver ? (
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
        disabled={locked || !isDraftComplete(form.draft)}
        onPress={submit}
      />

      {isDraftComplete(form.draft) ? null : (
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
