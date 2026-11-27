import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { ServerWakeBanner } from '@/widgets/server-wake-banner';

import { AppProviders } from './app-providers';
import { configureApiAuthorization } from './configure-api-authorization';
import { SessionGate } from './session-gate';

configureApiAuthorization();

export function RootLayout() {
  return (
    <AppProviders>
      <StatusBar style="auto" />
      <ServerWakeBanner />
      <SessionGate>
        <Stack screenOptions={{ headerShown: false }} />
      </SessionGate>
    </AppProviders>
  );
}
