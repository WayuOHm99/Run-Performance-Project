import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/theme/tokens";

type NoticeProps = {
  title: string;
  message: string;
};

/**
 * A short, non-blocking message. Used for sanitized auth and data errors, so it
 * only ever receives a string chosen from features/auth/errors -- never a
 * server error, an email address, or a token.
 */
export function Notice({ title, message }: NoticeProps) {
  return (
    <View accessibilityRole="alert" style={styles.notice}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  notice: {
    backgroundColor: colors.notice,
    borderRadius: radius.md,
    gap: spacing.xs,
    padding: spacing.lg,
  },
  title: {
    color: colors.noticeInk,
    fontSize: type.label,
    fontWeight: "700",
  },
  message: {
    color: colors.noticeInk,
    fontSize: type.small,
    lineHeight: 20,
  },
});
