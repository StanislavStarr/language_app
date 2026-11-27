import { View } from 'react-native';

import { AppText } from './app-text';

type Props = {
  message: string;
};

export function FormError({ message }: Props) {
  return (
    <View accessibilityRole="alert" accessibilityLiveRegion="polite">
      <AppText tone="danger">{message}</AppText>
    </View>
  );
}
