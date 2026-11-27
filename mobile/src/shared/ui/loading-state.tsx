import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AppText } from './app-text';
import { CenteredState } from './centered-state';
import { SPACING, useTheme } from './theme';

type Props = {
  label?: string;
};

export function LoadingState({ label = 'Загрузка…' }: Props) {
  const { colors } = useTheme();

  return (
    <CenteredState>
      <View
        accessible
        accessibilityRole="progressbar"
        accessibilityLabel={label}
        style={styles.content}
      >
        <ActivityIndicator color={colors.primary} />
        <AppText tone="muted">{label}</AppText>
      </View>
    </CenteredState>
  );
}

const styles = StyleSheet.create({
  content: { alignItems: 'center', gap: SPACING.md },
});
