import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { ServerWakeBanner } from '@/widgets/server-wake-banner';

import { AppProviders } from './app-providers';

export function RootLayout() {
  return (
    <AppProviders>
      <StatusBar style="auto" />
      <ServerWakeBanner />
      <Stack screenOptions={{ headerShown: false }} />
    </AppProviders>
  );
}
