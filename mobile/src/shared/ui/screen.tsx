import type { ReactNode } from 'react';
import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useTheme } from './theme';

type Props = {
  children: ReactNode;
};

export function Screen({ children }: Props) {
  const { colors, spacing } = useTheme();

  return (
    <SafeAreaView
      style={[styles.screen, { backgroundColor: colors.background, padding: spacing.md }]}
    >
      {children}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
});
