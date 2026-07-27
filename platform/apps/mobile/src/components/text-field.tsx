import { StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing, type } from "@/theme/tokens";

type TextFieldProps = {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  secureTextEntry?: boolean;
  autoComplete?: "email" | "password" | "new-password" | "name" | "off";
  keyboardType?: "default" | "email-address";
  error?: string | undefined;
  editable?: boolean;
  maxLength?: number;
};

export function TextField({
  label,
  value,
  onChangeText,
  placeholder,
  secureTextEntry = false,
  autoComplete = "off",
  keyboardType = "default",
  error,
  editable = true,
  maxLength,
}: TextFieldProps) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        style={[styles.input, error ? styles.inputError : null]}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.inkMuted}
        secureTextEntry={secureTextEntry}
        autoComplete={autoComplete}
        // The email field must never be auto-capitalised: the value is
        // lower-cased before it is sent, and a capitalised first character
        // only makes the field look wrong while it is being typed.
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType={keyboardType}
        editable={editable}
        maxLength={maxLength}
      />
      {error === undefined ? null : <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  field: {
    gap: spacing.xs,
  },
  label: {
    color: colors.ink,
    fontSize: type.label,
    fontWeight: "700",
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: 1,
    color: colors.ink,
    fontSize: type.body,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  inputError: {
    borderColor: colors.noticeInk,
  },
  error: {
    color: colors.noticeInk,
    fontSize: type.small,
  },
});
