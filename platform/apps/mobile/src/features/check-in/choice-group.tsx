import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/theme/tokens";

export type Choice<T extends string | number> = {
  readonly value: T;
  readonly label: string;
  readonly accessibilityLabel: string;
};

type ChoiceGroupProps<T extends string | number> = {
  readonly legend: string;
  readonly hint?: string;
  readonly choices: readonly Choice<T>[];
  /** Null means nothing chosen yet, which is the only initial state allowed. */
  readonly selected: T | null;
  readonly disabled: boolean;
  readonly busy: boolean;
  readonly onSelect: (value: T) => void;
  readonly layout: "wrap" | "stack";
};

const TOUCH_TARGET = 48;

/**
 * A single-select group of health answers.
 *
 * Exposed to assistive technology as a radio group of radios, each carrying its
 * own spoken label plus `selected`, `disabled`, and `busy` state, so the absence
 * of a selection is announced rather than merely looking empty. Every target is
 * at least 48×48, which is the mobile minimum the charter's 30-second check-in
 * depends on.
 *
 * `selected` is deliberately `T | null` and there is no default value: decision 6
 * requires the athlete to choose all three answers explicitly, so this component
 * has no way to express a preselected option.
 */
export function ChoiceGroup<T extends string | number>({
  legend,
  hint,
  choices,
  selected,
  disabled,
  busy,
  onSelect,
  layout,
}: ChoiceGroupProps<T>) {
  return (
    <View style={styles.group}>
      <Text style={styles.legend}>{legend}</Text>
      {hint === undefined ? null : <Text style={styles.hint}>{hint}</Text>}

      <View
        accessibilityRole="radiogroup"
        accessibilityLabel={legend}
        style={layout === "wrap" ? styles.wrap : styles.stack}
      >
        {choices.map((choice) => {
          const isSelected = selected === choice.value;

          return (
            <Pressable
              key={String(choice.value)}
              accessibilityRole="radio"
              accessibilityLabel={choice.accessibilityLabel}
              accessibilityState={{ selected: isSelected, disabled, busy }}
              disabled={disabled}
              onPress={() => {
                onSelect(choice.value);
              }}
              style={({ pressed }) => [
                styles.choice,
                layout === "stack" ? styles.stackChoice : styles.wrapChoice,
                isSelected ? styles.choiceSelected : null,
                disabled ? styles.choiceDisabled : null,
                pressed && !disabled ? styles.choicePressed : null,
              ]}
            >
              <Text
                style={[
                  styles.choiceLabel,
                  isSelected ? styles.choiceLabelSelected : null,
                ]}
              >
                {choice.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    gap: spacing.sm,
  },
  legend: {
    color: colors.ink,
    fontSize: type.label,
    fontWeight: "700",
  },
  hint: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 21,
  },
  wrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  stack: {
    gap: spacing.sm,
  },
  choice: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderRadius: radius.md,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: TOUCH_TARGET,
    paddingHorizontal: spacing.md,
  },
  wrapChoice: {
    minWidth: TOUCH_TARGET,
  },
  stackChoice: {
    paddingVertical: spacing.sm,
  },
  choiceSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primaryStrong,
  },
  choiceDisabled: {
    opacity: 0.6,
  },
  choicePressed: {
    opacity: 0.85,
  },
  choiceLabel: {
    color: colors.ink,
    fontSize: type.label,
    fontWeight: "700",
  },
  choiceLabelSelected: {
    color: colors.onPrimary,
  },
});
