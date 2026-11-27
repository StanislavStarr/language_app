import type { ReactNode } from 'react';
import { StyleSheet, Text } from 'react-native';

import { type Colors, type TextVariant, useTheme } from './theme';

type Tone = 'default' | 'muted' | 'danger' | 'onPrimary';

const TONE_COLOR: Record<Tone, keyof Colors> = {
  default: 'text',
  muted: 'textMuted',
  danger: 'danger',
  onPrimary: 'onPrimary',
};

type Props = {
  children: ReactNode;
  variant?: TextVariant;
  tone?: Tone;
};

export function AppText({ children, variant = 'body', tone = 'default' }: Props) {
  const { colors, typography } = useTheme();

  return (
    <Text
      style={[styles.base, typography[variant], { color: colors[TONE_COLOR[tone]] }]}
      accessibilityRole={variant === 'title' ? 'header' : undefined}
    >
      {children}
    </Text>
  );
}

const styles = StyleSheet.create({
  base: { includeFontPadding: false },
});
