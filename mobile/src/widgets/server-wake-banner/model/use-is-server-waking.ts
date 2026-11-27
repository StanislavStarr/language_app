import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useSyncExternalStore } from 'react';

import { isRetryableError } from '@/shared/api';

export function useIsServerWaking(): boolean {
  const queryCache = useQueryClient().getQueryCache();

  const subscribe = useCallback(
    (onChange: () => void) => queryCache.subscribe(onChange),
    [queryCache],
  );
  const getSnapshot = useCallback(
    () =>
      queryCache
        .getAll()
        .some(
          ({ state }) =>
            state.fetchStatus === 'fetching' &&
            state.fetchFailureCount > 0 &&
            isRetryableError(state.fetchFailureReason),
        ),
    [queryCache],
  );

  return useSyncExternalStore(subscribe, getSnapshot);
}
