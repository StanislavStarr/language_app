import { Stack } from 'expo-router';

import { isOnboardingCompleted, useCurrentUser } from '@/entities/user';

export function RootNavigator() {
  const { data: user } = useCurrentUser();
  const onboardingCompleted = user !== undefined && isOnboardingCompleted(user);

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={onboardingCompleted}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
      <Stack.Protected guard={!onboardingCompleted}>
        <Stack.Screen name="onboarding" />
      </Stack.Protected>
    </Stack>
  );
}
