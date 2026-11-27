import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { useTheme } from './theme';

type Props = {
  children: ReactNode;
};

export function CenteredState({ children }: Props) {
  const { spacing } = useTheme();

  return (
    <View style={[styles.container, { gap: spacing.md, padding: spacing.lg }]}>{children}</View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
