import { View } from 'react-native';

import { AppText } from './app-text';
import { Button } from './button';
import { CenteredState } from './centered-state';

type Props = {
  message: string;
  onRetry?: () => void;
};

export function ErrorState({ message, onRetry }: Props) {
  return (
    <CenteredState>
      <View accessibilityRole="alert">
        <AppText tone="danger">{message}</AppText>
      </View>
      {onRetry ? <Button label="Повторить" variant="secondary" onPress={onRetry} /> : null}
    </CenteredState>
  );
}
