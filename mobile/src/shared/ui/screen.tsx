import type { ReactNode } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { SPACING, useTheme } from './theme';

type Props = {
  children: ReactNode;
  scrollable?: boolean;
};

export function Screen({ children, scrollable = false }: Props) {
  const { colors, spacing } = useTheme();

  return (
    <SafeAreaView
      style={[styles.screen, { backgroundColor: colors.background, padding: spacing.md }]}
    >
      {scrollable ? (
        <ScrollView contentContainerStyle={styles.scrollContent}>{children}</ScrollView>
      ) : (
        children
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { gap: SPACING.md, paddingBottom: SPACING.xl },
});
