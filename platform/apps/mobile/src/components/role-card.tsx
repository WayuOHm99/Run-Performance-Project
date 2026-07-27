import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/theme/tokens";

type RoleCardProps = {
  title: string;
  description: string;
  actionLabel: string;
  primary?: boolean;
  onPress: () => void;
};

export function RoleCard({
  title,
  description,
  actionLabel,
  primary = false,
  onPress,
}: RoleCardProps) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        primary && styles.primaryCard,
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.copy}>
        <Text style={[styles.title, primary && styles.primaryTitle]}>
          {title}
        </Text>
        <Text
          style={[styles.description, primary && styles.primaryDescription]}
        >
          {description}
        </Text>
      </View>
      <Text style={[styles.action, primary && styles.primaryAction]}>
        {actionLabel} →
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.lg,
    padding: spacing.lg,
  },
  primaryCard: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  pressed: {
    opacity: 0.8,
    transform: [{ scale: 0.995 }],
  },
  copy: {
    gap: spacing.sm,
  },
  title: {
    color: colors.ink,
    fontSize: type.subtitle,
    fontWeight: "800",
  },
  primaryTitle: {
    color: colors.onPrimary,
  },
  description: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 21,
  },
  primaryDescription: {
    color: colors.onPrimaryMuted,
  },
  action: {
    color: colors.primaryStrong,
    fontSize: type.label,
    fontWeight: "800",
  },
  primaryAction: {
    color: colors.onPrimary,
  },
});
