import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/theme/tokens";

type InfoCardProps = {
  label: string;
  title: string;
  description: string;
  accent?: "neutral" | "primary";
};

export function InfoCard({
  label,
  title,
  description,
  accent = "neutral",
}: InfoCardProps) {
  return (
    <View style={[styles.card, accent === "primary" && styles.primaryCard]}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.description}>{description}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  primaryCard: {
    borderColor: colors.primarySoft,
    borderLeftColor: colors.primary,
    borderLeftWidth: 4,
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
  description: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 21,
  },
});
