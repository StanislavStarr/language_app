import {
  loadOrCreateDeviceCredentials,
  requestDeviceToken,
  useSessionStore,
} from '@/entities/session';

export async function signInWithDevice(): Promise<void> {
  const credentials = await loadOrCreateDeviceCredentials();
  const accessToken = await requestDeviceToken(credentials);
  useSessionStore.getState().setAccessToken(accessToken);
}
