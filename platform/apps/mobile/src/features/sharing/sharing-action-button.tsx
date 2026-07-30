import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { colors, radius, spacing, type } from "@/theme/tokens";

type SharingActionButtonProps = {
  /** Visible label. Fixed copy, never a server string. */
  label: string;
  /** Spoken label, which names the team so rows are distinguishable. */
  accessibilityLabel: string;
  onPress: () => void;
  /** True while *this* control's action is in flight. */
  busy?: boolean;
  /** True while any sharing action is in flight, including another team's. */
  disabled?: boolean;
  /** `revoke` is styled quietly so the destructive direction is not the loud one. */
  intent?: "grant" | "revoke";
};

/**
 * The per-team grant/revoke control.
 *
 * A sharing-owned component rather than the shared `PrimaryButton` for one reason:
 * this control needs its own `accessibilityLabel`, because every row's visible
 * label is identical fixed copy and a screen-reader user would otherwise hear
 * "อนุญาตให้ทีมนี้ดูข้อมูล" repeated with nothing to tell the teams apart.
 * `PrimaryButton` exposes no such prop, and TASK-014 does not own
 * `components/`, so widening the shared component was not available.
 *
 * It is a button, not a switch. A switch reads as instant local state, which is
 * exactly the impression decision 6 and decision 7 forbid: nothing here changes
 * until the server confirms it.
 *
 * A busy or disabled control is unpressable, which is the visual half of the
 * duplicate-submit guard. The half that actually decides is the section's own
 * `isPending` check.
 */
export function SharingActionButton({
  label,
  accessibilityLabel,
  onPress,
  busy = false,
  disabled = false,
  intent = "grant",
}: SharingActionButtonProps) {
  const inactive = busy || disabled;
  const quiet = intent === "revoke";

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: inactive, busy }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        quiet ? styles.quiet : styles.solid,
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
  solid: {
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
