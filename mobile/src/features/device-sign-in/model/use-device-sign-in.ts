import { useQuery } from '@tanstack/react-query';

import { sessionKeys } from '@/entities/session';
import { ApiError, reportUnexpectedError, toApiError } from '@/shared/api';

import { signInWithDevice } from './sign-in-with-device';

type DeviceSignIn =
  | { status: 'loading'; failureCount: number; error: null; retry: () => void }
  | { status: 'ready'; failureCount: number; error: null; retry: () => void }
  | { status: 'error'; failureCount: number; error: ApiError; retry: () => void };

export function useDeviceSignIn(): DeviceSignIn {
  const query = useQuery({
    queryKey: sessionKeys.deviceSignIn(),
    queryFn: async () => {
      try {
        await signInWithDevice();
      } catch (caught) {
        if (!(caught instanceof ApiError)) {
          reportUnexpectedError('device sign-in failed', caught);
        }
        throw caught;
      }
      return { signedIn: true };
    },
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const retry = () => {
    void query.refetch();
  };

  if (query.status === 'success') {
    return { status: 'ready', failureCount: 0, error: null, retry };
  }
  if (query.status === 'error') {
    return {
      status: 'error',
      failureCount: query.failureCount,
      error: toApiError(query.error),
      retry,
    };
  }
  return { status: 'loading', failureCount: query.failureCount, error: null, retry };
}
