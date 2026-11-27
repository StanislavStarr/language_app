import type { ReactNode } from 'react';

import { useCurrentUser } from '@/entities/user';
import { getErrorMessage } from '@/shared/api';
import { ErrorState, LoadingState, Screen } from '@/shared/ui';

type Props = {
  children: ReactNode;
};

export function ProfileGate({ children }: Props) {
  const { data, error, refetch } = useCurrentUser();

  if (data !== undefined) {
    return children;
  }
  if (error === null) {
    return <LoadingState />;
  }
  return (
    <Screen>
      <ErrorState
        message={getErrorMessage(error)}
        onRetry={() => {
          void refetch();
        }}
      />
    </Screen>
  );
}
