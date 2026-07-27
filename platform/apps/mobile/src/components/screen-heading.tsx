import { StyleSheet, Text, View } from "react-native";

import { colors, spacing, type } from "@/theme/tokens";

type ScreenHeadingProps = {
  eyebrow?: string | undefined;
  title: string;
  description?: string | undefined;
};

export function ScreenHeading({
  eyebrow,
  title,
  description,
}: ScreenHeadingProps) {
  return (
    <View style={styles.heading}>
      {eyebrow === undefined ? null : (
        <Text style={styles.eyebrow}>{eyebrow}</Text>
      )}
      <Text style={styles.title}>{title}</Text>
      {description === undefined ? null : (
        <Text style={styles.description}>{description}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  heading: {
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  eyebrow: {
    color: colors.primaryStrong,
    fontSize: type.caption,
    fontWeight: "800",
    letterSpacing: 1,
  },
  title: {
    color: colors.ink,
    fontSize: type.title,
    fontWeight: "800",
  },
  description: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 21,
  },
});
