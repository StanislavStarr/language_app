import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, useTheme } from '@/shared/ui';

import { useIsServerWaking } from '../model/use-is-server-waking';

export function ServerWakeBanner() {
  const isWaking = useIsServerWaking();
  const { colors, spacing } = useTheme();
  const { top } = useSafeAreaInsets();

  if (!isWaking) {
    return null;
  }

  return (
    <View
      pointerEvents="none"
      accessibilityLiveRegion="polite"
      style={[
        styles.banner,
        { backgroundColor: colors.primary, padding: spacing.sm, paddingTop: top + spacing.sm },
      ]}
    >
      <AppText tone="onPrimary">Сервер просыпается… Это может занять около минуты.</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { position: 'absolute', top: 0, left: 0, right: 0, zIndex: 1, alignItems: 'center' },
});
