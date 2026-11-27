import { useSessionStore } from '@/entities/session';
import { signInWithDevice } from '@/features/device-sign-in';
import { configureApiAuth } from '@/shared/api';

export function configureApiAuthorization(): void {
  configureApiAuth({
    getAccessToken: () => useSessionStore.getState().accessToken,
    refreshSession: signInWithDevice,
  });
}
