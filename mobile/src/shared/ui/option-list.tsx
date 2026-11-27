import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from './app-text';
import { BORDER_WIDTH, DISABLED_OPACITY, MIN_TOUCH_TARGET, SPACING, useTheme } from './theme';

export type Option<Value extends string> = {
  value: Value;
  label: string;
  hint?: string;
};

type Props<Value extends string> = {
  title: string;
  options: readonly Option<Value>[];
  value: Value;
  onChange: (value: Value) => void;
  disabled?: boolean;
};

export function OptionList<Value extends string>({
  title,
  options,
  value,
  onChange,
  disabled = false,
}: Props<Value>) {
  const { colors, radii, spacing } = useTheme();

  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={title} style={styles.group}>
      <AppText variant="caption" tone="muted">
        {title}
      </AppText>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityLabel={option.label}
            accessibilityHint={option.hint}
            accessibilityState={{ selected, disabled }}
            disabled={disabled}
            onPress={() => {
              onChange(option.value);
            }}
            style={[
              styles.option,
              {
                borderColor: selected ? colors.primary : colors.border,
                backgroundColor: selected ? colors.surface : colors.background,
                borderRadius: radii.md,
                padding: spacing.md,
                opacity: disabled ? DISABLED_OPACITY : 1,
              },
            ]}
          >
            <AppText>{option.label}</AppText>
            {option.hint ? (
              <AppText variant="caption" tone="muted">
                {option.hint}
              </AppText>
            ) : null}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: { gap: SPACING.sm },
  option: { minHeight: MIN_TOUCH_TARGET, borderWidth: BORDER_WIDTH, gap: SPACING.xs },
});
