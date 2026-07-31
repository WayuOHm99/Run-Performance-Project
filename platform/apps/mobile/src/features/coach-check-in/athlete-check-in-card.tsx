import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/theme/tokens";

import {
  COACH_REVIEW_COPY,
  overallFeelingText,
  painText,
  rpeText,
} from "./copy";
import type { CoachReviewAthlete } from "./domain";

/**
 * One athlete's latest shared check-in, under one team.
 *
 * Presentation only. It receives an already-validated `CoachReviewAthlete` and
 * renders exactly the six fields decision 5 permits — team name is rendered by the
 * parent, the other five here — with no interpretation, no derived score, no
 * trend, no colour coding by value, and no comparison between athletes. A card
 * that visually graded RPE would be offering an assessment the product charter
 * does not allow this screen to make.
 *
 * `athleteProfileId` is present on the prop as a join and reconciliation key and is
 * **not rendered**; the source scan asserts that structurally.
 *
 * `checkIn === null` is the one and only "has not checked in yet" state, and it is
 * reachable only for an athlete who *does* actively share. It is worded as an
 * absence of a record, never as a statement about the athlete.
 */
export function AthleteCheckInCard({
  athlete,
}: {
  readonly athlete: CoachReviewAthlete;
}) {
  const { athleteName, checkIn } = athlete;

  return (
    <View style={styles.card}>
      <Text style={styles.name}>{athleteName}</Text>

      {checkIn === null ? (
        <Text style={styles.pending}>{COACH_REVIEW_COPY.noCheckIn}</Text>
      ) : (
        <View style={styles.readings}>
          <Reading
            label={COACH_REVIEW_COPY.dateLabel}
            // The athlete's own recorded civil date, rendered verbatim. Never
            // reformatted through a `Date`, and never labelled "today".
            value={checkIn.checkInDate}
          />
          <Reading
            label={COACH_REVIEW_COPY.rpeLabel}
            value={rpeText(checkIn.rpe)}
          />
          <Reading
            label={COACH_REVIEW_COPY.feelingLabel}
            value={overallFeelingText(checkIn.overallFeeling)}
          />
          <Reading
            label={COACH_REVIEW_COPY.painLabel}
            value={painText(checkIn.painStatus)}
          />
        </View>
      )}
    </View>
  );
}

/** One label/value line. Neutral styling for every value, deliberately. */
function Reading({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string;
}) {
  return (
    <View style={styles.reading}>
      <Text style={styles.readingLabel}>{label}</Text>
      <Text style={styles.readingValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.canvas,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  name: {
    color: colors.ink,
    fontSize: type.label,
    fontWeight: "700",
  },
  pending: {
    color: colors.inkMuted,
    fontSize: type.small,
    fontWeight: "700",
  },
  readings: {
    gap: spacing.xs,
  },
  reading: {
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "space-between",
  },
  readingLabel: {
    color: colors.inkMuted,
    flexShrink: 1,
    fontSize: type.small,
  },
  readingValue: {
    color: colors.ink,
    fontSize: type.small,
    fontWeight: "700",
  },
});
