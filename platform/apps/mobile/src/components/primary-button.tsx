import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { colors, radius, spacing, type } from "@/theme/tokens";

type PrimaryButtonProps = {
  label: string;
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
  variant?: "primary" | "quiet";
};

export function PrimaryButton({
  label,
  onPress,
  busy = false,
  disabled = false,
  variant = "primary",
}: PrimaryButtonProps) {
  // A busy button is also an unpressable button. This is the visual half of the
  // duplicate-submission guard; the state machine in features/auth/submission
  // is the half that actually decides.
  const inactive = busy || disabled;
  const quiet = variant === "quiet";

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        quiet ? styles.quiet : styles.primary,
        inactive ? styles.inactive : null,
        pressed && !inactive ? styles.pressed : null,
      ]}
    >
      <View style={styles.content}>
        {busy ? (
          <ActivityIndicator
            color={quiet ? colors.primaryStrong : colors.onPrimary}
            size="small"
          />
        ) : null}
        <Text style={[styles.label, quiet ? styles.quietLabel : null]}>
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  primary: {
    backgroundColor: colors.primary,
  },
  quiet: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderWidth: 1,
  },
  inactive: {
    opacity: 0.6,
  },
  pressed: {
    opacity: 0.85,
  },
  content: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.sm,
    justifyContent: "center",
  },
  label: {
    color: colors.onPrimary,
    fontSize: type.label,
    fontWeight: "700",
  },
  quietLabel: {
    color: colors.primaryStrong,
  },
});
