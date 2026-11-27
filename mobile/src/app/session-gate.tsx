import { hideAsync, preventAutoHideAsync } from 'expo-splash-screen';
import type { ReactNode } from 'react';
import { useEffect } from 'react';

import { useDeviceSignIn } from '@/features/device-sign-in';
import { SignInErrorPage } from '@/pages/sign-in-error';
import { LoadingState } from '@/shared/ui';

void preventAutoHideAsync();

type Props = {
  children: ReactNode;
};

export function SessionGate({ children }: Props) {
  const { status, failureCount, error, retry } = useDeviceSignIn();
  const splashHeld = status === 'loading' && failureCount === 0;

  useEffect(() => {
    if (!splashHeld) {
      void hideAsync();
    }
  }, [splashHeld]);

  if (status === 'ready') {
    return children;
  }
  if (status === 'error') {
    return <SignInErrorPage error={error} onRetry={retry} />;
  }
  return <LoadingState label="Подключаемся к серверу…" />;
}
