import { StyleSheet, TextInput, View } from 'react-native';

import { AppText } from './app-text';
import { BORDER_WIDTH, MIN_TOUCH_TARGET, SPACING, useTheme } from './theme';

type Props = {
  label: string;
  value: string;
  onChangeText: (text: string) => void;
  error?: string;
  placeholder?: string;
};

export function TextField({ label, value, onChangeText, error, placeholder }: Props) {
  const { colors, radii, spacing, typography } = useTheme();

  return (
    <View style={styles.field}>
      <AppText variant="caption" tone="muted">
        {label}
      </AppText>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.textMuted}
        style={[
          styles.input,
          typography.body,
          {
            color: colors.text,
            borderColor: error ? colors.danger : colors.border,
            borderRadius: radii.md,
            paddingHorizontal: spacing.md,
          },
        ]}
      />
      {error ? (
        <View accessibilityLiveRegion="polite">
          <AppText variant="caption" tone="danger">
            {error}
          </AppText>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  field: { gap: SPACING.xs },
  input: { minHeight: MIN_TOUCH_TARGET, borderWidth: BORDER_WIDTH },
});
