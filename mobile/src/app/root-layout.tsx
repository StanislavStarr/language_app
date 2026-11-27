import { StatusBar } from 'expo-status-bar';

import { ServerWakeBanner } from '@/widgets/server-wake-banner';

import { AppProviders } from './app-providers';
import { configureApiAuthorization } from './configure-api-authorization';
import { ProfileGate } from './profile-gate';
import { RootNavigator } from './root-navigator';
import { SessionGate } from './session-gate';

configureApiAuthorization();

export function RootLayout() {
  return (
    <AppProviders>
      <StatusBar style="auto" />
      <ServerWakeBanner />
      <SessionGate>
        <ProfileGate>
          <RootNavigator />
        </ProfileGate>
      </SessionGate>
    </AppProviders>
  );
}
